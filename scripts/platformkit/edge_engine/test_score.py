"""Per-file test for edge_engine.score. Run ONLY this file (full suite freezes).

  cd /c/Users/neelj/nba-ai-system && \
  C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
  scripts/platformkit/edge_engine/test_score.py -q
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from scripts.platformkit.edge_engine.score import (  # noqa: E402
    MAX_LOGIT_ADJ, ScoreResult, SignalRow, score_candidate,
)


def _ts(i: int, hour: int) -> str:
    """Distinct ISO timestamp per game so walk_forward orders them and purge/embargo
    never collapse the sample (each game a unique matchup, days apart)."""
    return (datetime(2026, 1, 1) + timedelta(days=i, hours=hour)).isoformat()


def _make_states(n: int, signal_vals, signal_effect: float, seed: int = 0):
    """Build n leak-free states with a Shin-devigged close prob and outcomes.

    The outcome is drawn from a TRUE prob = sigmoid(logit(close) + signal_effect * value),
    so when signal_effect != 0 the signal genuinely carries information the close lacks;
    when signal_effect == 0 the value is pure noise and must REJECT.
    Each game is a UNIQUE matchup on its own day (no purge/embargo collisions).
    """
    rng = np.random.default_rng(seed)
    states, rows = [], []
    for i in range(n):
        pc = float(np.clip(rng.uniform(0.30, 0.70), 1e-3, 1 - 1e-3))
        v = float(signal_vals[i])
        true_logit = np.log(pc / (1 - pc)) + signal_effect * v
        true_p = 1.0 / (1.0 + np.exp(-true_logit))
        y = int(rng.random() < true_p)
        gid = f"G{i:04d}"
        states.append({
            "game_id": gid, "home": f"H{i}", "away": f"A{i}",
            "state_ts": _ts(i, 18), "outcome": y, "devig_close_prob": pc,
            "season": "2026",
        })
        rows.append(SignalRow(game_id=gid, value=v,
                              available_ts=_ts(i, 10),     # known 8h before the line move
                              line_move_ts=_ts(i, 17)))
    return states, rows


def test_pure_noise_signal_rejects():
    rng = np.random.default_rng(1)
    vals = rng.standard_normal(400)
    states, rows = _make_states(400, vals, signal_effect=0.0, seed=7)
    r = score_candidate(states, rows, min_n=200)
    assert isinstance(r, ScoreResult)
    assert r.verdict == "REJECT"          # noise must never SHIP -- honest null
    assert r.n_subset == 400


def test_genuinely_informative_signal_can_ship():
    rng = np.random.default_rng(2)
    vals = rng.standard_normal(500)
    # strong, clean effect the close does not contain -> should beat the close significantly
    states, rows = _make_states(500, vals, signal_effect=1.4, seed=3)
    r = score_candidate(states, rows, min_n=200)
    assert r.verdict == "SHIP"
    assert r.bss > 0.0
    assert r.dm_p < 0.05
    assert "SHIP" in r.reason


def test_small_subset_rejects_for_insufficient_n():
    rng = np.random.default_rng(4)
    vals = rng.standard_normal(50)
    states, rows = _make_states(50, vals, signal_effect=1.4, seed=5)
    r = score_candidate(states, rows, min_n=200)
    assert r.verdict == "REJECT"
    assert "min_n" in r.reason
    assert r.n_subset == 50


def test_off_subset_games_do_not_leak_signal():
    """A game whose FACT became available AFTER the line move must be excluded from the
    confirmed-before subset (no leak)."""
    rng = np.random.default_rng(6)
    vals = rng.standard_normal(300)
    states, rows = _make_states(300, vals, signal_effect=1.4, seed=8)
    # Poison the last 100 rows: availability AFTER the line move -> not confirmed-before.
    poisoned = rows[:200] + [
        SignalRow(game_id=r.game_id, value=r.value,
                  available_ts=_ts(i + 200, 19),   # 2h AFTER the 17:00 line move
                  line_move_ts=_ts(i + 200, 17))
        for i, r in enumerate(rows[200:])
    ]
    r = score_candidate(states, poisoned, min_n=150)
    # only the 200 confirmed-before games may enter the scored subset
    assert r.n_subset == 200


def test_leak_planted_row_trips_vintage_guard():
    """If a confirmed-before row is mislabeled so the feature is stamped at/after the
    line-move state_ts, the walk_forward vintage assertion must fire."""
    states, rows = _make_states(220, np.zeros(220), signal_effect=0.0, seed=9)
    bad = list(rows)
    # available == line_move (not strictly before) -> confirmed_before() False, so it would
    # be dropped from the subset; force a true leak by directly stamping a state instead.
    from scripts.platformkit.edge_engine.score import _build_states
    sig = {r.game_id: r for r in bad}
    enriched = _build_states(states, sig)
    # Hand-plant a leak: feature available AT the state_ts (not strictly before).
    enriched[0]["signal_value"] = 1.0
    enriched[0]["feature_avail"] = {"signal_value": enriched[0]["state_ts"]}
    from scripts.platformkit.eval_gate.walkforward import assert_vintage
    with pytest.raises(AssertionError) as e:
        assert_vintage(enriched[0])
    assert "LEAK" in str(e.value)


def test_bounded_adjustment_constant():
    assert MAX_LOGIT_ADJ == 1.0
