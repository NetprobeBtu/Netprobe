"""Small optional TCP baseline helpers for comparison experiments."""

from __future__ import annotations

from pathlib import Path
import socket
import time


def send_file_tcp(path: str | Path, host: str, port: int, chunk_size: int = 1024) -> float:
    """Send a file over TCP and return completion time in seconds.

    This helper is intentionally small because the project focus is the custom
    UDP reliability mechanism. It can be used as an optional bonus baseline.
    """

    start = time.perf_counter()
    with socket.create_connection((host, port), timeout=5) as sock:
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(chunk_size), b""):
                sock.sendall(chunk)
    return time.perf_counter() - start
