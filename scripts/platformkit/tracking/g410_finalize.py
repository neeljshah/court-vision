"""G410 summary, per-class tables, Q6 scan, repeat receipts and SHA256SUMS."""
from __future__ import annotations
import csv
import hashlib
import json
import statistics
from pathlib import Path
from scripts.platformkit.tracking.g410_measure import (
    MAX_2D_JUMP, PAD, TOPCUT, write_csv,
)
from scripts.platformkit.tracking.g410_q6_scan import scan_paths

CLASSES = ("CLAMP", "SUBPIXEL", "DETECTION", "PREDICTION")
TEXT_SUFFIXES = (".csv", ".json", ".jsonl", ".md", ".txt", ".py", ".sh")
CODE_CITATIONS = [
    ("src/tracking/player_detection.py", 20, "PAD = 15 inflates the stored box on all four sides"),
    ("src/tracking/advanced_tracker.py", 1825, "TOPCUT = 60 crops the decoded frame before detection"),
    ("src/tracking/video_handler.py", 11, "TOPCUT = 60 is defined here and re-exported"),
    ("src/pipeline/unified_pipeline.py", 1693, "frame = frame[TOPCUT:] is the frame handed to the detector"),
    ("src/tracking/advanced_tracker.py", 1336, "stored bbox = (y1-PAD, x1-PAD, y2+PAD, x2+PAD) in cropped pixels"),
    ("src/tracking/advanced_tracker.py", 1410, "head_x = (x1c+x2c)//2 and foot_y = y2c from the clipped unpadded box"),
    ("src/tracking/advanced_tracker.py", 1421, "confident ankle keypoints replace the box foot entirely"),
    ("src/tracking/advanced_tracker.py", 1427, "homo = M1 @ (M @ kpt) then numpy int32 truncation"),
    ("src/tracking/advanced_tracker.py", 1165, "previous_bb is overwritten by the Kalman prediction each tick"),
    ("src/tracking/advanced_tracker.py", 636, "detector clamp keeps the previous court point above MAX_2D_JUMP"),
    ("src/pipeline/unified_pipeline.py", 2032, "pipeline jump_clamp keeps the previous emitted point above 350 px"),
    ("src/pipeline/unified_pipeline.py", 2041, "the emitted row pairs that retained point with p.previous_bb"),
]
def floats(rows: list, key: str) -> list:
    """Return the finite float values of one column."""
    out = []
    for row in rows:
        value = row.get(key, "")
        if value not in ("", None):
            out.append(float(value))
    return out
def quantile(values: list, fraction: float):
    """Return an order statistic without interpolation, empty when absent."""
    if not values:
        return ""
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(fraction * len(ordered)))
    return round(ordered[index], 3)
def staleness_table(per_row: list) -> list:
    """Per-class retention and box-advance counts with full denominators."""
    table = []
    selected = [r for r in per_row if r["role"] == "SELECTED"]
    for label in CLASSES:
        rows = [r for r in selected if r["position_source"] == label]
        paired = [r for r in rows if r["predecessor_status"] == "PRESENT"]
        l2 = floats(paired, "box_l2_px")
        unclipped = floats([r for r in rows
                            if r.get("archived_foot_clipped") == "0"],
                           "stored_box_bottom_minus_projected_foot_px")
        ages = [int(r["retained_position_age"]) for r in paired
                if r["retained_position_age"] != ""]
        table.append({
            "class": label,
            "selected_rows": len(rows),
            "rows_with_predecessor": len(paired),
            "rows_missing_initial_history": len(rows) - len(paired),
            "position_retained": sum(1 for r in paired if r["position_retained"] == "1"),
            "box_moved": sum(1 for r in paired if r["box_moved"] == "1"),
            "position_retained_and_box_moved": sum(
                1 for r in paired
                if r["position_retained"] == "1" and r["box_moved"] == "1"),
            "box_foot_l2_median_px": quantile(l2, 0.5),
            "box_foot_l2_p90_px": quantile(l2, 0.9),
            "box_foot_l2_max_px": quantile(l2, 1.0),
            "retained_position_age_median": quantile([float(a) for a in ages], 0.5),
            "retained_position_age_max": max(ages) if ages else "",
            "distinct_ticks": len(set((r["draw_kind"], r["section_id"], r["frame"])
                                      for r in rows)),
            "rows_foot_clipped": sum(1 for r in rows
                                     if r.get("archived_foot_clipped") == "1"),
            "foot_offset_unclipped_min_px": quantile(unclipped, 0.0),
            "foot_offset_unclipped_median_px": quantile(unclipped, 0.5),
            "foot_offset_unclipped_max_px": quantile(unclipped, 1.0),
        })
    return table
def consistency_table(checks: list) -> list:
    """Per-branch same-invocation projection agreement with full denominators."""
    table = []
    branches = sorted(set(r["derived_branch"] for r in checks))
    for branch in branches:
        rows = [r for r in checks if r["derived_branch"] == branch]
        offsets = floats(rows, "backprojected_minus_archived_foot_y")
        table.append({
            "derived_branch": branch,
            "n": len(rows),
            "position_equals_current_box_projection": sum(
                1 for r in rows if r["position_equals_current_box_projection"] == "1"),
            "classification_consistent": sum(
                1 for r in rows if r["classification"] == "CONSISTENT_BY_CONTRACT"),
            "classification_stale_box": sum(
                1 for r in rows if r["classification"] == "STALE_BOX"),
            "classification_frame_mismatch": sum(
                1 for r in rows if r["classification"] == "FRAME_MISMATCH"),
            "backprojection_inside_stored_box": sum(
                1 for r in rows if r["backprojection_inside_stored_box"] == "1"),
            "backprojected_minus_foot_y_median_px": quantile(offsets, 0.5),
            "distinct_ticks": len(set((r["draw_kind"], r["section_id"], r["frame"])
                                      for r in rows)),
        })
    return table
def coverage_table(draw: list, checks: list, unknowns: list) -> list:
    """Same-invocation coverage of the sealed draw, counted per drawn class."""
    seen: dict = {}
    for row in checks:
        seen.setdefault((row["draw_kind"], row["section_id"], row["frame"]),
                        []).append(row)
    missing: dict = {}
    for row in unknowns:
        missing.setdefault((row["draw_kind"], row["section_id"],
                            str(row["frame"])), set()).add(row["reason"])
    table = []
    for label in ("CLAMP", "SUBPIXEL"):
        ticks = [(d["draw_kind"], d["section_id"], d["frame"]) for d in draw
                 if d["class"] == label]
        covered = [t for t in ticks if t in seen]
        rows = [r for t in covered for r in seen[t]]
        table.append({
            "class": label,
            "drawn_ticks": len(ticks),
            "ticks_with_same_invocation_check": len(covered),
            "same_invocation_rows": len(rows),
            "rows_position_equals_current_box_projection": sum(
                1 for r in rows if r["position_equals_current_box_projection"] == "1"),
            "rows_consistent_by_contract": sum(
                1 for r in rows if r["classification"] == "CONSISTENT_BY_CONTRACT"),
            "rows_stale_box": sum(1 for r in rows
                                  if r["classification"] == "STALE_BOX"),
            "rows_frame_mismatch": sum(1 for r in rows
                                        if r["classification"] == "FRAME_MISMATCH"),
            "rows_branch_mismatch": sum(1 for r in rows if r["classification"] == "BRANCH_MISMATCH"),
            "rows_unknown": sum(1 for r in rows if r["classification"] == "UNKNOWN"),
            "ticks_unknown": len([t for t in ticks if t not in seen]),
            "unknown_reasons": ";".join(sorted(set(
                reason for t in ticks if t not in seen
                for reason in missing.get(t, {"NO_OBSERVER_REPLAY_TRACE"})))),
        })
    return table
def launch_receipts(out: Path) -> list:
    """Convert the driver's per-launch TSV receipts into the delivered JSON."""
    path = out / "runtime_receipts" / "launch_receipts.tsv"
    if not path.exists():
        return []
    fields = ("draw_kind", "section_id", "status", "vram_free_mib_before",
              "seconds", "trace_bytes", "route_digest_before", "route_digest_after")
    records = []
    for line in path.read_text(encoding="ascii").splitlines():
        if not line.strip():
            continue
        parts = line.split(chr(9))
        record = dict(zip(fields, parts + [""] * (len(fields) - len(parts))))
        record["pre_launch_identity"] = ("COMPLETE" if record["route_digest_before"]
                                         else "ABSENT")
        records.append(record)
    (out / "launch_receipts.json").write_text(
        json.dumps({"launches": records,
                    "route_digest_unchanged": all(
                        r["route_digest_before"] == r["route_digest_after"]
                        and r["route_digest_before"] != "" for r in records),
                    "pre_launch_identity_complete": all(
                        r["pre_launch_identity"] == "COMPLETE" for r in records),
                    "pre_launch_identity_complete_count": "%d/%d" % (
                        sum(r["pre_launch_identity"] == "COMPLETE" for r in records),
                        len(records)),
                    "digest_domain": ("sha256 of the LF sha256sum listing of "
                                      "unified_pipeline.py, advanced_tracker.py, "
                                      "player_detection.py and run_clip.py in the "
                                      "read-only deploy tree")},
                   indent=2, sort_keys=True) + chr(10),
        encoding="ascii", newline="")
    return records
def digests(root: Path) -> dict:
    """SHA-256 of every delivered file below the evidence root, POSIX-keyed."""
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path != root / "SHA256SUMS":
            out[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()).hexdigest()
    return out
def read_csv(path: Path) -> list:
    """Read one delivered table, or an empty list when it was not produced."""
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="ascii") as handle:
        return list(csv.DictReader(handle))
def main(out_dir: str) -> None:
    """Write the per-class tables, summary, Q6 scan and SHA256SUMS."""
    out = Path(out_dir)
    per_row = read_csv(out / "per_row.csv")
    checks = read_csv(out / "contract_checks.csv")
    unknowns = read_csv(out / "unknowns.csv")
    draw = read_csv(out / "draw.csv")
    trace_receipts = read_csv(out / "runtime_receipts" / "trace_receipts.csv")
    population = read_csv(out / "population.csv")
    launches = launch_receipts(out)
    pre_identity_count = sum(r["pre_launch_identity"] == "COMPLETE" for r in launches)
    stale = staleness_table(per_row)
    consistent = consistency_table(checks)
    coverage = coverage_table(draw, checks, unknowns)
    write_csv(out / "staleness_by_class.csv", stale)
    write_csv(out / "consistency_by_branch.csv", consistent)
    write_csv(out / "consistency_by_class.csv", coverage)
    (out / ".gitattributes").write_text(
        "# Evidence bytes are verbatim: digests in SHA256SUMS must verify.\n"
        "* -text\n", encoding="ascii", newline="")
    premise_path = out / "premise.json"
    premise = (json.loads(premise_path.read_text(encoding="ascii"))
               if premise_path.exists() else {})
    summary = {
        "row": "G410",
        "premise": premise,
        "archived_constants": {"PAD": PAD, "TOPCUT": TOPCUT,
                               "MAX_2D_JUMP": MAX_2D_JUMP,
                               "pipeline_jump_clamp_px": 350},
        "code_citations": [{"path": a, "line": b, "fact": c}
                           for a, b, c in CODE_CITATIONS],
        "population": {row["class"]: int(row["population_n"])
                       for row in population},
        "draw": {"ticks_per_class": 30, "drawn_rows": len(draw),
                 "formula": "floor(j*(N-1)/29+0.5)"},
        "landed_rows_at_selected_ticks": len(
            [r for r in per_row if r["role"] == "SELECTED"]),
        "predecessor_rows_retained": len(
            [r for r in per_row if r["role"] == "PREDECESSOR"]),
        "staleness_by_class": stale,
        "same_invocation_checks": len(checks),
        "classification_counts": {name: sum(1 for row in checks
                                               if row["classification"] == name)
                                  for name in ("CONSISTENT_BY_CONTRACT", "FRAME_MISMATCH",
                                               "STALE_BOX", "BRANCH_MISMATCH", "UNKNOWN")},
        "pre_launch_identity_complete": pre_identity_count == len(launches),
        "pre_launch_identity_complete_count": "%d/%d" % (pre_identity_count, len(launches)),
        "consistency_by_branch": consistent,
        "consistency_by_class": coverage,
        "emitted_vs_tracker_position": {
            "sections": len(trace_receipts),
            "emitted_rows_compared": sum(int(r["emitted_rows_compared"])
                                         for r in trace_receipts),
            "emitted_differs_from_tracker_position": sum(
                int(r["emitted_differs_from_tracker_position"])
                for r in trace_receipts),
            "meaning": ("a difference is the pipeline jump_clamp replacing the "
                        "tick's own court point inside ONE observed run"),
        },
        "unknown_rows": len(unknowns),
        "unknown_reasons": {reason: sum(1 for r in unknowns if r["reason"] == reason)
                            for reason in sorted(set(r["reason"] for r in unknowns))},
        "coordinate_frame": {
            "declared_input_frame": "TOPCUT-cropped decoded pixels",
            "crop_origin_x": 0, "crop_origin_y": TOPCUT,
            "stored_box_frame": "same cropped pixels as the projected foot",
            "court_map_units": "pixels of the rectified court-map image",
        },
    }
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="ascii", newline="")
    paths = [p for p in sorted(out.rglob("*"))
             if p.is_file() and p.suffix in TEXT_SUFFIXES]
    paths += [Path("scripts/platformkit/tracking/g410_q6_scan.py"),
              Path("scripts/platformkit/tracking/g410_contract.py"),
              Path("scripts/platformkit/tracking/g410_prepare.py"),
              Path("scripts/platformkit/tracking/g410_measure.py"),
              Path("scripts/platformkit/tracking/g410_report.py"),
              Path("scripts/platformkit/tracking/g410_render.py"),
              Path("scripts/platformkit/tracking/g410_finalize.py"),
              Path("scripts/platformkit/tracking/g410_sources.py"),
              Path("scripts/platformkit/tracking/g410_bound_trace.py"),
              Path("scripts/platformkit/tracking/g410_repeats.py"),
              Path("scripts/platformkit/tracking/g410_trace_hook_sitecustomize.py"),
              Path("scripts/platformkit/tracking/g410_replay_driver.sh"),
              Path("tests/platformkit/test_g410_position_box_frame_consistency.py"),
               Path("docs/evidence/tracking/g410_position_box_frame_consistency_2026-09-12.md"),
               Path("docs/evidence/tracking/G410_VERIFY_att1_REJECT_2026-09-11.md"), Path("docs/evidence/tracking/G410_VERIFY_fix1b_ACCEPT_WITH_CORRECTIONS_2026-09-11.md"),
               Path("docs/evidence/tracking/RESULTS_LEDGER.md"), Path(".pytest_tmp_g410/test_parse_trace_reads_matrice0/t.trace.txt"), out / "SHA256SUMS", out / "pre_fix1b" / "SHA256SUMS"]
    paths = [p for p in paths if p.exists()]
    scan = scan_paths(paths)
    (out / "q6_scan.json").write_text(
        json.dumps({"pattern_count": 4, "emits": "pattern_index_to_count_only",
                    "paths": {k.replace("\\", "/"): v for k, v in scan.items()}},
                   indent=2, sort_keys=True) + "\n",
        encoding="ascii", newline="")
    table = digests(out)
    lines = ["# BYTE DOMAIN: SHA-256 of each file's bytes exactly as committed",
             "# (LF text, binary renders verbatim); verify from this directory",
             "# with: sha256sum -c SHA256SUMS"]
    lines += ["%s  %s" % (value, key) for key, value in sorted(table.items())]
    (out / "SHA256SUMS").write_text("\n".join(lines) + "\n",
                                    encoding="ascii", newline="")
    print("staleness=%d consistency=%d files=%d"
          % (len(stale), len(consistent), len(table)))
if __name__ == "__main__":
    import sys
    main(sys.argv[1])
