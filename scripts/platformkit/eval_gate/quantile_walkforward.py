"""Continuous-quantile extension that uses walkforward's leak contract unchanged."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta
from typing import Callable, List, Sequence

from scripts.platformkit.eval_gate.walkforward import (
    EMBARGO_DAYS,
    PURGE_HOURS,
    _same_matchup,
    _same_team,
    assert_vintage,
    redact_test_view,
)

QuantilePredictor = Callable[[List[dict], List[dict]], List[dict]]
QuantileScorer = Callable[[dict, dict], dict]


def _purged(train: dict, test: dict, embargo_days: int) -> bool:
    """Apply the shared walk-forward team and matchup exclusions symmetrically."""
    train_ts, test_ts = datetime.fromisoformat(train["state_ts"]), datetime.fromisoformat(test["state_ts"])
    gap = abs(train_ts - test_ts)
    return (abs((train_ts.date() - test_ts.date()).days) <= embargo_days
            or (_same_matchup(train, test) and gap < timedelta(days=EMBARGO_DAYS))
            or (_same_team(train, test) and gap < timedelta(hours=PURGE_HOURS)))


def quantile_walk_forward(states: List[dict], fit_predict: QuantilePredictor,
                          score: QuantileScorer, *, test_filter: Callable[[dict], bool],
                          embargo_days: int = 1, strict_redaction: bool = True,
                          allow_keys: Sequence[str] = ()) -> List[dict]:
    """Score a held-out block from only its purged, strictly earlier train states.

    This adapter retains ``walk_forward.py``'s timestamp ordering, vintage
    assertion, redaction, matchup embargo, and team purge for continuous
    quantiles, which its probability-only public return schema cannot carry.
    """
    ordered = copy.deepcopy(sorted(states, key=lambda state: state["state_ts"]))
    tests = [state for state in ordered if test_filter(state)]
    if not tests:
        raise ValueError("quantile evaluator received no held-out states")
    first_test_ts = datetime.fromisoformat(tests[0]["state_ts"])
    train = [state for state in ordered if datetime.fromisoformat(state["state_ts"]) < first_test_ts]
    first_for_home = {}
    for test in tests:
        first_for_home.setdefault(test["home"], test)
    train = [state for state in train if not (_purged(state, tests[0], embargo_days)
             or _purged(state, first_for_home.get(state["home"], tests[0]), embargo_days))]
    if not train:
        raise ValueError("symmetric purge emptied quantile evaluator training states")
    if any(datetime.fromisoformat(state["state_ts"]) >= first_test_ts for state in train):
        raise AssertionError("quantile evaluator train state is not strictly earlier")
    views = []
    for test in tests:
        assert_vintage(test)
        views.append(redact_test_view(test, allow_keys=allow_keys, strict=strict_redaction))
    predictions = fit_predict(train, views)
    if len(predictions) != len(tests):
        raise ValueError("quantile predictor count does not match evaluator test states")
    records = []
    for test, prediction in zip(tests, predictions):
        records.append({"game_id": test["game_id"], "ts": test["state_ts"], "n_train": len(train),
                        "evaluator_output": True, **score(test, prediction)})
    return records
