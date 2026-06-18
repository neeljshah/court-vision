"""Leak-free walk-forward backtest harness -- the eval gate's long pole (blueprint N1).

Self-contained (stdlib only). This is where leak-freeness is ENFORCED, not assumed:
  - expanding window: train only on states strictly before the test state's timestamp (no lookahead);
  - purge: drop same-team games within 48h of the test game (kills back-to-back autocorrelation);
  - embargo: drop the same matchup within 3 days of the boundary (rolling-window spillover);
  - vintage alignment: every feature must be known strictly before the prediction time;
  - feature selection / tuning MUST happen inside the window -> the `select_inside` flag is recorded,
    and a caller that selects on the full history (select_inside=False) is surfaced so the gate fails.

predict_fn(train_states, test_state, select_inside) -> p in [0,1]. The harness never trains a model;
it orchestrates the leak-free split and collects per-state probabilities for scoring (scoring.py).
Calibration-first; no dollar edge is computed.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Tuple

PURGE_HOURS = 48
EMBARGO_DAYS = 3


def _teams(s: dict) -> set:
    return {s["home"], s["away"]}


def _same_team(a: dict, b: dict) -> bool:
    return len(_teams(a) & _teams(b)) > 0


def _same_matchup(a: dict, b: dict) -> bool:
    return _teams(a) == _teams(b)


def assert_vintage(s: dict) -> None:
    """LEAK GUARD: every feature must be known strictly before the prediction time."""
    for f, avail in s.get("feature_avail", {}).items():
        assert avail < s["state_ts"], (
            f"LEAK: feature {f} availability {avail} >= state_ts {s['state_ts']} "
            f"in {s.get('game_id')}"
        )


@dataclass
class WalkForwardResult:
    records: List[dict]          # per-state {game_id, ts, p_model, p_close, y}
    select_inside: bool          # recorded; False -> the gate must FAIL the run
    n_train_sizes: List[int]     # train-set size at each step (for diagnostics)


def walk_forward(states: List[dict],
                 predict_fn: Callable[[List[dict], dict, bool], float],
                 select_inside: bool = True) -> WalkForwardResult:
    """Expanding-window walk-forward with purge + embargo + vintage. Returns per-state records."""
    states = sorted(states, key=lambda s: s["state_ts"])
    records: List[dict] = []
    sizes: List[int] = []
    for i, test in enumerate(states):
        t = datetime.fromisoformat(test["state_ts"])
        train: List[dict] = []
        for s in states[:i]:
            ts = datetime.fromisoformat(s["state_ts"])
            if ts >= t:                                   # never look ahead (tie-safe)
                continue
            if _same_matchup(s, test) and (t - ts) < timedelta(days=EMBARGO_DAYS):
                continue                                  # embargo same matchup near boundary
            if _same_team(s, test) and (t - ts) < timedelta(hours=PURGE_HOURS):
                continue                                  # purge same-team back-to-back
            train.append(s)
        assert_vintage(test)                              # defense in depth (schema also checks)
        p = predict_fn(train, test, select_inside)
        assert 0.0 <= p <= 1.0, f"predict_fn returned {p} out of [0,1]"
        records.append({
            "game_id": test["game_id"], "ts": test["state_ts"],
            "p_model": float(p), "p_close": test.get("devig_close_prob"),
            "y": int(test["outcome"]),
        })
        sizes.append(len(train))
    return WalkForwardResult(records, bool(select_inside), sizes)
