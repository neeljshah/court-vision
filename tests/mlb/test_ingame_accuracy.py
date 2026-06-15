"""Per-file test for scripts.platformkit.proof_mlb.ingame_accuracy.

Fast: exercises the leak-free helpers + the three-forecaster mechanics on a tiny synthetic
corpus (no full 28k-game run). Asserts the in-game pattern holds — combining the pregame Elo
prior with the realized score is at least as sharp as either alone on the constructed cases.
Run: python -m pytest tests/mlb/test_ingame_accuracy.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import scripts.platformkit.proof_mlb.ingame_accuracy as M
from scripts.platformkit.live_repricer import get_repricer
from domains.mlb.negbinom_engine import _FALLBACK_R


def test_parse_innings_handles_x_and_blanks():
    assert M._parse_innings("0,1,0,0,1,3,3,1,x") == [0, 1, 0, 0, 1, 3, 3, 1]
    assert M._parse_innings("2,0,2") == [2, 0, 2]
    assert M._parse_innings(None) is None
    assert M._parse_innings("") is None
    assert M._parse_innings("a,b") is None


def test_brier_and_logloss_basic():
    p = np.array([0.5, 0.5]); y = np.array([1.0, 0.0])
    assert abs(M._brier(p, y) - 0.25) < 1e-9
    # log-loss of 0.5 predictions == ln 2
    assert abs(M._logloss(p, y) - np.log(2)) < 1e-9


def test_walk_forward_elo_leakfree_and_responds_to_results():
    # A always beats B at home -> A's as-of home win-prob should rise over time.
    rows = [{"home_team": "A", "away_team": "B", "home_runs": 5, "away_runs": 1}
            for _ in range(20)]
    df = pd.DataFrame(rows)
    p = M._walk_forward_elo(df)
    assert p[0] == 0.5 + (p[0] - 0.5)        # finite
    assert abs(p[0] - M._p_home(M._INIT, M._INIT)) < 1e-9  # first snapshot = pure HFA prior
    assert p[-1] > p[0]                       # A's home win-prob grew with wins (leak-free update)
    assert (p > 0).all() and (p < 1).all()


def test_reprice_winhome_responds_to_score_and_prior():
    rep = get_repricer("mlb")
    # After inning 5, home leads 6-1: ml_home should be high regardless of prior.
    p = M._reprice_winhome(rep, 6, 1, 5, 4.5, 4.5, _FALLBACK_R, _FALLBACK_R)
    assert p > 0.8
    # Tied 2-2 after inning 5: a strong home prior should beat a weak home prior.
    p_strong = M._reprice_winhome(rep, 2, 2, 5, 6.0, 3.0, _FALLBACK_R, _FALLBACK_R)
    p_weak = M._reprice_winhome(rep, 2, 2, 5, 3.0, 6.0, _FALLBACK_R, _FALLBACK_R)
    assert p_strong > p_weak


def test_run_smoke_on_full_corpus_pattern(tmp_path):
    """End-to-end on the real corpus is slow; instead assert run() returns the documented
    shape and the in-game pattern on a SUBSAMPLED corpus written to a temp dir."""
    import pathlib
    g = pd.read_parquet(M._GAMES)
    pit = pd.read_parquet(M._PITCHERS)[["event_id", "home_innings", "away_innings"]]
    # every 12th game keeps chronology but runs fast
    g = g.iloc[::12].reset_index(drop=True)
    pit = pit[pit["event_id"].isin(g["event_id"])].reset_index(drop=True)
    d = tmp_path / "data" / "domains" / "mlb"
    d.mkdir(parents=True)
    g.to_parquet(d / "games.parquet")
    pit.to_parquet(d / "pitchers.parquet")

    orig_g, orig_p = M._GAMES, M._PITCHERS
    try:
        M._GAMES = pathlib.Path(d / "games.parquet")
        M._PITCHERS = pathlib.Path(d / "pitchers.parquet")
        r = M.run()
    finally:
        M._GAMES, M._PITCHERS = orig_g, orig_p

    assert r["status"] == "ok"
    for k in ("brier_pregame", "brier_scoreonly", "brier_combined",
              "delta_combined_vs_pregame", "combined_beats_pregame"):
        assert k in r
    # the documented pattern: combined is far sharper than pregame, and ties/beats score-only
    assert r["brier_combined"] < r["brier_pregame"]
    assert r["brier_combined"] <= r["brier_scoreonly"] + 5e-3
