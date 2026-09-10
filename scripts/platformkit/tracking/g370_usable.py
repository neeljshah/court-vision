"""G370 usable-control pass: the sealed v0 gates on UNPLANTED rated sections.

A control is a section a blind rater called usable court play. It is scored through
the same imported A0 / M1 route the admission rows use; a gate that never reached a
bar is ABSENT and leaves the row out of the rejection denominator instead of
counting as a pass (B1 is avoided by naming the excluded set in the artifact).
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Mapping

from scripts.platformkit.tracking.g358_gate_execution import (REACHED_STATUSES,
                                                              evaluate_section_arm_duration,
                                                              load_merged)
from scripts.platformkit.tracking.g359_held_position import collapse_held
from scripts.platformkit.tracking.g370_controls import V0_GATES
from scripts.platformkit.tracking.production_schema_adapter import adapt_production_section

COLUMNS = ("section_id", "game_id", "task", "usable", "status", "reached_gates",
           "reject_gates", "measurements")


def control_row(section: Mapping[str, Any], usable: bool) -> dict[str, Any]:
    """Score one unplanted section on the v0 gates and record every measurement."""
    adapted = adapt_production_section(load_merged(Path(section["tracking_path"]),
                                                   Path(section["ball_path"])))
    collapsed, _ = collapse_held(adapted.table)
    cells = [cell for cell in evaluate_section_arm_duration(
        section["section_id"], section.get("pool", "G370"), "A0", "FULL", collapsed,
        adapted.frame_width, adapted.frame_height, adapted.frame_size_source)
        if cell["gate"] in V0_GATES]
    reached = [cell["gate"] for cell in cells if cell["status"] in REACHED_STATUSES]
    rejects = [cell["gate"] for cell in cells if cell["status"] == "REJECT"]
    status = "REJECT" if rejects else ("PASS" if reached else "ABSENT")
    return {"section_id": section["section_id"], "game_id": section["game_id"],
            "task": "position", "usable": int(usable), "status": status,
            "reached_gates": "|".join(sorted(reached)), "reject_gates": "|".join(sorted(rejects)),
            "measurements": json.dumps({cell["gate"]: cell["measurement"] for cell in cells},
                                       sort_keys=True)}


def run(manifest: Path, ratings: Path, out: Path) -> None:
    """Write one control row per rated section; unrated sections are never invented."""
    sections = {entry["section_id"]: entry
                for entry in json.loads(manifest.read_text(encoding="utf-8"))["sections"]}
    with ratings.open(encoding="utf-8", newline="") as handle:
        rated = list(csv.DictReader(handle))
    rows = [control_row(sections[row["section_id"]], row["verdict"] == "USABLE")
            for row in rated if row["section_id"] in sections]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    usable = [row for row in rows if row["usable"]]
    scored = [row for row in usable if row["status"] in ("PASS", "REJECT")]
    rejected = sum(1 for row in scored if row["status"] == "REJECT")
    print("CONTROLS rated={} usable={} games={} scored={} absent={} rejected={} share={}".format(
        len(rows), len(usable), len({row["game_id"] for row in usable}), len(scored),
        len(usable) - len(scored), rejected,
        "{:.4f}".format(rejected / len(scored)) if scored else "ABSENT"))


def main() -> None:
    parser = argparse.ArgumentParser(description="G370 usable-control pass")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--ratings", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    run(args.manifest, args.ratings, args.out)


if __name__ == "__main__":
    main()
