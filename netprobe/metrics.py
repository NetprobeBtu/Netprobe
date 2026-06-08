"""Metric helpers for NetProbe experiment outputs."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable


@dataclass
class TransferMetrics:
    label: str
    file_size_bytes: int
    chunk_size: int
    timeout_seconds: float
    loss_rate: float
    window_size: int
    completion_time_seconds: float
    original_packets: int
    datagrams_sent: int
    ack_received: int
    timeout_count: int
    retransmission_count: int
    failed_packets: int
    avg_rtt_ms: float
    integrity_ok: bool
    client_log: str
    server_log: str

    @property
    def throughput_bps(self) -> float:
        if self.completion_time_seconds <= 0:
            return 0.0
        return (self.datagrams_sent * self.chunk_size * 8) / self.completion_time_seconds

    @property
    def goodput_bps(self) -> float:
        if self.completion_time_seconds <= 0:
            return 0.0
        return (self.file_size_bytes * 8) / self.completion_time_seconds

    @property
    def retransmission_rate(self) -> float:
        if self.original_packets <= 0:
            return 0.0
        return self.retransmission_count / self.original_packets

    @property
    def observed_loss_rate(self) -> float:
        if self.datagrams_sent <= 0:
            return 0.0
        return self.timeout_count / self.datagrams_sent

    def as_row(self) -> dict[str, object]:
        row = asdict(self)
        row.update(
            throughput_bps=round(self.throughput_bps, 3),
            goodput_bps=round(self.goodput_bps, 3),
            retransmission_rate=round(self.retransmission_rate, 6),
            observed_loss_rate=round(self.observed_loss_rate, 6),
        )
        return row


def mean(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        return 0.0
    return sum(values) / len(values)
