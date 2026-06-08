"""Reliable UDP file transfer client."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import math
import os
import socket
import time
import uuid

from .logger import EventLogger, NullLogger
from .metrics import TransferMetrics, mean
from .protocol import (
    PacketError,
    PacketType,
    decode_packet,
    encode_packet,
    file_sha256,
    json_payload,
    parse_json_payload,
)


@dataclass
class OutboundPacket:
    sequence: int
    datagram: bytes
    payload_bytes: int
    first_sent_at: float | None = None
    last_sent_at: float | None = None
    sends: int = 0


@dataclass
class TransferResult:
    ok: bool
    metrics: TransferMetrics
    final_ack: dict[str, object]


class ReliableUDPClient:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        chunk_size: int = 1024,
        timeout_seconds: float = 0.2,
        max_retries: int = 5,
        window_size: int = 8,
        log_path: str | Path = "logs/client_events.jsonl",
        socket_timeout: float = 0.01,
    ) -> None:
        if chunk_size <= 0 or chunk_size > 60_000:
            raise ValueError("chunk_size must be between 1 and 60000")
        if window_size <= 0:
            raise ValueError("window_size must be positive")
        self.address = (host, port)
        self.chunk_size = chunk_size
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.window_size = window_size
        self.socket_timeout = socket_timeout
        self.logger = EventLogger(Path(log_path), "client") if log_path else NullLogger()

    def send_file(self, file_path: str | Path, *, label: str = "manual", loss_rate: float = 0.0) -> TransferResult:
        file_path = Path(file_path)
        file_size = file_path.stat().st_size
        file_hash = file_sha256(str(file_path))
        total_chunks = max(1, math.ceil(file_size / self.chunk_size))
        total_packets = total_chunks + 2
        transfer_id = uuid.uuid4().hex

        metadata = {
            "transfer_id": transfer_id,
            "filename": file_path.name,
            "file_size": file_size,
            "chunk_size": self.chunk_size,
            "total_chunks": total_chunks,
            "sha256": file_hash,
        }

        meta_packet = OutboundPacket(
            0,
            encode_packet(PacketType.META, 0, total_packets, json_payload(metadata)),
            len(json_payload(metadata)),
        )
        data_packets = self._build_data_packets(file_path, total_packets, total_chunks)
        fin_payload = json_payload({"transfer_id": transfer_id, "sha256": file_hash, "total_chunks": total_chunks})
        fin_packet = OutboundPacket(
            total_packets - 1,
            encode_packet(PacketType.FIN, total_packets - 1, total_packets, fin_payload),
            len(fin_payload),
        )

        start = time.perf_counter()
        counters = {
            "datagrams_sent": 0,
            "ack_received": 0,
            "timeout_count": 0,
            "retransmission_count": 0,
            "failed_packets": 0,
        }
        rtts: list[float] = []
        final_ack: dict[str, object] = {}

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(self.socket_timeout)
            self.logger.log(
                "transfer_start",
                label=label,
                file=str(file_path),
                file_size=file_size,
                file_sha256=file_hash,
                chunk_size=self.chunk_size,
                total_packets=total_packets,
                window_size=self.window_size,
                timeout_seconds=self.timeout_seconds,
                max_retries=self.max_retries,
            )

            ok = self._send_window(sock, [meta_packet], counters, rtts, phase="metadata")
            if ok:
                ok = self._send_window(sock, data_packets, counters, rtts, phase="data")
            if ok:
                ok, final_ack = self._send_window(sock, [fin_packet], counters, rtts, phase="finish", want_payload=True)

        completion = time.perf_counter() - start
        integrity_ok = bool(final_ack.get("integrity_ok")) if final_ack else False
        ok = bool(ok and integrity_ok)
        metrics = TransferMetrics(
            label=label,
            file_size_bytes=file_size,
            chunk_size=self.chunk_size,
            timeout_seconds=self.timeout_seconds,
            loss_rate=loss_rate,
            window_size=self.window_size,
            completion_time_seconds=round(completion, 6),
            original_packets=total_packets,
            datagrams_sent=counters["datagrams_sent"],
            ack_received=counters["ack_received"],
            timeout_count=counters["timeout_count"],
            retransmission_count=counters["retransmission_count"],
            failed_packets=counters["failed_packets"],
            avg_rtt_ms=round(mean(rtts) * 1000, 3),
            integrity_ok=integrity_ok,
            client_log=str(getattr(self.logger, "path", "")),
            server_log="",
        )
        self.logger.log("transfer_complete", ok=ok, **metrics.as_row())
        return TransferResult(ok=ok, metrics=metrics, final_ack=final_ack)

    def _build_data_packets(self, file_path: Path, total_packets: int, total_chunks: int) -> list[OutboundPacket]:
        packets: list[OutboundPacket] = []
        with file_path.open("rb") as handle:
            for index in range(total_chunks):
                chunk = handle.read(self.chunk_size)
                sequence = index + 1
                packets.append(
                    OutboundPacket(
                        sequence,
                        encode_packet(PacketType.DATA, sequence, total_packets, chunk),
                        len(chunk),
                    )
                )
        if not packets:
            packets.append(OutboundPacket(1, encode_packet(PacketType.DATA, 1, total_packets, b""), 0))
        return packets

    def _send_window(
        self,
        sock: socket.socket,
        packets: list[OutboundPacket],
        counters: dict[str, int],
        rtts: list[float],
        *,
        phase: str,
        want_payload: bool = False,
    ) -> bool | tuple[bool, dict[str, object]]:
        base_index = 0
        next_index = 0
        acked: set[int] = set()
        in_flight: dict[int, OutboundPacket] = {}
        ack_payload: dict[str, object] = {}

        while len(acked) < len(packets):
            while next_index < len(packets) and len(in_flight) < self.window_size:
                packet = packets[next_index]
                self._send_packet(sock, packet, counters, retransmission=False, phase=phase)
                in_flight[packet.sequence] = packet
                next_index += 1

            self._receive_acks(sock, in_flight, acked, counters, rtts, phase, ack_payload)

            now = time.perf_counter()
            for sequence, packet in list(in_flight.items()):
                if packet.last_sent_at is None:
                    continue
                if now - packet.last_sent_at >= self.timeout_seconds:
                    counters["timeout_count"] += 1
                    self.logger.log(
                        "timeout",
                        phase=phase,
                        sequence=sequence,
                        sends=packet.sends,
                        timeout_seconds=self.timeout_seconds,
                    )
                    retransmissions_done = max(0, packet.sends - 1)
                    if retransmissions_done >= self.max_retries:
                        counters["failed_packets"] += 1
                        self.logger.log(
                            "packet_failed",
                            phase=phase,
                            sequence=sequence,
                            retransmissions_done=retransmissions_done,
                            max_retries=self.max_retries,
                        )
                        if want_payload:
                            return False, ack_payload
                        return False
                    self._send_packet(sock, packet, counters, retransmission=True, phase=phase)

            while base_index < len(packets) and packets[base_index].sequence in acked:
                base_index += 1
            time.sleep(0.001)

        if want_payload:
            return True, ack_payload
        return True

    def _send_packet(
        self,
        sock: socket.socket,
        packet: OutboundPacket,
        counters: dict[str, int],
        *,
        retransmission: bool,
        phase: str,
    ) -> None:
        now = time.perf_counter()
        sock.sendto(packet.datagram, self.address)
        print(f"[Client] Paket {packet.sequence} gönderildi ({len(packet.datagram)} byte).")
        packet.sends += 1
        packet.last_sent_at = now
        if packet.first_sent_at is None:
            packet.first_sent_at = now
        counters["datagrams_sent"] += 1
        if retransmission:
            counters["retransmission_count"] += 1
        self.logger.log(
            "retransmit" if retransmission else "send",
            phase=phase,
            sequence=packet.sequence,
            attempt=packet.sends,
            payload_bytes=packet.payload_bytes,
            datagram_bytes=len(packet.datagram),
        )

    def _receive_acks(
        self,
        sock: socket.socket,
        in_flight: dict[int, OutboundPacket],
        acked: set[int],
        counters: dict[str, int],
        rtts: list[float],
        phase: str,
        ack_payload: dict[str, object],
    ) -> None:
        while True:
            try:
                datagram, _ = sock.recvfrom(4096)
            except socket.timeout:
                return
            try:
                packet = decode_packet(datagram)
            except PacketError as exc:
                self.logger.log("invalid_ack", phase=phase, error=str(exc))
                continue
            if packet.packet_type != PacketType.ACK:
                self.logger.log("unexpected_packet", phase=phase, sequence=packet.sequence, packet_type=int(packet.packet_type))
                continue

            payload = parse_json_payload(packet.payload) if packet.payload else {}
            ack_number = int(payload.get("ack", packet.sequence))
            counters["ack_received"] += 1
            if ack_number in in_flight:
                sent = in_flight.pop(ack_number)
                acked.add(ack_number)
                if sent.last_sent_at is not None:
                    rtts.append(time.perf_counter() - sent.last_sent_at)
                ack_payload.clear()
                ack_payload.update(payload)
                self.logger.log(
                    "ack_received",
                    phase=phase,
                    sequence=ack_number,
                    status=payload.get("status", "ack"),
                    sends=sent.sends,
                )
                print(f"[Client] Paket {ack_number} için ACK alındı.")
            else:
                self.logger.log("duplicate_or_late_ack", phase=phase, sequence=ack_number)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NetProbe reliable UDP client")
    parser.add_argument("file", help="file to transfer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--chunk-size", type=int, default=1024)
    parser.add_argument("--timeout", type=float, default=0.2)
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--window-size", type=int, default=8)
    parser.add_argument("--log-path", default=os.path.join("logs", "client_events.jsonl"))
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    client = ReliableUDPClient(
        args.host,
        args.port,
        chunk_size=args.chunk_size,
        timeout_seconds=args.timeout,
        max_retries=args.max_retries,
        window_size=args.window_size,
        log_path=args.log_path,
    )
    result = client.send_file(args.file, label="manual")
    print("OK" if result.ok else "FAILED")
    print(result.metrics.as_row())


if __name__ == "__main__":
    main()
