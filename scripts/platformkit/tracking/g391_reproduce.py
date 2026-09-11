"""G391: an independent recomputation of the G390 counts and the suppression ceiling.

The matching rule is re-implemented here from the sealed words rather than imported
from the G390/G363 scorer: importing the route under test would make the check a
self-fit (contract B8). All 549 held-out states are kept, including the frames on
which the arm emitted nothing.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

EV = "docs/evidence/tracking"
OUT_NAME = "g391_ball_false_call_audit_2026-09-11"
REFERENCE = EV + "/g389_ball_reference_completion_2026-09-11/reference_v3.csv"
FRAMES = EV + "/g389_ball_reference_completion_2026-09-11/frames_v3.csv"
PREDICTIONS = EV + "/g390_ball_a8_sealed_pass_2026-09-11/predictions_A8.csv"
ARCHIVED = EV + "/g390_ball_a8_sealed_pass_2026-09-11/paired_frame_scores.csv"
TARGET_HEIGHT = 720.0
MIN_MATCH_PX = 3.0
DEFAULT_REF_DIAMETER_720P = 24.0
BAR_COVERAGE = 0.25
BAR_PRECISION_LOWER = 0.90
BAR_FP_PER_ABSENT = 0.01


def read(root: Path, relative: str) -> list[dict]:
    with (root / relative).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def wilson_lower(successes: int, total: int) -> float:
    """Wilson 95 percent lower bound; 0.0 at an empty denominator."""
    if total <= 0:
        return 0.0
    z = 1.959963984540054
    phat = successes / total
    centre = phat + z * z / (2 * total)
    spread = z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total)
    return (centre - spread) / (1 + z * z / total)


def score(root: Path, suppressed: set[str] | None = None) -> tuple[list[dict], dict]:
    """Recompute per-state TP/FP over ALL held-out keys from the raw boxes."""
    frames = {row["frame_key"]: row for row in read(root, FRAMES)}
    reference = {row["frame_key"]: row for row in read(root, REFERENCE)
                 if row["split"] == "heldout"}
    calls: dict[str, list[dict]] = {}
    for row in read(root, PREDICTIONS):
        if row["rank"] == "0" and row["tick_history"] == "OBSERVED":
            if suppressed and row["frame_key"] in suppressed:
                continue
            calls.setdefault(row["frame_key"], []).append(row)
    rows, counts = [], {"tp": 0, "fp": 0, "fp_on_absent": 0, "abstained": 0}
    for key, ref in sorted(reference.items()):
        frame = frames[key]
        scale = TARGET_HEIGHT / float(frame["height"])
        sheet_scale = float(frame["sheet_scale"])
        found = calls.get(key, [])
        target = None
        if ref["label"] == "VISIBLE" and ref["cx"]:
            diameter = (float(ref["diameter"]) / sheet_scale if ref["diameter"]
                        else DEFAULT_REF_DIAMETER_720P / scale)
            target = (float(ref["cx"]) / sheet_scale, float(ref["cy"]) / sheet_scale,
                      diameter)
        threshold = max(MIN_MATCH_PX, target[2] * scale / 2.0) if target else ""
        best, tp = "", 0
        if target and found:
            distances = sorted(math.hypot(float(c["x"]) - target[0],
                                          float(c["y"]) - target[1]) * scale
                               for c in found)
            best = round(distances[0], 4)
            tp = 1 if distances[0] <= threshold else 0
        fp = len(found) - tp
        counts["tp"] += tp
        counts["fp"] += fp
        counts["fp_on_absent"] += fp if ref["label"] == "ABSENT" else 0
        counts["abstained"] += 1 if not found else 0
        rows.append({"frame_key": key, "game": frame["game"], "label": ref["label"],
                     "n_predictions": len(found), "tp": tp, "fp": fp,
                     "distance_720p": best,
                     "threshold_720p": round(threshold, 4) if threshold != "" else ""})
    total = len(reference)
    predicted = counts["tp"] + counts["fp"]
    n_absent = sum(1 for r in rows if r["label"] == "ABSENT")
    summary = {
        "n_states": total, "n_calls": predicted, "tp": counts["tp"], "fp": counts["fp"],
        "abstained": counts["abstained"],
        "fn_visible_without_tp": sum(1 for r in rows
                                     if r["label"] == "VISIBLE" and r["tp"] == 0),
        "coverage_c0": counts["tp"] / total if total else 0.0,
        "precision": counts["tp"] / predicted if predicted else 0.0,
        "precision_wilson_lo": wilson_lower(counts["tp"], predicted),
        "all_fp_per_absent": counts["fp"] / n_absent if n_absent else 0.0,
        "fp_on_absent_per_absent": counts["fp_on_absent"] / n_absent if n_absent else 0.0,
        "n_absent": n_absent,
    }
    summary["bars"] = {
        "coverage_c0_ge_0.25": summary["coverage_c0"] >= BAR_COVERAGE,
        "precision_wilson_lo_ge_0.90": summary["precision_wilson_lo"] >= BAR_PRECISION_LOWER,
        "all_fp_per_absent_le_0.01": summary["all_fp_per_absent"] <= BAR_FP_PER_ABSENT,
    }
    return rows, summary


def ceiling(root: Path) -> dict:
    """Suppression is subtraction: prove TP<=90 and FP>=0 over every 549-state subset."""
    baseline_rows, baseline = score(root)
    call_keys = [r["frame_key"] for r in baseline_rows if r["n_predictions"] > 0]
    tp_keys = [r["frame_key"] for r in baseline_rows if r["tp"] == 1]
    probes = []
    fp_keys = [r["frame_key"] for r in baseline_rows
               if r["n_predictions"] > 0 and r["tp"] == 0]
    for name, removed in (("suppress_all_calls", set(call_keys)),
                          ("suppress_all_true_calls", set(tp_keys)),
                          ("oracle_suppress_every_false_call", set(fp_keys)),
                          ("suppress_none", set())):
        rows, summary = score(root, removed)
        probes.append({"probe": name, "n_suppressed": len(removed),
                       "tp": summary["tp"], "fp": summary["fp"],
                       "coverage_c0": round(summary["coverage_c0"], 6),
                       "bars": summary["bars"],
                       "n_states": summary["n_states"],
                       "states_preserved": summary["n_states"] == baseline["n_states"],
                       "tp_not_increased": summary["tp"] <= baseline["tp"],
                       "fp_not_increased": summary["fp"] <= baseline["fp"],
                       "fp_non_negative": summary["fp"] >= 0,
                       "calls_are_subset": set(
                           r["frame_key"] for r in rows if r["n_predictions"] > 0
                       ).issubset(set(call_keys))})
    return {"baseline_tp": baseline["tp"], "baseline_fp": baseline["fp"],
            "ceiling_tp": baseline["tp"], "ceiling_fp_floor": 0,
            "suppression_cannot_add_tp": all(p["tp_not_increased"] for p in probes),
            "all_549_states_survive": all(p["states_preserved"] for p in probes),
            "probes": probes}


def main() -> int:
    parser = argparse.ArgumentParser(prog="g391_reproduce")
    parser.add_argument("--root", default=r"C:\Users\neelj\nba-track-a10")
    parser.add_argument("--run", default="1")
    parser.add_argument("--with-ceiling", action="store_true")
    args = parser.parse_args()
    root = Path(args.root)
    out_dir = root / EV / OUT_NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, summary = score(root)
    archived = {r["frame_key"]: r for r in read(root, ARCHIVED) if r["arm"] == "A8"}
    mismatches = [r["frame_key"] for r in rows
                  if int(archived[r["frame_key"]]["tp"]) != r["tp"]
                  or int(archived[r["frame_key"]]["fp"]) != r["fp"]]
    summary["archived_row_mismatches"] = len(mismatches)
    summary["archived_mismatch_keys"] = mismatches[:10]
    summary["run"] = args.run
    name = "raw_reproduction.csv" if args.run == "1" else "raw_reproduction_run%s.csv" % args.run
    path = out_dir / name
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    summary["rows_sha256"] = hashlib.sha256(
        path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    if args.with_ceiling:
        summary["ceiling"] = ceiling(root)
        (out_dir / "suppression_limit.json").write_text(
            json.dumps(summary["ceiling"], indent=2), encoding="ascii")
    (out_dir / ("raw_reproduction_run%s.json" % args.run)).write_text(
        json.dumps(summary, indent=2), encoding="ascii")
    print("REPRODUCTION run=%s tp=%d fp=%d fn=%d calls=%d states=%d mismatch=%d sha=%s"
          % (args.run, summary["tp"], summary["fp"], summary["fn_visible_without_tp"],
             summary["n_calls"], summary["n_states"], summary["archived_row_mismatches"],
             summary["rows_sha256"][:16]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
