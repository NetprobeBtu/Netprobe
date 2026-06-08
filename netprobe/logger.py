"""Structured event logging for NetProbe transfers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import threading
import time
from typing import Any


@dataclass
class EventLogger:
    path: Path
    role: str
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def log(self, event: str, **fields: Any) -> None:
        record = {
            "timestamp": time.time(),
            "role": self.role,
            "event": event,
            **fields,
        }
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")


class NullLogger:
    def log(self, event: str, **fields: Any) -> None:
        return None


def read_events(path: str | Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events
