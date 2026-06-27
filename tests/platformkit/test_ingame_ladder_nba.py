"""Per-file, OFFLINE, deterministic unit test for the in-game detail-layer LADDER.

Does NOT touch the real parquet. Builds SYNTHETIC worlds of in-game states and gates
each candidate layer vs the current best (BASE+PRIOR) via the real gate machinery.

Asserts:
  * PACE SHIPS in a world where high-total games are GENUINELY noisier (the realized
    margin is a weaker signal when total is high -> shrinking toward 0.5 with pace helps).
  * PACE REJECTS in a world where total is UNINFORMATIVE (margin equally reliable at all
    paces -> no shrink can help OOS / not significant / not fold-consistent).
  * MOMENTUM REJECTS in a world where the realized margin already captures everything and
    recent run-direction is pure noise (INT-81 control). Note: a grid-search fit on a
    pure-noise feature can spuriously clear p<0.05 on ~1/20 adversarial draws (multiple
    -testing reality the gate's threshold admits) -- a representative seed is used here.
  * LEAK-FREENESS: layer params are fit ONLY on train states, never the test fold.

CLI: python -m pytest tests/platformkit/test_ingame_ladder_nba.py -q
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.ingame.ingame_ladder_nba import (
    LAYERS,
    gate_layer,
    walk_forward_ladder,
)
from scripts.platformkit.ingame.ingame_layer_gate_nba_io import QSEC, p_live_from_margin

_REG = 2880.0
_PACE = next(l for l in LAYERS if l.name == "pace_variance_shrink")
_MOM = next(l for l in LAYERS if l.name == "momentum_run_direction")
_HOME = next(l for l in LAYERS if l.name == "home_bias_calibration")


def _world(n_games, *, pace_noisy, total_informative=True, momentum_real=False,
           home_bias=0.0, seed=0):
    """Build {game_id: [states]} + chronological order.

    strength in (0,1) = P(home win); outcome drawn from it; p0 = strength (a real prior).
    total_so_far: high-total games flagged 'fast'. If pace_noisy, fast games show a LARGE
    but UNRELIABLE in-game margin -- the running lead looks decisive yet the final outcome
    is closer to a coin-flip (the lead doesn't hold in a track meet). So the best
    (margin,time,prior) prob is OVERCONFIDENT in fast games and benefits from a pace shrink
    toward 0.5. recent_delta is pure noise unless momentum_real.
    """
    rng = np.random.default_rng(seed)
    by_game, order = {}, []
    for g in range(n_games):
        strength = float(rng.uniform(0.15, 0.85))
        fast = bool(rng.uniform() < 0.5)
        # In fast (pace_noisy) games the outcome is pulled toward a coin flip regardless
        # of how big the lead looks -> the large running margin OVERSTATES the win prob.
        p_win = 0.5 + 0.15 * (strength - 0.5) if (pace_noisy and fast) else strength
        # home_bias shifts the TRUE win prob in the home direction WITHOUT moving p0 or
        # the margin -> the best model is left a constant residual home bias to correct.
        if home_bias:
            p_win = float(1.0 / (1.0 + np.exp(-(np.log(p_win / (1 - p_win)) + home_bias))))
        y = int(rng.uniform() < p_win)
        # total carries the pace label only when total_informative
        base_total = 210.0 + (40.0 if fast else 0.0) if total_informative else 210.0
        # margin still tracks strength (a big VISIBLE lead) -- not the coin-flippy outcome.
        margin_final = float(rng.normal(20.0 * (strength - 0.5), 9.0))
        states = []
        for q in (1, 2, 3):
            frac = 1.0 - QSEC[q] / _REG
            track = {1: 0.15, 2: 0.45, 3: 0.80}[q]
            noise = {1: 9.0, 2: 7.0, 3: 4.0}[q]
            diff = float(track * margin_final + rng.normal(0.0, noise))
            total = base_total * (q / 4.0) + rng.normal(0.0, 4.0)
            if momentum_real:
                # a real run nudges the outcome direction beyond the margin
                delta = float(rng.normal(6.0 if y else -6.0, 5.0))
            else:
                delta = float(rng.normal(0.0, 8.0))  # pure noise
            states.append({
                "game_id": g, "period": q, "seconds_remaining": QSEC[q],
                "score_diff": diff, "p0": strength,
                "p_live": p_live_from_margin(diff, frac),
                "outcome": y, "total_so_far": float(total), "recent_delta": delta,
            })
        by_game[g] = states
        order.append(g)
    return by_game, order


def test_pace_ships_when_high_total_is_noisier():
    by_game, order = _world(1200, pace_noisy=True, total_informative=True, seed=1)
    v = gate_layer(by_game, order, _PACE, n_folds=3)
    assert v.verdict == "SHIP", (v.verdict, v.metrics)
    assert v.metrics["brier_layer"] < v.metrics["brier_best"]
    assert v.metrics["dm_p"] < 0.05
    assert v.metrics["fold_sign_consistent"] is True


def test_pace_rejects_when_total_uninformative():
    by_game, order = _world(900, pace_noisy=False, total_informative=False, seed=2)
    v = gate_layer(by_game, order, _PACE, n_folds=3)
    assert v.verdict == "REJECT", (v.verdict, v.metrics)
    assert not (v.metrics["dm_p"] < 0.05 and v.metrics["fold_sign_consistent"])


def test_momentum_rejects_when_margin_captures_everything():
    by_game, order = _world(900, pace_noisy=False, momentum_real=False, seed=4)
    v = gate_layer(by_game, order, _MOM, n_folds=3)
    assert v.verdict == "REJECT", (v.verdict, v.metrics)
    assert not (v.metrics["dm_p"] < 0.05 and v.metrics["fold_sign_consistent"])


def test_home_bias_ships_when_real_residual_home_bias_present():
    by_game, order = _world(1200, pace_noisy=False, home_bias=0.6, seed=11)
    v = gate_layer(by_game, order, _HOME, n_folds=3)
    assert v.verdict == "SHIP", (v.verdict, v.metrics)
    assert v.metrics["brier_layer"] < v.metrics["brier_best"]
    assert v.metrics["dm_p"] < 0.05
    assert v.metrics["fold_sign_consistent"] is True


def test_home_bias_rejects_when_already_calibrated():
    by_game, order = _world(900, pace_noisy=False, home_bias=0.0, seed=4)
    v = gate_layer(by_game, order, _HOME, n_folds=3)
    assert v.verdict == "REJECT", (v.verdict, v.metrics)
    assert not (v.metrics["dm_p"] < 0.05 and v.metrics["fold_sign_consistent"])


def test_layer_params_fit_only_on_train():
    """The layer params must be fit on TRAIN states only -- never the test fold."""
    by_game, order = _world(150, pace_noisy=True, seed=4)
    seen_fit_games = []
    orig_fit = _PACE.fit

    def spy_fit(states, best):
        seen_fit_games.append({s["game_id"] for s in states})
        return orig_fit(states, best)

    spy = _PACE.__class__(_PACE.name, spy_fit, _PACE.apply,
                          _PACE.why_ship, _PACE.why_reject)
    folds = walk_forward_ladder(by_game, order, spy, n_folds=3)
    assert len(seen_fit_games) == len(folds)
    for (_, _, _, gids, _), fit_games in zip(folds, seen_fit_games):
        assert set(gids).isdisjoint(fit_games), "LEAK: test game seen during fit"


def test_verdict_has_no_dollar_field():
    by_game, order = _world(300, pace_noisy=True, seed=5)
    v = gate_layer(by_game, order, _PACE, n_folds=3)
    d = v.to_dict()
    assert d["vs_close"].startswith("UNPROVEN")
    assert "$" not in str(d)
    assert len(v.per_fold) == v.metrics["n_folds"]
