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
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Callable, List, Sequence

from scripts.platformkit.cpcv import cpcv_splits
from scripts.platformkit.eval_gate.walkforward import (
    EMBARGO_DAYS,
    PURGE_HOURS,
    _SETTLED_DENY,
    _same_matchup,
    _same_team,
    assert_vintage,
    redact_test_view,
)

Predictor = Callable[[List[dict], dict, bool], float]

# S40b / RT-18: the redaction is now walk_forward's own `redact_test_view`, IMPORTED rather
# than hand-copied, so the two harnesses cannot drift. `_REDACTED_KEYS` is kept as an alias
# for the legacy deny-list because test_redaction_parity_field_by_field reads it.
_REDACTED_KEYS = _SETTLED_DENY


def _redact(state: dict, *, allow_keys: Sequence[str] = (), strict: bool = False) -> dict:
    """Strip the settled-outcome / close keys a test row must never see."""
    return redact_test_view(state, allow_keys=allow_keys, strict=strict)


def _purged(train_state: dict, train_ts: datetime, test_state: dict,
            test_ts: datetime, embargo_days: int) -> bool:
    """True if this train row must be dropped for this test row (both sides)."""
    gap = abs(train_ts - test_ts)
    if abs((train_ts.date() - test_ts.date()).days) <= embargo_days:
        return True                                    # calendar-day embargo
    if _same_matchup(train_state, test_state) and gap < timedelta(days=EMBARGO_DAYS):
        return True                                    # same matchup near boundary
    return _same_team(train_state, test_state) and gap < timedelta(hours=PURGE_HOURS)


def _blocked_indices(states: List[dict], stamps: List[datetime], test_idx: Sequence[int],
                     embargo_days: int) -> set[int]:
    """Index-equivalent symmetric purge, avoiding a corpus-size squared scan."""
    by_day, by_team, by_matchup = defaultdict(list), defaultdict(list), defaultdict(list)
    for index, (state, stamp) in enumerate(zip(states, stamps)):
        by_day[stamp.date()].append(index)
        for team in {state["home"], state["away"]}:
            by_team[team].append((stamp, index))
        by_matchup[frozenset((state["home"], state["away"]))].append((stamp, index))

    def nearby(entries: list[tuple[datetime, int]], stamp: datetime, window: timedelta) -> set[int]:
        lo = bisect_left(entries, (stamp - window, -1))
        hi = bisect_right(entries, (stamp + window, len(states)))
        return {index for candidate, index in entries[lo:hi] if abs(candidate - stamp) < window}

    blocked: set[int] = set()
    for index in test_idx:
        state, stamp = states[index], stamps[index]
        for offset in range(-embargo_days, embargo_days + 1):
            blocked.update(by_day[stamp.date() + timedelta(days=offset)])
        blocked.update(nearby(by_matchup[frozenset((state["home"], state["away"]))], stamp,
                              timedelta(days=EMBARGO_DAYS)))
        for team in {state["home"], state["away"]}:
            blocked.update(nearby(by_team[team], stamp, timedelta(hours=PURGE_HOURS)))
    return blocked


def cpcv_evaluate(states: List[dict], predictor: Predictor, n_groups: int = 8,
                  n_test_groups: int = 2, embargo_days: int = 1,
                  *, strict_redaction: bool = False,
                  allow_keys: Sequence[str] = ()) -> List[dict]:
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
        blocked = _blocked_indices(ordered, stamps, test_idx, embargo_days)
        train_indices = [i for i in train_idx if i not in blocked]
        assert not set(train_indices).intersection(blocked), "symmetric purge or embargo violation"
        train_states = [ordered[i] for i in train_indices]
        for i in test_idx:
            test = ordered[i]
            assert_vintage(test)
            p = predictor(train_states,
                          _redact(test, allow_keys=allow_keys, strict=strict_redaction),
                          True)
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
