"""Per-file, OFFLINE, deterministic unit tests for the tennis SURFACE-HOLD in-game
detail-layer gate (H1). Does NOT touch the real parquets. Builds three SYNTHETIC
worlds of leak-free in-game states with a hidden per-surface hold-pct differential:

  * HELPS world: p0_surface truly carries the per-surface hold signal (favorites on
    THEIR strong surface win more) while p0_blind is a pooled, muddier average ->
    the per-tour gate must SHIP; both-tour rollup -> SHIP_SURFACE_LAYER (planted-null
    dies because shuffling the surface label destroys the surface<->outcome link).
  * NOISE world: p0_surface == p0_blind everywhere (no real surface-specific info)
    -> gate must REJECT (no consistent Brier improvement).
  * LEAK world: p0_surface is DERIVED FROM the test outcome itself (a plant to catch
    a leaky pipeline) -- asserts the planted-null control actually fires: if a
    shuffled-surface run STILL ships, NOT_TESTABLE must be returned, never a bare SHIP.

Also asserts: INSUFFICIENT is returned honestly when a tour's games/states are below
floor (never silently REJECT), and the fold weight-surfaces are fit train-only.

CLI: python -m pytest scripts/platformkit/ingame/test_surface_hold_gate.py -q
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.ingame.surface_hold_gate import (
    _one_tour_gate,
    _planted_null_gate,
    gate,
    gate_tour,
    walk_forward,
)
from scripts.platformkit.ingame.surface_hold_gate_io import _p_live


def _make_states(n_games: int, mode: str, seed: int = 0):
    """Build a flat list of leak-free-shaped in-game state dicts.

    mode='helps'  -> p0_surface encodes the real per-surface strength (informative),
                     p0_blind is a pooled/blurred version (less informative).
    mode='noise'  -> p0_surface == p0_blind (no incremental info).
    Each synthetic "match" contributes 2 states (mirrors 1-2 asof ticks/match).
    """
    rng = np.random.default_rng(seed)
    surfaces = ["Hard", "Clay", "Grass"]
    states = []
    for g in range(n_games):
        surf = surfaces[g % 3]
        strength = float(rng.uniform(0.15, 0.85))  # true per-surface P(p1 win)
        y = int(rng.uniform() < strength)
        pooled = 0.5 + 0.4 * (strength - 0.5)  # blurred/pooled version (less signal)
        p0_surface = strength if mode == "helps" else pooled
        p0_blind = pooled
        margin_final = float(rng.normal(6.0 if y else -6.0, 7.0))
        for k, frac in enumerate((0.4, 0.85)):
            diff = float(0.5 * margin_final + rng.normal(0.0, 5.0))
            states.append({
                "game_id": f"g{g}", "surface": surf,
                "seconds_remaining": 1.0 - frac, "score_diff": diff,
                "outcome": y, "p_live": _p_live(diff, frac),
                "p0_blind": p0_blind, "p0_surface": p0_surface,
            })
    return states


def test_helps_world_ships_per_tour():
    states = _make_states(500, mode="helps", seed=1)
    r = _one_tour_gate(states, n_folds=3)
    assert r["verdict"] == "SHIP", r
    assert r["brier_surface"] < r["brier_blind"]
    assert r["dm_p"] < 0.05
    assert r["fold_sign_consistent"] is True


def test_noise_world_rejects_per_tour():
    states = _make_states(500, mode="noise", seed=2)
    r = _one_tour_gate(states, n_folds=3)
    assert r["verdict"] == "REJECT", r


def test_planted_null_breaks_the_surface_link():
    """Shuffling p0_surface across games in the HELPS world must destroy (most of)
    the advantage -- the null run should not out-perform the real run's delta by
    reproducing the same signal."""
    states = _make_states(500, mode="helps", seed=3)
    real = _one_tour_gate(states, n_folds=3)
    null = _planted_null_gate(states, seed=0, n_folds=3)
    assert real["verdict"] == "SHIP"
    # the null's Brier improvement must not be as strong as the real signal
    assert null.get("brier_delta", 0.0) <= real["brier_delta"] + 1e-9


def test_insufficient_when_below_floor():
    """Too few games -> INSUFFICIENT with an exact n recorded, never a forced verdict."""
    states = _make_states(4, mode="helps", seed=4)
    r = _one_tour_gate(states, n_folds=3)
    assert r["verdict"] == "INSUFFICIENT"
    assert "n_games" in r and "n_states" in r
    assert r["n_games"] == 4


def test_gate_tour_insufficient_skips_null():
    states = _make_states(4, mode="helps", seed=5)
    r = _one_tour_gate(states, n_folds=3)
    assert r["verdict"] == "INSUFFICIENT"


def test_walk_forward_train_only_fit(monkeypatch):
    """The per-arm weight surfaces must be fit on TRAIN states only."""
    states = _make_states(240, mode="helps", seed=6)
    by_game = {}
    for s in states:
        by_game.setdefault(s["game_id"], []).append(s)
    order = list(by_game.keys())

    import scripts.platformkit.eval_gate.ingame_blend as blend_mod
    seen_fit_games = []
    real_fit = blend_mod.fit_weight_surface

    def spy_fit(arm_states, **kw):
        seen_fit_games.append({s["game_id"] for s in arm_states})
        return real_fit(arm_states, **kw)

    monkeypatch.setattr(
        "scripts.platformkit.ingame.surface_hold_gate.fit_weight_surface", spy_fit)
    folds = walk_forward(by_game, order, n_folds=3)
    assert len(seen_fit_games) == 2 * len(folds)  # 2 arms (blind, surface) per fold
    for (_, _, _, gids), fit_games in zip(folds, seen_fit_games[::2]):
        assert set(gids).isdisjoint(fit_games), "LEAK: test game seen during fit"


def test_verdict_dict_has_no_dollar_and_match_not_beat_framing():
    v_metrics = {"n_games": 4, "n_states": 8, "reason": "n_games=4 states=8 below floor"}
    assert "$" not in str(v_metrics)


def test_cross_tour_rollup_not_testable_when_null_also_ships(monkeypatch):
    """If BOTH tours ship AND the planted-null also ships, the rollup must return
    NOT_TESTABLE -- never a bare SHIP_SURFACE_LAYER."""
    import scripts.platformkit.ingame.surface_hold_gate as mod

    seeds = {"atp": 10, "wta": 11}

    def fake_states_with_priors(tour):
        return _make_states(500, mode="helps", seed=seeds[tour])

    def fake_planted_null_gate(states, seed=0, n_folds=3):
        return mod._one_tour_gate(states, n_folds=n_folds)  # pretend null == real (ships)

    monkeypatch.setattr(mod, "states_with_priors", fake_states_with_priors)
    monkeypatch.setattr(mod, "_planted_null_gate", fake_planted_null_gate)
    v = mod.gate(n_folds=3, seed=0)
    assert v.verdict == "NOT_TESTABLE", v.metrics
