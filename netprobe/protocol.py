"""Application layer packet format for NetProbe.

Packet layout:

    magic(4) version(1) type(1) sequence(4) total(4) payload_len(2)
    checksum(32) payload(n)

The checksum is SHA-256 over all header fields except the checksum plus the
payload. This keeps DATA and ACK packets protected by the same verification
logic while staying small enough for UDP datagrams used in the project.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import hashlib
import json
import struct
from typing import Any


MAGIC = b"NPB1"
VERSION = 1
HEADER_STRUCT = struct.Struct("!4sBBIIH32s")
CHECKSUMLESS_HEADER_STRUCT = struct.Struct("!4sBBIIH")
HEADER_SIZE = HEADER_STRUCT.size
MAX_PAYLOAD_SIZE = 60_000


class PacketType(IntEnum):
    META = 1
    DATA = 2
    FIN = 3
    ACK = 4


class PacketError(ValueError):
    """Raised when a UDP datagram is not a valid NetProbe packet."""


@dataclass(frozen=True)
class Packet:
    packet_type: PacketType
    sequence: int
    total_packets: int
    payload: bytes
    checksum: bytes

    @property
    def payload_length(self) -> int:
        return len(self.payload)


def _checksum(packet_type: PacketType, sequence: int, total_packets: int, payload: bytes) -> bytes:
    header = CHECKSUMLESS_HEADER_STRUCT.pack(
        MAGIC,
        VERSION,
        int(packet_type),
        sequence,
        total_packets,
        len(payload),
    )
    return hashlib.sha256(header + payload).digest()


def encode_packet(packet_type: PacketType, sequence: int, total_packets: int, payload: bytes = b"") -> bytes:
    if len(payload) > MAX_PAYLOAD_SIZE:
        raise PacketError(f"payload too large: {len(payload)} > {MAX_PAYLOAD_SIZE}")
    checksum = _checksum(packet_type, sequence, total_packets, payload)
    header = HEADER_STRUCT.pack(
        MAGIC,
        VERSION,
        int(packet_type),
        sequence,
        total_packets,
        len(payload),
        checksum,
    )
    return header + payload


def decode_packet(datagram: bytes) -> Packet:
    if len(datagram) < HEADER_SIZE:
        raise PacketError("datagram is shorter than NetProbe header")

    magic, version, packet_type_raw, sequence, total_packets, payload_len, checksum = HEADER_STRUCT.unpack(
        datagram[:HEADER_SIZE]
    )
    if magic != MAGIC:
        raise PacketError("invalid magic value")
    if version != VERSION:
        raise PacketError(f"unsupported protocol version: {version}")

    payload = datagram[HEADER_SIZE:]
    if len(payload) != payload_len:
        raise PacketError(f"payload length mismatch: header={payload_len}, actual={len(payload)}")

    try:
        packet_type = PacketType(packet_type_raw)
    except ValueError as exc:
        raise PacketError(f"unknown packet type: {packet_type_raw}") from exc

    expected = _checksum(packet_type, sequence, total_packets, payload)
    if checksum != expected:
        raise PacketError("packet checksum verification failed")

    return Packet(packet_type, sequence, total_packets, payload, checksum)


def json_payload(data: dict[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def parse_json_payload(payload: bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PacketError("invalid JSON payload") from exc
    if not isinstance(parsed, dict):
        raise PacketError("JSON payload must be an object")
    return parsed


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
