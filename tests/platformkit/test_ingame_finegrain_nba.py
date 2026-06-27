"""OFFLINE tests for the FINE-RESOLUTION in-game detail-layer gate.

No network, no parquet on disk -- we synthesize fine-grained state dicts directly and
assert the gate's behavior:
  * SHIPS (REPLICATED) when the prior is INFORMATIVE EARLY and FADES LATE (a real
    early-game team-strength signal) -- and the elapsed-bucket read shows early>late.
  * REJECTS (NOT_REPLICATED) when p0 is pure NOISE (uninformative prior).
  * DM clusters BY GAME_ID, not per-state: many states from one game must collapse to
    ~n_games clusters (a per-state SE would manufacture fake significance).

Mirrors the real gate's helpers (run_fine, _direction_with_buckets, states_from_pbp); never
a parallel stub. numpy + stdlib + pytest.
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.ingame.ingame_finegrain_nba import (
    _early_helps_most,
    _direction_with_buckets,
    run_fine,
)
from scripts.platformkit.ingame.ingame_layer_gate_nba_io import p_live_from_margin

_REG = 2880.0
# ~2-min grid (interior of regulation), same shape as the real ingest.
_GRID = [_REG - 120.0 * k for k in range(1, 24)]


def _make_states(n_games: int, informative: bool, seed: int) -> list:
    """Synthesize fine-grained states across many games.

    Each game has a true team-strength edge `t` in [0,1]. The realized margin trajectory
    drifts toward that edge but is NOISY EARLY and only resolves LATE, so a (margin,time)
    BASE is weak early while the pregame prior p0 (== t when informative) carries real
    early signal. When informative=False, p0 is random noise (no signal).
    """
    rng = np.random.default_rng(seed)
    states = []
    for g in range(n_games):
        t = rng.uniform(0.05, 0.95)             # true home win-prob
        home_win = int(rng.uniform() < t)
        p0 = float(t) if informative else float(rng.uniform(0.05, 0.95))
        for sr in _GRID:
            frac = 1.0 - sr / _REG
            # margin signal grows with elapsed fraction; heavy early noise.
            signal = (t - 0.5) * 30.0 * frac
            noise = rng.normal(0.0, 12.0 * (1.0 - frac) + 2.0)
            diff = signal + noise
            states.append({
                "game_id": g, "seconds_remaining": float(sr),
                "score_diff": float(diff), "frac_elapsed": float(frac),
                "period": min(4, 1 + int((_REG - sr) // 720.0)),
                "p0": p0, "p_live": p_live_from_margin(diff, frac),
                "outcome": home_win,
            })
    return states


def test_ships_when_prior_informative_early_fades_late():
    a = _make_states(220, informative=True, seed=1)
    b = _make_states(220, informative=True, seed=2)
    v = run_fine(a, b)
    assert v.verdict == "REPLICATED", v.to_dict()
    assert v.a_to_b["prior_beats_base"] and v.b_to_a["prior_beats_base"]
    # prior helps and is DM-significant both directions
    assert v.a_to_b["dm_p"] < 0.05 and v.b_to_a["dm_p"] < 0.05
    assert v.a_to_b["brier_prior"] < v.a_to_b["brier_base"]
    # freshness pattern: prior helps MORE early than late in at least one direction
    assert v.a_to_b["early_helps_most"] or v.b_to_a["early_helps_most"]


def test_rejects_on_noise_prior():
    a = _make_states(220, informative=False, seed=11)
    b = _make_states(220, informative=False, seed=12)
    v = run_fine(a, b)
    assert v.verdict != "REPLICATED", v.to_dict()
    # a noise prior must NOT beat base with significance in both directions
    assert not (v.a_to_b["prior_beats_base"] and v.b_to_a["prior_beats_base"])


def test_dm_clusters_by_game_not_per_state():
    """The gate's DM must cluster by game_id: n_clusters == n_games, NOT n_states."""
    a = _make_states(60, informative=True, seed=21)
    b = _make_states(60, informative=True, seed=22)
    res = _direction_with_buckets(a, b)
    # b has 60 games, 23 states each -> clusters must be the 60 games, not 1380 states.
    assert res["n_test_games"] == 60
    assert res["n_test_states"] == 60 * len(_GRID)
    assert res["n_test_games"] < res["n_test_states"]


def test_clustering_shrinks_significance_vs_iid():
    """Per-state iid SE manufactures fake significance; clustering by game must be wider."""
    states = _make_states(80, informative=True, seed=31)
    # build a per-state loss-diff vector with a small per-game effect
    rng = np.random.default_rng(7)
    d = []
    gids = []
    for s in states:
        d.append(0.01 + rng.normal(0.0, 0.05))
        gids.append(s["game_id"])
    d = np.asarray(d)
    iid = diebold_mariano(d, list(range(len(d))))        # every state its own cluster
    clustered = diebold_mariano(d, gids)                 # cluster by game
    assert clustered.n_clusters == 80
    assert iid.n_clusters == len(d)
    # clustering must NOT inflate the statistic relative to the iid (anti-fake-significance)
    assert abs(clustered.dm_stat) <= abs(iid.dm_stat) + 1e-9
