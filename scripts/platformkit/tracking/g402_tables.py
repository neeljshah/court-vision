"""G402 accounting, held-step, provenance, frozen mask and coverage tables.

Evaluated ticks come ONLY from the instrumented receipt; they are never
reconstructed from emitted player rows. Every denominator is named and the
silent units (zero-output ticks, no-shared-player pairs) are carried.
"""
from __future__ import annotations
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from scripts.platformkit.tracking.g402_mask import coverage, held_pairs, mask_target
TICK_FIELDS = ("draw_kind", "section_id", "status", "sealed_start_frame",
               "sealed_end_frame_exclusive", "bounded_rows", "excluded_overrun_rows",
               "bounded_evaluated_ticks", "excluded_overrun_evaluated_ticks",
               "source_decoded_frames_in_window",
               "sealed_window_source_frames", "window_overrun_frames",
               "producer_attempted_ticks", "receipt_evaluated_ticks", "trace_attempt_ticks",
               "receipt_equals_trace", "trace_subset_of_receipt", "emitting_ticks",
               "zero_output_evaluated_ticks", "suspended_rows", "rows",
               "receipt_only_ticks", "trace_only_ticks", "schedule")
HELD_FIELDS = ("draw_kind", "section_id", "sealed_start_frame", "sealed_end_frame_exclusive",
               "held_pairs", "shared_pairs", "no_shared_pairs",
               "adjacent_evaluated_pairs", "zero_output_evaluated_ticks", "held_share")
COVER_FIELDS = ("draw_kind", "section_id", "coverage_status", "sealed_start_frame",
                "sealed_end_frame_exclusive", "bounded_rows", "excluded_overrun_rows",
                "rows", "candidate_rows",
                "sealed_window_source_frames", "all_decoded_frames",
                "decoded_frames_with_candidate", "all_evaluated_ticks",
                "evaluated_ticks_with_candidate", "zero_output_evaluated_ticks",
                "candidate_rows_per_row", "candidate_frames_per_decoded_frame",
                "candidate_ticks_per_evaluated_tick")
MASK_FIELDS = ("draw_kind", "section_id", "sealed_start_frame",
               "sealed_end_frame_exclusive", "frame", "player_id", "position_source",
               "source_branch", "matched_event_id", "matched_event_valid",
               "repeated_coordinate", "x_position", "y_position", "bbox_x1", "bbox_y1",
               "bbox_x2", "bbox_y2", "target_weight", "mask_reason")
PROV_FIELDS = ("draw_kind", "section_id", "sealed_start_frame", "sealed_end_frame_exclusive",
               "position_source", "repeated_coordinate",
               "rows", "target_weight_1")
KINDS = ("1080p30", "720p60")
def read_rows(path: Path) -> list:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        return list(csv.DictReader(handle))

def trace_attempts(path: Path) -> list:
    if not path.is_file():
        return []
    ticks = set()
    for line in path.read_text(encoding="ascii", errors="replace").splitlines():
        if line.startswith("A,"):
            try:
                ticks.add(int(line.split(",")[1]))
            except (IndexError, ValueError):
                continue
    return sorted(ticks)

def event_valid(row) -> bool:
    parts = str(row.get("matched_event_id", "")).split("_")
    if len(parts) != 5:
        return False
    try:
        got = [int(item) for item in parts]
        want = [int(row["frame"]), int(float(row["bbox_y1"])), int(float(row["bbox_x1"])),
                int(float(row["bbox_y2"])), int(float(row["bbox_x2"]))]
    except (KeyError, TypeError, ValueError):
        return False
    return got == want

def box_id(row) -> str:
    try:
        return "%d_%d_%d_%d" % tuple(int(float(row[key])) for key in
                                     ("bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"))
    except (KeyError, TypeError, ValueError):
        return ""

def repeats_flags(rows: list, ticks: list) -> dict:
    """Flag a row whose byte-equal coordinate repeats the same track on the
    immediately preceding EVALUATED tick. A missing tick is never bridged."""
    order = {tick: index for index, tick in enumerate(ticks)}
    by_key: dict = {}
    for row in rows:
        try:
            index = order[int(row["frame"])]
        except (KeyError, ValueError):
            continue
        by_key.setdefault((str(row.get("player_id", "")), index), set()).add(
            (str(row.get("x_position", "")), str(row.get("y_position", ""))))
    flags = {}
    for position, row in enumerate(rows):
        try:
            index = order[int(row["frame"])]
        except (KeyError, ValueError):
            flags[position] = False
            continue
        point = (str(row.get("x_position", "")), str(row.get("y_position", "")))
        prior = by_key.get((str(row.get("player_id", "")), index - 1), set())
        flags[position] = index > 0 and point in prior
    return flags

def section_tables(row, evidence: Path):
    kind, section = row["draw_kind"], row["section_id"]
    raw = evidence / "raw_tables" / kind / section
    trace = evidence / "trace" / (kind + "__" + section + ".trace")
    all_rows = read_rows(raw / "tracking_data.csv")
    receipt_path = raw / "evaluated_tick_receipt.json"
    schedule, ticks, attempted = "UNKNOWN", [], ""
    if receipt_path.is_file():
        data = json.loads(receipt_path.read_text(encoding="utf-8"))
        ticks = sorted(int(item) for item in data.get("evaluated_tick_ids") or [])
        attempted = data.get("attempted_frames_capped", "")
        schedule = "COMPLETE" if ticks else "EMPTY"
    start, sealed = int(row["start_frame"]), int(row["frames"])
    end = start + sealed
    rows = [item for item in all_rows if start <= int(item["frame"]) < end]
    raw_ticks, raw_traced = ticks, trace_attempts(trace)
    ticks = [item for item in raw_ticks if start <= item < end]
    traced = [item for item in raw_traced if start <= item < end]
    decoded = list(range(start, end))
    flags = repeats_flags(rows, ticks)
    masked = []
    for position, item in enumerate(rows):
        valid = event_valid(item)
        decision = mask_target({**item, "matched_event_valid": valid,
                                "matched_box_id": box_id(item),
                                "repeated_coordinate": flags.get(position, False)})
        masked.append({"draw_kind": kind, "section_id": section, "frame": item.get("frame"),
                       "player_id": item.get("player_id"),
                       "position_source": item.get("position_source", "MISSING"),
                       "source_branch": item.get("source_branch", ""),
                       "matched_event_id": item.get("matched_event_id", ""),
                       "matched_event_valid": int(valid),
                       "repeated_coordinate": int(flags.get(position, False)),
                       "x_position": item.get("x_position"), "y_position": item.get("y_position"),
                       "bbox_x1": item.get("bbox_x1"), "bbox_y1": item.get("bbox_y1"),
                       "bbox_x2": item.get("bbox_x2"), "bbox_y2": item.get("bbox_y2"),
                       "target_weight": decision["target_weight"],
                       "mask_reason": decision["mask_reason"]})
    candidates = [item for item in masked if item["target_weight"] == 1]
    tick_set = set(ticks)
    emitting = len({int(item["frame"]) for item in rows if int(item["frame"]) in tick_set})
    cover = coverage(decoded, ticks, [{"frame": int(item["frame"])} for item in candidates]) \
        if ticks else {"all_decoded_frames": len(decoded), "decoded_frames_with_candidate": 0,
                       "all_evaluated_ticks": 0, "evaluated_ticks_with_candidate": 0,
                       "zero_output_evaluated_ticks": 0}
    held = held_pairs(ticks, rows) if ticks else {
        "held_pairs": 0, "shared_pairs": 0, "no_shared_pairs": 0,
        "adjacent_evaluated_pairs": 0, "zero_output_evaluated_ticks": 0}
    tick_row = {"draw_kind": kind, "section_id": section, "status": row.get("status", ""),
                "sealed_start_frame": start, "sealed_end_frame_exclusive": end,
                "bounded_rows": len(rows), "excluded_overrun_rows": len(all_rows) - len(rows),
                "bounded_evaluated_ticks": len(ticks),
                "excluded_overrun_evaluated_ticks": len(raw_ticks) - len(ticks),
                "sealed_window_source_frames": sealed,
                "source_decoded_frames_in_window": len(decoded),
                "window_overrun_frames": 0,
                "producer_attempted_ticks": attempted, "receipt_evaluated_ticks": len(ticks),
                "trace_attempt_ticks": len(traced) if trace.is_file() else "NOT_TRACED",
                "receipt_equals_trace": int(ticks == traced) if trace.is_file() else "",
                "trace_subset_of_receipt": int(set(traced) <= tick_set) if trace.is_file() else "",
                "emitting_ticks": emitting,
                "zero_output_evaluated_ticks": len(tick_set) - emitting,
                "suspended_rows": sum(1 for item in rows
                                      if str(item.get("homography_valid", "1")) == "0"),
                "rows": len(rows),
                "receipt_only_ticks": len(tick_set - set(traced)) if trace.is_file() else "",
                "trace_only_ticks": len(set(traced) - tick_set) if trace.is_file() else "",
                "schedule": schedule}
    held_row = {"draw_kind": kind, "section_id": section, "sealed_start_frame": start,
                "sealed_end_frame_exclusive": end, **held,
                "held_share": round(held["held_pairs"] / held["shared_pairs"], 6)
                if held["shared_pairs"] else ""}
    cover_row = {"draw_kind": kind, "section_id": section, "coverage_status": "COMPLETE",
                 "sealed_start_frame": start, "sealed_end_frame_exclusive": end,
                 "bounded_rows": len(rows), "excluded_overrun_rows": len(all_rows) - len(rows),
                 "rows": len(rows),
                 "sealed_window_source_frames": sealed,
                 "candidate_rows": len(candidates), **cover,
                 "candidate_rows_per_row": round(len(candidates) / len(rows), 6) if rows else "",
                 "candidate_frames_per_decoded_frame":
                     round(cover["decoded_frames_with_candidate"] / len(decoded), 6),
                 "candidate_ticks_per_evaluated_tick":
                     round(cover["evaluated_ticks_with_candidate"] / len(ticks), 6)
                     if ticks else ""}
    counts = Counter((item["position_source"], item["repeated_coordinate"]) for item in masked)
    admitted = Counter((item["position_source"], item["repeated_coordinate"])
                       for item in candidates)
    prov = [{"draw_kind": kind, "section_id": section, "sealed_start_frame": start,
             "sealed_end_frame_exclusive": end, "position_source": key[0],
             "repeated_coordinate": key[1], "rows": value,
             "target_weight_1": admitted.get(key, 0)} for key, value in sorted(counts.items())]
    return tick_row, held_row, cover_row, masked, prov


def unknown_coverage(row) -> dict:
    """Retain an unmeasured planned window without inventing emitted coverage."""
    start, sealed = int(row["start_frame"]), int(row["frames"])
    return {"draw_kind": row["draw_kind"], "section_id": row["section_id"],
            "coverage_status": "UNKNOWN", "sealed_start_frame": start,
            "sealed_end_frame_exclusive": start + sealed, "bounded_rows": 0,
            "excluded_overrun_rows": 0, "rows": 0, "candidate_rows": 0,
            "sealed_window_source_frames": sealed, "all_decoded_frames": sealed,
            "decoded_frames_with_candidate": 0, "all_evaluated_ticks": 0,
            "evaluated_ticks_with_candidate": 0, "zero_output_evaluated_ticks": 0,
            "candidate_rows_per_row": "", "candidate_frames_per_decoded_frame": 0,
            "candidate_ticks_per_evaluated_tick": ""}


def write(path: Path, fields: tuple, rows: list) -> None:
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore",
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def summarize(launches: list, ticks: list, helds: list, covers: list, masks: list) -> dict:
    per_kind = {}
    for kind in KINDS:
        planned = [item for item in launches if item["draw_kind"] == kind]
        complete = [item for item in planned if item.get("status") == "COMPLETE"]
        kmask = [item for item in masks if item["draw_kind"] == kind]
        kcover = [item for item in covers if item["draw_kind"] == kind]
        ktick = [item for item in ticks if item["draw_kind"] == kind]
        kheld = [item for item in helds if item["draw_kind"] == kind]
        pool = {
            "planned": len(planned), "complete": len(complete),
            "status": dict(Counter(item.get("status", "") for item in planned)),
            "rows": len(kmask), "candidate_rows": sum(item["target_weight"] for item in kmask),
            "provenance_frequencies": dict(sorted(Counter(
                item["position_source"] for item in kmask).items())),
            "all_decoded_frames": sum(item["all_decoded_frames"] for item in kcover),
            "decoded_frames_with_candidate": sum(item["decoded_frames_with_candidate"]
                                                 for item in kcover),
            "all_evaluated_ticks": sum(item["all_evaluated_ticks"] for item in kcover),
            "evaluated_ticks_with_candidate": sum(item["evaluated_ticks_with_candidate"]
                                                  for item in kcover),
            "zero_output_evaluated_ticks": sum(item["zero_output_evaluated_ticks"]
                                               for item in ktick),
            "receipt_equals_trace": sum(1 for item in ktick if item["receipt_equals_trace"] == 1),
            "schedule_unknown": len(planned) - len(ktick),
            "held_pairs": sum(item["held_pairs"] for item in kheld),
            "shared_pairs": sum(item["shared_pairs"] for item in kheld),
            "no_shared_pairs": sum(item["no_shared_pairs"] for item in kheld),
            "distinct_games": len({item["section_id"].split("_s")[0] for item in complete}),
        }
        pool["held_share_pooled"] = round(pool["held_pairs"] / pool["shared_pairs"], 6) \
            if pool["shared_pairs"] else ""
        pool["candidate_rows_per_row"] = round(pool["candidate_rows"] / pool["rows"], 6) \
            if pool["rows"] else ""
        per_kind[kind] = pool
    return {"per_kind": per_kind, "planned_total": len(launches),
            "masked_classes_admitted": sum(
                1 for item in masks if item["target_weight"] == 1 and (
                    item["position_source"] != "DETECTION" or item["repeated_coordinate"]
                    or not item["matched_event_valid"]))}
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()
    evidence = Path(args.evidence)
    launches = read_rows(evidence / "launch_receipts.csv")
    ticks, helds, covers, masks, provs = [], [], [], [], []
    for row in launches:
        if row.get("status") == "COMPLETE":
            tick_row, held_row, cover_row, masked, prov = section_tables(row, evidence)
            ticks.append(tick_row); helds.append(held_row); covers.append(cover_row)
            masks.extend(masked); provs.extend(prov)
        else:
            covers.append(unknown_coverage(row))
    write(evidence / "evaluated_ticks.csv", TICK_FIELDS, ticks)
    write(evidence / "held_pairs.csv", HELD_FIELDS, helds)
    write(evidence / "coverage_per_section.csv", COVER_FIELDS, covers)
    write(evidence / "target_mask.csv", MASK_FIELDS, masks)
    write(evidence / "provenance_counts.csv", PROV_FIELDS, provs)
    summary = summarize(launches, ticks, helds, covers, masks)
    summary["failures"] = {}
    for row in launches:
        if row.get("status") == "COMPLETE":
            continue
        log = evidence / "raw_tables" / row["draw_kind"] / row["section_id"] / "run.log.txt"
        reason = "NO_LOG"
        if log.is_file():
            text = log.read_text(encoding="utf-8", errors="replace")
            reason = "PREFLIGHT_PERSON_COUNT" if "[PREFLIGHT FAIL]" in text else \
                ("NO_TRACKING_CSV" if "tracking_data.csv" not in row.get("outputs_present", "")
                 else "UNCLASSIFIED")
        summary["failures"]["%s/%s" % (row["draw_kind"], row["section_id"])] = reason
    (evidence / "summary_tables.json").write_bytes(
        (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("ascii"))
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
