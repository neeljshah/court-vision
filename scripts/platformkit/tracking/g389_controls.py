"""G389 receipts: transform controls, context audit, usability and the eye check.

The transform controls plant a prediction AT the reference centre and push it through
the inherited G363 scorer: they measure the coordinate transform, not a detector, and
are labelled as controls everywhere they appear. The eye check renders evenly spaced
keys over the WHOLE completed sweep (contract A3/B7 -- never a head slice).
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

from PIL import Image, ImageDraw

from scripts.platformkit.tracking.g363_ball_coverage import read_csv, write_csv
from scripts.platformkit.tracking.g363_score import score_arm
from scripts.platformkit.tracking.g384_native_frames import require_native_scale

CONTROL_N, EYE_N, THUMB = 30, 30, 320
PRIMARY = ("terra", "sol")


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def even(rows: list, count: int) -> list:
    """Evenly spaced picks over the whole ordered set."""
    if len(rows) <= count:
        return list(rows)
    return [rows[(index * len(rows)) // count + (len(rows) // count) // 2]
            for index in range(count)]


def transform_controls(frames: list[dict], reference: list[dict]) -> tuple[list[dict], dict]:
    """Planted-at-reference matching through the sealed scorer, per split."""
    require_native_scale(frames)
    refs = {row["frame_key"]: {"label": row["label"], "cx": _float(row["cx"]),
                               "cy": _float(row["cy"]), "diameter": _float(row["diameter"])}
            for row in reference if row["label"]}
    index = {row["frame_key"]: row for row in frames}
    rows, summary = [], {}
    for split in ("development", "heldout"):
        picks = even([row for row in reference
                      if row["split"] == split and row["label"] == "VISIBLE"
                      and _float(row["cx"]) is not None], CONTROL_N)
        preds = [{"arm": "CONTROL", "rank": "0", "tick_history": "OBSERVED",
                  "frame_key": row["frame_key"],
                  "x": _float(row["cx"]) / float(index[row["frame_key"]]["sheet_scale"]),
                  "y": _float(row["cy"]) / float(index[row["frame_key"]]["sheet_scale"])}
                 for row in picks if row["frame_key"] in index]
        subset = [index[row["frame_key"]] for row in picks if row["frame_key"] in index]
        arm, _frame_rows = score_arm("CONTROL", split, subset, refs, preds)
        summary[split] = {"planted": len(preds), "tp": int(arm["tp"]), "fp": int(arm["fp"])}
        rows.append({"check": "planted_native_match", "split": split,
                     "detail": "prediction planted at the reference centre",
                     "observed": "%d/%d TP" % (int(arm["tp"]), len(preds)),
                     "expected": "%d/%d TP" % (len(preds), len(preds)),
                     "status": "PASS" if int(arm["tp"]) == len(preds) and not int(arm["fp"])
                     else "FAIL"})
    scales = sorted({row["sheet_scale"] for row in frames})
    rows.append({"check": "sheet_scale", "split": "all",
                 "detail": "every native reference row", "observed": str(scales),
                 "expected": "['1.0']", "status": "PASS" if scales == ["1.0"] else "FAIL"})
    return rows, summary


def usability(ratings: list[dict], keys: set[str]) -> dict:
    """Inherited primary-rater usability rule, recomputed over the retained keys."""
    pairs: dict[str, dict[str, dict]] = {}
    for row in ratings:
        if row["rater"] in PRIMARY and row["frame_key"] in keys:
            pairs.setdefault(row["frame_key"], {})[row["rater"]] = row
    gaps, sizes, missing = [], [], 0
    for pair in pairs.values():
        if len(pair) != 2 or {row["label"] for row in pair.values()} != {"VISIBLE"}:
            continue
        points = []
        for row in pair.values():
            x, y = _float(row.get("cx")), _float(row.get("cy"))
            size = max(_float(row.get("box_w")) or 0.0, _float(row.get("box_h")) or 0.0)
            if x is None or y is None:
                continue
            points.append((x, y))
            if size:
                sizes.append(size)
        if len(points) != 2:
            missing += 1
            continue
        gaps.append(math.hypot(points[0][0] - points[1][0], points[0][1] - points[1][1]))
    median_diameter = statistics.median(sizes) if sizes else None
    p50 = statistics.median(gaps) if gaps else None
    threshold = None if median_diameter is None else round(0.5 * median_diameter, 2)
    ordered = sorted(gaps)
    return {"n_pairs": len(gaps), "p50_px": None if p50 is None else round(p50, 2),
            "p90_px": round(ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))], 2) if ordered else None,
            "max_px": round(max(gaps), 2) if gaps else None,
            "boxless_pairs": missing, "median_native_diameter_px": median_diameter,
            "threshold_px": threshold,
            "rule": "median centre disagreement <= 0.5 x median native diameter",
            "verdict": "usable" if p50 is not None and threshold is not None
            and p50 <= threshold and len(gaps) >= 30 else "NOT MET"}


def context_audit(boxes: list[dict], frames: dict[str, dict]) -> dict:
    """Unique boxes, causal-neighbour identity and held-out context separation."""
    heldout_games = {row["game"] for row in frames.values() if row["split"] == "heldout"}
    heldout_sections = {row["section"] for row in frames.values() if row["split"] == "heldout"}
    return {"rows": len(boxes), "unique_frame_keys": len({row["frame_key"] for row in boxes}),
            "unique_section_frame_pairs": len({(row["section"], row["frame_index"])
                                               for row in boxes}),
            "games": len({row["game"] for row in boxes}),
            "rows_from_heldout_games": sum(1 for row in boxes if row["game"] in heldout_games),
            "rows_from_heldout_sections": sum(1 for row in boxes
                                              if row["section"] in heldout_sections)}


def eye_check(picks: list[dict], sheets: Path, out: Path) -> list[dict]:
    """One contact sheet plus its index; every tile names its own decision."""
    columns = 6
    rows = (len(picks) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * THUMB, rows * THUMB), (16, 16, 16))
    draw = ImageDraw.Draw(canvas)
    index = []
    for position, item in enumerate(picks):
        path = sheets / item["sheet"]
        column, row = position % columns, position // columns
        if path.is_file():
            with Image.open(path) as image:
                scale = THUMB / max(image.width, image.height)
                thumb = image.resize((int(image.width * scale), int(image.height * scale)))
                canvas.paste(thumb, (column * THUMB, row * THUMB))
                cx, cy = _float(item.get("cx")), _float(item.get("cy"))
                if cx is not None and cy is not None:
                    px = column * THUMB + cx * scale
                    py = row * THUMB + cy * scale
                    draw.ellipse((px - 9, py - 9, px + 9, py + 9), outline=(255, 220, 0), width=2)
        draw.text((column * THUMB + 4, row * THUMB + 4),
                  "%d %s" % (position + 1, item.get("label", "")), fill=(255, 255, 255))
        index.append({"ordinal": position + 1, "frame_key": item["frame_key"],
                      "sheet": item["sheet"], "label": item.get("label", ""),
                      "cx": item.get("cx", ""), "cy": item.get("cy", ""),
                      "split": item.get("split", ""), "role": item.get("role", "")})
    canvas.save(out, quality=88)
    return index


def run(args) -> int:
    out = Path(args.out_dir)
    frames = read_csv(out / "frames_v3.csv")
    reference = [row for row in read_csv(out / "reference_v3.csv") if row["label"]]
    controls, planted = transform_controls(frames, reference)
    write_csv(out / "transform_controls.csv",
              ("check", "split", "detail", "observed", "expected", "status"), controls)

    completed = {row["frame_key"] for row in read_csv(out / "adjudications_g389.csv")}
    ratings = read_csv(Path(args.ratings))
    all_keys = {row["frame_key"] for row in read_csv(out / "reference_v3.csv")}
    # Two populations, both named: the INHERITED one over every scheduled key (this
    # must reproduce the G373 figure unchanged -- the bar may not move), and the one
    # restricted to keys that are settled now.
    inherited = usability(ratings, all_keys)
    stats = usability(ratings, {row["frame_key"] for row in reference})
    boxes = read_csv(out / "dev_boxes_v3.csv")
    audit = context_audit(boxes, {row["frame_key"]: row for row in frames})
    write_csv(out / "context_audit.csv", tuple(audit),
              [{key: value for key, value in audit.items()}])

    sweep = read_csv(out / "sweep_permutation.csv")
    index = {row["frame_key"]: row for row in reference}
    # The audit keys were themselves chosen by an even sweep over the same order, so
    # they are EXCLUDED from the backlog pool here: sampling both with one formula
    # would render the same 30 frames twice and call it 60 (it did, before this line).
    backlog = [dict(index.get(row["frame_key"], {}), sheet=row["sheet"], role="backlog",
                    frame_key=row["frame_key"], split=row["split"])
               for row in sweep
               if row["frame_key"] in completed and row["audit_duplicate"] != "1"]
    audit_keys = [dict(index.get(row["frame_key"], {}), sheet=row["sheet"], role="audit",
                       frame_key=row["frame_key"], split=row["split"])
                  for row in sweep if row["audit_duplicate"] == "1"
                  and row["frame_key"] in completed]
    picks = even(backlog, EYE_N) + even(audit_keys, EYE_N)
    rows = eye_check(picks, Path(args.sheets), out / "renders" / "eye_check_g389_60.jpg")
    write_csv(out / "renders" / "eye_check_index.csv",
              ("ordinal", "frame_key", "sheet", "label", "cx", "cy", "split", "role"), rows)

    payload = {"transform_controls": planted, "control_rows": controls,
               "usability_settled_keys": stats,
               "usability_inherited_all_scheduled_keys": inherited,
               "context_audit": audit,
               "eye_check_backlog": sum(1 for row in picks if row["role"] == "backlog"),
               "eye_check_audit": sum(1 for row in picks if row["role"] == "audit")}
    (out / "controls.json").write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n",
                                       encoding="ascii", newline="\n")
    print(json.dumps({"planted": planted, "usability_settled": stats,
                      "usability_inherited": inherited, "context": audit},
                     sort_keys=True))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g389_controls")
    for flag in ("--ratings", "--sheets", "--out-dir"):
        parser.add_argument(flag, required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
