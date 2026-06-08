"""Reliable UDP file transfer server."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import argparse
import hashlib
import os
import random
import socket
import threading
import time

from .logger import EventLogger, NullLogger
from .protocol import PacketError, PacketType, decode_packet, encode_packet, json_payload, parse_json_payload


@dataclass
class TransferSession:
    client_address: tuple[str, int]
    transfer_id: str
    filename: str
    file_size: int
    chunk_size: int
    total_chunks: int
    expected_sha256: str
    chunks: dict[int, bytes] = field(default_factory=dict)
    duplicate_packets: int = 0
    started_at: float = field(default_factory=time.perf_counter)
    completed: bool = False

    def add_chunk(self, sequence: int, payload: bytes) -> bool:
        chunk_index = sequence - 1
        if chunk_index in self.chunks:
            self.duplicate_packets += 1
            return False
        self.chunks[chunk_index] = payload
        return True

    def is_complete(self) -> bool:
        return len(self.chunks) == self.total_chunks

    def assemble(self) -> bytes:
        return b"".join(self.chunks[index] for index in range(self.total_chunks))


class ReliableUDPServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9000,
        *,
        output_dir: str | Path = "received",
        log_path: str | Path = "logs/server_events.jsonl",
        loss_rate: float = 0.0,
        delay_ms: float = 0.0,
        random_seed: int | None = 42,
    ) -> None:
        self.host = host
        self.port = port
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = EventLogger(Path(log_path), "server") if log_path else NullLogger()
        self.loss_rate = loss_rate
        self.delay_ms = delay_ms
        self.random = random.Random(random_seed)
        self.sessions: dict[tuple[str, int], TransferSession] = {}
        self._stop_event = threading.Event()
        self._socket: socket.socket | None = None
        self.bound_address: tuple[str, int] = (host, port)

    def start_in_thread(self, *, max_transfers: int | None = None, idle_timeout: float = 30.0) -> threading.Thread:
        thread = threading.Thread(
            target=self.serve_forever,
            kwargs={"max_transfers": max_transfers, "idle_timeout": idle_timeout},
            daemon=True,
        )
        thread.start()
        while self._socket is None:
            time.sleep(0.001)
        return thread

    def stop(self) -> None:
        self._stop_event.set()
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass

    def serve_forever(self, *, max_transfers: int | None = None, idle_timeout: float = 30.0) -> None:
        completed_transfers = 0
        last_activity = time.perf_counter()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind((self.host, self.port))
            self.bound_address = sock.getsockname()
            self._socket = sock
            sock.settimeout(0.05)
            self.logger.log(
                "server_start",
                host=self.bound_address[0],
                port=self.bound_address[1],
                loss_rate=self.loss_rate,
                delay_ms=self.delay_ms,
            )
            while not self._stop_event.is_set():
                if idle_timeout and time.perf_counter() - last_activity > idle_timeout:
                    self.logger.log("server_idle_timeout", idle_timeout=idle_timeout)
                    break
                try:
                    datagram, address = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                except OSError:
                    break

                last_activity = time.perf_counter()
                completed = self._handle_datagram(sock, datagram, address)
                if completed:
                    completed_transfers += 1
                    if max_transfers is not None and completed_transfers >= max_transfers:
                        break

            self.logger.log("server_stop", completed_transfers=completed_transfers)
            self._socket = None

    def _handle_datagram(self, sock: socket.socket, datagram: bytes, address: tuple[str, int]) -> bool:
        try:
            packet = decode_packet(datagram)
        except PacketError as exc:
            self.logger.log("invalid_packet", client=f"{address[0]}:{address[1]}", error=str(exc))
            return False

        if packet.packet_type == PacketType.DATA and self.random.random() < self.loss_rate:
            self.logger.log("simulated_packet_loss", client=f"{address[0]}:{address[1]}", sequence=packet.sequence)
            return False

        if self.delay_ms > 0:
            time.sleep(self.delay_ms / 1000)

        if packet.packet_type == PacketType.META:
            return self._handle_meta(sock, packet, address)
        if packet.packet_type == PacketType.DATA:
            return self._handle_data(sock, packet, address)
        if packet.packet_type == PacketType.FIN:
            return self._handle_fin(sock, packet, address)

        self.logger.log("unexpected_packet_type", client=f"{address[0]}:{address[1]}", packet_type=int(packet.packet_type))
        return False

    def _handle_meta(self, sock: socket.socket, packet, address: tuple[str, int]) -> bool:
        metadata = parse_json_payload(packet.payload)
        session = TransferSession(
            client_address=address,
            transfer_id=str(metadata["transfer_id"]),
            filename=Path(str(metadata["filename"])).name,
            file_size=int(metadata["file_size"]),
            chunk_size=int(metadata["chunk_size"]),
            total_chunks=int(metadata["total_chunks"]),
            expected_sha256=str(metadata["sha256"]),
        )
        self.sessions[address] = session
        self.logger.log(
            "metadata_received",
            client=f"{address[0]}:{address[1]}",
            sequence=packet.sequence,
            filename=session.filename,
            file_size=session.file_size,
            total_chunks=session.total_chunks,
            expected_sha256=session.expected_sha256,
        )
        self._send_ack(sock, address, packet.sequence, "metadata_ack")
        return False

    def _handle_data(self, sock: socket.socket, packet, address: tuple[str, int]) -> bool:
        session = self.sessions.get(address)
        if session is None:
            self.logger.log("data_without_metadata", client=f"{address[0]}:{address[1]}", sequence=packet.sequence)
            return False

        stored = session.add_chunk(packet.sequence, packet.payload)
        self.logger.log(
            "data_received" if stored else "duplicate_data_ignored",
            client=f"{address[0]}:{address[1]}",
            sequence=packet.sequence,
            payload_bytes=len(packet.payload),
            received_chunks=len(session.chunks),
            total_chunks=session.total_chunks,
        )
        self._send_ack(sock, address, packet.sequence, "data_ack" if stored else "duplicate_ack")
        print(f"[Server] Paket {packet.sequence} alındı, ACK gönderildi.")
        return False

    def _handle_fin(self, sock: socket.socket, packet, address: tuple[str, int]) -> bool:
        session = self.sessions.get(address)
        if session is None:
            self._send_ack(sock, address, packet.sequence, "missing_metadata", integrity_ok=False)
            return True

        if not session.is_complete():
            missing = session.total_chunks - len(session.chunks)
            self.logger.log("finish_incomplete", client=f"{address[0]}:{address[1]}", missing_chunks=missing)
            self._send_ack(sock, address, packet.sequence, "incomplete", integrity_ok=False, missing_chunks=missing)
            return True

        content = session.assemble()
        actual_hash = hashlib.sha256(content).hexdigest()
        integrity_ok = actual_hash == session.expected_sha256 and len(content) == session.file_size
        safe_name = f"{Path(session.filename).stem}_{session.transfer_id[:8]}{Path(session.filename).suffix}"
        output_path = self.output_dir / safe_name
        if integrity_ok:
            output_path.write_bytes(content)

        session.completed = integrity_ok
        self.logger.log(
            "transfer_finished",
            client=f"{address[0]}:{address[1]}",
            sequence=packet.sequence,
            filename=session.filename,
            output_path=str(output_path),
            received_bytes=len(content),
            expected_bytes=session.file_size,
            expected_sha256=session.expected_sha256,
            actual_sha256=actual_hash,
            integrity_ok=integrity_ok,
            duplicate_packets=session.duplicate_packets,
            completion_time_seconds=round(time.perf_counter() - session.started_at, 6),
        )
        self._send_ack(
            sock,
            address,
            packet.sequence,
            "complete" if integrity_ok else "hash_mismatch",
            integrity_ok=integrity_ok,
            output_path=str(output_path),
            actual_sha256=actual_hash,
        )
        return True

    def _send_ack(self, sock: socket.socket, address: tuple[str, int], sequence: int, status: str, **fields: object) -> None:
        payload = json_payload({"ack": sequence, "status": status, **fields})
        ack = encode_packet(PacketType.ACK, sequence, sequence, payload)
        sock.sendto(ack, address)
        self.logger.log("ack_sent", client=f"{address[0]}:{address[1]}", sequence=sequence, status=status)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NetProbe reliable UDP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--output-dir", default="received")
    parser.add_argument("--log-path", default=os.path.join("logs", "server_events.jsonl"))
    parser.add_argument("--loss-rate", type=float, default=0.0)
    parser.add_argument("--delay-ms", type=float, default=0.0)
    parser.add_argument("--max-transfers", type=int, default=None)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    server = ReliableUDPServer(
        args.host,
        args.port,
        output_dir=args.output_dir,
        log_path=args.log_path,
        loss_rate=args.loss_rate,
        delay_ms=args.delay_ms,
    )
    try:
        server.serve_forever(max_transfers=args.max_transfers)
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()
