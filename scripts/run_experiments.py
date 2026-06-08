from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from netprobe.client import ReliableUDPClient
from netprobe.metrics import TransferMetrics
from netprobe.server import ReliableUDPServer


DATA_DIR = ROOT / "data" / "samples"
LOG_DIR = ROOT / "logs"
RESULT_DIR = ROOT / "results"
RECEIVED_DIR = ROOT / "received"


@dataclass(frozen=True)
class Experiment:
    label: str
    file_size: int
    chunk_size: int
    timeout: float
    loss_rate: float
    window_size: int = 8
    delay_ms: float = 0.0


def ensure_sample_file(size: int) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"sample_{size // 1024}kb.bin"
    if path.exists() and path.stat().st_size == size:
        return path

    block = bytearray()
    for index in range(4096):
        block.append((index * 31 + size) % 256)
    with path.open("wb") as handle:
        remaining = size
        while remaining > 0:
            chunk = bytes(block[: min(len(block), remaining)])
            handle.write(chunk)
            remaining -= len(chunk)
    return path


def run_one(experiment: Experiment, index: int) -> TransferMetrics:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RECEIVED_DIR.mkdir(parents=True, exist_ok=True)
    sample_path = ensure_sample_file(experiment.file_size)
    safe_label = experiment.label.replace("/", "_").replace(" ", "_")
    server_log = LOG_DIR / f"{index:02d}_{safe_label}_server.jsonl"
    client_log = LOG_DIR / f"{index:02d}_{safe_label}_client.jsonl"

    server = ReliableUDPServer(
        "127.0.0.1",
        0,
        output_dir=RECEIVED_DIR,
        log_path=server_log,
        loss_rate=experiment.loss_rate,
        delay_ms=experiment.delay_ms,
        random_seed=1000 + index,
    )
    thread = server.start_in_thread(max_transfers=1, idle_timeout=10.0)
    host, port = server.bound_address

    client = ReliableUDPClient(
        host,
        port,
        chunk_size=experiment.chunk_size,
        timeout_seconds=experiment.timeout,
        max_retries=5,
        window_size=experiment.window_size,
        log_path=client_log,
    )
    result = client.send_file(sample_path, label=experiment.label, loss_rate=experiment.loss_rate)
    server.stop()
    thread.join(timeout=2.0)

    metrics = result.metrics
    metrics.server_log = str(server_log)
    metrics.client_log = str(client_log)
    return metrics


def experiment_plan() -> list[Experiment]:
    base_size = 128 * 1024
    return [
        Experiment("packet_size__512B", base_size, 512, 0.20, 0.03),
        Experiment("packet_size__1024B", base_size, 1024, 0.20, 0.03),
        Experiment("packet_size__2048B", base_size, 2048, 0.20, 0.03),
        Experiment("timeout__50ms", base_size, 1024, 0.05, 0.08),
        Experiment("timeout__150ms", base_size, 1024, 0.15, 0.08),
        Experiment("timeout__300ms", base_size, 1024, 0.30, 0.08),
        Experiment("loss__0pct", base_size, 1024, 0.20, 0.00),
        Experiment("loss__5pct", base_size, 1024, 0.20, 0.05),
        Experiment("loss__15pct", base_size, 1024, 0.20, 0.15),
        Experiment("file_size__32KB", 32 * 1024, 1024, 0.20, 0.05),
        Experiment("file_size__128KB", 128 * 1024, 1024, 0.20, 0.05),
        Experiment("file_size__384KB", 384 * 1024, 1024, 0.20, 0.05),
    ]


def write_results(rows: list[dict[str, object]]) -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULT_DIR / "experiment_results.csv"
    json_path = RESULT_DIR / "experiment_results.json"
    if not rows:
        return
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")


def main() -> None:
    rows: list[dict[str, object]] = []
    start = time.perf_counter()
    for index, experiment in enumerate(experiment_plan(), start=1):
        print(f"[{index:02d}] {experiment.label}")
        metrics = run_one(experiment, index)
        row = metrics.as_row()
        row["scenario"] = experiment.label.split("__", 1)[0]
        row["variant"] = experiment.label.split("__", 1)[1]
        rows.append(row)
        status = "OK" if metrics.integrity_ok and metrics.failed_packets == 0 else "FAILED"
        print(
            f"     {status} completion={metrics.completion_time_seconds:.4f}s "
            f"goodput={metrics.goodput_bps / 1_000_000:.3f}Mbps "
            f"retx={metrics.retransmission_count}"
        )
    write_results(rows)
    print(f"Completed {len(rows)} experiments in {time.perf_counter() - start:.2f}s")
    print(f"Results: {RESULT_DIR / 'experiment_results.csv'}")


if __name__ == "__main__":
    main()
