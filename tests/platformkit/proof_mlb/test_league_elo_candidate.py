"""Per-file test for league_elo_candidate (run THIS file only; never full pytest).

Synthetic-frame checks only -- no real MLB corpus needed, no odds, no prices.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from domains.mlb.config import ELO_HFA
from domains.mlb.ratings import walk_forward_elo
from scripts.platformkit.proof_mlb import league_elo_candidate as C


def _games(rows):
    return pd.DataFrame([
        {"date": d, "season": s, "home_team": h, "away_team": a,
         "home_runs": hr, "away_runs": ar, "game_seq": 1, "home_league": lg}
        for (d, s, h, a, hr, ar, lg) in rows
    ])


def _small_frame():
    # Unique team names per row so every game is a "first appearance"
    # (elo_home == elo_away == ELO_MEAN pre-game, i.e. diff_base == 0).
    return _games([
        (dt.date(2010, 4, 1), 2010, "A1", "A2", 5, 3, "AL"),
        (dt.date(2010, 4, 2), 2010, "N1", "N2", 2, 6, "NL"),
        (dt.date(2010, 4, 3), 2010, "A3", "A4", 4, 1, "AL"),
        (dt.date(2010, 4, 4), 2010, "N3", "N4", 7, 2, "NL"),
    ])


def test_equivalence_with_baseline_when_hfa_matches_default():
    """hfa_by_league == {every league: ELO_HFA} must reproduce the UNMODIFIED
    domains.mlb.ratings.walk_forward_elo bit-for-bit."""
    df = _small_frame()
    baseline = walk_forward_elo(df)
    variant = C.walk_forward_elo_league_hfa(df, {"AL": ELO_HFA, "NL": ELO_HFA})
    for col in ("elo_home", "elo_away", "elo_diff_hfa", "p_home_elo"):
        assert np.allclose(baseline[col].to_numpy(), variant[col].to_numpy(), atol=1e-12), col


def test_per_league_hfa_diverges_from_baseline():
    """A per-league HFA must actually change the applied offset per row --
    checked on first-appearance rows where diff_base is exactly 0, so
    elo_diff_hfa == hfa exactly (no float fuzz)."""
    df = _small_frame()
    baseline = walk_forward_elo(df)
    variant = C.walk_forward_elo_league_hfa(df, {"AL": 40.0, "NL": 10.0})

    # row 0 = AL first-appearance game
    assert baseline["elo_diff_hfa"].iloc[0] == ELO_HFA
    assert variant["elo_diff_hfa"].iloc[0] == 40.0
    # row 1 = NL first-appearance game
    assert baseline["elo_diff_hfa"].iloc[1] == ELO_HFA
    assert variant["elo_diff_hfa"].iloc[1] == 10.0

    expected_p_al = 1.0 / (1.0 + 10.0 ** (-40.0 / 400.0))
    expected_p_nl = 1.0 / (1.0 + 10.0 ** (-10.0 / 400.0))
    assert abs(variant["p_home_elo"].iloc[0] - expected_p_al) < 1e-9
    assert abs(variant["p_home_elo"].iloc[1] - expected_p_nl) < 1e-9


def test_fit_league_hfa_never_touches_eval_seasons():
    """Leak discipline: fitting with train_seasons=[2010] must be unaffected
    by contradicting outcomes planted in an eval season (2019), proving the
    season filter -- not just the argument -- actually excludes eval rows."""
    train_rows = [
        (dt.date(2010, 4, i + 1), 2010, f"TH{i}", f"TA{i}", 5, 1, "NL")  # home always wins
        for i in range(6)
    ]
    eval_rows = [
        (dt.date(2019, 4, i + 1), 2019, f"EH{i}", f"EA{i}", 1, 5, "NL")  # home always loses
        for i in range(6)
    ]
    df = _games(train_rows + eval_rows)

    fit_train_only = C.fit_league_hfa(df, train_seasons=[2010], leagues=("NL",))["NL"]
    fit_leaked = C.fit_league_hfa(df, train_seasons=[2010, 2019], leagues=("NL",))["NL"]

    # diff_base == 0 for every row (fresh teams); home-always-wins train data
    # pushes the Brier-minimizing HFA to the top of the (non-negative) grid.
    assert fit_train_only == float(C._HFA_GRID[-1])
    # Including the contradicting 2019 rows must change the fit.
    assert fit_leaked != fit_train_only


def test_verdict_labels():
    eps = C._VERDICT_EPS
    assert C._verdict({"brier": 0.20}, {"brier": 0.20 - 10 * eps}) == "IMPROVED"
    assert C._verdict({"brier": 0.20}, {"brier": 0.20 + 10 * eps}) == "WORSE"
    assert C._verdict({"brier": 0.20}, {"brier": 0.20 + eps / 2}) == "NO-IMPROVEMENT"
