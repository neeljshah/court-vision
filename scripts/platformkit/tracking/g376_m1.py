"""G376 -- the M1-corrected producer-evaluated denominator (AMENDMENT A1).

A1.1 of `docs/evidence/tracking/g376_declared_tick_observations_2026-09-10/
g376_amendment_A1_2026-09-10.md` (SEAL sha256
d5e8a9214995ab6ac48c55953543958e5000c68515751c49693022c5b2f260c4) fixes the numerator the
preregistration left open. Per section this module computes `|M1 & E|` and `|E| - |M1 & E|`,
where `E` is the reconstructed producer schedule (`g376_schedule.reconstructed_schedule`) and
`M1` is the G370 M1 player-frame set obtained by IMPORTING the landed G370 route
(`g376_premise.m1_observed_frames`, the identical construction to
`scripts/platformkit/tracking/g370_scorer.py:104-117`; nothing is copied).

The RAW `observed_ticks` columns of `g376_report.py` are NOT touched (A1.2). Reads the immutable
lane snapshot only; writes nothing under `src/`, `data/` or the deploy tree.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Mapping

from scripts.platformkit.tracking.g376_premise import m1_observed_frames
from scripts.platformkit.tracking.g376_schedule import reconstructed_schedule

ABSENT = "ABSENT"
M1_FIELDS = ("m1_observed_ticks_in_producer_evaluated",
             "m1_zero_ticks_over_producer_evaluated",
             "m1_zero_share_over_producer_evaluated")
FIELDS = ("section_id", "set", "declared_ticks", "producer_evaluated_ticks", "schedule_reason",
          "m1_observed_ticks_in_declared", "m1_zero_ticks_over_declared",
          "m1_zero_share_over_declared") + M1_FIELDS
_f = "{:.6f}".format


def section_row(section_id: str, set_name: str, section_dir: Path,
                declared_ticks: int, stride: int) -> dict[str, Any]:
    """A1.1 for one section. A section with no reconstructed schedule contributes nothing."""
    section_dir = Path(section_dir)
    schedule = reconstructed_schedule(section_dir / "ball_tracking.csv")
    row: dict[str, Any] = {"section_id": section_id, "set": set_name,
                           "declared_ticks": declared_ticks,
                           "schedule_reason": schedule["reason"]}
    if schedule["reason"] or not stride:
        row.update({field: ABSENT for field in FIELDS if field not in row})
        return row
    evaluated = schedule["evaluated"]
    declared = {index * stride for index in range(declared_ticks)}
    m1 = m1_observed_frames(section_dir / "tracking_data.csv", section_dir / "ball_tracking.csv")
    in_declared, in_evaluated = len(m1 & declared), len(m1 & evaluated)
    row.update({
        "producer_evaluated_ticks": len(evaluated),
        "m1_observed_ticks_in_declared": in_declared,
        "m1_zero_ticks_over_declared": declared_ticks - in_declared,
        "m1_zero_share_over_declared":
            _f((declared_ticks - in_declared) / declared_ticks) if declared_ticks else ABSENT,
        "m1_observed_ticks_in_producer_evaluated": in_evaluated,
        "m1_zero_ticks_over_producer_evaluated": len(evaluated) - in_evaluated,
        "m1_zero_share_over_producer_evaluated":
            _f((len(evaluated) - in_evaluated) / len(evaluated)) if evaluated else ABSENT,
    })
    return row


def totals(rows: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Set totals: sum |E| and sum (|E| - |M1 & E|) over the sections that HAVE a schedule."""
    out = {}
    for set_name in sorted({row["set"] for row in rows}):
        scored = [row for row in rows if row["set"] == set_name
                  and row["m1_zero_ticks_over_producer_evaluated"] != ABSENT]
        evaluated = sum(int(row["producer_evaluated_ticks"]) for row in scored)
        zero = sum(int(row["m1_zero_ticks_over_producer_evaluated"]) for row in scored)
        declared = sum(int(row["declared_ticks"]) for row in scored)
        zero_declared = sum(int(row["m1_zero_ticks_over_declared"]) for row in scored)
        out[set_name] = {
            "sections_scored": len(scored),
            "sections_without_schedule": sum(1 for row in rows if row["set"] == set_name
                                             and row["m1_zero_ticks_over_producer_evaluated"] == ABSENT),
            "g370_declared_ticks": declared,
            "g370_m1_zero_ticks_over_declared": zero_declared,
            "g370_m1_zero_share_over_declared": _f(zero_declared / declared) if declared else None,
            "m1_producer_evaluated_ticks": evaluated,
            "m1_zero_ticks_over_producer_evaluated": zero,
            "m1_zero_share_over_producer_evaluated": _f(zero / evaluated) if evaluated else None,
        }
    return out


def run(classification: Path, snapshot: Path, out_dir: Path) -> dict[str, dict[str, Any]]:
    """Write `m1_denominators.csv` and `m1_denominators.json` beside the RAW artifacts."""
    rows = []
    with Path(classification).open(newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            stride = int(record["stride"]) if record["stride"] else 0
            rows.append(section_row(record["section_id"], record["set"],
                                    Path(snapshot) / record["section_id"],
                                    int(record["declared_ticks"]), stride))
    out_dir = Path(out_dir)
    with (out_dir / "m1_denominators.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FIELDS))
        writer.writeheader()
        writer.writerows(rows)
    summary = totals(rows)
    (out_dir / "m1_denominators.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    summary = run(Path(args.out) / "classification.csv", Path(args.snapshot), Path(args.out))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
