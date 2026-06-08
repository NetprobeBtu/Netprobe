from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import csv
import html
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = ROOT / "results"
FIG_DIR = ROOT / "reports" / "figures"


def read_rows() -> list[dict[str, str]]:
    path = RESULT_DIR / "experiment_results.csv"
    if not path.exists():
        raise SystemExit("results/experiment_results.csv bulunamadi. Once scripts/run_experiments.py calistirin.")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def f(row: dict[str, str], key: str) -> float:
    return float(row[key])


def bar_chart(
    rows: list[dict[str, str]],
    *,
    title: str,
    value_key: str,
    y_label: str,
    output: Path,
    scale: float = 1.0,
    color: str = "#2563eb",
) -> None:
    width = 900
    height = 420
    margin_left = 90
    margin_right = 30
    margin_top = 55
    margin_bottom = 95
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    values = [f(row, value_key) / scale for row in rows]
    max_value = max(values) if values else 1.0
    max_value = max(max_value, 0.000001)
    bar_gap = 18
    bar_w = max(18, (plot_w - bar_gap * (len(rows) + 1)) / max(1, len(rows)))

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="28" text-anchor="middle" font-family="Arial" font-size="20" font-weight="700">{html.escape(title)}</text>',
        f'<line x1="{margin_left}" y1="{margin_top + plot_h}" x2="{margin_left + plot_w}" y2="{margin_top + plot_h}" stroke="#334155"/>',
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}" stroke="#334155"/>',
        f'<text x="18" y="{margin_top + plot_h / 2}" transform="rotate(-90 18 {margin_top + plot_h / 2})" font-family="Arial" font-size="13">{html.escape(y_label)}</text>',
    ]
    for tick in range(5):
        value = max_value * tick / 4
        y = margin_top + plot_h - (value / max_value) * plot_h
        parts.append(f'<line x1="{margin_left - 5}" y1="{y:.2f}" x2="{margin_left + plot_w}" y2="{y:.2f}" stroke="#e2e8f0"/>')
        parts.append(f'<text x="{margin_left - 12}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11" fill="#475569">{value:.2f}</text>')

    for index, row in enumerate(rows):
        value = values[index]
        x = margin_left + bar_gap + index * (bar_w + bar_gap)
        bar_h = (value / max_value) * plot_h
        y = margin_top + plot_h - bar_h
        label = row["variant"]
        parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" height="{bar_h:.2f}" rx="4" fill="{color}"/>')
        parts.append(f'<text x="{x + bar_w / 2:.2f}" y="{y - 7:.2f}" text-anchor="middle" font-family="Arial" font-size="11" fill="#0f172a">{value:.2f}</text>')
        parts.append(f'<text x="{x + bar_w / 2:.2f}" y="{height - 42}" text-anchor="middle" font-family="Arial" font-size="12" fill="#0f172a">{html.escape(label)}</text>')
    parts.append("</svg>")
    output.write_text("\n".join(parts), encoding="utf-8")


def notes_for_scenario(name: str, rows: list[dict[str, str]]) -> str:
    ordered = sorted(rows, key=lambda row: row["variant"])
    best_goodput = max(ordered, key=lambda row: f(row, "goodput_bps"))
    most_retx = max(ordered, key=lambda row: f(row, "retransmission_count"))
    slowest = max(ordered, key=lambda row: f(row, "completion_time_seconds"))
    return (
        f"- {name}: en yuksek goodput `{best_goodput['variant']}` varyantinda "
        f"{f(best_goodput, 'goodput_bps') / 1_000_000:.3f} Mbps olarak olculdu. "
        f"En fazla retransmission `{most_retx['variant']}` varyantinda "
        f"{int(f(most_retx, 'retransmission_count'))} adet; en uzun completion time "
        f"`{slowest['variant']}` varyantinda {f(slowest, 'completion_time_seconds'):.3f} saniyedir."
    )


def write_analysis_notes(groups: dict[str, list[dict[str, str]]]) -> None:
    lines = [
        "# Deney Ozeti",
        "",
        "Bu dosya `scripts/analyze_results.py` tarafindan uretilmistir.",
        "",
    ]
    for scenario, rows in groups.items():
        lines.append(notes_for_scenario(scenario, rows))
    lines.append("")
    (RESULT_DIR / "analysis_notes.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_rows()
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row["scenario"]].append(row)

    for scenario, scenario_rows in groups.items():
        scenario_rows.sort(key=lambda row: row["label"])
        bar_chart(
            scenario_rows,
            title=f"{scenario}: Goodput",
            value_key="goodput_bps",
            y_label="Goodput (Mbps)",
            output=FIG_DIR / f"{scenario}_goodput.svg",
            scale=1_000_000,
            color="#0f766e",
        )
        bar_chart(
            scenario_rows,
            title=f"{scenario}: Completion Time",
            value_key="completion_time_seconds",
            y_label="Saniye",
            output=FIG_DIR / f"{scenario}_completion.svg",
            scale=1.0,
            color="#7c3aed",
        )
        bar_chart(
            scenario_rows,
            title=f"{scenario}: Retransmission Rate",
            value_key="retransmission_rate",
            y_label="Oran",
            output=FIG_DIR / f"{scenario}_retransmission.svg",
            scale=1.0,
            color="#ea580c",
        )

    write_analysis_notes(groups)
    print(f"Generated SVG charts in {FIG_DIR}")
    print(f"Generated notes in {RESULT_DIR / 'analysis_notes.md'}")


if __name__ == "__main__":
    main()
