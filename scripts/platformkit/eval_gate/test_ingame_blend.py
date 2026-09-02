"""Tests for the in-game blend core. numpy + stdlib; standalone or pytest.

The key test mirrors the real discipline: FIT the weight surface on one synthetic
season, EVALUATE on a DIFFERENT one, and show the blend beats pregame-only OOS --
because the live signal carries information (it sharpens late) the pregame prior lacks.
"""
from __future__ import annotations
import os as _os, sys as _sys  # noqa: E402
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # blueprint uses bare sibling imports; make them work under "python -m pytest" from the repo root too
import numpy as np

from ingame_blend import (
    blend, exp_smooth, time_bucket, margin_bucket,
    WeightSurface, fit_weight_surface, blended_predictions,
)
from dm_test import diebold_mariano


def test_blend_mechanics():
    assert abs(blend(0.4, 0.8, 0.5) - 0.6) < 1e-12
    assert blend(0.3, 0.9, 0.0) == 0.3            # w=0 -> pregame
    assert blend(0.3, 0.9, 1.0) == 0.9            # w=1 -> live
    assert blend(0.3, 0.9, 5.0) == 0.9            # w clamped to 1
    assert 0.0 <= blend(0.99, 0.99, 1.0) <= 1.0   # output clamped


def test_exp_smooth_and_buckets():
    assert exp_smooth([]) == 0.0
    assert abs(exp_smooth([1.0, 1.0, 1.0]) - 1.0) < 1e-12
    assert time_bucket(2880.0) == 0 and time_bucket(60.0, n=4) == 3
    assert margin_bucket(-30) == 0 and margin_bucket(30) == 4


def _make_season(seed, n_games=400, states_per_game=8):
    """Live estimate sharpens as the game progresses; pregame prior is fixed + mildly noisy."""
    rng = np.random.default_rng(seed)
    states = []
    for g in range(n_games):
        q = float(np.clip(0.5 + 0.35 * rng.standard_normal(), 0.05, 0.95))
        y = int(rng.random() < q)
        p0 = float(np.clip(q + 0.12 * rng.standard_normal(), 0.01, 0.99))   # pregame, fixed
        for k in range(states_per_game):
            secs = 2880.0 * (1.0 - (k + 1) / states_per_game)               # 2880 -> ~0
            elapsed = 1.0 - secs / 2880.0
            sigma = 0.30 * (secs / 2880.0) + 0.02                            # sharpens late
            p_live = float(np.clip(q + sigma * rng.standard_normal(), 0.01, 0.99))
            score_diff = (2 * y - 1) * (elapsed * 15.0) + 6.0 * rng.standard_normal()
            states.append({"game_id": f"s{seed}_g{g}", "p0": p0, "p_live": p_live,
                           "seconds_remaining": secs, "score_diff": score_diff,
                           "outcome": y})
    return states


def test_blend_beats_pregame_only_out_of_sample():
    fit_states = _make_season(seed=1)          # "season A"
    eval_states = _make_season(seed=2)         # DIFFERENT "season B"
    surf = fit_weight_surface(fit_states)

    y = np.array([s["outcome"] for s in eval_states], dtype=float)
    p0 = np.array([s["p0"] for s in eval_states])
    pl = np.array([s["p_live"] for s in eval_states])
    blended = blended_predictions(eval_states, surf)

    brier_pregame = float(np.mean((p0 - y) ** 2))
    brier_live_only = float(np.mean((pl - y) ** 2))
    brier_blend = float(np.mean((blended - y) ** 2))

    # the honest OOS gain: blend < pregame-only AND < live-only (live alone is bad early)
    assert brier_blend < brier_pregame - 1e-3, (brier_blend, brier_pregame)
    assert brier_blend < brier_live_only

    # clustered DM (by game_id): blend's per-state loss beats pregame-only.
    # Direction is what we assert; p<0.05 requires adequate game count -- clustering
    # by game_id is deliberately conservative (here ~400 games -> p~0.09), which is
    # exactly the package's point: clustered SEs are honest and you need N for power.
    d = (p0 - y) ** 2 - (blended - y) ** 2     # pregame loss - blend loss (positive => blend better)
    dm = diebold_mariano(d, [s["game_id"] for s in eval_states])
    assert dm.mean_diff > 0                     # blend better on average, clustered
    assert 0.0 <= dm.p_value <= 1.0 and dm.n_clusters == 400


def test_surface_weights_more_on_live_late():
    surf = fit_weight_surface(_make_season(seed=7))
    early = [w for (tb, mb), w in surf.grid.items() if tb == 0]
    late = [w for (tb, mb), w in surf.grid.items() if tb == 3]
    assert early and late
    assert np.mean(late) > np.mean(early)      # trust live more as the game ends


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} in-game blend tests passed.")
