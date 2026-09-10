"""G370 eye-check strips: 30 admission rows spread evenly over the decision ordering.

The picks span the exported ordering end to end (B7) and always include rows whose
observations are absent or unattributed, so a refused or unknown case is never
sampled away.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

STRIP_TARGET = 30
STRIP_MAX_BYTES = 200 * 1024


def even_pick(count: int, target: int) -> list[int]:
    """Exactly `target` indexes spanning 0..count-1, last member always included."""
    if count <= target:
        return list(range(count))
    step = (count - 1) / (target - 1)
    return sorted({round(index * step) for index in range(target)})


def _load(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)


def _items(value: Any) -> list[Mapping[str, Any]]:
    """Observation arrays arrive as JSON text from CSV and as arrays from parquet."""
    if isinstance(value, str):
        return json.loads(value)
    return [] if value is None else list(value)


def _cell(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _lines(row: Mapping[str, Any]) -> list[str]:
    tracks = [item["position_source"] for item in _items(row["track_observations"])]
    balls = [item["position_source"] for item in _items(row["ball_observations"])]
    gates = _cell(row["gate_scores_m1"]) or {}
    v0 = {gate: value.get("status") for gate, value in gates.items() if isinstance(value, dict)}
    return [
        "section {} frame {}".format(row["section_id"], row["frame_index"]),
        "game {} competition {}".format(row["game_id"], row["competition"]),
        "evaluated tick {} verified {}".format(row["evaluated_tick_id"],
                                               row["evaluated_tick_verified"]),
        "track observations {} by source {}".format(
            len(tracks), json.dumps(dict(collections.Counter(tracks)), sort_keys=True)),
        "ball observations {} by source {}".format(
            len(balls), json.dumps(dict(collections.Counter(balls)), sort_keys=True)),
        "observed labels {}".format(sum(bool(item["observed"])
                                        for item in _items(row["track_observations"]))),
        "gate status {}".format(json.dumps(v0, sort_keys=True)),
        "task status {}".format(json.dumps(_cell(row["gate_status_by_task"]), sort_keys=True)),
        "task mask {}".format(json.dumps(_cell(row["task_mask"]), sort_keys=True)),
        "admission status {} scorable {}".format(row["admission_status"], row["scorable"]),
        "geometry {} table sha256 {}".format(row["geometry_status"], row["table_sha256"]),
    ]


def strip_svg(index: int, row: Mapping[str, Any]) -> bytes:
    """One ASCII strip; the row is rendered verbatim, never summarized away."""
    lines = ["STRIP {:02d}".format(index)] + _lines(row)
    body = "".join("<text x='8' y='{}' font-family='monospace' font-size='11'>{}</text>".format(
        20 + 16 * order, text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        for order, text in enumerate(lines))
    return ("<svg xmlns='http://www.w3.org/2000/svg' width='980' height='{}'>"
            "<rect width='980' height='{}' fill='#ffffff'/>{}</svg>".format(
                24 + 16 * len(lines), 24 + 16 * len(lines), body)).encode("ascii", "replace")


def build(rows_path: Path, out_dir: Path) -> None:
    """Write the strips and print the picked ordering positions."""
    table = _load(rows_path)
    picks = even_pick(len(table), STRIP_TARGET)
    out_dir.mkdir(parents=True, exist_ok=True)
    for order, position in enumerate(picks):
        payload = strip_svg(order, table.iloc[position].to_dict())
        if len(payload) > STRIP_MAX_BYTES:
            raise ValueError("strip {} is {} bytes".format(order, len(payload)))
        (out_dir / "strip_{:02d}.svg".format(order)).write_bytes(payload)
    print("strips n={} of rows={} positions={}".format(len(picks), len(table), picks[:5]))


def main() -> None:
    parser = argparse.ArgumentParser(description="G370 eye-check strips")
    parser.add_argument("--rows", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    build(args.rows, args.out_dir)


if __name__ == "__main__":
    main()
