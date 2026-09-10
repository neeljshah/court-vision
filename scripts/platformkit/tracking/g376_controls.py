"""G376 controls -- the three sealed checks of the tick classifier.

Expected values are sealed in g376_prereg_2026-09-10.md section 4
(SEAL sha256 32bcad44e602ac870f06e02cf5118272bf1343797906905f0ed4d8d4705173ee):
  a  re-run reproduction: symmetric difference 0, reproduction 1.000000
  b  fully observed synthetic: OBSERVED 1.000000, every other class 0
  c  doubled declaration: NOT_SCHEDULED 0.500000 and OBSERVED 0.500000
They are exact equalities, never tolerances. Nothing under `src/` or `data/` is written.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping

from scripts.platformkit.tracking.g376_classify import classify_section, section_row
from scripts.platformkit.tracking.g376_schedule import section_facts

CONTROL_FIELDS = ("control", "quantity", "expected", "observed", "passed")
_f = "{:.6f}".format


def write_synthetic_section(directory: Path, ticks: int, stride: int = 3) -> Path:
    """A section whose every declared tick is evaluated and carries one track row."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    frames = [index * stride for index in range(ticks)]
    with (directory / "tracking_data.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["frame", "player_id", "x_position", "y_position"])
        writer.writerows([frame, 1, 100, 100] for frame in frames)
    with (directory / "ball_tracking.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["frame", "timestamp", "ball_x2d", "ball_y2d", "detected", "live",
                         "ball_inferred"])
        writer.writerows([frame, 0.0, 1, 1, 1, 1, 0] for frame in frames)
    return directory


def _shares(directory: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    facts = section_facts(directory.name, "CONTROL", directory, record)
    return section_row(facts, list(classify_section(facts)))


def synthetic_controls(directory: Path, ticks: int = 40, stride: int = 3) -> list[dict[str, Any]]:
    """Controls b and c: one synthetic section, then the same section declared twice as long."""
    section = write_synthetic_section(Path(directory) / "g376_control_section", ticks, stride)
    record = {"stride": stride, "evaluated_frames": ticks,
              "decoded_frames": ticks * stride, "rows": ticks, "seconds": 1,
              "source_fps": 30.0}
    full = _shares(section, record)
    doubled = _shares(section, dict(record, evaluated_frames=ticks * 2,
                                    decoded_frames=ticks * stride * 2))
    checks = [
        ("b_fully_observed", "observed_share", _f(1.0), full["observed_share"]),
        ("b_fully_observed", "scheduled_no_detection", 0, full["scheduled_no_detection"]),
        ("b_fully_observed", "not_scheduled", 0, full["not_scheduled"]),
        ("b_fully_observed", "unknown", 0, full["unknown"]),
        ("b_fully_observed", "zero_observation_ticks", 0, full["zero_observation_ticks"]),
        ("c_doubled_declaration", "not_scheduled_share", _f(0.5), doubled["not_scheduled_share"]),
        ("c_doubled_declaration", "observed_share", _f(0.5), doubled["observed_share"]),
        ("c_doubled_declaration", "scheduled_no_detection", 0, doubled["scheduled_no_detection"]),
        ("c_doubled_declaration", "unknown", 0, doubled["unknown"]),
    ]
    return [{"control": name, "quantity": quantity, "expected": expected, "observed": observed,
             "passed": int(expected == observed)} for name, quantity, expected, observed in checks]


def reproduction_control(rerun_summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Control a from the controlled re-run summary; an absent re-run is NOT a pass (B3)."""
    if not rerun_summary:
        return [{"control": "a_rerun_reproduction", "quantity": "reproduction",
                 "expected": _f(1.0), "observed": "ABSENT", "passed": 0}]
    return [
        {"control": "a_rerun_reproduction", "quantity": "reproduction", "expected": _f(1.0),
         "observed": rerun_summary.get("reproduction"),
         "passed": int(rerun_summary.get("reproduction") == _f(1.0))},
        {"control": "a_rerun_reproduction", "quantity": "symmetric_difference", "expected": 0,
         "observed": rerun_summary.get("symmetric_difference"),
         "passed": int(rerun_summary.get("symmetric_difference") == 0)},
    ]


def write_controls(rows: list[dict[str, Any]], out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CONTROL_FIELDS))
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, help="scratch directory for the synthetic section")
    parser.add_argument("--rerun-summary", default="", help="g376_rerun summary json, when present")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    summary: dict[str, Any] = {}
    if args.rerun_summary and Path(args.rerun_summary).exists():
        summary = json.loads(Path(args.rerun_summary).read_text(encoding="utf-8"))
    rows = synthetic_controls(Path(args.work)) + reproduction_control(summary)
    write_controls(rows, Path(args.out))
    for row in rows:
        print("%-24s %-24s expected=%-10s observed=%-10s passed=%d"
              % (row["control"], row["quantity"], row["expected"], row["observed"], row["passed"]))
    return 0 if all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
