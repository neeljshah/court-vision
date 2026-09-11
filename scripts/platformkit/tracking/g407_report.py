"""G407 delivered tables, cards and summary, rebuilt only from delivered bytes.

Derived from `population.json`, `probes.json`, `source_receipts.csv` and the bounded traces
under `raw_traces/`. No producer is launched and no stratum is pooled with another.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g407_accounting import window_counts
from scripts.platformkit.tracking.g407_cards import (
    SELF_REFERENTIAL, render_cards, scan_files, sha256sums,
)
from scripts.platformkit.tracking.g407_observer import q6_scan
from scripts.platformkit.tracking.g407_population import even_draw
from scripts.platformkit.tracking.g407_tables import (
    QUOTA, bind_rendition, boundary_split, class_summaries, held_share,
    stratum_counts,
)

SELECTOR_UTC = "2026-09-11T17:01:52Z"
PROBE_UTC = "2026-09-11T18:56:17Z"
RESIDUAL = ("UNRESOLVED", "UNKNOWN")
SCHEDULE_COUNTS = ("attempted_reads", "evaluated_ticks", "suspension_ticks", "zero_output_evaluated_ticks", "held_pairs", "shared_pairs")
CLAIM_FIELDS = {"status", "retention_status", "probe_status", "schedule_reason", "verdict",
                "format_join_status", "itag_consistency", "stratum", "note", "cap_status",
                "measured_class", "actual_rendition", "probe_agreement", "scope", "card_kind"}
def _write(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore",
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
def _json(path: Path, payload: Any) -> None:
    Path(path).write_text(json.dumps(payload, indent=1, sort_keys=True, default=str),
                          encoding="utf-8", newline="\n")
def load_rows(out: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Merge the census, the two independent probes and the retention receipts."""
    payload = json.loads((out / "population.json").read_text(encoding="utf-8"))
    probes = {str(row["section_identity"]): row
              for row in json.loads((out / "probes.json").read_text(encoding="utf-8"))}
    with (out / "source_receipts.csv").open(newline="", encoding="utf-8") as handle:
        receipts = {row["section_identity"]: row for row in csv.DictReader(handle)}
    rows = []
    for row in payload["population"]:
        identity = row["section_identity"]
        merged = dict(row)
        merged.update({key: value for key, value in receipts.get(identity, {}).items()
                       if key != "section_identity"})
        merged["digest_match"] = int(str(merged.get("digest_match", "")) == "1")
        merged["retained"] = int(str(merged.get("retained", "0")) == "1")
        pod = probes.get(identity, {})
        for name in ("cap_status", "cap_limited_span_s", "available_span_s", "cap_loss_s",
                     "cap_loss_over_5s", "cap_admitted_count", "pts_constant_rate",
                     "cap_frame_cap", "cap_target_s"):
            merged["pod_" + name] = pod.get(name, "UNKNOWN")
        merged["competition"] = merged.get("sport", "")
        merged["canonical_game"] = merged.get("video", "")
        trace_path = out / "raw_traces" / (identity + ".json")
        merged["_trace"] = json.loads(trace_path.read_text(encoding="utf-8"))
        rows.append(bind_rendition(merged))
    return rows, payload
def section_counts(row: dict[str, Any]) -> dict[str, Any]:
    """Sealed-window denominators plus the section-wide admitted-span denominators."""
    trace = row["_trace"]
    window = trace.get("sealed_window", {})
    evaluated = [int(value) for value in trace["evaluated_tick_ids"]]
    suspended = [int(value) for value in trace["suspended_tick_ids"]]
    reason = str(trace.get("schedule_reason") or "")
    status = "KNOWN" if not reason else "UNKNOWN"
    if "sealed_start_frame" not in window:
        sealed = {"schedule_status": status, "schedule_reason": reason,
                  "sealed_window_status": "UNKNOWN_NO_SOURCE"}
        sealed.update({name: "UNKNOWN" for name in
                       ("decoded_source_frames", "attempted_reads", "evaluated_ticks",
                        "suspension_ticks", "held_pairs", "shared_pairs",
                        "zero_output_evaluated_ticks")})
        sealed["raw_overrun_rows"] = "UNKNOWN"
        sealed["derived_out_of_window_rows"] = 0
        return sealed
    start, stop = int(window["sealed_start_frame"]), int(window["sealed_stop_frame"])
    counts = window_counts([0.0] * int(window["sealed_source_frames"]),
                           sorted(evaluated + suspended), evaluated, suspended,
                           trace["sealed_coordinate_rows"], start, stop, status)
    counts.update({"sealed_window_status": "SEALED", "schedule_reason": reason})
    if status != "KNOWN":
        counts.update({name: "UNKNOWN" for name in SCHEDULE_COUNTS})
    counts["raw_overrun_rows"] = trace.get("raw_overrun_rows_outside_sealed_window", "UNKNOWN")
    return counts
def build(out: Path) -> dict[str, Any]:
    """Write every delivered table and return the summary payload."""
    rows, payload = load_rows(out)
    _write(out / "population.csv", rows, [
        "section_identity", "competition", "canonical_game", "section_offset_s", "terminal_utc",
        "fetch_utc", "status", "requested_format_id", "fetch_receipt_status", "retained",
        "retention_status", "rows", "decoded_frames", "evaluated_frames", "stride",
        "source_height", "source_fps", "source_duration", "probe_status", "degenerate",
        "resumed_partial", "repeat_attempts_in_window", "attempt_id"])
    _write(out / "source_format_join.csv", rows, [
        "section_identity", "requested_format_id", "fetch_receipt_status", "pod_sha256",
        "pc_sha256", "digest_match", "probe_agreement", "measured_width", "measured_height",
        "measured_fps", "avg_frame_rate_rational", "r_frame_rate_rational", "codec_name",
        "itag_consistency", "actual_format_id", "actual_rendition", "format_join_status",
        "measured_class", "measured_fps_bin", "source_height", "source_fps"])
    _write(out / "pts.csv", rows, [
        "section_identity", "measured_class", "decoded_pts_count", "first_pts", "last_pts",
        "sealed_start_pts", "sealed_stop_pts", "sealed_start_frame", "sealed_stop_frame",
        "sealed_source_frames", "pod_pts_constant_rate"])
    draw_rows = draw_table(rows)
    _write(out / "draw.csv", draw_rows, ["stratum_system", "stratum", "unique_retained_sections",
                                         "quota", "status", "ordinal", "section_identity"])
    counts_rows, held_rows, coverage_rows = [], [], []
    for row in rows:
        counts = section_counts(row)
        trace, full = row["_trace"], row["_trace"]["full_span_held"]
        known = counts["schedule_status"] == "KNOWN"
        counts_rows.append(dict(counts, section_identity=row["section_identity"],
                                measured_class=row["measured_class"],
                                actual_rendition=row["actual_rendition"]))
        for scope, held, shared, zero in (
                ("FULL_ADMITTED", *(full[name] if known else "UNKNOWN" for name in
                                     ("held_pairs", "shared_pairs", "zero_output_evaluated_ticks"))),
                ("SEALED_2S", counts["held_pairs"], counts["shared_pairs"],
                 counts["zero_output_evaluated_ticks"])):
            held_rows.append({"section_identity": row["section_identity"], "scope": scope,
                              "measured_class": row["measured_class"],
                              "actual_rendition": row["actual_rendition"], "held_pairs": held,
                               "shared_pairs": shared, "zero_output_evaluated_ticks": zero,
                               "held_share": held_share(held, shared)
                               if shared != "UNKNOWN" else "UNKNOWN",
                               "schedule_status": counts["schedule_status"],
                               "schedule_reason": counts["schedule_reason"]})
        coverage_rows.append({
            "section_identity": row["section_identity"], "measured_class": row["measured_class"],
            "status": row["status"], "ledger_decoded_frames": row.get("decoded_frames"),
            "producer_read_frames": trace["producer_read_frames"] if known else "UNKNOWN",
            "evaluated_ticks": trace["evaluated_ticks"] if known else "UNKNOWN",
            "suspended_ticks": trace["suspended_ticks"] if known else "UNKNOWN",
            "ledger_evaluated_frames": row.get("evaluated_frames") if known else "UNKNOWN",
            "verdict_evaluated_frames": trace.get("verdict_evaluated_frames") if known else "UNKNOWN",
            "verdict_attempted_frames_capped": trace.get("verdict_attempted_frames_capped") if known else "UNKNOWN",
            "route_max_frames": trace.get("route_max_frames"),
            "reads_reconcile": ("UNKNOWN" if counts["schedule_status"] != "KNOWN" else
                                int(trace["evaluated_ticks"] + trace["suspended_ticks"]
                                    == trace["producer_read_frames"])),
            "schedule_status": counts["schedule_status"],
            "schedule_reason": counts["schedule_reason"],
            "cap_status": row.get("pod_cap_status", "UNKNOWN"),
            "cap_limited_span_s": row.get("pod_cap_limited_span_s", "UNKNOWN"),
            "available_span_s": row.get("pod_available_span_s", "UNKNOWN"),
            "cap_loss_s": row.get("pod_cap_loss_s", "UNKNOWN"),
            "cap_loss_over_5s": row.get("pod_cap_loss_over_5s", "UNKNOWN"),
            "tracking_rows": trace["tracking_rows"]})
    _write(out / "window_counts.csv", counts_rows, [
        "section_identity", "measured_class", "actual_rendition", "sealed_window_status",
        "decoded_source_frames", "attempted_reads", "evaluated_ticks", "suspension_ticks",
        "zero_output_evaluated_ticks", "held_pairs", "shared_pairs", "raw_overrun_rows",
         "derived_out_of_window_rows", "schedule_status", "schedule_reason"])
    _write(out / "held_pairs.csv", held_rows, [
        "section_identity", "scope", "measured_class", "actual_rendition", "held_pairs",
         "shared_pairs", "held_share", "zero_output_evaluated_ticks", "schedule_status",
         "schedule_reason"])
    _write(out / "coverage.csv", coverage_rows, list(coverage_rows[0]))
    provenance = (stratum_counts(rows, "measured_class") +
                  stratum_counts(rows, "actual_rendition"))
    _write(out / "provenance_counts.csv", provenance, list(provenance[0]))
    cards = render_cards(rows, out)
    _write(out / "eye_index.csv", cards, list(cards[0]))
    _write(out / "launch_receipts.csv", [{
        "launch_id": "NONE", "launches": 0, "scope": "OBSERVATIONAL_CENSUS_ONLY",
        "reason": "no scratch producer launch in this landing; the live GPU is held by the "
                  "ORIGINAL daemon and no competing launch or restart was permitted",
        "verdict": "NOT VALIDATED"}],
        ["launch_id", "launches", "scope", "reason", "verdict"])
    summary = summarize(rows, payload, provenance, draw_rows, held_rows, coverage_rows)
    _json(out / "summary.json", summary)
    with (out / "model_hashes.csv").open(newline="", encoding="utf-8") as handle:
        assets = list(csv.DictReader(handle))
    ops = json.loads((out / "ops_snapshot.json").read_text(encoding="utf-8"))
    _json(out / "route_hashes.json", {
        "scope": "ORIGINAL live producer identity sealed at census UTC",
        "daemon_cmdline": ops.get("daemon_cmdline", "UNKNOWN"),
        "daemon_start_utc": ops.get("daemon_start_utc", "UNKNOWN"),
        "window_start_utc": SELECTOR_UTC, "census_utc": ops.get("census_utc", "UNKNOWN"),
        "routes": [row for row in assets if row["role"] == "route"],
        "models": [row for row in assets if row["role"] == "model"],
        "assets_sealed": len(assets),
        "assets_mtime_before_daemon_start": sum(
            row["mtime_utc"] < str(ops.get("daemon_start_utc", "")) for row in assets),
        "assets_mtime_before_window_start": sum(
            row["mtime_utc"] < SELECTOR_UTC for row in assets),
        "launches_in_this_landing": 0})
    classes = class_summaries(rows, held_rows, coverage_rows, counts_rows)
    _write(out / "class_summaries.csv", classes, list(classes[0]))
    scan_records = ([{key: value for key, value in row.items() if key != "_trace"}
                     for row in rows] + provenance + draw_rows + held_rows + classes +
                    [row for row in cards if row["card_kind"] == "METADATA_CARD"])
    record_scan = q6_scan(scan_records, CLAIM_FIELDS)
    file_scan = q6_scan(scan_files(out, (out.parent / (out.name + ".md"),)), {"text"})
    _json(out / "q6_scan.json", {
        "record_scan": record_scan, "file_scan": file_scan,
        "excluded_self_referential": list(SELF_REFERENTIAL),
        "excluded_reason": "written after this scan; digests, counts and pattern indices only",
        "non_opaque_hits": (len(record_scan["pattern_indices"]) +
                            len(file_scan["pattern_indices"]))})
    return summary
def draw_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply the sealed even draw to both stratum systems; a short stratum draws nothing."""
    out = []
    for system in ("actual_rendition", "measured_class"):
        eligible = [dict(row, actual_rendition=row[system]) for row in rows
                    if row["retained"] == 1]
        selected = even_draw(eligible, QUOTA, 180)
        for stratum in sorted(selected):
            unique = len({row["section_identity"] for row in eligible
                          if row["actual_rendition"] == stratum})
            drawn = selected[stratum]
            if not drawn:
                out.append({"stratum_system": system, "stratum": stratum,
                            "unique_retained_sections": unique, "quota": QUOTA,
                            "status": "PARTIAL", "ordinal": "", "section_identity": ""})
                continue
            for ordinal, row in enumerate(drawn):
                out.append({"stratum_system": system, "stratum": stratum,
                            "unique_retained_sections": unique, "quota": QUOTA,
                            "status": "COMPLETE" if stratum not in RESIDUAL else "PARTIAL", "ordinal": ordinal,
                            "section_identity": row["section_identity"]})
    return out
def summarize(rows: list[dict[str, Any]], payload: dict[str, Any], provenance: list[dict],
              draw_rows: list[dict], held_rows: list[dict],
              coverage: list[dict]) -> dict[str, Any]:
    """Collect the census result without deciding any cause for it."""
    sealed = [row for row in held_rows if row["scope"] == "SEALED_2S" and
              row["schedule_status"] == "KNOWN" and row["shared_pairs"] != "UNKNOWN"]
    full = [row for row in held_rows if row["scope"] == "FULL_ADMITTED" and
            row["schedule_status"] == "KNOWN"]
    losses = [row for row in coverage if row["schedule_status"] == "KNOWN" and
              row["cap_loss_over_5s"] not in ("UNKNOWN", "")]
    return {
        "census_utc": payload.get("census_utc"),
        "window_start_utc": SELECTOR_UTC, "probe_aware_boundary_utc": PROBE_UTC,
        "sections_in_window": len(rows),
        "sections_retained_off_pod": sum(row["retained"] for row in rows),
        "sections_digest_match": sum(row["digest_match"] for row in rows),
        "sections_probe_agree": sum(row.get("probe_agreement") == "AGREE" for row in rows),
        "sections_receipt_bound": sum(row["format_join_status"] == "BOUND" for row in rows),
        "fetch_boundary_counts": boundary_split(rows, SELECTOR_UTC, PROBE_UTC),
        "strata": provenance,
        "admitted_strata_meeting_quota": sorted({row["stratum"] for row in draw_rows
                                                 if row["status"] == "COMPLETE"
                                                 and row["stratum"] not in RESIDUAL}),
        "admitted_strata_partial": sorted({row["stratum"] for row in draw_rows
                                           if row["status"] == "PARTIAL"
                                           and row["stratum"] not in RESIDUAL}),
        "residual_strata": [dict(row) for row in provenance if row["stratum"] in RESIDUAL],
        "held_pairs_full_admitted": sum(int(row["held_pairs"]) for row in full),
        "shared_pairs_full_admitted": sum(int(row["shared_pairs"]) for row in full),
        "held_share_full_admitted": held_share(
            sum(int(row["held_pairs"]) for row in full),
            sum(int(row["shared_pairs"]) for row in full)),
        "held_pairs_sealed_2s": sum(int(row["held_pairs"]) for row in sealed),
        "shared_pairs_sealed_2s": sum(int(row["shared_pairs"]) for row in sealed),
        "held_share_sealed_2s": held_share(
            sum(int(row["held_pairs"]) for row in sealed),
            sum(int(row["shared_pairs"]) for row in sealed)),
        "sections_reads_reconcile": sum(int(row["reads_reconcile"]) for row in coverage
                                          if row["reads_reconcile"] != "UNKNOWN"),
        "sections_reads_reconcile_unknown": sum(row["reads_reconcile"] == "UNKNOWN"
                                                  for row in coverage),
        "sections_schedule_known": sum(row["schedule_status"] == "KNOWN" for row in coverage),
        "sections_schedule_unknown": sum(row["schedule_status"] == "UNKNOWN" for row in coverage),
        "cap_sections_measured": len(losses),
        "cap_sections_loss_over_5s": sum(int(row["cap_loss_over_5s"]) for row in losses),
        "derived_out_of_window_rows": 0,
        "scratch_replay_launches": 0,
    }
def main() -> int:
    parser = argparse.ArgumentParser(description="G407 delivered tables and cards")
    parser.add_argument("--out", required=True)
    parser.add_argument("--sha256sums", action="store_true")
    args = parser.parse_args()
    out = Path(args.out)
    if args.sha256sums:
        print("SHA256SUMS %d" % sha256sums(out))
        return 0
    summary = build(out)
    print("SECTIONS %d RETAINED %d BOUND %d ADMITTED_COMPLETE %d ADMITTED_PARTIAL %d" % (
        summary["sections_in_window"], summary["sections_retained_off_pod"],
        summary["sections_receipt_bound"], len(summary["admitted_strata_meeting_quota"]),
        len(summary["admitted_strata_partial"])))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
