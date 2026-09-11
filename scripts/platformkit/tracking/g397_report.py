"""G397 per-section denominators, held pairs, enriched ledger copy and summary."""
from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g376_schedule import reconstructed_schedule
from scripts.platformkit.tracking.g397_census import cap_duration_seconds, sha256_file
from scripts.platformkit.tracking.g397_tables import (enrich_ledger, evaluated_tick_rows,
                                                      held_pair_summary)

FRAME_CAP = 3000
DIFF_KEYS = ("rows", "raw_rows", "unique_player_tick_rows", "producer_decoded_frames",
             "source_decoded_pts_frames", "evaluated_ticks", "suspended_ticks",
             "emitting_ticks", "zero_output_evaluated_ticks", "rows_per_decoded_frame",
             "rows_per_evaluated_tick", "held_share", "cap_implied_duration_s",
             "elapsed_source_pts_s", "expected_ticks_from_cap", "evaluated_gap_runs",
             "max_gap_frames")

__all__ = ["read_csv", "section_row", "distributions", "main"]


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read one caller-named CSV artifact into explicit row dictionaries."""
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    names: list[str] = []
    for row in rows:
        for key in row:
            if key not in names:
                names.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _number(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def section_row(receipt: dict[str, str], attempt: dict[str, Any] | None,
                snapshots: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Account for one selected section, keeping every denominator named or UNKNOWN."""
    section = receipt["section_id"]
    ball = snapshots / section / "ball_tracking.csv"
    tracking = snapshots / section / "tracking_data.csv"
    ticks, reason = evaluated_tick_rows(ball, tracking)
    held = held_pair_summary(ball, tracking)
    schedule = reconstructed_schedule(ball)
    sidecar = snapshots / section / "evaluated_frame_count.json"
    declared = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.is_file() else {}
    evaluated = [row for row in ticks if row["state"] == "EVALUATED"]
    suspended = [row for row in ticks if row["state"] == "SUSPENDED"]
    fps = _number(receipt.get("measured_avg_fps")) or _number(attempt and attempt.get("source_fps"))
    decoded = _number(attempt and attempt.get("decoded_frames"))
    raw_rows = sum(row["raw_rows"] for row in ticks)
    unique_rows = sum(row["unique_players"] for row in ticks)
    row: dict[str, Any] = {
        "section_id": section, "draw_kind": receipt.get("draw_kind"),
        "draw_order": receipt.get("draw_order"), "competition": receipt.get("competition"),
        "attempt_id": None if attempt is None else attempt.get("attempt_id"),
        "attempt_status": "MISSING" if attempt is None else attempt.get("status"),
        "attempts": receipt.get("attempts"), "schedule_reason": reason or schedule["reason"],
        "rows": None if attempt is None else attempt.get("rows"),
        "raw_rows": raw_rows, "unique_player_tick_rows": unique_rows,
        "producer_decoded_frames": decoded,
        "source_decoded_pts_frames": _number(receipt.get("decoded_pts_frames")),
        "source_status": receipt.get("source_status"), "pts_status": receipt.get("pts_status"),
        "declared_ticks": declared.get("evaluated_frames"),
        "ledger_evaluated_frames": None if attempt is None else attempt.get("evaluated_frames"),
        "evaluated_ticks": "UNKNOWN" if reason else len(evaluated),
        "suspended_ticks": "UNKNOWN" if reason else len(suspended),
        "emitting_ticks": "UNKNOWN" if reason else sum(r["emitting"] for r in evaluated),
        "zero_output_evaluated_ticks": "UNKNOWN" if reason else sum(1 - r["emitting"] for r in evaluated),
        "observed_stride": schedule.get("observed_stride"),
        "expected_ticks_from_cap": None,
        "evaluated_gap_runs": "UNKNOWN" if reason else 0,
        "max_gap_frames": "UNKNOWN" if reason else 0,
        "ledger_stride": None if attempt is None else attempt.get("stride"),
        "frame_cap": FRAME_CAP, "measured_avg_fps": fps,
        "measured_r_fps": _number(receipt.get("measured_r_fps")),
        "time_base": receipt.get("time_base"), "codec_name": receipt.get("codec_name"),
        "cap_implied_duration_s": None if not fps else cap_duration_seconds(FRAME_CAP, fps),
        "elapsed_source_pts_s": _number(receipt.get("pts_elapsed")),
        "declared_duration_s": None if attempt is None else attempt.get("source_duration"),
        "measured_kind": receipt.get("measured_kind"),
        "declared_kind": receipt.get("declared_kind"),
        "source_sha256": receipt.get("source_sha256", ""),
        "tracking_sha256": receipt.get("tracking_data.csv_sha256", ""),
        "ball_sha256": receipt.get("ball_tracking.csv_sha256", ""),
    }
    stride = _number(schedule.get("observed_stride")) or _number(attempt and attempt.get("stride"))
    if stride:
        row["expected_ticks_from_cap"] = FRAME_CAP / stride
    if not reason and stride:
        frames = sorted(row2["frame"] for row2 in evaluated)
        gaps = [right - left for left, right in zip(frames, frames[1:]) if right - left > stride]
        row["evaluated_gap_runs"] = len(gaps)
        row["max_gap_frames"] = max(gaps) if gaps else 0
    row["rows_per_decoded_frame"] = None if not decoded else raw_rows / decoded
    row["rows_per_evaluated_tick"] = None if reason or not evaluated else raw_rows / len(evaluated)
    row["held_share"] = held.get("held_share")
    row["held_status"] = held.get("status")
    held_row = dict(held, section_id=section, draw_kind=receipt.get("draw_kind"),
                    draw_order=receipt.get("draw_order"))
    return row, [dict(tick, section_id=section) for tick in evaluated], held_row


def distributions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Report per-kind descriptive distributions and their plain difference, never pooled."""
    out: dict[str, Any] = {"per_kind": {}, "difference_720p60_minus_1080p30": {}}
    for kind in ("1080p30", "720p60"):
        subset = [row for row in rows if row["draw_kind"] == kind]
        stats: dict[str, Any] = {"sections": len(subset)}
        for key in DIFF_KEYS:
            values = [_number(row.get(key)) for row in subset]
            values = [value for value in values if value is not None]
            stats[key] = {"n": len(values), "missing": len(subset) - len(values),
                          "median": None if not values else statistics.median(values),
                          "mean": None if not values else statistics.fmean(values),
                          "min": None if not values else min(values),
                          "max": None if not values else max(values)}
        stats["competition"] = dict(Counter(str(row["competition"]) for row in subset))
        stats["video"] = dict(Counter(str(row["section_id"]).rpartition("_s")[0] for row in subset))
        stats["measured_kind"] = dict(Counter(str(row["measured_kind"]) for row in subset))
        stats["source_status"] = dict(Counter(str(row["source_status"]) for row in subset))
        stats["schedule_unknown"] = sum(1 for row in subset if row["evaluated_ticks"] == "UNKNOWN")
        out["per_kind"][kind] = stats
    for key in DIFF_KEYS:
        high = out["per_kind"]["720p60"][key]["median"]
        low = out["per_kind"]["1080p30"][key]["median"]
        out["difference_720p60_minus_1080p30"][key] = (
            None if high is None or low is None else high - low)
    return out


def main(argv: list[str]) -> int:
    """Build every per-unit table and the descriptive summary from frozen snapshots."""
    scratch = Path(argv[1] if len(argv) > 1 else "/workspace/g397_scratch")
    receipts = read_csv(scratch / "source_receipts.csv")
    attempts: dict[str, list[dict[str, Any]]] = {}
    for line in (scratch / "selected_ledger.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            attempts.setdefault(str(record["game_id"]), []).append(record)
    sections, ticks, held = [], [], []
    for receipt in receipts:
        section = receipt["section_id"]
        primary = None
        for record in sorted(attempts.get(section, []), key=lambda r: str(r.get("finished_at", ""))):
            if record.get("terminal"):
                primary = record
                break
        row, tick_rows, held_row = section_row(receipt, primary, scratch / "snapshots")
        sections.append(row)
        ticks.extend(tick_rows)
        held.append(held_row)
    _write_csv(scratch / "per_section.csv", sections)
    _write_csv(scratch / "evaluated_ticks.csv", ticks)
    _write_csv(scratch / "held_pairs.csv", held)
    probes = {}
    for record in read_csv(scratch / "census.csv"):
        if record.get("source_sha256"):
            probes[record["attempt_id"]] = {"width": record["measured_width"],
                                            "height": record["measured_height"],
                                            "fps": record["measured_fps"]}
    flat = [record for group in attempts.values() for record in group]
    flat.sort(key=lambda r: r["ledger_line"])
    with (scratch / "enriched_ledger.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for record in enrich_ledger(flat, probes):
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    summary = distributions(sections)
    summary["census_utc"] = (scratch / "census_utc.txt").read_text(encoding="utf-8").strip()
    summary["ledger_snapshot_sha256"] = sha256_file(scratch / "ledger_snapshot.jsonl")
    summary["selected_attempts"] = len(flat)
    summary["enriched_join_matched"] = sum(1 for record in flat if record["attempt_id"] in probes)
    (scratch / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                                          encoding="utf-8", newline="\n")
    print("SECTIONS %d TICKS %d HELD %d ATTEMPTS %d" % (len(sections), len(ticks), len(held), len(flat)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
