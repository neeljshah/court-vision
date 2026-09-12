"""Assemble the delivered G409 evidence directory from the sealed inputs.

Run twice in fresh processes to populate repeats.json; the delivered tables are
byte-identical across runs because nothing here samples or fits.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from scripts.platformkit.tracking import g409_build as B
from scripts.platformkit.tracking import g409_blind as BL
from scripts.platformkit.tracking import g409_construct as C
from scripts.platformkit.tracking.g409_audit import field_scan

OUT = B.OUT
TOPCUT = B.TOPCUT

TRANSFORMS = {
    "route": "scripts/run_clip.py -> src/pipeline/unified_pipeline.py (UnifiedPipeline)",
    "archived_tree": "/workspace/deploy/nba-ai-system @ 7eb25dc (read only)",
    "stages": [
        {"stage": "A_decode_native", "site": "src/pipeline/unified_pipeline.py:1686",
         "transform": "identity", "frame_space": "native", "evidence": "observer crop.native.shape"},
        {"stage": "B_topcut_crop", "site": "src/pipeline/unified_pipeline.py:1693",
         "statement": "frame = frame[TOPCUT:]", "constant": "TOPCUT = 60 "
                      "(src/tracking/video_handler.py:11)",
         "transform": "native_y -> native_y - 60; x unchanged", "frame_space": "cropped",
         "evidence": "observer crop.post_crop.shape height = native height - 60"},
        {"stage": "C_detector_input", "site": "src/pipeline/unified_pipeline.py:1917",
         "statement": "self.feet_det.get_players_pos(M, self.M1, frame, frame_idx, ...)",
         "transform": "identity on the cropped array", "frame_space": "cropped",
         "evidence": "the cropped array hashed at stage B is the argument"},
        {"stage": "C2_prefetch_cache", "site": "src/pipeline/unified_pipeline.py:1909",
         "statement": "_pf_list = [f[TOPCUT:] for f in _peek_frames]",
         "transform": "native_y -> native_y - 60", "frame_space": "cropped",
         "evidence": "the prefetched cache is cropped by the same constant"},
        {"stage": "D_tracker_store", "site": "src/tracking/advanced_tracker.py:626",
         "statement": "p.previous_bb = det[\"bbox\"]",
         "transform": "identity; tuple order (y1, x1, y2, x2)", "frame_space": "cropped",
         "evidence": "observer detector_box records"},
        {"stage": "D2_kalman_predict", "site": "src/tracking/advanced_tracker.py:1165",
         "statement": "self.players[slot].previous_bb = self._kf_pred[slot]",
         "transform": "identity", "frame_space": "cropped",
         "evidence": "PREDICTION rows carry the same frame space"},
        {"stage": "E_export_read", "site": "src/pipeline/unified_pipeline.py:2702",
         "statement": "bbox = track[\"bbox\"]  # stored as (y1, x1, y2, x2)",
         "transform": "identity", "frame_space": "cropped",
         "evidence": "observer export.bbox"},
        {"stage": "E2_off_frame_guard", "site": "src/pipeline/unified_pipeline.py:2703",
         "statement": "UnifiedPipeline._bbox_off_frame(bbox, frame.shape[1], frame.shape[0])",
         "transform": "bounds taken from the CROPPED frame", "frame_space": "cropped",
         "evidence": "observer export.export_frame_shape height = native height - 60"},
        {"stage": "F_csv_serialize", "site": "src/pipeline/unified_pipeline.py:2736-2739",
         "statement": "bbox_x1=bbox[1]; bbox_y1=bbox[0]; bbox_x2=bbox[3]; bbox_y2=bbox[2]",
         "transform": "yxyx -> xyxy tuple reorder ONLY; no uncrop is applied",
         "frame_space": "cropped", "erroneous_boundary": True,
         "evidence": "observer export.serialized equals the CSV row"},
        {"stage": "G_g402_window_join", "site": "docs/evidence/tracking/"
                                                "g402_mixed_provenance_target_mask_2026-09-11",
         "transform": "identity on coordinates; native_width/native_height recorded as NATIVE",
         "frame_space": "cropped values labelled with native dimensions",
         "evidence": "export_join.csv coordinates_equal"},
        {"stage": "H_g406_comparator", "site": "docs/evidence/tracking/"
                                               "g406_masked_target_pixel_audit_2026-09-11",
         "transform": "identity; detections computed on the NATIVE decoded PNG",
         "frame_space": "native",
         "evidence": "frame_receipts.csv decoded_height equals the native height"},
    ],
    "declared_inverse": {
        "expression": "native_x = stored_x; native_y = stored_y + TOPCUT",
        "topcut": TOPCUT,
        "fitted": False,
        "exact_when": "the native box lies fully below the crop line (native y1 >= 60)",
        "lossy_when": "the native box straddles y = 60; the crop clips it and y1 "
                      "cannot be recovered",
    },
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_stage_trace(replay_dir: Path) -> tuple[list[dict], dict]:
    records, accounting = [], {"windows_with_observations": 0, "windows_absent": 0,
                               "ticks_observed": 0, "crop_records": 0, "export_records": 0,
                               "detector_records": 0, "topcut_values": {}, "shape_pairs": {}}
    draw = {(r["section_id"], int(r["frame"])): r for r in B.build_draw()}
    for key in sorted({"%s__%s" % (r["draw_kind"], r["section_id"]) for r in B.build_draw()}):
        path = replay_dir / (key + ".jsonl")
        if not path.exists() or not path.stat().st_size:
            accounting["windows_absent"] += 1
            continue
        accounting["windows_with_observations"] += 1
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            rec["window_key"] = key
            section = key.split("__", 1)[1]
            frame = rec.get("frame", rec.get("timestamp"))
            rec["sealed_tick"] = (section, frame) in draw
            if rec["stage"] == "crop":
                accounting["crop_records"] += 1
                accounting["topcut_values"][str(rec["topcut"])] = \
                    accounting["topcut_values"].get(str(rec["topcut"]), 0) + 1
                pair = "%s->%s" % (rec["native"]["shape"], rec["post_crop"]["shape"])
                accounting["shape_pairs"][pair] = accounting["shape_pairs"].get(pair, 0) + 1
            elif rec["stage"] == "export":
                accounting["export_records"] += 1
            else:
                accounting["detector_records"] += 1
            records.append(rec)
    accounting["ticks_observed"] = len({(r["window_key"], r.get("frame"))
                                        for r in records if r["stage"] == "crop"})
    replay: dict[tuple, set] = {}
    for rec in records:
        if rec["stage"] != "export" or not rec["bbox"]:
            continue
        key = (rec["window_key"].split("__", 1)[1], rec["frame"])
        box = tuple(rec["serialized"][k] for k in ("bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"))
        replay.setdefault(key, set()).add(box)
    stored_rows = B.read_csv(B.G406 / "all_masked_rows.csv")
    exact = 0
    for row in stored_rows:
        key = (row["section_id"], int(row["frame"]))
        box = tuple(float(row["bbox_" + k]) for k in ("x1", "y1", "x2", "y2"))
        exact += int(box in replay.get(key, set()))
    accounting["replay_export_rows_at_sealed_ticks"] = sum(len(v) for v in replay.values())
    accounting["stored_rows_exactly_reproduced_by_replay"] = exact
    accounting["stored_rows"] = len(stored_rows)
    accounting["historical_inference_equality"] = "UNKNOWN"
    accounting["note"] = ("the replay binds the executed frame contract at every sealed tick; "
                          "it is not expected to reproduce the historical box values because "
                          "the pod library stack has moved since the G402 run")
    return records, accounting


def build_renders() -> list[dict]:
    by_card = BL.render_rows()
    rows = []
    for card in sorted(by_card):
        frame_path = BL.frame_path(card)
        target = OUT / "renders" / (card + ".jpg")
        if not frame_path.exists():
            rows.append({"card_id": card, "render_path": "", "render_bytes": "",
                         "render_sha256": "ABSENT-IN-WORKTREE",
                         "stored_boxes": len(by_card[card]["stored"]),
                         "comparator_boxes": len(by_card[card]["comparator"]),
                         "status": "ABSENT_FRAME"})
            continue
        size, digest = C.render_card(frame_path, target, by_card[card]["stored"],
                                     by_card[card]["mapped"], by_card[card]["comparator"])
        rows.append({"card_id": card, "render_path": "renders/" + card + ".jpg",
                     "render_bytes": size, "render_sha256": digest,
                     "stored_boxes": len(by_card[card]["stored"]),
                     "comparator_boxes": len(by_card[card]["comparator"]), "status": "OK"})
    return rows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    replay = B.ROOT / ".g409_rep"

    inputs = B.build_input_hashes()
    B.write_csv(OUT / "input_hashes.csv", inputs, list(inputs[0]))
    sources = B.build_source_receipts()
    B.write_csv(OUT / "source_receipts.csv", sources, list(sources[0]))
    draw = B.build_draw()
    B.write_csv(OUT / "draw.csv", draw, list(draw[0]))
    residuals, geometry = B.build_residuals()
    B.write_csv(OUT / "residuals.csv", residuals, list(residuals[0]))
    ticks = B.build_tick_accounting()
    B.write_csv(OUT / "tick_accounting.csv", ticks, list(ticks[0]))
    joins = B.build_export_join()
    B.write_csv(OUT / "export_join.csv", joins, list(joins[0]))
    cases = C.construct_cases()
    C.write_csv(OUT / "construct_cases.csv", cases, list(cases[0]))

    (OUT / "transforms.json").write_text(
        json.dumps(TRANSFORMS, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

    trace, accounting = build_stage_trace(replay)
    with (OUT / "stage_trace.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for rec in trace:
            handle.write(json.dumps(rec, sort_keys=True) + "\n")

    per_tick, blind_receipts, blind_summary = BL.build_per_tick()
    B.write_csv(OUT / "per_tick_transform.csv", per_tick, list(per_tick[0]))
    B.write_csv(OUT / "blind_receipt.csv", blind_receipts, list(blind_receipts[0]))

    renders = build_renders()
    B.write_csv(OUT / "eye_index.csv", renders, list(renders[0]))

    join_status: dict[str, int] = {}
    for row in joins:
        join_status[row["join_status"]] = join_status.get(row["join_status"], 0) + 1
    summary = {
        "premise_step0": {
            "ticks": len(draw), "distinct_ticks": len({(r["section_id"], r["frame"]) for r in draw}),
            "producer_rows": len(joins), "comparator_boxes": len(
                B.read_csv(B.G406 / "comparator_detections.csv")),
            "matched_pairs": len(residuals),
            "silent_ticks": sum(1 for r in ticks if r["silence"] == 1),
            "ticks_with_producer_rows": sum(1 for r in ticks if r["silence"] == 0),
            "ticks_accounted": len(ticks),
            "distinct_frames_in_matched_pairs": len({r["card_id"] for r in residuals}),
            "sources_rehashed_equal": sum(1 for r in sources if r["rehash_equal"] == "1"),
            "sources_absent": sum(1 for r in sources if r["status"] == "ABSENT"),
            "expected_input_digests_matched": sum(
                1 for r in inputs if r["expected_match_lf"] == "1"),
        },
        "geometry_matched_pairs": geometry,
        "export_join": join_status,
        "coordinates_equal_rows": sum(1 for r in joins if r["coordinates_equal"] == "1"),
        "construct": {
            "cases": len(cases),
            "code_consistent": sum(1 for r in cases if r["crop_y_matches_code"] == "1"
                                   and r["crop_x_unchanged"] == "1"
                                   and r["uncrop_recovers_native_y1"] == "1"),
            "exact_inverse_cases": sum(1 for r in cases if r["uncrop_exact"] == "1"),
        },
        "stage_trace": accounting,
        "renders": {"cards": len(renders),
                    "ok": sum(1 for r in renders if r["status"] == "OK"),
                    "absent": sum(1 for r in renders if r["status"] != "OK")},
        "blind_marks": blind_summary,
        "declared_transform": TRANSFORMS["declared_inverse"],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n",
                                      encoding="utf-8", newline="\n")

    scans = [field_scan(p) for p in sorted(OUT.rglob("*"))
             if p.is_file() and p.suffix.lower() in {".csv", ".json", ".jsonl", ".md", ".txt"}]
    scans += [field_scan(B.ROOT / "scripts/platformkit/tracking" / n) for n in
              ("g409_audit.py", "g409_build.py", "g409_construct.py", "g409_observer.py",
               "g409_blind.py", "g409_finalize.py", "g409_prepare.py", "g409_run.py",
               "g409_transforms.py")]
    scans += [field_scan(B.ROOT / p) for p in
              ("tests/platformkit/test_g409_box_coordinate_cause.py",
               "docs/evidence/tracking/g409_box_coordinate_cause_2026-09-12.md")
              if (B.ROOT / p).exists()]
    (OUT / "q6_scan.json").write_text(
        json.dumps({"scanned": len(scans), "total_hits": sum(s["count"] for s in scans),
                    "scans": scans}, indent=1, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    print(json.dumps(summary["premise_step0"], sort_keys=True))
    print(json.dumps(summary["geometry_matched_pairs"], sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
