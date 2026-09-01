"""Combinatorial purged walk-forward engine -- CPCV splits, walk_forward contract.

Reuses cpcv.py's ``cpcv_splits`` (read-only) for the train/test index paths and
walkforward.py's leak contract UNCHANGED -- ``assert_vintage``, ``_same_team``,
``_same_matchup``, ``PURGE_HOURS`` and ``EMBARGO_DAYS`` are imported, never
re-implemented. A test row never sees its own settled outcome or the closing
price used to grade it, and every feature must be known strictly before the
prediction time.

Where this DIFFERS from walk_forward, and why:
  - walk_forward's train set is strictly the past. A CPCV path's train set
    straddles the test block on BOTH sides, so every window here is symmetric
    (``abs`` on the delta): the same team's game the night AFTER the test game
    is already settled, which is exactly the leak the purge exists to kill.
  - ``cpcv_splits`` groups by DISTINCT TIMESTAMP, so its own purge only drops
    exact-timestamp ties and its embargo is forward-only. It is disabled here
    (``embargo_blocks=0``) and replaced by a symmetric calendar-day window plus
    walk_forward's own team / matchup rules.

Measurement tooling (calibration and Brier distributions across paths). It
never computes or claims a betting edge.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta
from typing import Callable, List

from scripts.platformkit.cpcv import cpcv_splits
from scripts.platformkit.eval_gate.walkforward import (
    EMBARGO_DAYS,
    PURGE_HOURS,
    _same_matchup,
    _same_team,
    assert_vintage,
)

Predictor = Callable[[List[dict], dict, bool], float]

# Hand-copied from walk_forward's inline test_view filter -- there is no
# importable constant to reuse. test_redaction_parity_field_by_field pins the
# two together by diffing the ACTUAL view each harness hands its predictor, so
# drift in either direction fails the test rather than leaking silently.
_REDACTED_KEYS = ("outcome", "devig_close_prob", "truth_wp", "index")


def _redact(state: dict) -> dict:
    """Strip the settled-outcome / close keys a test row must never see."""
    return {k: v for k, v in state.items() if k not in _REDACTED_KEYS}


def _purged(train_state: dict, train_ts: datetime, test_state: dict,
            test_ts: datetime, embargo_days: int) -> bool:
    """True if this train row must be dropped for this test row (both sides)."""
    gap = abs(train_ts - test_ts)
    if abs((train_ts.date() - test_ts.date()).days) <= embargo_days:
        return True                                    # calendar-day embargo
    if _same_matchup(train_state, test_state) and gap < timedelta(days=EMBARGO_DAYS):
        return True                                    # same matchup near boundary
    return _same_team(train_state, test_state) and gap < timedelta(hours=PURGE_HOURS)


def cpcv_evaluate(states: List[dict], predictor: Predictor, n_groups: int = 8,
                  n_test_groups: int = 2, embargo_days: int = 1) -> List[dict]:
    """Combinatorial purged cross-validation over walk_forward-shaped states.

    ``states`` are walk_forward-shaped dicts (game_id, state_ts, home, away,
    outcome, devig_close_prob, features, feature_avail, ...). ``predictor`` has
    walk_forward's predict_fn signature: (train_states, test_view,
    select_inside) -> p in [0, 1]. Returns per-test-row records shaped like
    walk_forward's (game_id, ts, p_model, p_close, y) plus split_id and n_train,
    so per-path matrices feed a PBO estimator later. ``n_train`` is the
    diagnostic that surfaces a path whose train set the purges emptied.
    """
    # Deep copy mirrors walk_forward's mutation guard (red-team 2026-09-01).
    ordered = copy.deepcopy(sorted(states, key=lambda s: s["state_ts"]))
    stamps = [datetime.fromisoformat(s["state_ts"]) for s in ordered]

    records: List[dict] = []
    splits = cpcv_splits([s["state_ts"] for s in ordered], n_groups=n_groups,
                         n_test_groups=n_test_groups, embargo_blocks=0)
    for split_id, (train_idx, test_idx) in enumerate(splits):
        train_states = [
            ordered[i] for i in train_idx
            if not any(_purged(ordered[i], stamps[i], ordered[j], stamps[j], embargo_days)
                       for j in test_idx)
        ]
        for i in test_idx:
            test = ordered[i]
            assert_vintage(test)
            p = predictor(train_states, _redact(test), True)
            if not 0.0 <= p <= 1.0:
                raise ValueError(f"predictor returned {p} out of [0,1]")
            records.append({
                "split_id": split_id, "game_id": test["game_id"], "ts": test["state_ts"],
                "p_model": float(p), "p_close": test.get("devig_close_prob"),
                "y": int(test["outcome"]), "n_train": len(train_states),
            })
    # cpcv_splits raises "No usable CPCV path" itself when it yields nothing,
    # and every yielded path has a non-empty test index, so records is non-empty.
    return records
