"""G363 scorer: one-to-one matching, coverage/precision metrics and the verdict.

Sealed by docs/evidence/tracking/g363_ball_coverage_2026-09-09/g363_prereg_2026-09-09.md.
Only rank-0 OBSERVED predictions are scored; INFERRED temporal history rows are
archived and never counted as a true positive.  Distances are normalised to 720p.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Sequence

from scripts.platformkit.g130_recensus import wilson_interval

TARGET_HEIGHT = 720.0
MIN_MATCH_PX = 3.0
DEFAULT_REF_DIAMETER_720P = 24.0
SCORED_RANK = "0"
SCORED_HISTORY = "OBSERVED"
LABELS = ("VISIBLE", "ABSENT", "UNKNOWN")
ADJUDICATOR = "ADJUDICATOR"
BASELINE_ARM = "A0"
BAR_COVERAGE_MULTIPLE = 3.0
BAR_PRECISION_LOWER = 0.90
BAR_FP_PER_ABSENT = 0.01
MIN_VISIBLE = 150
MIN_ABSENT = 150
PREMISE_FALSE_C0 = 0.50

FRAME_SCORE_FIELDS = ("arm", "split", "frame_key", "game", "competition", "label",
                      "n_predictions", "tp", "fp", "distance_720p", "threshold_720p")
ARM_FIELDS = ("arm", "split", "inherits", "n_frames", "n_visible", "n_absent", "n_unknown",
              "tp", "fp", "coverage", "precision", "precision_wilson_lo", "precision_wilson_hi",
              "fp_per_absent", "fp_on_absent_per_absent", "recall_on_visible", "abstention",
              "games", "paired_delta_mean", "paired_delta_min", "paired_delta_max",
              "games_improved")


def wilson(successes: int, total: int) -> tuple[float, float]:
    """Wilson 95 percent interval, degenerating to the full unit range at n = 0."""
    if total <= 0:
        return 0.0, 1.0
    return wilson_interval(successes, total)


def cohen_kappa(first: Sequence[str], second: Sequence[str]) -> float | None:
    """Cohen kappa over the sealed three-label set for the two primary raters."""
    n = len(first)
    if n == 0 or n != len(second):
        return None
    observed = sum(1 for a, b in zip(first, second) if a == b) / n
    expected = sum((first.count(label) / n) * (second.count(label) / n) for label in LABELS)
    return None if expected >= 1.0 else (observed - expected) / (1.0 - expected)


def match(refs: Sequence[tuple[float, float, float]],
          preds: Sequence[tuple[float, float]], scale: float) -> dict[int, tuple[int, float]]:
    """Greedy one-to-one matching; every unmatched or duplicate prediction is a FP."""
    candidates = []
    for pred_i, (px, py) in enumerate(preds):
        for ref_i, (rx, ry, diameter) in enumerate(refs):
            distance = math.hypot(px - rx, py - ry) * scale
            if distance <= max(MIN_MATCH_PX, diameter * scale / 2.0):
                candidates.append((distance, pred_i, ref_i))
    matched: dict[int, tuple[int, float]] = {}
    used_refs: set[int] = set()
    for distance, pred_i, ref_i in sorted(candidates):
        if pred_i in matched or ref_i in used_refs:
            continue
        matched[pred_i] = (ref_i, distance)
        used_refs.add(ref_i)
    return matched


def _number(value: str | None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def reference(ratings: Sequence[dict]) -> tuple[dict[str, dict], dict[str, object]]:
    """Adjudicated reference per frame plus the rater-agreement diagnostics."""
    by_frame: dict[str, list[dict]] = {}
    for row in ratings:
        by_frame.setdefault(row["frame_key"], []).append(row)
    refs: dict[str, dict] = {}
    primary_a: list[str] = []
    primary_b: list[str] = []
    unadjudicated = 0
    for frame, rows in by_frame.items():
        judged = [row for row in rows if row["rater"] == ADJUDICATOR]
        primary = sorted((row for row in rows if row["rater"] != ADJUDICATOR),
                         key=lambda row: row["rater"])
        if len(primary) == 2:
            primary_a.append(primary[0]["label"])
            primary_b.append(primary[1]["label"])
        chosen = judged[:1] or ([primary[0]] if len(primary) == 2 and
                                primary[0]["label"] == primary[1]["label"] else [])
        if not chosen:
            unadjudicated += 1
            continue
        label = chosen[0]["label"]
        centres = [row for row in (judged or primary) if _number(row.get("cx")) is not None]
        if label == "VISIBLE" and centres:
            cx = sum(_number(row["cx"]) for row in centres) / len(centres)
            cy = sum(_number(row["cy"]) for row in centres) / len(centres)
            sizes = [max(_number(row.get("box_w")) or 0.0, _number(row.get("box_h")) or 0.0)
                     for row in centres]
            sizes = [size for size in sizes if size > 0]
            diameter = sum(sizes) / len(sizes) if sizes else None
        else:
            cx = cy = diameter = None
        refs[frame] = {"label": label, "cx": cx, "cy": cy, "diameter": diameter}
    return refs, {"unadjudicated_frames": unadjudicated,
                  "cohen_kappa": cohen_kappa(primary_a, primary_b),
                  "rated_frames": len(by_frame)}


def score_arm(arm: str, split: str, frames: Sequence[dict], refs: dict[str, dict],
              preds: Sequence[dict]) -> tuple[dict, list[dict]]:
    """Coverage, precision and abstention for one arm on one split."""
    by_frame: dict[str, list[dict]] = {}
    for row in preds:
        if row["arm"] == arm and row["rank"] == SCORED_RANK and row["tick_history"] == SCORED_HISTORY:
            by_frame.setdefault(row["frame_key"], []).append(row)
    rows: list[dict] = []
    counts = {"tp": 0, "fp": 0, "fp_on_absent": 0, "abstained": 0}
    labels = {label: 0 for label in LABELS}
    per_game: dict[str, list[int]] = {}
    for frame in frames:
        key = frame["frame_key"]
        if frame["split"] != split or key not in refs:
            continue
        ref = refs[key]
        labels[ref["label"]] = labels.get(ref["label"], 0) + 1
        height = float(frame["height"])
        scale = TARGET_HEIGHT / height
        sheet_scale = float(frame["sheet_scale"])
        targets = []
        if ref["label"] == "VISIBLE" and ref["cx"] is not None:
            diameter = (ref["diameter"] / sheet_scale if ref["diameter"]
                        else DEFAULT_REF_DIAMETER_720P / scale)
            targets = [(ref["cx"] / sheet_scale, ref["cy"] / sheet_scale, diameter)]
        found = by_frame.get(key, [])
        matched = match(targets, [(float(row["x"]), float(row["y"])) for row in found], scale)
        tp, fp = len(matched), len(found) - len(matched)
        counts["tp"] += tp
        counts["fp"] += fp
        counts["fp_on_absent"] += fp if ref["label"] == "ABSENT" else 0
        counts["abstained"] += 1 if not found else 0
        per_game.setdefault(frame["game"], [0, 0])
        per_game[frame["game"]][0] += tp
        per_game[frame["game"]][1] += 1
        best = min(matched.values(), key=lambda item: item[1])[1] if matched else ""
        rows.append({"arm": arm, "split": split, "frame_key": key, "game": frame["game"],
                     "competition": frame["competition"], "label": ref["label"],
                     "n_predictions": len(found), "tp": tp, "fp": fp,
                     "distance_720p": round(best, 4) if best != "" else "",
                     "threshold_720p": round(max(MIN_MATCH_PX, targets[0][2] * scale / 2.0), 4)
                     if targets else ""})
    total = sum(labels.values())
    predicted = counts["tp"] + counts["fp"]
    lower, upper = wilson(counts["tp"], predicted)
    summary = {
        "arm": arm, "split": split, "inherits": "", "n_frames": total,
        "n_visible": labels["VISIBLE"], "n_absent": labels["ABSENT"],
        "n_unknown": labels["UNKNOWN"], "tp": counts["tp"], "fp": counts["fp"],
        "coverage": counts["tp"] / total if total else 0.0,
        "precision": counts["tp"] / predicted if predicted else None,
        "precision_wilson_lo": lower, "precision_wilson_hi": upper,
        "fp_per_absent": counts["fp"] / labels["ABSENT"] if labels["ABSENT"] else None,
        "fp_on_absent_per_absent": (counts["fp_on_absent"] / labels["ABSENT"]
                                    if labels["ABSENT"] else None),
        "recall_on_visible": counts["tp"] / labels["VISIBLE"] if labels["VISIBLE"] else None,
        "abstention": counts["abstained"] / total if total else None,
        "games": len(per_game),
        "per_game": {game: value[0] / value[1] for game, value in per_game.items() if value[1]},
    }
    return summary, rows


def verdict(baseline: dict | None, candidate: dict | None) -> str:
    """The sealed verdict ladder; bars are byte-identical to the spec."""
    if baseline is None or candidate is None:
        return "PARTIAL"
    if baseline["coverage"] >= PREMISE_FALSE_C0:
        return "PREMISE FALSE"
    if baseline["coverage"] == 0.0:
        return "LIMIT"
    if baseline["n_visible"] < MIN_VISIBLE or baseline["n_absent"] < MIN_ABSENT:
        return "PARTIAL"
    passed = (candidate["coverage"] >= BAR_COVERAGE_MULTIPLE * baseline["coverage"]
              and candidate["precision_wilson_lo"] >= BAR_PRECISION_LOWER
              and (candidate["fp_per_absent"] or 0.0) <= BAR_FP_PER_ABSENT)
    return "DONE" if passed else "NOT VALIDATED"


def run(args) -> None:
    """Score every arm present in predictions.csv and write the sealed artifacts."""
    from scripts.platformkit.tracking.g363_ball_coverage import read_csv, write_csv

    frames = read_csv(Path(args.frames))
    preds = read_csv(Path(args.predictions))
    refs, diagnostics = reference(read_csv(Path(args.ratings)))
    summaries: list[dict] = []
    frame_rows: list[dict] = []
    for split in sorted({row["split"] for row in preds}):
        for arm in sorted({row["arm"] for row in preds if row["split"] == split}):
            summary, rows = score_arm(arm, split, frames, refs, preds)
            summary["inherits"] = next((row.get("inherits", "") for row in preds
                                        if row["arm"] == arm), "")
            summaries.append(summary)
            frame_rows.extend(rows)
    baselines = {row["split"]: row for row in summaries if row["arm"] == BASELINE_ARM}
    for summary in summaries:
        base = baselines.get(summary["split"])
        deltas = [summary["per_game"][game] - base["per_game"].get(game, 0.0)
                  for game in summary["per_game"]] if base else []
        summary["paired_delta_mean"] = sum(deltas) / len(deltas) if deltas else None
        summary["paired_delta_min"] = min(deltas) if deltas else None
        summary["paired_delta_max"] = max(deltas) if deltas else None
        summary["games_improved"] = sum(1 for delta in deltas if delta > 0)
    write_csv(Path(args.frame_scores), FRAME_SCORE_FIELDS, frame_rows)
    write_csv(Path(args.arms_out), ARM_FIELDS,
              [{field: row.get(field) for field in ARM_FIELDS} for row in summaries])
    held = [row for row in summaries if row["split"] == "heldout"]
    baseline = next((row for row in held if row["arm"] == BASELINE_ARM), None)
    candidate = next((row for row in held if row["arm"] != BASELINE_ARM), None)
    payload = {"diagnostics": diagnostics, "arms": summaries,
               "verdict": verdict(baseline, candidate),
               "bars": {"coverage_multiple": BAR_COVERAGE_MULTIPLE,
                        "precision_wilson_lo": BAR_PRECISION_LOWER,
                        "fp_per_absent": BAR_FP_PER_ABSENT,
                        "min_visible": MIN_VISIBLE, "min_absent": MIN_ABSENT,
                        "premise_false_c0": PREMISE_FALSE_C0}}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n",
                              encoding="utf-8", newline="\n")
    print("SCORE verdict=" + payload["verdict"] + " arms=" + str(len(summaries)))
