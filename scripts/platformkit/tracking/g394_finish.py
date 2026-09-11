"""G394 finish: score the one A10 pass beside archived A8 and A0 on the fixed set.

No threshold sweep, no re-selection and no second inference. A8 and A0 are archived
baseline rescores from G390's saved predictions; only A10 came from fresh detector
inference. Every one of the 549 planned held-out keys stays in the denominator.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, "/workspace/wt/a7")

from scripts.platformkit.tracking.g363_score import (  # noqa: E402
    ARM_FIELDS, FRAME_SCORE_FIELDS, score_arm)
from scripts.platformkit.tracking.g390_score import evaluator_loss_records  # noqa: E402
from scripts.platformkit.tracking.g390_sealed_input import load_sealed_input  # noqa: E402
from scripts.platformkit.tracking.g394_prepare import FROZEN_BARS, all_planned_states  # noqa: E402
from scripts.platformkit.tracking.g394_run import (  # noqa: E402
    G389, LANE, SCRATCH, rows, sha256_file, write_csv)

G390 = LANE / "docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11"
EVIDENCE = LANE / "docs/evidence/tracking/g394_ball_person_negatives_2026-09-11"
PRED_FIELDS = ("arm", "inherits", "split", "frame_key", "rank", "x", "y", "w", "h",
               "score", "tick_history", "source", "imgsz", "conf")
LOSS_FIELDS = ("arm", "state_key", "split_id", "state_ts", "cluster_id", "p_model",
               "outcome", "loss")
ARMS = ("A0", "A8", "A10")


def bars(summary: dict) -> dict[str, object]:
    """Measure each unmoved bar against one arm summary."""
    return {
        "c0": summary["coverage"], "c0_bar": FROZEN_BARS["c0_min"],
        "c0_met": summary["coverage"] >= FROZEN_BARS["c0_min"],
        "precision_wilson_lo": summary["precision_wilson_lo"],
        "precision_wilson_lo_bar": FROZEN_BARS["precision_wilson_lower_min"],
        "precision_met": (summary["precision_wilson_lo"]
                          >= FROZEN_BARS["precision_wilson_lower_min"]),
        "all_fp_per_absent": summary["fp_per_absent"],
        "all_fp_per_absent_bar": FROZEN_BARS["all_fp_per_absent_max"],
        "all_fp_met": (summary["fp_per_absent"] or 0.0) <= FROZEN_BARS["all_fp_per_absent_max"],
    }


def load_predictions() -> list[dict[str, str]]:
    """Archived A0/A8 rows from G390 plus the one fresh A10 pass."""
    archived = [row for row in rows(G390 / "predictions_paired.csv") if row["arm"] in ("A0", "A8")]
    candidate = rows(SCRATCH / "predictions_A10.csv")
    if any(row["arm"] != "A10" for row in candidate):
        raise ValueError("candidate-arm-identity-mismatch")
    return archived + candidate


def score(predictions: list[dict[str, str]]) -> tuple[dict, list[dict], list[dict]]:
    """Score every arm through the landed G363 path on the settled native reference."""
    sealed = load_sealed_input(G389 / "frames_v3.csv", G389 / "reference_v3.csv")
    refs = {key: {"label": row["label"], "cx": row["cx"], "cy": row["cy"],
                  "diameter": row["diameter"]} for key, row in sealed.reference.items()}
    summaries, frame_rows = {}, []
    for arm in ARMS:
        summary, arm_rows = score_arm(arm, "heldout", sealed.frames, refs, predictions)
        expected = {"n_frames": FROZEN_BARS["heldout_states"],
                    "n_visible": FROZEN_BARS["visible_states"],
                    "n_absent": FROZEN_BARS["absent_states"],
                    "n_unknown": FROZEN_BARS["unknown_states"]}
        if {name: summary[name] for name in expected} != expected:
            raise ValueError("scoring-denominator-mismatch " + arm)
        summary.pop("per_game", None)
        summaries[arm] = summary
        frame_rows.extend(arm_rows)
    planned = [row["frame_key"] for row in sealed.frames if row["split"] == "heldout"]
    states = all_planned_states(planned, [row for row in predictions if row["arm"] == "A10"])
    missing = [row["frame_key"] for row in states if row.get("status") == "MISSING_INFERENCE"]
    return {"arms": summaries, "input_hashes": sealed.hashes,
            "planned_heldout_keys": len(planned),
            "a10_keys_without_detection": len(missing)}, frame_rows, states


def losses(frame_rows: list[dict]) -> list[dict]:
    """Archive the Q9 per-state paired-loss series for both compared arms."""
    context = rows(G390 / "evaluator_context.csv")
    records: list[dict] = []
    for arm in ("A8", "A10"):
        records.extend(evaluator_loss_records(frame_rows, context, arm))
    return records


def main() -> None:
    """Score once, archive every per-key record, and write the evidence tables."""
    ledger = json.loads((SCRATCH / "launch_accounting.json").read_text(encoding="ascii"))
    if not (ledger.get("training_charged") and ledger.get("candidate_inference_charged")):
        raise ValueError("uncharged-launch-refused")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    predictions = load_predictions()
    summary, frame_rows, states = score(predictions)
    summary["launch_accounting"] = ledger
    summary["bars"] = {arm: bars(summary["arms"][arm]) for arm in ARMS}
    summary["audit"] = json.loads((SCRATCH / "audit_counts.json").read_text(encoding="ascii"))
    summary["candidates"] = json.loads(
        (SCRATCH / "candidates_report.json").read_text(encoding="ascii"))
    summary["final_weights_sha256"] = sha256_file(SCRATCH / "runs/a10/weights/last.pt")
    write_csv(EVIDENCE / "predictions.csv", PRED_FIELDS, predictions)
    write_csv(EVIDENCE / "paired_frame_scores.csv", FRAME_SCORE_FIELDS, frame_rows)
    write_csv(EVIDENCE / "results.csv", ARM_FIELDS,
              [{name: summary["arms"][arm].get(name, "") for name in ARM_FIELDS} for arm in ARMS])
    write_csv(EVIDENCE / "heldout_states.csv", ("frame_key", "status"),
              [{"frame_key": row["frame_key"],
                "status": row.get("status", "OBSERVED")} for row in states])
    write_csv(EVIDENCE / "evaluator_records.csv", LOSS_FIELDS, losses(frame_rows))
    (EVIDENCE / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii", newline="\n")
    print("G394 SCORE COMPLETE " + json.dumps(
        {arm: {"tp": summary["arms"][arm]["tp"], "fp": summary["arms"][arm]["fp"],
               "c0": summary["arms"][arm]["coverage"]} for arm in ARMS}, sort_keys=True),
        flush=True)


if __name__ == "__main__":
    sys.exit(main())
