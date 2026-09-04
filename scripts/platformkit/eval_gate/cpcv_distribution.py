"""Distributional CPCV scoring through the protected CPCV leak contract."""
from __future__ import annotations

import copy
import math
from datetime import datetime
from typing import Callable, List, Sequence

from scripts.platformkit.eval_gate import cpcv_engine

DistributionalPredictor = Callable[[List[dict], dict, bool], Sequence[float]]
ScoreFunction = Callable[[Sequence[float], float], dict[str, float]]
_RECORD_FIELDS = frozenset(
    {"split_id", "game_id", "ts", "forecast_samples", "y", "n_train"}
)


def cpcv_evaluate_distributional(
        states: List[dict], predictor: DistributionalPredictor,
        score_fn: ScoreFunction, n_groups: int = 8, n_test_groups: int = 2,
        embargo_days: int = 1, *, strict_redaction: bool = False,
        allow_keys: Sequence[str] = (), debug_disable_purge: bool = False) -> List[dict]:
    """Score empirical forecasts with CPCV's existing splits and symmetric purge.

    The debug switch exists only for a synthetic leak construct. Scored callers
    must retain its default False value.
    """
    ordered = copy.deepcopy(sorted(states, key=lambda state: state["state_ts"]))
    stamps = [datetime.fromisoformat(state["state_ts"]) for state in ordered]
    records: List[dict] = []
    splits = cpcv_engine.cpcv_splits(
        [state["state_ts"] for state in ordered], n_groups=n_groups,
        n_test_groups=n_test_groups, embargo_blocks=0,
    )
    for split_id, (train_idx, test_idx) in enumerate(splits):
        blocked = set() if debug_disable_purge else cpcv_engine._blocked_indices(
            ordered, stamps, test_idx, embargo_days)
        train_indices = [index for index in train_idx if index not in blocked]
        assert not set(train_indices).intersection(blocked), "symmetric purge or embargo violation"
        train_states = [ordered[index] for index in train_indices]
        for index in test_idx:
            test = ordered[index]
            cpcv_engine.assert_vintage(test)
            forecast = tuple(float(value) for value in predictor(
                train_states,
                cpcv_engine._redact(test, allow_keys=allow_keys, strict=strict_redaction),
                True,
            ))
            if not forecast or not all(math.isfinite(value) for value in forecast):
                raise ValueError("predictor returned an empty or non-finite empirical forecast")
            quantities = score_fn(forecast, float(test["outcome"]))
            if not quantities or set(quantities).intersection(_RECORD_FIELDS):
                raise ValueError("score_fn returned no quantities or conflicts with record fields")
            if not all(math.isfinite(float(value)) for value in quantities.values()):
                raise ValueError("score_fn returned a non-finite quantity")
            records.append({
                "split_id": split_id,
                "game_id": test["game_id"],
                "ts": test["state_ts"],
                "forecast_samples": forecast,
                "y": float(test["outcome"]),
                "n_train": len(train_states),
                **{name: float(value) for name, value in quantities.items()},
            })
    return records
