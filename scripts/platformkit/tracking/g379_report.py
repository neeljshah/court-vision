"""G379 merge, per-section aggregation, the required eye check, and `summary.json`.

Sealed in the G379 prereg sections 6, 7, 9 and 11. Every denominator is the SCHEDULED decoded frame
count of its section, never the count of frames that happen to carry a fit (contract H1). Frames
that cannot be scored are charged, never dropped (B1); renders span every observed status and are
evenly spaced, never a head slice (A3, B7).
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking import g362_fit_validate as fv
from scripts.platformkit.tracking import g362_strokes as st
from scripts.platformkit.tracking.g334_court_template import TEMPLATE_POINTS, project
from scripts.platformkit.tracking.g364_sampler import interior_indices

SCHEDULED = 60
RENDERS = 30


def _rows(path: Path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write(path: Path, rows: list[dict], fields=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    names = list(fields) if fields else list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, lineterminator="\n",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def merge(shards: Path, out_dir: Path) -> tuple[list[dict], dict]:
    """Concatenate every shard's rows, splits, matrices and per-point forward residuals."""
    rows, splits, matrices, forward = [], [], {}, {}
    for path in sorted(shards.glob("rows_*.csv")):
        rows.extend(_rows(path))
    for path in sorted(shards.glob("splits_*.csv")):
        splits.extend(_rows(path))
    for path in sorted(shards.glob("matrices_*.json")):
        matrices.update(json.loads(path.read_text(encoding="ascii")))
    for path in sorted(shards.glob("forward_*.npz")):
        archive = np.load(path)
        for key in archive.files:
            forward[key] = np.asarray(archive[key], dtype=float)
    rows.sort(key=lambda row: (row["section_id"], int(row["frame_index"])))
    splits.sort(key=lambda row: (row["section_id"], int(row["frame_index"]), row["stroke_id"]))
    _write(out_dir / "residuals.csv", rows)
    _write(out_dir / "stroke_split.csv", splits)
    (out_dir / "selected_H.json").write_text(
        json.dumps(matrices, sort_keys=True, indent=1) + "\n", encoding="ascii")
    np.savez_compressed(out_dir / "forward_residuals.npz", **forward)
    refusals = [row for row in rows if row["validation_status"] != fv.STATE_VALID]
    _write(out_dir / "refusals.csv", refusals)
    print("MERGE frames=%d strokes=%d matrices=%d residual_frames=%d refusals=%d"
          % (len(rows), len(splits), len(matrices), len(forward), len(refusals)))
    return rows, forward


def _median(values: list[float]) -> float:
    return float(np.median(np.asarray(values, dtype=float))) if len(values) else float("nan")


def sections(rows: list[dict], forward: dict, feet: list[dict]) -> list[dict]:
    """Per-section shares, all against the SCHEDULED denominator, charged and evaluable side by side."""
    by_section: dict[str, list[dict]] = {}
    for row in rows:
        by_section.setdefault(row["section_id"], []).append(row)
    feet_by: dict[str, list[dict]] = {}
    for row in feet:
        feet_by.setdefault(row["section_id"], []).append(row)
    out = []
    for section, group in sorted(by_section.items()):
        status = Counter(row["validation_status"] for row in group)
        evaluable, charged = [], []
        for row in group:
            values = forward.get(row["frame_key"])
            if values is None:
                charged.extend([fv.PENALTY_PX] * len(TEMPLATE_POINTS))
            else:
                evaluable.extend(values.tolist())
                charged.extend(values.tolist())
        mine = feet_by.get(section, [])
        inside = sum(int(row["inside_full_court"]) for row in mine)
        out.append({
            "section_id": section, "game_id": group[0]["game_id"],
            "n_scheduled": len(group),
            "n_decoded": sum(row["validation_status"] != "DECODE_FAILED" for row in group),
            "n_valid": status[fv.STATE_VALID],
            "valid_share": round(status[fv.STATE_VALID] / len(group), 6),
            "n_feet": len(mine), "n_feet_inside": inside,
            "feet_inside": round(inside / len(mine), 6) if mine else float("nan"),
            "n_feet_near_half": sum(int(row["inside_near_half"]) for row in mine),
            "forward_median_px_charged": round(_median(charged), 6),
            "forward_median_px_evaluable": round(_median(evaluable), 6),
            "n_frames_evaluable": sum(1 for row in group if forward.get(row["frame_key"]) is not None),
            "n_cascade_accept": sum(row["selection_status"] == "ACCEPT" for row in group),
            "validation_status_counts": json.dumps(dict(sorted(status.items()))),
            "selection_status_counts": json.dumps(dict(sorted(
                Counter(row["selection_status"] for row in group).items()))),
            "raw_state_counts": json.dumps(dict(sorted(
                Counter(row["raw_state"] for row in group).items()))),
            "presence_counts": json.dumps(dict(sorted(
                Counter(row["presence_prediction"] for row in group).items())))})
    return out


def render(rows: list[dict], frames: list[dict], matrices: dict, out_dir: Path,
           count: int = RENDERS) -> list[dict]:
    """Evenly spaced source-bound renders spanning every observed validation status."""
    paths = {row["frame_key"]: row.get("path", "") for row in frames}
    pool = [row for row in rows if paths.get(row["frame_key"])
            and Path(paths[row["frame_key"]]).exists()]
    groups: dict[str, list[dict]] = {}
    for row in pool:
        groups.setdefault("%s|%s" % (row["validation_status"], row["selection_status"]),
                          []).append(row)
    order = sorted(groups)
    quota = {status: max(1, round(count * len(groups[status]) / max(1, len(pool))))
             for status in order}
    while sum(quota.values()) > count and max(quota.values()) > 1:
        quota[max(quota, key=lambda key: quota[key])] -= 1
    while sum(quota.values()) < count:
        biggest = max(order, key=lambda key: len(groups[key]) - quota[key])
        if quota[biggest] >= len(groups[biggest]):
            break
        quota[biggest] += 1
    chosen = []
    for status in order:
        group = sorted(groups[status], key=lambda row: (row["section_id"],
                                                        int(row["frame_index"])))
        want = min(quota[status], len(group))
        try:
            picks = interior_indices(len(group), want) if len(group) > want + 1 else list(
                range(want))
        except ValueError:
            picks = list(range(want))
        chosen.extend(group[index] for index in picks)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for index, row in enumerate(chosen, start=1):
        path = paths.get(row["frame_key"], "")
        image = cv2.imread(path) if path else None
        if image is None:
            continue
        canvas = image.copy()
        entry = matrices.get(row["frame_key"])
        if entry is not None:
            points = project(np.asarray(entry["image_matrix"], dtype=float), TEMPLATE_POINTS)
            for x, y in points:
                if np.isfinite(x) and np.isfinite(y):
                    cv2.circle(canvas, (int(round(x)), int(round(y))), 1, (60, 220, 60), -1)
        _fit, validation = st.partition(st.extract_strokes(canvas))
        for x, y in st.support_array(validation):
            cv2.circle(canvas, (int(round(x)), int(round(y))), 1, (240, 160, 40), -1)
        stamp = "%s f%s %s | sel %s | raw %s" % (row["section_id"][-28:], row["frame_index"],
                                                 row["validation_status"], row["selection_status"],
                                                 row["raw_state"])
        cv2.putText(canvas, stamp, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (250, 250, 250), 1,
                    cv2.LINE_AA)
        target = out_dir / ("render_%02d_%s.jpg" % (index, row["validation_status"]))
        cv2.imwrite(str(target), canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 72])
        written.append({"render": target.name, "frame_key": row["frame_key"],
                        "section_id": row["section_id"], "frame_index": row["frame_index"],
                        "source_sha256": row["source_sha256"],
                        "validation_status": row["validation_status"],
                        "selection_status": row["selection_status"], "raw_state": row["raw_state"],
                        "presence_prediction": row["presence_prediction"]})
    _write(out_dir / "renders.csv", written)
    print("RENDERS n=%d statuses=%s" % (len(written),
                                        dict(Counter(row["validation_status"] for row in written))))
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="G379 merge, aggregate, render, summarise")
    parser.add_argument("--shards", type=Path, required=True)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--feet", type=Path)
    parser.add_argument("--negatives", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows, forward = merge(args.shards, args.out)
    feet = _rows(args.feet) if args.feet and args.feet.exists() else []
    per_section = sections(rows, forward, feet)
    _write(args.out / "sections.csv", per_section)
    matrices = json.loads((args.out / "selected_H.json").read_text(encoding="ascii"))
    render(rows, _rows(args.frames), matrices, args.out / "renders")
    negatives = (json.loads(args.negatives.read_text(encoding="ascii"))
                 if args.negatives and args.negatives.exists() else {})
    met = [row for row in per_section
           if row["valid_share"] >= 0.50 and row["feet_inside"] >= 0.60
           and row["forward_median_px_charged"] <= fv.MAX_MEDIAN_PX]
    summary = {
        "row": "G379", "sections": per_section, "negatives": negatives,
        "n_sections": len(per_section), "n_games": len({row["game_id"] for row in per_section}),
        "n_frames": len(rows), "sections_meeting_all_three": len(met),
        "bars": {"valid_share": 0.50, "feet_inside": 0.60,
                 "forward_median_px": fv.MAX_MEDIAN_PX, "sections_required": 4,
                 "negatives_required": 200, "cascade_accepts_allowed": 0},
        "constants": {"MAX_MEDIAN_PX": fv.MAX_MEDIAN_PX, "PENALTY_PX": fv.PENALTY_PX,
                      "MIN_VAL_POINTS": fv.MIN_VAL_POINTS, "MIN_VAL_FAMILIES": fv.MIN_VAL_FAMILIES,
                      "SUPPORT_SPACING_PX": st.SUPPORT_SPACING_PX, "BASE_HEIGHT": fv.BASE_HEIGHT},
        "validation_status_totals": dict(sorted(
            Counter(row["validation_status"] for row in rows).items())),
        "selection_status_totals": dict(sorted(
            Counter(row["selection_status"] for row in rows).items())),
        "raw_state_totals": dict(sorted(Counter(row["raw_state"] for row in rows).items())),
        "presence_totals": dict(sorted(
            Counter(row["presence_prediction"] for row in rows).items())),
        "feet_total": len(feet),
        "feet_inside_total": sum(int(row["inside_full_court"]) for row in feet)}
    (args.out / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=1) + "\n",
                                           encoding="ascii")
    print("SUMMARY sections=%d meeting_all_three=%d feet=%d"
          % (len(per_section), len(met), len(feet)))


if __name__ == "__main__":
    main()
