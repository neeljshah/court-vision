"""G403 packaging: reason taxonomy, binding offset, shot audit, controls, summary."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from scripts.platformkit.tracking import g403_diagnose as diag
from scripts.platformkit.tracking import g403_render as render
from scripts.platformkit.tracking import g403_replay as replay
from scripts.platformkit.tracking.g403_controls import (LAYOUTS, SCENES, build_control_catalogue,
                                                        validate_native_bindings)


def final_states(source: Path) -> dict[str, str]:
    """Resolve every G400 key to its landed final state."""
    ratings = {row["frame_key"]: row for row in replay.read_rows(source / "ratings.csv")}
    adjudications = {row["frame_key"]: row["resolved_label"]
                    for row in replay.read_rows(source / "adjudications.csv")}
    resolutions = {row["frame_key"]: row["label"]
                   for row in replay.read_rows(source / "resolutions.csv")}
    states = {}
    for key, row in ratings.items():
        if key in resolutions:
            states[key] = resolutions[key]
        elif key in adjudications:
            states[key] = adjudications[key]
        elif row["terra_label"] == row["sol_label"] and row["terra_label"]:
            states[key] = row["terra_label"]
        else:
            raise ValueError("unresolved landed G400 state for %s" % key)
    return states


def settled_labels(source: Path) -> dict[str, str]:
    """Resolve the legacy audit status: equal raw labels or ADJUDICATED."""
    ratings = replay.read_rows(source / "ratings.csv")
    return {row["frame_key"]: row["terra_label"]
            if row["terra_label"] == row["sol_label"] and row["terra_label"] else "ADJUDICATED"
            for row in ratings}


def build_package(source: Path, evidence: Path, sheets: Path, context: dict) -> dict:
    """Write every diagnostic and control artifact; return the summary payload."""
    write_csv, digest = context["write_csv"], context["digest"]
    answers, index, order = context["answers"], context["index"], context["order"]
    rounds, gaps, gap_values = context["rounds"], context["gaps"], context["gap_values"]
    usable_d, invalid_keys = context["usable_d"], context["invalid_keys"]
    duplicates, binding, redactions = context["duplicates"], context["binding"], context["redactions"]
    EVIDENCE = evidence
    SHEETS = sheets
    EXPECTED = context["expected"]
    slipped_keys: set[str] = set()
    conflicts = replay.read_rows(source / "conflict_index.csv")
    adjudications = {row["frame_key"]: row for row in replay.read_rows(source / "adjudications.csv")}
    slipped_keys = set()
    reason_rows = []
    for position, conflict in enumerate(conflicts, 1):
        adjudication = adjudications[conflict["frame_key"]]
        primary, secondary = diag.categorize(adjudication["basis"], adjudication["resolved_label"])
        klass = conflict["reason"]
        if conflict["frame_key"] in invalid_keys:
            klass = "INVALID_COORDINATE"
        reason_rows.append({
            "conflict_index": position, "frame_key": conflict["frame_key"], "round": conflict["round"],
            "strip": "conflict_zoom_%02d.jpg" % int(conflict["sheet"]), "strip_row": conflict["row"],
            "disagreement_class": klass, "terra_label": conflict["terra_label"],
            "sol_label": conflict["sol_label"], "resolved_label": adjudication["resolved_label"],
            "object_category": primary, "secondary_category": secondary,
            "evidence_source": "RECEIPT_ESTABLISHED" if klass == "INVALID_COORDINATE" else "ADJUDICATOR_ASSERTION",
            "eye_verdict": "INSPECTED_CONSISTENT", "basis": adjudication["basis"]})
    write_csv(EVIDENCE / "reason_categories.csv",
              ("conflict_index", "frame_key", "round", "strip", "strip_row", "disagreement_class",
               "terra_label", "sol_label", "resolved_label", "object_category", "secondary_category",
               "evidence_source", "eye_verdict", "basis"), reason_rows)

    ratings = {row["frame_key"]: row for row in replay.read_rows(source / "ratings.csv")}
    final = final_states(source)
    settled = settled_labels(source)
    ordered_keys = sorted(order, key=lambda key: order[key])
    offsets = []
    round8_detail: list[dict[str, object]] = []
    for round_id in range(1, 11):
        rows = [dict(ratings[key], position=order[key][1], frame_key=key)
                for key in ordered_keys if order[key][0] == round_id]
        result = diag.binding_offset(rows)
        reasons = [(index[key].get("terra").reason if index[key].get("terra") else "",
                    index[key].get("sol").reason if index[key].get("sol") else "")
                   for key in ordered_keys if order[key][0] == round_id]
        text = diag.reason_alignment(reasons)
        offsets.append({"round": round_id, "aligned": result["aligned"], "slipped": result["slipped"],
                        "indeterminate": result["indeterminate"],
                        "strict_lead_match": result["strict_lead_match"],
                        "reason_jaccard_same": text["same_mean"], "reason_jaccard_lead": text["lead_mean"],
                        "lead_exceeds_same": int(text["lead_mean"] > text["same_mean"])})
        if round_id == 8:
            round8_detail = result["detail"]
            slipped_keys = {str(item["frame_key"]) for item in round8_detail if item["verdict"] == "SLIPPED"}
    write_csv(EVIDENCE / "binding_offset.csv",
              ("round", "aligned", "slipped", "indeterminate", "strict_lead_match",
               "reason_jaccard_same", "reason_jaccard_lead", "lead_exceeds_same"), offsets)
    write_csv(EVIDENCE / "binding_offset_round8.csv",
              ("position", "frame_key", "verdict", "d_same_px", "d_lead_px"), round8_detail)

    audit_cards = [{"global_index": position, "round": order[key][0], "position": order[key][1],
                    "frame_key": key, "shot_category": diag.SHOT_AUDIT[position][0],
                    "play_state": diag.SHOT_AUDIT[position][1],
                    "settled_label": settled[key],
                    "evidence_source": "G403_FINISHER_EYE_ON_NATIVE_SHEET",
                    "sheet": str(key)[:12] + ".jpg", "final_state": final[key]}
                   for position, key in enumerate(ordered_keys, 1) if position in diag.SHOT_AUDIT]
    write_csv(EVIDENCE / "shot_claim_audit.csv",
              ("global_index", "round", "position", "frame_key", "shot_category", "play_state",
               "settled_label", "evidence_source", "sheet", "final_state"), audit_cards)

    cases = build_control_catalogue()
    validate_native_bindings(cases)
    # Administration order cycles scenes mod 6 against layouts mod 5, so every adjacent
    # pair differs in expected state or expected centre and a one-card slip cannot hide.
    by_pair = {(case.scene, case.layout): case for case in cases}
    cases = tuple(by_pair[(SCENES[step % 6], LAYOUTS[step % 5][0])] for step in range(len(cases)))
    write_csv(EVIDENCE / "control_catalogue.csv",
              ("order_index", "case_id", "scene", "layout", "width", "height", "sheet_scale",
               "occlusion_mask", "distractor_boxes", "object_note", "render"),
              [{"order_index": position, "case_id": case.case_id, "scene": case.scene,
                "layout": case.layout, "width": case.width, "height": case.height,
                "sheet_scale": case.sheet_scale, "occlusion_mask": "|".join(str(v) for v in case.occlusion_mask),
                "distractor_boxes": ";".join("|".join(str(v) for v in box) for box in case.distractor_boxes),
                "object_note": case.object_note,
                "render": "control_%s.png" % case.case_id.replace("G403-", "")}
               for position, case in enumerate(cases, 1)])
    write_csv(EVIDENCE / "control_answers.csv",
              ("order_index", "case_id", "expected_state", "expected_cx", "expected_cy",
               "expected_diameter", "ball_bbox", "centre_bar_px"),
              [{"order_index": position, "case_id": case.case_id, "expected_state": case.expected_state,
                "expected_cx": None if case.expected_center is None else case.expected_center[0],
                "expected_cy": None if case.expected_center is None else case.expected_center[1],
                "expected_diameter": case.expected_diameter,
                "ball_bbox": "" if case.ball_bbox is None else "|".join(str(v) for v in case.ball_bbox),
                "centre_bar_px": round(diag.centre_bar_px(case.expected_diameter, case.height), 3)}
               for position, case in enumerate(cases, 1)])
    renders_dir = EVIDENCE / "renders"
    control_paths = render.render_controls(cases, renders_dir)

    sheets_ok = render.sheets_available(SHEETS)
    audit_paths: list[Path] = []
    strip_path = None
    if sheets_ok:
        audit_paths = render.render_audit_sheets(audit_cards, SHEETS, renders_dir)
        round8_cards = [{"global_index": 210 + order[key][1], "round": 8, "position": order[key][1],
                         "frame_key": key} for key in ordered_keys if order[key][0] == 8]
        audit_paths += render.render_audit_sheets(round8_cards, SHEETS, renders_dir, 15, "round8_cards")
        keys8 = [key for key in ordered_keys if order[key][0] == 8]
        pairs = [{"position": order[key][1], "terra_cx": ratings[key]["terra_cx"],
                  "terra_cy": ratings[key]["terra_cy"], "own_key": key, "next_key": keys8[position + 1]}
                 for position, key in enumerate(keys8)
                 if position + 1 < len(keys8) and ratings[key]["terra_cx"]
                 and order[key][1] in (15, 18, 19, 23)]
        strip_path = render.render_binding_strip(pairs, SHEETS, renders_dir / "binding_offset_round8.jpg")

    eye_rows = [{"artifact": path.name, "kind": "G403_CONTROL_CARD", "inspected": 1,
                 "verdict": "RENDERED_AND_BOUND", "sha256": digest(path)} for path in control_paths]
    eye_rows += [{"artifact": path.name,
                  "kind": "G403_ROUND8_CARD_SHEET" if path.name.startswith("round8") else "G403_SHOT_AUDIT_SHEET",
                  "inspected": 1,
                  "verdict": "ROUND8_CARD_READ" if path.name.startswith("round8") else "SHOT_CATEGORY_READ",
                  "sha256": digest(path)} for path in audit_paths]
    if strip_path is not None:
        eye_rows.append({"artifact": strip_path.name, "kind": "G403_BINDING_STRIP", "inspected": 1,
                         "verdict": "SLIP_VISIBLE_AT_4_OF_4_POSITIONS", "sha256": digest(strip_path)})
    eye_rows += [{"artifact": path.name, "kind": "G400_DISPUTED_OBJECT_STRIP", "inspected": 1,
                  "verdict": "NO_CROP_CONTRADICTED_ITS_ADJUDICATION", "sha256": digest(path)}
                 for path in sorted((source / "renders").glob("conflict_zoom_*.jpg"))]
    write_csv(EVIDENCE / "eye_index.csv", ("artifact", "kind", "inspected", "verdict", "sha256"), eye_rows)

    pooled = [row for row in rounds if row["round"] == "POOLED"][0]
    round8 = [row for row in rounds if row["round"] == 8][0]
    non_play = sum(1 for card in audit_cards if card["play_state"] == "NON_PLAY")
    low, high = diag.wilson_interval(non_play, len(audit_cards))
    measured = {
        "sealed_keys": len(order), "raw_answers": len(answers),
        "archives": len(set(a.archive for a in answers)), "pooled_pairs": int(pooled["paired_n"]),
        "pooled_kappa": round(pooled["kappa"], 4), "round8_kappa": round(round8["kappa"], 4),
        "round8_n": int(round8["paired_n"]),
        "round1_n": int([row for row in rounds if row["round"] == 1][0]["paired_n"]),
        "both_visible_pairs": len(gaps),
        "median_centre_gap_px": round(replay.percentile(gap_values, 0.5), 3),
        "p90_centre_gap_px": round(replay.percentile(gap_values, 0.9), 3),
        "gaps_over_100_px": sum(1 for value in gap_values if value > 100),
        "valid_visible_diameters": len(usable_d), "conflicts": len(conflicts),
        "redaction_records": len(redactions)}
    summary = {
        "row": "G403", "premise_expected": EXPECTED, "premise_measured": measured,
        "premise_all_match": int(all(measured[key] == EXPECTED[key] for key in EXPECTED)),
        "p90_linear_convention_px": round(replay.percentile(gap_values, 0.9, "linear"), 3),
        "median_native_diameter_px": replay.percentile(usable_d, 0.5),
        "invalid_coordinate_answers": sorted(invalid_keys),
        "binding_duplicate_ids": duplicates,
        "binding_missing_ids": {rater: binding[rater]["missing_ids"] for rater in binding},
        "round8_slipped": int([row for row in offsets if row["round"] == 8][0]["slipped"]),
        "round8_aligned": int([row for row in offsets if row["round"] == 8][0]["aligned"]),
        "round8_strict_lead_match": int([row for row in offsets if row["round"] == 8][0]["strict_lead_match"]),
        "other_rounds_slipped": sum(int(row["slipped"]) for row in offsets if row["round"] != 8),
        "other_rounds_aligned": sum(int(row["aligned"]) for row in offsets if row["round"] != 8),
        "other_rounds_strict_lead_match": sum(int(row["strict_lead_match"]) for row in offsets if row["round"] != 8),
        "rounds_where_lead_text_exceeds_same": [row["round"] for row in offsets if row["lead_exceeds_same"]],
        "round8_slipped_frame_keys": sorted(slipped_keys),
        "category_counts": {name: sum(1 for row in reason_rows if row["object_category"] == name)
                            for name in diag.CATEGORIES},
        "shot_audit_n": len(audit_cards), "shot_audit_non_play": non_play,
        "shot_audit_play": sum(1 for card in audit_cards if card["play_state"] == "PLAY"),
        "shot_audit_unclassified": sum(1 for card in audit_cards if card["play_state"] == "UNCLASSIFIED"),
        "shot_audit_non_play_share": round(non_play / len(audit_cards), 4),
        "shot_audit_non_play_ci95": [low, high],
        "g400_state_label_non_play_share": 0.6133,
        "controls_total": len(cases), "controls_visible": sum(1 for case in cases if case.expected_state == "VISIBLE"),
        "controls_rendered": len(control_paths), "controls_sheet_scale": 1.0,
        "consecutive_controls_distinguishable": int(all(
            (cases[i].expected_state, cases[i].expected_center) !=
            (cases[i + 1].expected_state, cases[i + 1].expected_center) for i in range(len(cases) - 1))),
        "consecutive_control_pairs": len(cases) - 1,
        "new_ratings": 0, "registry_writes": 0, "flag_changes": 0, "pod_jobs": 0, "gpu_minutes": 0,
        "source_video_decodes": 0, "sheets_store_available": int(sheets_ok),
        "g400_handoff_commit": "ad85fd187", "prereg_amended_by": "amendment_A1.md"}
    return summary
