"""Extract and compare G195 route-determinism measurement records."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SOURCE_FRAMES = (474, 1377)
_SURVIVOR_COLUMNS = ("player_id", "team", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2")


def _csv_hash(path: Path) -> str:
    """Return the SHA-256 digest of one emitted CSV."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sort_survivors(rows: Iterable[Mapping[str, str]]) -> list[list[str]]:
    """Return source-frame survivors in a stable presentation order."""
    tuples = [[row[column] for column in _SURVIVOR_COLUMNS] for row in rows]
    return sorted(tuples, key=lambda item: (int(item[0]), item[1], *item[2:]))


def measure_directory(data_dir: Path) -> dict[str, Any]:
    """Recount one route output directory without filtering any emitted row."""
    tracking_path = data_dir / "tracking_data.csv"
    ball_path = data_dir / "ball_tracking.csv"
    with tracking_path.open(newline="", encoding="utf-8") as handle:
        player_rows = list(csv.DictReader(handle))
    with ball_path.open(newline="", encoding="utf-8") as handle:
        ball_rows = list(csv.DictReader(handle))
    survivors = {
        str(frame): _sort_survivors(row for row in player_rows if row["frame"] == str(frame))
        for frame in SOURCE_FRAMES
    }
    return {
        "data_dir": str(data_dir),
        "player_rows": len(player_rows),
        "distinct_player_row_frames": len({row["frame"] for row in player_rows}),
        "eligible_denominator_attempted_gameplay_frames": len(
            {row["frame"] for row in ball_rows}
        ),
        "survivors": survivors,
        "tracking_data_csv_sha256": _csv_hash(tracking_path),
        "ball_tracking_csv_sha256": _csv_hash(ball_path),
    }


def arm_comparison(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Determine whether all complete emitted-route records are identical."""
    if len(records) != 3:
        raise ValueError("G195 compares exactly three runs per arm")
    comparable = [{key: value for key, value in record.items() if key != "data_dir"} for record in records]
    serialized = [json.dumps(record, sort_keys=True, separators=(",", ":")) for record in comparable]
    return {
        "run_count": len(records),
        "identical_across_three_runs": len(set(serialized)) == 1,
        "comparison_includes_complete_csv_hashes": True,
    }


def main() -> None:
    """Print one JSON measurement record or one three-run arm verdict."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("data_dirs", nargs="+", type=Path)
    args = parser.parse_args()
    records = [measure_directory(path) for path in args.data_dirs]
    payload: dict[str, Any] = {"records": records}
    if len(records) == 3:
        payload["comparison"] = arm_comparison(records)
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
