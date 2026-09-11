"""G390 single sealed scoring pass: archived A0 baseline against the A8 candidate.

The candidate token must already read INFERENCE_COMPLETE; `score_sealed` advances
it to SCORING_STARTED, so a second invocation is refused by construction.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from scripts.platformkit.tracking.g363_score import FRAME_SCORE_FIELDS, wilson
from scripts.platformkit.tracking.g390_score import evaluator_loss_records, score_sealed
from scripts.platformkit.tracking.g390_sealed_input import HELDOUT_LABELS

BAR_COVERAGE = 0.25
BAR_PRECISION_LOWER = 0.90
BAR_FP_PER_ABSENT = 0.01
HELDOUT_TOTAL = 549
N_GROUPS = 8
EPOCH = "2026-01-01T00:00:00+00:00"
CONTEXT_FIELDS = ("frame_key", "game", "section", "offset_s", "frame_index",
                  "state_ts", "feature_ts", "home", "away", "cpcv_group")


def rows(path: Path) -> list[dict[str, str]]:
    """Read one bounded CSV input."""
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields, records) -> None:
    """Write one LF, ASCII artifact with an explicit field order."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="ascii", newline="\n") as handle:
        writer = csv.DictWriter(handle, fields, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def build_context(frames: list[dict[str, str]]) -> list[dict[str, str]]:
    """Sealed per-tick evaluator context; one state per held-out frame."""
    heldout = [row for row in frames if row["split"] == "heldout"]
    games = sorted({row["game"] for row in heldout})
    out = []
    for row in heldout:
        index = games.index(row["game"])
        minute = int(row["offset_s"]) // 60 + int(row["frame_index"])
        stamp = "2026-01-%02dT%02d:%02d:30+00:00" % (
            1 + index % 28, (minute // 60) % 24, minute % 60)
        out.append({"frame_key": row["frame_key"], "game": row["game"],
                    "section": row["section"], "offset_s": row["offset_s"],
                    "frame_index": row["frame_index"], "state_ts": stamp,
                    "feature_ts": stamp[:17] + "00+00:00", "home": row["game"] + "_H",
                    "away": row["game"] + "_A",
                    "cpcv_group": "g%d" % (index % N_GROUPS)})
    return out


def bars(summary: dict) -> dict[str, object]:
    """Measure the three immutable G390 bars on one arm summary."""
    coverage = summary["tp"] / HELDOUT_TOTAL
    lower = summary["precision_wilson_lo"]
    fp_per_absent = summary["fp"] / HELDOUT_LABELS["ABSENT"]
    return {"coverage_tp_over_549": coverage, "bar_coverage": BAR_COVERAGE,
            "coverage_pass": coverage >= BAR_COVERAGE,
            "precision_wilson_lo": lower, "bar_precision_wilson_lo": BAR_PRECISION_LOWER,
            "precision_pass": lower >= BAR_PRECISION_LOWER,
            "all_fp_per_absent": fp_per_absent, "bar_all_fp_per_absent": BAR_FP_PER_ABSENT,
            "all_fp_pass": fp_per_absent <= BAR_FP_PER_ABSENT,
            "recall_on_visible": summary["tp"] / HELDOUT_LABELS["VISIBLE"],
            "recall_denominator": HELDOUT_LABELS["VISIBLE"],
            "tp": summary["tp"], "fp": summary["fp"],
            "fn": HELDOUT_LABELS["VISIBLE"] - summary["tp"],
            "precision_wilson": list(wilson(summary["tp"], summary["tp"] + summary["fp"]))}


def reproduce(frames_path: Path, reference_path: Path, predictions, archived: Path):
    """Spec clause 9: recompute from archived predictions and diff the sealed rows."""
    from scripts.platformkit.tracking.g363_score import score_arm
    from scripts.platformkit.tracking.g390_sealed_input import load_sealed_input

    sealed = load_sealed_input(frames_path, reference_path)
    summaries, recomputed = {}, []
    for name, arm in (("baseline", "A0"), ("candidate", "A8")):
        one, arm_rows = score_arm(arm, "heldout", sealed.frames, sealed.reference, predictions)
        summaries[name] = one
        recomputed.extend(arm_rows)
    fresh = [{field: str(row[field]) for field in FRAME_SCORE_FIELDS} for row in recomputed]
    if fresh != rows(archived):
        raise ValueError("reproduction-mismatch-against-archived-frame-scores")
    summaries["input_hashes"] = sealed.hashes
    summaries["reproduced_rows"] = len(fresh)
    return summaries, recomputed


def main() -> None:
    """Score once and write every reader-required artifact beside the memo."""
    g389, out, predictions_path, token = (Path(part) for part in sys.argv[1:5])
    frames_path, reference_path = g389 / "frames_v3.csv", g389 / "reference_v3.csv"
    frames = rows(frames_path)
    predictions = rows(predictions_path)
    archived = out / "paired_frame_scores.csv"
    if archived.is_file():
        summary, frame_rows = reproduce(frames_path, reference_path, predictions, archived)
    else:
        summary, frame_rows = score_sealed(
            baseline_arm="A0", candidate_arm="A8", frames_path=frames_path,
            reference_path=reference_path, predictions=predictions, token_path=token,
            input_hashes=None)
        write_csv(archived, FRAME_SCORE_FIELDS, frame_rows)
    context = build_context(frames)
    write_csv(out / "evaluator_context.csv", CONTEXT_FIELDS, context)
    records = []
    for arm in ("A0", "A8"):
        records.extend(evaluator_loss_records(frame_rows, context, arm))
    write_csv(out / "evaluator_records.csv",
              ("arm", "state_key", "split_id", "state_ts", "cluster_id", "p_model",
               "outcome", "loss"), records)
    losses = {arm: [row["loss"] for row in records if row["arm"] == arm] for arm in ("A0", "A8")}
    payload = {
        "denominators": {"all_heldout_keys": HELDOUT_TOTAL, **HELDOUT_LABELS},
        "baseline_A0": bars(summary["baseline"]), "candidate_A8": bars(summary["candidate"]),
        "input_hashes": summary["input_hashes"],
        "evaluator": {"records": len(records), "groups": N_GROUPS,
                      "baseline_loss": sum(losses["A0"]) / len(losses["A0"]),
                      "candidate_loss": sum(losses["A8"]) / len(losses["A8"]),
                      "improvement": (sum(losses["A0"]) / len(losses["A0"]) -
                                      sum(losses["A8"]) / len(losses["A8"]))},
    }
    candidate = payload["candidate_A8"]
    payload["all_bars_pass"] = bool(candidate["coverage_pass"] and
                                    candidate["precision_pass"] and candidate["all_fp_pass"])
    (out / "summary.json").write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n",
                                      encoding="ascii", newline="\n")
    print("G390 SCORED " + json.dumps(payload["candidate_A8"], sort_keys=True))


if __name__ == "__main__":
    sys.exit(main())
