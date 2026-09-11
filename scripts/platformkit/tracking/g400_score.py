"""G400 reconciliation: raw kappa, conflict list, usability, yield and exports.

Stage A (--stage raw) seals the raw paired table and the pre-adjudication kappa and
lists every state that needs pixel adjudication. Stage B (--stage final) folds in the
finisher's resolutions and writes the audited boxes, the additive reference, the
whole-stage yield and the summary. Adjudication never edits a raw judgment.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g400_prepare as rails

RATING_FIELDS = ("frame_key", "round", "video_id", "canonical_game", "width", "height",
                 "state_status", "terra_label", "terra_cx", "terra_cy", "terra_d",
                 "sol_label", "sol_cx", "sol_cy", "sol_d", "raw_agreement",
                 "centre_gap_px", "needs_adjudication", "adjudication_reason")
ROUND_N = 30      # sealed n per complete round; below it the kappa is descriptive (INCOMPLETE)
POOLED_N = 300    # sealed pooled n
KAPPA_FIELDS = ("round", "paired_n", "kappa", "observed_agreement", "bar", "verdict",
                "terra_missing", "sol_missing")
YIELD_FIELDS = ("metric", "value", "denominator", "note")


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write(path: Path, fields, rows) -> None:
    with path.open("w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: str(row.get(field, "")).encode(
                "ascii", "replace").decode("ascii") for field in fields})


def _diameter(row: dict) -> float:
    try:
        return (float(row["box_w"]) + float(row["box_h"])) / 2.0
    except (KeyError, ValueError):
        return 0.0


def build_raw(out: Path, gap_factor: float) -> dict:
    plan = _read(out / "batch_plan.csv")
    manifest = {row["frame_key"]: row for row in _read(out / "native_manifest.csv")}
    judged = {"terra": {}, "sol": {}}
    for rater in judged:
        for row in _read(out / ("ratings_%s.csv" % rater)):
            judged[rater][row["frame_key"]] = row
    rails.validate_completed_answers(
        [{"rater": row["rater"], "frame_key": row["frame_key"], "label": row["label"]}
         for rater in judged for row in judged[rater].values()])
    diameters = [_diameter(row) for rater in judged for row in judged[rater].values()
                 if row["label"] == "VISIBLE" and _diameter(row) > 0]
    median_d = statistics.median(diameters) if diameters else 0.0
    rows = []
    for entry in plan:
        key = entry["frame_key"]
        record = {"frame_key": key, "round": entry["round"],
                  "video_id": entry["video_id"],
                  "canonical_game": entry["canonical_game"],
                  "width": entry["width"], "height": entry["height"],
                  "state_status": manifest[key]["status"]}
        gap, reasons = "", []
        for rater in ("terra", "sol"):
            found = judged[rater].get(key)
            record[rater + "_label"] = found["label"] if found else ""
            for short, field in (("cx", "cx"), ("cy", "cy")):
                record[rater + "_" + short] = found[field] if found else ""
            record[rater + "_d"] = (round(_diameter(found), 3)
                                    if found and found["label"] == "VISIBLE" else "")
        both = bool(record["terra_label"]) and bool(record["sol_label"])
        record["raw_agreement"] = int(both and record["terra_label"] == record["sol_label"])
        if both and record["terra_label"] == record["sol_label"] == "VISIBLE":
            gap = round(((float(record["terra_cx"]) - float(record["sol_cx"])) ** 2
                         + (float(record["terra_cy"]) - float(record["sol_cy"])) ** 2) ** 0.5, 3)
            if median_d and gap > gap_factor * median_d:
                reasons.append("DISCREPANT_CENTRE")
        record["centre_gap_px"] = gap
        if not both:
            reasons.append("MISSING_JUDGMENT")
        elif not record["raw_agreement"]:
            reasons.append("LABEL_DISAGREEMENT")
        if manifest[key]["status"] != "PLANNED":
            reasons.append("STATE_" + manifest[key]["status"])
        record["needs_adjudication"] = int(bool(reasons))
        record["adjudication_reason"] = ";".join(reasons)
        rows.append(record)
    _write(out / "ratings.csv", RATING_FIELDS, rows)
    kappa_rows = []
    pooled_left, pooled_right = [], []
    for round_no in sorted({int(row["round"]) for row in rows}):
        pairs = [(row["terra_label"], row["sol_label"]) for row in rows
                 if int(row["round"]) == round_no and row["terra_label"]
                 and row["sol_label"]]
        left = [pair[0] for pair in pairs]
        right = [pair[1] for pair in pairs]
        pooled_left.extend(left)
        pooled_right.extend(right)
        value = rails.cohen_kappa(left, right) if pairs else None
        observed = (sum(a == b for a, b in pairs) / len(pairs)) if pairs else ""
        kappa_rows.append({
            "round": round_no, "paired_n": len(pairs),
            "kappa": "UNDEFINED" if value is None else round(value, 4),
            "observed_agreement": round(observed, 4) if pairs else "",
            "bar": rails.KAPPA_BAR,
            "verdict": ("NO_PAIRS" if not pairs else "UNKNOWN" if value is None
                        else "INCOMPLETE" if len(pairs) < ROUND_N
                        else "PASS" if value >= rails.KAPPA_BAR else "FAIL"),
            "terra_missing": sum(1 for row in rows if int(row["round"]) == round_no
                                 and not row["terra_label"]),
            "sol_missing": sum(1 for row in rows if int(row["round"]) == round_no
                               and not row["sol_label"])})
    pooled = rails.cohen_kappa(pooled_left, pooled_right) if pooled_left else None
    kappa_rows.append({
        "round": "POOLED", "paired_n": len(pooled_left),
        "kappa": "UNDEFINED" if pooled is None else round(pooled, 4),
        "observed_agreement": round(sum(a == b for a, b in zip(pooled_left, pooled_right))
                                    / len(pooled_left), 4) if pooled_left else "",
        "bar": rails.KAPPA_BAR,
        "verdict": ("NO_PAIRS" if not pooled_left else "UNKNOWN" if pooled is None
                    else "INCOMPLETE" if len(pooled_left) < POOLED_N
                    else "PASS" if pooled >= rails.KAPPA_BAR else "FAIL"),
        "terra_missing": sum(1 for row in rows if not row["terra_label"]),
        "sol_missing": sum(1 for row in rows if not row["sol_label"])})
    _write(out / "kappa.csv", KAPPA_FIELDS, kappa_rows)
    both_visible = [row for row in rows
                    if row["terra_label"] == row["sol_label"] == "VISIBLE"]
    gaps = sorted(float(row["centre_gap_px"]) for row in both_visible)
    usability = {"median_native_diameter_px": round(median_d, 3),
                 "both_visible_pairs": len(both_visible),
                 "median_centre_gap_px": round(statistics.median(gaps), 3) if gaps else None,
                 "p90_centre_gap_px": round(gaps[min(len(gaps) - 1, int(0.9 * len(gaps)))], 3)
                 if gaps else None,
                 "max_centre_gap_px": round(gaps[-1], 3) if gaps else None,
                 "gap_bar_px": round(gap_factor * median_d, 3),
                 "terra_missing": sum(1 for row in rows if not row["terra_label"]),
                 "sol_missing": sum(1 for row in rows if not row["sol_label"]),
                 "needs_adjudication": sum(row["needs_adjudication"] for row in rows)}
    (out / "usability.json").write_text(json.dumps(usability, indent=1, sort_keys=True)
                                        + "\n", encoding="ascii")
    print(json.dumps(usability, sort_keys=True))
    return usability


def build_final(out: Path, old_boxes: Path) -> dict:
    rows = _read(out / "ratings.csv")
    manifest = {row["frame_key"]: row for row in _read(out / "native_manifest.csv")}
    resolutions = {row["frame_key"]: row for row in _read(out / "resolutions.csv")}
    accepted, adjudications, audit = [], [], []
    for row in rows:
        key = row["frame_key"]
        settled = resolutions.get(key)
        label, cx, cy, diameter, decided = "", "", "", "", ""
        if settled:
            label, cx, cy = settled["label"], settled["cx"], settled["cy"]
            diameter, decided = settled["diameter"], "ADJUDICATED"
            adjudications.append({"frame_key": key, "round": row["round"],
                                  "video_id": row["video_id"],
                                  "reason": row["adjudication_reason"],
                                  "terra_label": row["terra_label"],
                                  "sol_label": row["sol_label"],
                                  "resolved_label": label, "cx": cx, "cy": cy,
                                  "diameter": diameter, "basis": settled["basis"]})
        elif row["raw_agreement"] == "1" and row["terra_label"] == "VISIBLE":
            label, decided = "VISIBLE", "AGREED"
            cx = round((float(row["terra_cx"]) + float(row["sol_cx"])) / 2.0, 3)
            cy = round((float(row["terra_cy"]) + float(row["sol_cy"])) / 2.0, 3)
            diameter = round((float(row["terra_d"]) + float(row["sol_d"])) / 2.0, 3)
        elif row["raw_agreement"] == "1":
            label, decided = row["terra_label"], "AGREED"
        audited = int(label == "VISIBLE" and cx != "" and cy != "")
        audit.append({"frame_key": key, "video_id": row["video_id"],
                      "round": row["round"], "state_status": row["state_status"],
                      "settled_label": label, "decided_by": decided, "cx": cx, "cy": cy,
                      "diameter": diameter, "width": row["width"],
                      "height": row["height"], "audited_at_native_zoom": audited,
                      "sheet_path": manifest[key]["sheet_path"]})
        if audited:
            accepted.append({"frame_key": key, "game": row["video_id"],
                             "section": manifest[key]["median_section_file"],
                             "competition": row["competition"]
                             if "competition" in row else manifest[key]["competition"],
                             "width": row["width"], "height": row["height"],
                             "sheet_scale": "1.0", "label": "VISIBLE", "cx": cx,
                             "cy": cy, "diameter": diameter, "decided_by": decided,
                             "source": "g400_stage1"})
    _write(out / "adjudications.csv",
           ("frame_key", "round", "video_id", "reason", "terra_label", "sol_label",
            "resolved_label", "cx", "cy", "diameter", "basis"), adjudications)
    _write(out / "box_audit.csv",
           ("frame_key", "video_id", "round", "state_status", "settled_label",
            "decided_by", "cx", "cy", "diameter", "width", "height",
            "audited_at_native_zoom", "sheet_path"), audit)
    new_fields = ("frame_key", "game", "section", "competition", "width", "height",
                  "sheet_scale", "label", "cx", "cy", "diameter", "decided_by", "source")
    _write(out / "new_boxes.csv", new_fields, accepted)
    old = _read(old_boxes)
    old_fields = list(old[0].keys()) if old else []
    merged = [dict(row) for row in old]
    for row in accepted:
        merged.append({field: row.get({"game": "game", "section": "section"}.get(
            field, field), "") for field in old_fields})
    for row, source in zip(merged[len(old):], accepted):
        row["frame_index"] = ""
        row["source"] = "g400_stage1"
        row["decided_by"] = source["decided_by"]
    _write(out / "reference.csv", tuple(old_fields), merged)
    contributions = {}
    for row in accepted:
        contributions[row["game"]] = contributions.get(row["game"], 0) + 1
    counted = len(accepted)
    verdict = rails.stage_verdict(
        [{"frame_key": row["frame_key"],
          "canonical_game": row["canonical_game"],
          "status": "REVIEWED" if row["terra_label"] and row["sol_label"] else "UNVISITED",
          "label": row["terra_label"] if row["terra_label"] and row["sol_label"] else ""}
         for row in rows], counted)
    yield_rows = [
        {"metric": "accepted_audited_new_boxes", "value": counted,
         "denominator": rails.PLANNED_STATES, "note": "whole-stage denominator"},
        {"metric": "stage_yield", "value": round(counted / rails.PLANNED_STATES, 4),
         "denominator": rails.PLANNED_STATES, "note": "never per-VISIBLE"},
        {"metric": "games_contributing", "value": len(contributions),
         "denominator": rails.GAMES, "note": "distinct new games with >=1 box"},
        {"metric": "old_boxes_preserved", "value": len(old), "denominator": 530,
         "note": "unchanged"},
        {"metric": "reference_total_boxes", "value": len(merged),
         "denominator": 1500, "note": "milestone NOT met by this stage"},
        {"metric": "route_verdict", "value": verdict, "denominator": rails.YIELD_LIMIT,
         "note": "<=120 accepted boxes closes the uniform route"}]
    _write(out / "yield.csv", YIELD_FIELDS, yield_rows)
    result = {"accepted_boxes": counted, "route_verdict": verdict,
              "games_contributing": len(contributions),
              "game_contributions": contributions,
              "old_boxes_preserved": len(old), "reference_total": len(merged)}
    print(json.dumps(result, sort_keys=True))
    return result


def run(args) -> int:
    out = Path(args.out_dir)
    if args.stage == "raw":
        build_raw(out, args.gap_factor)
    else:
        build_final(out, Path(args.old_boxes))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g400_score")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--stage", choices=("raw", "final"), required=True)
    parser.add_argument("--gap-factor", type=float, default=0.5)
    parser.add_argument("--old-boxes", default="")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
