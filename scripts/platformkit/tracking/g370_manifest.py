"""G370 finisher manifests: declared schedules, ledger records and source pins.

The scheduled frame set is DECLARED from the producer ledger (`stride` and
`evaluated_frames`), never from the frames that happen to carry rows (H1). A
section whose ledger lacks either field is excluded with a named reason instead of
being silently dropped.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Mapping

from scripts.platformkit.tracking.g359_held_position import LEDGER_FIELDS, latest_ledger_records
from scripts.platformkit.tracking.g361_source_identity import parse_gid, sha256_file

PLANT_KINDS = ("FROZEN", "COAST", "ID_MERGE")


def _rows(path: Path, selected_only: bool) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [row for row in rows if row.get("selected") == "1"] if selected_only else rows


def _schedule(record: Mapping[str, Any]) -> tuple[list[int], str]:
    """Declared evaluated-tick frame indexes, or an empty list and a named reason."""
    try:
        stride, evaluated = int(record["stride"]), int(record["evaluated_frames"])
    except (KeyError, TypeError, ValueError):
        return [], "ledger_cadence_absent"
    if stride <= 0 or evaluated <= 0:
        return [], "ledger_cadence_non_positive"
    return [index * stride for index in range(evaluated)], ""


def section_entry(name: str, game_id: str, pool: str, sections_dir: Path,
                  record: Mapping[str, Any]) -> dict[str, Any]:
    """One manifest section with its declared schedule and its source pins."""
    tracking = (sections_dir / name / "tracking_data.csv").resolve()
    ball = (sections_dir / name / "ball_tracking.csv").resolve()
    parsed = parse_gid(name) or {}
    scheduled, reason = _schedule(record)
    return {
        "section_id": name, "game_id": game_id, "pool": pool,
        "competition": record.get("sport"),
        "tracking_path": str(tracking), "ball_path": str(ball),
        "scheduled_frames": scheduled, "schedule_reason": reason,
        "decoded_frame_count": record.get("decoded_frames"),
        "ledger_record": {field: record.get(field) for field in LEDGER_FIELDS},
        "source_id": parsed.get("ytid"),
        "source_uri": None, "requested_start_s": parsed.get("offset"),
        "requested_end_s": None, "source_sha256": None, "byte_size": None,
        "source_identity_status": "UNKNOWN",
        "table_sha256_pin": sha256_file(tracking),
    }


def build(sources: list[tuple[Path, bool]], sections_dir: Path, ledger: Path,
          controls_path: str, plants_path: str, out: Path, excluded: Path) -> dict[str, Any]:
    """Materialize the scorer manifest and archive every excluded section."""
    records = latest_ledger_records(ledger)
    sections, dropped = [], []
    for path, selected_only in sources:
        for row in _rows(path, selected_only):
            name = row["section_name"]
            entry = section_entry(name, row["game_id"], row.get("pool", "G370"),
                                  sections_dir, records.get(name, {}))
            (sections if entry["scheduled_frames"] else dropped).append(entry)
    payload = {"controls_path": controls_path, "plants_path": plants_path,
               "sections": sections}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    with excluded.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("section_id", "game_id", "reason"))
        writer.writeheader()
        writer.writerows([{"section_id": entry["section_id"], "game_id": entry["game_id"],
                           "reason": entry["schedule_reason"]} for entry in dropped])
    print("manifest sections={} excluded={} scheduled_frames={}".format(
        len(sections), len(dropped), sum(len(entry["scheduled_frames"]) for entry in sections)))
    return payload


def plants(payload: Mapping[str, Any], out: Path, per_kind: int) -> None:
    """Every kind applied to the same evenly spanned sections; nothing is head-sliced."""
    sections = payload["sections"]
    step = max(len(sections) // per_kind, 1)
    chosen = [sections[index] for index in range(0, len(sections), step)][:per_kind]
    rows = [{"section_id": entry["section_id"], "game_id": entry["game_id"],
             "pool": entry["pool"], "tracking_path": entry["tracking_path"],
             "ball_path": entry["ball_path"], "kind": kind}
            for kind in PLANT_KINDS for entry in chosen]
    out.write_text(json.dumps(rows, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("plants sections={} per_kind={} rows={}".format(len(chosen), per_kind, len(rows)))


def main() -> None:
    parser = argparse.ArgumentParser(description="G370 finisher manifests")
    parser.add_argument("--fresh-sections", type=Path)
    parser.add_argument("--sealed-sections", type=Path)
    parser.add_argument("--sections-dir", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--controls-path", required=True)
    parser.add_argument("--plants-path", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--excluded", required=True, type=Path)
    parser.add_argument("--plants-out", type=Path)
    parser.add_argument("--plants-per-kind", type=int, default=30)
    args = parser.parse_args()
    sources = [(path, selected) for path, selected in
               ((args.fresh_sections, True), (args.sealed_sections, False)) if path]
    payload = build(sources, args.sections_dir, args.ledger, args.controls_path,
                    args.plants_path, args.out, args.excluded)
    if args.plants_out:
        plants(payload, args.plants_out, args.plants_per_kind)


if __name__ == "__main__":
    main()
