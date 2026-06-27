"""Per-file, OFFLINE, deterministic unit test for the in-game DETAIL-LAYER gate.

Does NOT touch the real parquet. Builds two SYNTHETIC worlds of in-game states:

  * INFORMATIVE world: the pregame prior p0 truly predicts the winner (favorites
    mostly win, and the edge is strongest EARLY when the live margin is still noisy)
    -> the gate must return SHIP_PRIOR_LAYER (prior layer beats base OOS, DM sig,
    fold-consistent).
  * NOISE world: p0 = 0.5 everywhere (pure noise prior) -> blending it in cannot beat
    the (margin,time) base -> the gate must REJECT.

Also asserts: leak-freeness (the fitted weight surface is built ONLY from train states,
never the test fold), and the Brier/DM wiring (verdict carries pooled Brier + DM p).

CLI: python -m pytest tests/platformkit/test_ingame_layer_gate_nba.py -q
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.eval_gate.ingame_blend import fit_weight_surface
from scripts.platformkit.ingame.ingame_layer_gate_nba import gate, walk_forward
from scripts.platformkit.ingame.ingame_layer_gate_nba_io import (
    QSEC,
    p_live_from_margin,
)

_REG = 2880.0


def _make_world(n_games: int, informative: bool, seed: int = 0):
    """Build {game_id: [states]} + chronological order for a synthetic season.

    Each game has a hidden 'strength' in (0,1) = P(home win). If informative, p0 is
    set to that strength (a real pregame signal) and the EARLY-quarter margins are
    deliberately noisy so the prior carries info the live margin lacks; if not, p0=0.5
    everywhere (noise). The outcome is drawn from the strength so favorites mostly win.
    """
    rng = np.random.default_rng(seed)
    by_game = {}
    order = []
    for g in range(n_games):
        strength = float(rng.uniform(0.15, 0.85))
        y = int(rng.uniform() < strength)
        p0 = strength if informative else 0.5
        # final margin correlated with the realized outcome
        margin_final = float(rng.normal(8.0 if y else -8.0, 9.0))
        states = []
        for q in (1, 2, 3):
            frac = 1.0 - QSEC[q] / _REG
            # early margins noisy (little live signal); late margins track final
            track = {1: 0.15, 2: 0.45, 3: 0.80}[q]
            noise = {1: 9.0, 2: 7.0, 3: 4.0}[q]
            diff = float(track * margin_final + rng.normal(0.0, noise))
            states.append({
                "game_id": g, "period": q, "seconds_remaining": QSEC[q],
                "score_diff": diff, "p0": p0,
                "p_live": p_live_from_margin(diff, frac),
                "outcome": y, "margin_final": margin_final,
            })
        by_game[g] = states
        order.append(g)
    return by_game, order


def test_informative_prior_ships():
    by_game, order = _make_world(600, informative=True, seed=1)
    v = gate(by_game, order, n_folds=3)
    assert v.verdict == "SHIP_PRIOR_LAYER", (v.verdict, v.metrics)
    # prior must actually lower pooled Brier and clear significance
    assert v.metrics["brier_prior"] < v.metrics["brier_base"]
    assert v.metrics["dm_p"] < 0.05
    assert v.metrics["fold_sign_consistent"] is True


def test_noise_prior_rejects():
    by_game, order = _make_world(600, informative=False, seed=2)
    v = gate(by_game, order, n_folds=3)
    # A pure-noise p0=0.5 prior carries no team signal: even if blending toward 0.5
    # regularizes the crude live logistic by a hair, the gain is NOT significant nor
    # fold-consistent, so the gate must withhold the layer -> REJECT.
    assert v.verdict == "REJECT", (v.verdict, v.metrics)
    assert not (v.metrics["dm_p"] < 0.05 and v.metrics["fold_sign_consistent"])


def test_leak_free_surface_fit_only_on_train(monkeypatch):
    """The weight surface must be fit on TRAIN states only -- never the test fold."""
    by_game, order = _make_world(120, informative=True, seed=3)
    test_game_ids = set()  # populated by the walk_forward fold split
    seen_fit_games = []

    import scripts.platformkit.ingame.ingame_layer_gate_nba as mod

    real_fit = fit_weight_surface

    def spy_fit(states, **kw):
        seen_fit_games.append({s["game_id"] for s in states})
        return real_fit(states, **kw)

    monkeypatch.setattr(mod, "fit_weight_surface", spy_fit)
    folds = walk_forward(by_game, order, n_folds=3)
    # for each fold, the test game ids must be disjoint from the fit game ids
    assert len(seen_fit_games) == len(folds)
    for (_, _, _, gids, _), fit_games in zip(folds, seen_fit_games):
        test_ids = set(gids)
        assert test_ids.isdisjoint(fit_games), "LEAK: test game seen during fit"


def test_brier_and_dm_wiring():
    by_game, order = _make_world(300, informative=True, seed=4)
    v = gate(by_game, order, n_folds=3)
    d = v.to_dict()
    for k in ("brier_base", "brier_prior", "dm_p", "dm_stat", "n_folds"):
        assert k in v.metrics
    assert d["vs_close"].startswith("UNPROVEN")
    assert "$" not in str(d)  # no dollar/edge field anywhere
    # per-quarter breakdown present and labelled
    assert set(v.per_quarter.keys()) <= {"endQ1", "endQ2", "endQ3"}
    assert len(v.per_fold) == v.metrics["n_folds"]
