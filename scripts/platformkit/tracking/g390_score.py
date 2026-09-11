"""G390 scorer: native guard, landed G363 detection score, and CPCV loss archive."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.tracking.g363_score import score_arm
from scripts.platformkit.tracking.g390_receipt import begin_scoring
from scripts.platformkit.tracking.g390_sealed_input import HELDOUT_LABELS, load_sealed_input

HELDOUT_TOTAL = 549


def _assert_denominators(summary: Mapping[str, object]) -> None:
    expected = {"n_frames": HELDOUT_TOTAL, "n_visible": HELDOUT_LABELS["VISIBLE"],
                "n_absent": HELDOUT_LABELS["ABSENT"], "n_unknown": HELDOUT_LABELS["UNKNOWN"]}
    actual = {name: summary.get(name) for name in expected}
    if actual != expected:
        raise ValueError("scoring-denominator-mismatch " + repr(actual))


def score_sealed(
    *,
    baseline_arm: str,
    candidate_arm: str,
    frames_path: Path,
    reference_path: Path,
    predictions: Sequence[dict[str, str]],
    token_path: Path,
    input_hashes: Mapping[str, str],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Score once through G363 after the immutable receipt closes repeat scoring."""
    begin_scoring(Path(token_path))
    inputs = load_sealed_input(Path(frames_path), Path(reference_path),
                               expected_hashes=input_hashes)
    baseline, baseline_rows = score_arm(baseline_arm, "heldout", inputs.frames,
                                        inputs.reference, predictions)
    candidate, candidate_rows = score_arm(candidate_arm, "heldout", inputs.frames,
                                          inputs.reference, predictions)
    _assert_denominators(baseline)
    _assert_denominators(candidate)
    for summary in (baseline, candidate):
        summary["coverage_denominator"] = HELDOUT_TOTAL
        summary["coverage_tp_over_549"] = summary["coverage"]
        summary["recall_denominator"] = HELDOUT_LABELS["VISIBLE"]
        summary["all_fp_denominator"] = HELDOUT_LABELS["ABSENT"]
        summary["all_fp_per_absent"] = summary["fp_per_absent"]
    return {"baseline": baseline, "candidate": candidate,
            "input_hashes": inputs.hashes}, baseline_rows + candidate_rows


def _states(
    rows: Sequence[Mapping[str, object]], context: Mapping[str, Mapping[str, str]], arm: str,
) -> list[dict[str, object]]:
    states: list[dict[str, object]] = []
    for row in rows:
        if row["arm"] != arm:
            continue
        key = str(row["frame_key"])
        source = context.get(key)
        if source is None:
            raise ValueError("missing-evaluator-context " + key)
        required = ("state_ts", "feature_ts", "home", "away", "cpcv_group")
        if any(not source.get(name) for name in required):
            raise ValueError("incomplete-evaluator-context " + key)
        states.append({
            "game_id": "g390:" + key,
            "state_ts": source["state_ts"],
            "home": source["home"],
            "away": source["away"],
            "outcome": int(row["label"] == "VISIBLE"),
            "devig_close_prob": 0.5,
            "features": {"detector_probability": float(int(row["n_predictions"]) > 0)},
            "feature_avail": {"detector_probability": source["feature_ts"]},
            "cpcv_group": source["cpcv_group"],
        })
    keys = [state["game_id"] for state in states]
    if len(keys) != len(set(keys)):
        raise ValueError("one-evaluator-state-per-tick-refused")
    return states


def evaluator_loss_records(
    rows: Sequence[Mapping[str, object]], context_rows: Sequence[Mapping[str, str]], arm: str,
) -> list[dict[str, object]]:
    """Archive only loss values derived from shared CPCV evaluator records."""
    context = {str(row["frame_key"]): row for row in context_rows}
    if len(context) != len(context_rows):
        raise ValueError("duplicate-evaluator-context-key")
    states = _states(rows, context, arm)
    groups = {state["cpcv_group"] for state in states}
    if len(groups) != 8:
        raise ValueError("sealed-cpcv-group-count-required-8")

    def predict(_train: list[dict], test: dict, _inside: bool) -> float:
        return float(test["features"]["detector_probability"])

    records = cpcv_evaluate(states, predict, n_groups=8, n_test_groups=2, embargo_days=1,
                            strict_redaction=True, allow_keys=("cpcv_group",),
                            group_key="cpcv_group", guard_state_keys=True)
    return [{"arm": arm, "state_key": record["game_id"], "split_id": record["split_id"],
             "state_ts": record["ts"], "cluster_id": record["game_id"].split(":", 1)[1],
             "p_model": record["p_model"], "outcome": record["y"],
             "loss": (record["p_model"] - record["y"]) ** 2}
            for record in records]
