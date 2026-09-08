"""Vector empirical distributions through the shared CPCV leak contract."""

from __future__ import annotations

import copy
import math
from datetime import datetime
from typing import Any, Callable, List, Mapping, Sequence

from scripts.platformkit.eval_gate import cpcv_engine

VectorForecast = Mapping[str, Any]
BatchPredictor = Callable[[List[dict], List[dict]], List[VectorForecast]]
VectorScorer = Callable[[VectorForecast, Sequence[float]], Mapping[str, float]]


def cpcv_evaluate_vector_distributional(
    states: List[dict], fit_predict: BatchPredictor, score_fn: VectorScorer,
    n_groups: int = 5, n_test_groups: int = 1, embargo_days: int = 1,
    *, strict_redaction: bool = False, allow_keys: Sequence[str] = (),
) -> List[dict]:
    """Emit one scored vector-distribution record per CPCV test state."""
    ordered = copy.deepcopy(sorted(states, key=lambda state: state["state_ts"]))
    stamps = [datetime.fromisoformat(state["state_ts"]) for state in ordered]
    splits = cpcv_engine.cpcv_splits(
        [state["state_ts"] for state in ordered], n_groups=n_groups,
        n_test_groups=n_test_groups, embargo_blocks=0,
    )
    records: List[dict] = []
    for split_id, (train_idx, test_idx) in enumerate(splits):
        blocked = cpcv_engine._blocked_indices(ordered, stamps, test_idx, embargo_days)
        train_indices = [index for index in train_idx if index not in blocked]
        train = [ordered[index] for index in train_indices]
        assert not set(train_indices).intersection(blocked), "symmetric purge or embargo violation"
        tests = [ordered[index] for index in test_idx]
        views = []
        for test in tests:
            cpcv_engine.assert_vintage(test)
            test_view = dict(test)
            test_view.pop("outcome_vector", None)
            views.append(cpcv_engine._redact(test_view, allow_keys=allow_keys, strict=strict_redaction))
        forecasts = fit_predict(train, views)
        if len(forecasts) != len(tests):
            raise ValueError("vector predictor count does not match test states")
        for test, forecast in zip(tests, forecasts):
            scores = score_fn(forecast, test["outcome_vector"])
            if not scores or not all(math.isfinite(float(value)) for value in scores.values()):
                raise ValueError("vector score callback must return finite numeric values")
            records.append({
                "split_id": split_id, "game_id": test["game_id"], "ts": test["state_ts"],
                "stable_key": test["stable_key"], "n_train": len(train),
                "forecast": forecast, "scores": dict(scores), "evaluator_output": True,
            })
    return records
