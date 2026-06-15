"""tests/platform/test_match_engine.py

Per-file tests for domains.tennis.match_engine (the raw point-by-point engine,
NOT the as-of wrapper match_engine_holds).  Covers the parity-by-construction
contract and full-surface coherence:

  1. game_win_prob is monotone, fixed at 0.5, and bounded in [0,1].
  2. serve_probs_from_winprob bisects so the hold gap moves with the target
     (favourite gets the higher hold) and stays in valid bounds.
  3. markets_from_engine match_win_p1 ~= the Elo target the holds were
     calibrated to (parity-by-construction, within sim noise).
  4. straight_sets_p1 <= match_win_p1 (a straight-sets win is a subset of a
     match win) and likewise for p2.
  5. Set-betting + total_games O/U surface is coherent: every probability in
     [0,1]; match_win_p1 + match_win_p2 complementary within sim noise; the
     set-score buckets sum to ~1; each O/U line's over+under sum to 1.

HONEST: accuracy/calibration only.  Parity == the win; NO edge claimed.
Domain-only imports - no src/ / kernel/ / api/ / scripts.team_system imports.

Run ONLY this file (full pytest freezes the box):
    python -m pytest tests/platform/test_match_engine.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from domains.tennis.match_engine import (
    game_win_prob,
    markets_from_engine,
    serve_probs_from_winprob,
)

_SIM_TOL = 0.045
_N = 4000


def test_game_win_prob_bounds_and_monotone():
    assert game_win_prob(0.5) == pytest.approx(0.5, abs=1e-9)
    prev = -1.0
    for p in np.linspace(0.05, 0.95, 19):
        gw = game_win_prob(float(p))
        assert 0.0 <= gw <= 1.0
        assert gw > prev
        prev = gw
    assert game_win_prob(0.62) > 0.62
    with pytest.raises(ValueError):
        game_win_prob(1.5)


@pytest.mark.parametrize("target", [0.40, 0.55, 0.65, 0.75])
def test_serve_probs_parity_by_construction(target):
    ph1, ph2 = serve_probs_from_winprob(target, best_of=3, n_sims=_N, seed=42)
    assert 0.0 < ph1 < 1.0 and 0.0 < ph2 < 1.0
    if target > 0.5:
        assert ph1 > ph2
    elif target < 0.5:
        assert ph1 < ph2
    surf = markets_from_engine(ph1, ph2, 3, seed=7, n_sims=_N)
    assert surf["match_win_p1"] == pytest.approx(target, abs=_SIM_TOL)


@pytest.mark.parametrize("best_of", [3, 5])
def test_market_surface_coherent(best_of):
    ph1, ph2 = serve_probs_from_winprob(0.62, best_of=best_of, n_sims=_N, seed=11)
    surf = markets_from_engine(ph1, ph2, best_of, seed=3, n_sims=_N)
    for k, v in surf.items():
        if k.startswith("total_games") or k == "_match":
            continue
        assert 0.0 <= float(v) <= 1.0
    mw1, mw2 = surf["match_win_p1"], surf["match_win_p2"]
    assert mw1 + mw2 == pytest.approx(1.0, abs=1e-9)
    assert surf["straight_sets_p1"] <= mw1 + 1e-9
    assert surf["straight_sets_p2"] <= mw2 + 1e-9
    set_mass = sum(v for k, v in surf.items() if k.startswith("sets_"))
    assert set_mass == pytest.approx(1.0, abs=1e-9)
    stw = (best_of + 1) // 2
    p1_set_mass = sum(v for k, v in surf.items()
                      if k.startswith("sets_") and int(k.split("_")[1]) == stw)
    assert p1_set_mass == pytest.approx(mw1, abs=1e-9)
    over_lines = [k for k in surf if k.startswith("over_")]
    assert over_lines
    for k in over_lines:
        line = k.split("_", 1)[1]
        assert surf[k] + surf[f"under_{line}"] == pytest.approx(1.0, abs=1e-9)
