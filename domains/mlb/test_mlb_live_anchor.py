"""domains.mlb.test_mlb_live_anchor - per-file test for FIX 2 (MLB live ML anchor).

Verifies that MLBPredictor.predict_live anchors the run-rate lambdas to the Elo
win-prob BEFORE handing them to the repricer -- exactly as predict()/to_jd() do --
so the LIVE moneyline at the start of the game matches the PREGAME moneyline.

Repro (pre-fix): NYY vs BOS pregame p_home=0.5462 but
predict_live(inning=1, half='top', 0, 0)=0.5022 (built off RAW lambdas).
Post-fix: predict_live@start ~= pregame p_home within ~0.01.

HONEST: calibration/coherence only; no $ edge asserted. Run ONLY this file:
    python -m pytest domains/mlb/test_mlb_live_anchor.py -q -s
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from domains.mlb.predictor import MLBPredictor

_CORPUS = Path(__file__).resolve().parents[2] / "data" / "domains" / "mlb" / "games.parquet"


def _predictor() -> MLBPredictor:
    if not _CORPUS.exists():
        pytest.skip(f"MLB corpus not materialised at {_CORPUS}")
    return MLBPredictor(pd.read_parquet(_CORPUS))


def _seen_pair(p: MLBPredictor):
    for cand in (("NYY", "BOS"), ("LAD", "SFG"), ("HOU", "TEX")):
        if cand[0] in p.teams and cand[1] in p.teams:
            return cand
    return (p.teams[0], p.teams[1]) if len(p.teams) >= 2 else (None, None)


def test_live_start_matches_pregame_ml():
    """predict_live at inning 1 top, 0-0 must ~= the pregame Elo win-prob."""
    p = _predictor()
    home, away = _seen_pair(p)
    if home is None:
        pytest.skip("need >=2 teams in corpus")
    pre = p.predict(home, away)
    live = p.predict_live(home, away, inning=1, half="top", home_runs=0, away_runs=0)
    print(f"\n{home} vs {away}: pregame p_home={pre['p_home_win']:.4f} "
          f"live@1-top-0-0 p_home={live['p_home_win']:.4f} "
          f"raw={live['p_home_win_raw']:.4f}")
    # the live in-game recal is W156 identity for MLB, so cal == raw; the anchor makes
    # the start-of-game ML agree with the pregame ML within tight tolerance.
    assert abs(live["p_home_win"] - pre["p_home_win"]) < 0.01


def test_live_start_not_pinned_to_half():
    """Guards the bug: if the lambdas were NOT anchored, a non-50/50 matchup would
    collapse toward ~0.50 at the start. Assert the live start tracks the (non-0.5)
    pregame number, not 0.50."""
    p = _predictor()
    home, away = _seen_pair(p)
    if home is None:
        pytest.skip("need >=2 teams in corpus")
    pre = p.predict(home, away)
    if abs(pre["p_home_win"] - 0.5) < 0.02:
        pytest.skip("this matchup is ~coin-flip; pick a tilted pair to exercise the anchor")
    live = p.predict_live(home, away, inning=1, half="top", home_runs=0, away_runs=0)
    # live start should be MUCH closer to the pregame ML than to 0.50
    assert abs(live["p_home_win"] - pre["p_home_win"]) < abs(live["p_home_win"] - 0.5)


def test_expected_total_unchanged_by_anchor():
    """SUM-preserving anchor: proj remaining runs at start ~= pregame expected total."""
    p = _predictor()
    home, away = _seen_pair(p)
    if home is None:
        pytest.skip("need >=2 teams in corpus")
    pre = p.predict(home, away)
    live = p.predict_live(home, away, inning=1, half="top", home_runs=0, away_runs=0)
    # at the very start (no runs in), remaining runs should be close to the pregame total
    print(f"\nexpected_total pregame={pre['expected_total']:.2f} "
          f"proj_remaining_runs@start={live['proj_remaining_runs']:.2f}")
    assert abs(live["proj_remaining_runs"] - pre["expected_total"]) < 1.0
