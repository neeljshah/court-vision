"""domains.soccer_intl.test_intl_live - per-file test for FIX 1 (intl in-game).

Verifies IntlSoccerPredictor.predict_live (added so World Cup / national-team games
have an in-game model, mirroring the CLUB soccer predict_live):

  * the method exists with the CLUB-matching positional signature
    (home, away, minute, home_goals, away_goals);
  * at minute 0, 0-0 the live 1X2 ~= the pregame 1X2 (no realized info yet);
  * a big lead late (England 3-0 Croatia, 85') pushes the win-prob to the leader;
  * a coherent simplex (p_home + p_draw + p_away ~= 1) and no crash on the
    World Cup neutral-site default;
  * predict_matchup.live_kwargs routes soccer_intl in-game state.

HONEST: calibration/coherence machinery only; NO $ edge asserted. International
pregame markets are efficient. Run ONLY this file (full pytest freezes the box):
    python -m pytest domains/soccer_intl/test_intl_live.py -q -s
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd
import pytest

from domains.soccer_intl.config import RESULTS_PARQUET
from domains.soccer_intl.predictor import IntlSoccerPredictor

_REPO = Path(__file__).resolve().parents[2]
_RESULTS = _REPO / RESULTS_PARQUET


def _predictor() -> IntlSoccerPredictor:
    if not _RESULTS.exists():
        pytest.skip(f"corpus not materialised at {_RESULTS}")
    return IntlSoccerPredictor(pd.read_parquet(_RESULTS))


def _seen_pair(p: IntlSoccerPredictor):
    """Two well-established national teams present in the corpus (else skip)."""
    seen = [t for t in p.teams if p._seen(t)]
    for cand in ("England", "Croatia", "Brazil", "France", "Germany", "Spain", "Argentina"):
        if cand in seen:
            yield cand


# ---------------------------------------------------------------------------


def test_predict_live_exists_with_club_matching_signature():
    """predict_live must exist and accept the club soccer positional params so
    predict_matchup consumes it identically."""
    assert hasattr(IntlSoccerPredictor, "predict_live")
    params = list(inspect.signature(IntlSoccerPredictor.predict_live).parameters)
    # self + the club soccer positional contract
    for need in ("home", "away", "minute", "home_goals", "away_goals"):
        assert need in params, f"predict_live missing {need} (club-parity signature)"


def test_minute_zero_matches_pregame():
    p = _predictor()
    teams = list(_seen_pair(p))
    if len(teams) < 2:
        pytest.skip("need >=2 seen national teams in corpus")
    home, away = teams[0], teams[1]
    pre = p.predict(home, away, neutral=True)
    live0 = p.predict_live(home, away, 0.0, 0, 0, neutral=True)
    # at kickoff 0-0 the live 1X2 must track the pregame 1X2 (only rho differs:
    # pregame uses the fitted DC rho, the live repricer uses rho=0.0 -- a tiny low-score
    # nudge), so allow a small tolerance.
    print(f"\n{home} vs {away}: pregame p_home={pre['p_home_win']:.4f} "
          f"live@0' p_home={live0['p_home_win']:.4f}")
    assert abs(live0["p_home_win"] - pre["p_home_win"]) < 0.05
    assert abs(live0["p_draw"] - pre["p_draw"]) < 0.05


def test_big_lead_late_goes_to_leader():
    p = _predictor()
    teams = list(_seen_pair(p))
    if len(teams) < 2:
        pytest.skip("need >=2 seen national teams in corpus")
    home, away = teams[0], teams[1]
    live = p.predict_live(home, away, 85.0, 3, 0, neutral=True)
    print(f"\n{home} 3-0 {away} @85': p_home={live['p_home_win']:.4f}")
    assert live["p_home_win"] > 0.95
    assert live["p_away_win"] < 0.05


def test_live_simplex_and_neutral_no_crash():
    """England 1-0 Croatia 31' (a live-style World Cup state): coherent simplex, no crash."""
    p = _predictor()
    teams = list(_seen_pair(p))
    if len(teams) < 2:
        pytest.skip("need >=2 seen national teams in corpus")
    home, away = teams[0], teams[1]
    live = p.predict_live(home, away, 31.0, 1, 0, neutral=True)
    s = live["p_home_win"] + live["p_draw"] + live["p_away_win"]
    print(f"\n{home} 1-0 {away} @31': p_home={live['p_home_win']:.4f} "
          f"p_draw={live['p_draw']:.4f} p_away={live['p_away_win']:.4f} sum={s:.4f}")
    assert abs(s - 1.0) < 0.02
    assert live["sport"] == "soccer_intl"
    assert live["neutral"] is True
    # leading at 31' -> home favoured over the (still-possible) away win
    assert live["p_home_win"] > live["p_away_win"]


def test_predict_matchup_routes_soccer_intl_ingame():
    """live_kwargs must map the generic CLI flags onto intl predict_live kwargs."""
    import argparse

    from scripts.platformkit.predict_matchup import live_kwargs

    ns = argparse.Namespace(
        elapsed=31.0, home_score=1, away_score=0, inning=None, half=None,
        sets_home=None, sets_away=None, games_home=None, games_away=None, surface="Hard")
    for sport in ("soccer_intl", "worldcup", "wc"):
        kw = live_kwargs(sport, ns)
        assert kw == {"minute": 31.0, "home_goals": 1, "away_goals": 0}, \
            f"{sport} did not route in-game state"
