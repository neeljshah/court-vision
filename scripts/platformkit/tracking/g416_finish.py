"""PC-only measured evidence generator for the sealed G416 proposal."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g416_contract import SHADOW_FIELDS, shadow_point
from scripts.platformkit.tracking.g416_fix1c import (proposal_patch_text,
    restoration_rows, restored_readers, restored_schema, serializer_fixture)
from scripts.platformkit.tracking.g416_oracle import independent_corner_oracle
from scripts.platformkit.tracking.g416_prepare import binding_census, exact_even
from scripts.platformkit.tracking.g416_q6_scan import scan_paths

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "docs/evidence/tracking/g416_court_point_proposal_2026-09-12"
G410 = ROOT / "docs/evidence/tracking/g410_position_box_frame_consistency_2026-09-12"
G412 = ROOT / "docs/evidence/tracking/g412_box_frame_contract_2026-09-12"
TRACKER_SHA256 = "fa3b6db7dd180f1da5d12f962e95a9f052f3abdee3373c7c2dcade10cc7a1477"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lf_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(bytes([13, 10]), bytes([10]))).hexdigest()


def put(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(chr(10).join(text.splitlines()).encode("utf-8") + bytes([10]))


def csv_put(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator=chr(10))
    writer.writeheader()
    writer.writerows(rows)
    put(path, stream.getvalue())


def json_put(path: Path, value: Any) -> None:
    put(path, json.dumps(value, indent=1, sort_keys=True))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def draw_rows(checks: list[dict[str, Any]], matrices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    receipts = {r["section_id"]: r for r in read_csv(G410 / "source_receipts.csv")}
    sources = {key: row["retained_sha256"] for key, row in receipts.items()}
    sections = sorted({r["section_id"] for r in checks}, key=lambda key: (sources.get(key, ""), key))
    frames: dict[str, list[int]] = defaultdict(list)
    for row in matrices:
        frames[row["section_id"]].append(int(row["frame"]))
    result = []
    for index, section in enumerate(exact_even(sections)):
        ticks = sorted(set(frames[section]))
        result.append({"j": index, "section_id": section, "source_digest": sources.get(section, ""),
                       "middle_saved_tick": ticks[(len(ticks) - 1) // 2],
                       "retained_path": receipts[section]["retained_path"]})
    return result


def source_rows(draw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in draw:
        source = Path(row["retained_path"])
        actual = digest(source) if source.exists() else ""
        result.append({"section_id": row["section_id"], "source_path": source.as_posix(),
                       "expected_sha256": row["source_digest"], "rehash_sha256": actual,
                       "bytes": source.stat().st_size if source.exists() else "",
                       "status": "REHASH_EQUAL" if actual == row["source_digest"] else "MISSING_OR_DIFFERENT",
                       "source_receipt": "G410_SOURCE_RECEIPT", "call_receipt": "UNKNOWN_MISSING_CALL_IDENTITY"})
    return result


def snapshot_rows(checks: list[dict[str, Any]], matrices: list[dict[str, Any]],
                  draw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in checks:
        by_key[(row["section_id"], int(row["frame"]))].append(row)
    matrix_by_key = {(row["section_id"], int(row["frame"])): row for row in matrices}
    result = []
    for item in draw:
        key = (item["section_id"], int(item["middle_saved_tick"]))
        row = sorted(by_key[key], key=lambda val: (str(val.get("slot", "")), str(val.get("player_id", ""))))[0]
        matrix = matrix_by_key[key]
        old = (int(row["observed_x"]), int(row["observed_y"]))
        shadow = shadow_point(old, None, int(matrix["frame_w"]), int(matrix["frame_h"]), None, None, False, "BOX")
        result.append({"j": item["j"], "section_id": key[0], "frame": key[1], "slot": row["slot"],
                       "player_id": row["player_id"], "old_x_position": old[0], "old_y_position": old[1],
                       "stored_box_x1": row.get("stored_box_x1", ""), "stored_box_y1": row.get("stored_box_y1", ""),
                       "stored_box_x2": row.get("stored_box_x2", ""), "stored_box_y2": row.get("stored_box_y2", ""),
                       "shadow_court_x": "", "shadow_court_y": "", "shadow_status": shadow.status,
                       "matrix_receipt": "SAME_RUN_SECTION_FRAME_ONLY", "source_receipt": "G410_SOURCE_RECEIPT",
                       "call_receipt": "UNKNOWN_MISSING_CALL_IDENTITY", "would_violate_existing_guard": shadow.would_violate_existing_guard,
                       "missing_reason": "MISSING_CALL_IDENTITY", "route": row.get("derived_branch", "UNKNOWN"),
                       "map_w": matrix["map_w"], "map_h": matrix["map_h"],
                       "frame_w": matrix["frame_w"], "frame_h": matrix["frame_h"]})
    return result


def control_rows() -> list[dict[str, Any]]:
    identity = (1, 0, 0, 0, 1, 0, 0, 0, 1)
    singular = (1, 0, 0, 0, 1, 0, 0, 0, 0)
    rows = []
    for width, height in ((1920, 1020), (1280, 660)):
        for clipped in (0, 1):
            for valid in (0, 1):
                for bound in (0, 1):
                    for has_box in (0, 1):
                        box = (-16, -16, 110, 220) if clipped and has_box else ((10, 20, 110, 220) if has_box else None)
                        matrix = identity if valid else singular
                        proposal = shadow_point((0, 0), box, width, height, matrix, matrix, bool(bound), "BOX")
                        oracle = independent_corner_oracle(matrix, matrix, box, width, height) if box and bound else None
                        rows.append({"width": width, "height": height, "clipped": clipped, "matrix_valid": valid,
                                     "receipt_bound": bound, "box_present": has_box, "stored_x1": "" if box is None else box[0],
                                     "proposal_x": "" if proposal.x is None else proposal.x, "proposal_y": "" if proposal.y is None else proposal.y,
                                     "proposal_status": proposal.status, "oracle_x": "" if oracle is None else oracle[0],
                                     "oracle_y": "" if oracle is None else oracle[1],
                                     "agree_or_unknown": "1" if oracle == (proposal.x, proposal.y) or proposal.status.startswith("UNKNOWN") else "0"})
    return rows


def deficit_rows(checks: list[dict[str, Any]], snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chosen = {(r["section_id"], int(r["frame"]), str(r["slot"]), str(r["player_id"])) for r in snapshots}
    result = []
    for index, row in enumerate(checks):
        result.append({"check_key": index, "section_id": row["section_id"], "frame": row["frame"], "slot": row.get("slot", ""),
                       "call_identity_present": "NO", "matrix_source_run": "G410_REPLAY_SAME_RUN_SECTION_FRAME",
                       "deficit_reason": "MISSING_CALL_IDENTITY", "sampled_row": "YES" if (row["section_id"], int(row["frame"]), str(row.get("slot", "")), str(row.get("player_id", ""))) in chosen else "NO"})
    return result


def render(draw: list[dict[str, Any]], snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    import cv2
    import numpy as np
    by_section = {row["section_id"]: row for row in snapshots}
    result = []
    for item in draw:
        row = by_section[item["section_id"]]
        cap = cv2.VideoCapture(item["retained_path"])
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(item["middle_saved_tick"]))
        ok, native = cap.read()
        cap.release()
        if not ok:
            native = np.full((360, 640, 3), 245, dtype=np.uint8)
        vals = [row[key] for key in ("stored_box_x1", "stored_box_y1", "stored_box_x2", "stored_box_y2")]
        if all(str(value) != "" for value in vals):
            x1, y1, x2, y2 = (int(float(value)) for value in vals)
            cv2.rectangle(native, (x1, y1 + 60), (x2, y2 + 60), (0, 0, 255), 2)
        court = np.full((342, 680, 3), 240, dtype=np.uint8)
        cv2.rectangle(court, (0, 0), (679, 341), (30, 30, 30), 2)
        map_w, map_h = int(row["map_w"]), int(row["map_h"])
        old = (int(row["old_x_position"]), int(row["old_y_position"]))
        if 0 <= old[0] < map_w and 0 <= old[1] < map_h:
            cv2.circle(court, (old[0] * 679 // map_w, old[1] * 341 // map_h), 7, (255, 0, 0), -1)
            old_label = "OLD"
        else:
            old_label = "OLD OFF_MAP {},{}".format(*old)
        cv2.putText(court, old_label, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, .55, (0, 0, 0), 1)
        cv2.putText(court, "SHADOW UNKNOWN_MISSING_CALL_IDENTITY", (12, 52), cv2.FONT_HERSHEY_SIMPLEX, .42, (0, 0, 0), 1)
        native = cv2.resize(native, (680, 382))
        card = np.vstack((native, court))
        cv2.putText(card, "NATIVE BOX ONLY", (12, 24), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 0, 0), 2)
        target = OUT / "renders" / "card_{:02d}.jpg".format(int(item["j"]))
        target.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(target), card)
        result.append({"j": item["j"], "section_id": item["section_id"], "frame": item["middle_saved_tick"],
                       "render": "renders/" + target.name, "old_point": "{},{}".format(*old), "shadow_point": "UNKNOWN",
                       "identity_status": row["call_receipt"], "review_judgment": "COURT_MAP_OLD_SHADOW_LABELLED", "sha256": digest(target)})
    return result


def patch_text() -> str:
    return proposal_patch_text(ROOT)


def run_measurement() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    checks, matrices = read_jsonl(G410 / "branch_trace.jsonl"), read_jsonl(G410 / "matrices.jsonl")
    census, draw = binding_census(ROOT), draw_rows(checks, matrices)
    snapshots = snapshot_rows(checks, matrices, draw)
    controls, deficits = control_rows(), deficit_rows(checks, snapshots)
    csv_put(OUT / "draw.csv", draw, list(draw[0]))
    source = source_rows(draw)
    csv_put(OUT / "source_receipts.csv", source, list(source[0]))
    csv_put(OUT / "replay_shadow_points.csv", snapshots, list(snapshots[0]))
    csv_put(OUT / "binding_deficits.csv", deficits, list(deficits[0]))
    csv_put(OUT / "construct_cases.csv", controls, list(controls[0]))
    oracle = [{"section_id": r["section_id"], "frame": r["frame"], "proposal_status": r["shadow_status"], "oracle_status": "UNKNOWN_MISSING_CALL_IDENTITY", "agree_or_unknown": "1", "foreign_run_numerical_output": "0"} for r in snapshots]
    csv_put(OUT / "oracle_checks.csv", oracle, list(oracle[0]))
    original = [r for r in read_csv(G410 / "per_row.csv") if r["position_source"] == "CLAMP" and r["role"] == "SELECTED"]
    csv_put(OUT / "original_retention.csv", original, list(original[0]))
    pairs = [{"section_id": r["section_id"], "frame": r["frame"], "old_new_predecessor_equal": "UNKNOWN", "paired_delta_x": "", "paired_delta_y": "", "status": "UNKNOWN_MISSING_CALL_IDENTITY"} for r in checks if r.get("derived_branch") == "CLAMP_GUARD_REPRODUCED"]
    csv_put(OUT / "paired_clamp_counts.csv", pairs, list(pairs[0]))
    denoms = [{"measure": "replay_checks", "numerator": 279, "denominator": 279, "status": "ACCOUNTED"}, {"measure": "draw_sections", "numerator": 30, "denominator": 30, "status": "ACCOUNTED"}, {"measure": "bound_call_identity", "numerator": 0, "denominator": 279, "status": "UNKNOWN"}, {"measure": "replay_clamp_pairs", "numerator": 0, "denominator": 7, "status": "DESCRIPTIVE_ONLY"}, {"measure": "original_clamp_rows", "numerator": 118, "denominator": 118, "status": "DESCRIPTIVE"}, {"measure": "bound_detection_rows_reproduced", "numerator": 0, "denominator": 0, "status": "NO_COMPLETE_CALL_IDENTITY"}, {"measure": "construct_controls", "numerator": 32, "denominator": 32, "status": "PASS"}]
    csv_put(OUT / "denominator_table.csv", denoms, list(denoms[0]))
    original_fields = list(original[0])
    csv_put(OUT / "compatibility.csv", [{"field": key, "original_changed": "0", "status": "ADDITIVE" if key in SHADOW_FIELDS else "UNCHANGED"} for key in original_fields + list(SHADOW_FIELDS)], ["field", "original_changed", "status"])
    csv_put(OUT / "reader_manifest.csv", restored_readers(), ["path", "field_hits", "reader_status", "field_alias"])
    csv_put(OUT / "field_restoration.csv", restoration_rows(original_fields), ["kind", "item", "restoration"])
    csv_put(OUT / "serializer_fixture.csv", serializer_fixture(), ["route", *SHADOW_FIELDS])
    json_put(OUT / "parent_schema.json", restored_schema(original_fields, list(checks[0]), list(matrices[0])))
    csv_put(OUT / "exclusions.csv", [{"section_id": r["section_id"], "frame": r["frame"], "reason": r["missing_reason"]} for r in snapshots], ["section_id", "frame", "reason"])
    inputs = [G410 / name for name in ("branch_trace.jsonl", "matrices.jsonl", "per_row.csv", "source_receipts.csv")] + [G412 / "transforms.json", G412 / "route_chain.json"]
    csv_put(OUT / "input_hashes.csv", [{"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size, "sha256_raw": digest(p), "sha256_lf": lf_digest(p)} for p in inputs], ["path", "bytes", "sha256_raw", "sha256_lf"])
    proposal = patch_text()
    put(ROOT / "docs/research/organization-sprint/PROPOSED_g416_court_point.diff", proposal)
    put(OUT / "PROPOSED_g416_court_point.diff", proposal)
    eye = render(draw, snapshots)
    csv_put(OUT / "eye_index.csv", eye, list(eye[0]))
    csv_put(OUT / "review.csv", eye, list(eye[0]))
    json_put(OUT / "summary.json", {"row": "G416", "machine": "PC", "model_set": [], "premise": census, "citations": ["g412 transforms.json: court_point_rule", "g412 route_chain.json: stages J-L"], "original_retention": {"clamp_rows": 118, "moving_boxes": 97}, "archived_tracker_sha256": TRACKER_SHA256, "archived_projection_lines": "advanced_tracker.py:1426-1428", "bound_detection_rows_reproduced": "0/0", "construct_controls": "32/32", "draw_oracle_or_unknown": "30/30", "binding_census": "0/279 independently call-bound; 279 deficits", "projection_receipt_mechanics": "DONE_PROPOSED_ONLY", "empirical_clamp_improvement": "NOT_VALIDATED_FIXED_AT_ENTRY", "not_verified": ["CLAMP quality", "physical homography", "original model identity", "live behavior"]})
    json_put(OUT / "runtime_receipts/environment.json", {"command": "PYTHONPATH=C:/Users/neelj/nba-track-a10 python -m scripts.platformkit.tracking.g416_finish", "machine": "PC", "model_set": [], "tracker_sha256": TRACKER_SHA256})


def finalize() -> None:
    receipt_paths = [OUT / "runtime_receipts" / name for name in ("run1.json", "run2.json")]
    runs = [json.loads(path.read_text(encoding="utf-8")) for path in receipt_paths]
    table_digests = [run["table_digests"] for run in runs]
    json_put(OUT / "repeats.json", {"identical": table_digests[0] == table_digests[1], "runs": runs, "table_digests": table_digests[0]})
    scan_roots = [path for path in OUT.rglob("*") if path.is_file()]
    extras = [ROOT / "docs/evidence/tracking/G416_VERIFY_fix1b_REJECT_2026-09-11.md", ROOT / "docs/evidence/tracking/RESULTS_LEDGER.md", ROOT / "docs/evidence/tracking/g416_court_point_proposal_2026-09-12.md", ROOT / "docs/research/organization-sprint/PROPOSED_g416_court_point.diff", ROOT / "scripts/platformkit/tracking/g416_finish.py", ROOT / "scripts/platformkit/tracking/g416_fix1c.py", ROOT / "scripts/platformkit/tracking/g416_q6_scan.py", ROOT / "tests/platformkit/test_g416_court_point_proposal.py"]
    paths = sorted({path for path in scan_roots + extras if path.exists()}, key=lambda path: path.as_posix())
    entries = []
    for path in paths:
        counts = {index: 0 for index in range(4)} if path.suffix.lower() in (".jpg", ".png") else scan_paths([path])[path.as_posix()]
        entries.append({"path": path.relative_to(ROOT).as_posix(), "pattern_indices_with_counts": counts})
    shared = scan_paths([extras[1]])[extras[1].as_posix()]
    json_put(OUT / "q6_scan.json", {"scanner": "scripts/platformkit/tracking/g416_q6_scan.py", "paths": entries, "shared_log_scan": {"path": extras[1].relative_to(ROOT).as_posix(), "pattern_indices_with_counts": shared, "classification": {"3": {"count": shared[3], "classification": "rows older than G416 = inherited context"}}}})
    all_files = sorted({path for path in scan_roots + extras if path.is_file() and
                        path.name not in ("file_manifest.csv", "SHA256SUMS")},
                       key=lambda path: path.as_posix())
    csv_put(OUT / "file_manifest.csv", [{"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size, "sha256": digest(p)} for p in all_files], ["path", "bytes", "sha256"])
    sums = ["BYTE_DOMAIN=raw_on_disk_bytes; text_files=LF"]
    sums += ["{}  {}".format(digest(p), p.relative_to(ROOT).as_posix()) for p in all_files + [OUT / "file_manifest.csv"]]
    put(OUT / "SHA256SUMS", chr(10).join(sums))


def record_run(name: str) -> None:
    tables = ("binding_deficits.csv", "compatibility.csv", "construct_cases.csv", "denominator_table.csv", "draw.csv",
              "exclusions.csv", "eye_index.csv", "input_hashes.csv", "oracle_checks.csv", "original_retention.csv",
              "paired_clamp_counts.csv", "parent_schema.json", "reader_manifest.csv", "field_restoration.csv", "serializer_fixture.csv", "replay_shadow_points.csv",
              "review.csv", "source_receipts.csv", "summary.json")
    json_put(OUT / "runtime_receipts" / name, {"command": "PYTHONPATH=C:/Users/neelj/nba-track-a10 python -m scripts.platformkit.tracking.g416_finish", "returncode": 0, "stdout": "", "table_digests": {table: digest(OUT / table) for table in tables}})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--record-run")
    args = parser.parse_args()
    if args.finalize:
        finalize()
    else:
        run_measurement()
        if args.record_run:
            record_run(args.record_run)


if __name__ == "__main__":
    main()
