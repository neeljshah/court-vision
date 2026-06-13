"""Tests for domains.basketball_nba.asof_features.

SMALL synthetic player_box only (~3 games x 2 teams x 2-3 players).  Fast,
low-RAM, never touches the real ~1299-game cache.  Verifies aggregation,
prior-only leak-freeness, future-insensitivity, the home/away pivot + diff,
NaN-on-zero-prior, and the schema / 1:1 game_id row count.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domains.basketball_nba.asof_features import (
    OUTPUT_COLS,
    build_asof_features,
    _aggregate_team_games,
)

A, B = "BOS", "ATL"


def _p(gid, date, team, opp, is_home, **stats):
    """One player-box row with sensible defaults; override stats via kwargs."""
    rec = {
        "game_id": gid, "date": date, "team": team, "opp": opp, "is_home": is_home,
        "ast": 0, "fgm": 0, "fga": 0, "fg3m": 0, "reb": 0, "oreb": 0, "dreb": 0,
        "tov": 0, "pts": 0, "fta": 0,
    }
    rec.update(stats)
    return rec


@pytest.fixture
def player_box():
    """3 games, teams A(BOS) & B(ATL).  A is home in G1/G3, B is home in G2.

    Each team-game = 2 players so we can verify SUM aggregation.
    A's team_ast per game: G1=10, G2=20, G3=(asof = mean of prior 2 = 15).
    A's team_fgm per game: G1=4, G2=6.
    """
    rows = [
        # --- G1 (date 1): A home vs B ---
        _p("G1", "2025-01-01", A, B, True, ast=6, fgm=2, fga=5, oreb=2, tov=1, fta=2),
        _p("G1", "2025-01-01", A, B, True, ast=4, fgm=2, fga=5, oreb=1, tov=2, fta=0),
        _p("G1", "2025-01-01", B, A, False, ast=3, fgm=1, fga=4, oreb=1, tov=1, fta=1),
        _p("G1", "2025-01-01", B, A, False, ast=2, fgm=1, fga=4, oreb=0, tov=1, fta=1),
        # --- G2 (date 2): B home vs A ---
        _p("G2", "2025-01-03", A, B, False, ast=12, fgm=3, fga=6, oreb=3, tov=2, fta=3),
        _p("G2", "2025-01-03", A, B, False, ast=8, fgm=3, fga=6, oreb=2, tov=1, fta=1),
        _p("G2", "2025-01-03", B, A, True, ast=5, fgm=2, fga=5, oreb=1, tov=2, fta=2),
        _p("G2", "2025-01-03", B, A, True, ast=5, fgm=2, fga=5, oreb=1, tov=1, fta=0),
        # --- G3 (date 3): A home vs B ---
        _p("G3", "2025-01-05", A, B, True, ast=7, fgm=4, fga=7, oreb=2, tov=1, fta=1),
        _p("G3", "2025-01-05", A, B, True, ast=7, fgm=3, fga=6, oreb=1, tov=2, fta=2),
        _p("G3", "2025-01-05", B, A, False, ast=4, fgm=2, fga=5, oreb=1, tov=1, fta=1),
        _p("G3", "2025-01-05", B, A, False, ast=3, fgm=2, fga=5, oreb=0, tov=1, fta=1),
    ]
    return pd.DataFrame(rows)


def _load(tmp_path, player_box):
    out = tmp_path / "asof.parquet"
    p = build_asof_features(player_box=player_box, out_path=str(out))
    return pd.read_parquet(str(p))


# --------------------------------------------------------------------------- #
# Aggregation: players -> team-game totals.
# --------------------------------------------------------------------------- #
def test_aggregation_players_to_team(player_box):
    tg = _aggregate_team_games(player_box)
    g1a = tg[(tg["game_id"] == "G1") & (tg["team"] == A)].iloc[0]
    assert g1a["team_ast"] == 10.0      # 6 + 4
    assert g1a["team_fgm"] == 4.0       # 2 + 2
    assert g1a["team_oreb"] == 3.0      # 2 + 1
    # one team-game row per (game_id, team): 3 games x 2 teams = 6
    assert len(tg) == 6


# --------------------------------------------------------------------------- #
# Prior-only: G3's as-of = mean over its 2 strictly-prior games.
# --------------------------------------------------------------------------- #
def test_prior_only_third_game(tmp_path, player_box):
    df = _load(tmp_path, player_box)
    g3 = df[df["game_id"] == "G3"].iloc[0]
    # A team_ast: G1=10, G2=20 -> ast_pg asof = 15.  A is HOME in G3.
    assert g3["home_ast_pg_asof"] == pytest.approx(15.0)
    assert g3["home_n_prior"] == 2
    # A ast_rate asof = sum(ast)/sum(fgm) over prior = (10+20)/(4+6) = 3.0
    assert g3["home_ast_rate_asof"] == pytest.approx(3.0)
    # A oreb_pg asof = (3 + 5)/2 = 4.0 ; tov_pg = (3 + 3)/2 = 3.0
    assert g3["home_oreb_pg_asof"] == pytest.approx(4.0)
    assert g3["home_tov_pg_asof"] == pytest.approx(3.0)
    # A pace asof: G1 fga+0.44*fta = 10 + 0.44*2 = 10.88; G2 = 12 + 0.44*4 = 13.76
    assert g3["home_pace_asof"] == pytest.approx((10.88 + 13.76) / 2)


# --------------------------------------------------------------------------- #
# Future-insensitivity: mutating a LATER game must not change earlier as-of.
# --------------------------------------------------------------------------- #
def test_flip_future_no_change(tmp_path, player_box):
    base = _load(tmp_path, player_box)
    g2_base = base[base["game_id"] == "G2"].iloc[0].copy()

    fut = player_box.copy()
    # Blow up G3 (the last game) — must not touch G1/G2 as-of features.
    mask = fut["game_id"] == "G3"
    fut.loc[mask, "ast"] = fut.loc[mask, "ast"] * 99 + 123

    df2 = _load(tmp_path, fut)
    g2_new = df2[df2["game_id"] == "G2"].iloc[0]
    for c in ("home_ast_rate_asof", "away_ast_rate_asof", "home_ast_pg_asof",
              "away_ast_pg_asof", "ast_rate_diff_asof"):
        assert g2_new[c] == pytest.approx(g2_base[c], nan_ok=True)


# --------------------------------------------------------------------------- #
# Home/away pivot correctness + ast_rate_diff = home - away.
# --------------------------------------------------------------------------- #
def test_home_away_pivot_and_diff(tmp_path, player_box):
    df = _load(tmp_path, player_box)
    g2 = df[df["game_id"] == "G2"].iloc[0]
    # In G2, B is HOME, A is AWAY.  Each has exactly 1 prior game (G1).
    # B G1 ast_rate = 5/2 = 2.5 (home).  A G1 ast_rate = 10/4 = 2.5 (away).
    assert g2["home_ast_rate_asof"] == pytest.approx(2.5)
    assert g2["away_ast_rate_asof"] == pytest.approx(2.5)
    assert g2["home_n_prior"] == 1 and g2["away_n_prior"] == 1
    # G3: A home ast_rate=3.0; B away ast_rate = sum(5+10)/sum(2+4)=15/6=2.5
    g3 = df[df["game_id"] == "G3"].iloc[0]
    assert g3["away_ast_rate_asof"] == pytest.approx(2.5)
    assert g3["ast_rate_diff_asof"] == pytest.approx(
        g3["home_ast_rate_asof"] - g3["away_ast_rate_asof"])


# --------------------------------------------------------------------------- #
# NaN on zero prior + n_prior counters.
# --------------------------------------------------------------------------- #
def test_nan_on_zero_prior(tmp_path, player_box):
    df = _load(tmp_path, player_box)
    g1 = df[df["game_id"] == "G1"].iloc[0]
    # First game for both teams -> no prior history -> NaN, n_prior == 0.
    assert g1["home_n_prior"] == 0 and g1["away_n_prior"] == 0
    for c in ("home_ast_rate_asof", "away_ast_rate_asof", "home_ast_pg_asof",
              "away_ast_pg_asof", "home_pace_asof", "ast_rate_diff_asof"):
        assert np.isnan(g1[c])


# --------------------------------------------------------------------------- #
# Schema + exactly one row per game_id.
# --------------------------------------------------------------------------- #
def test_schema_and_one_row_per_game(tmp_path, player_box):
    df = _load(tmp_path, player_box)
    assert list(df.columns) == list(OUTPUT_COLS)
    assert df["game_id"].nunique() == len(df) == 3
    assert str(df["home_n_prior"].dtype) == "int64"
    assert str(df["away_n_prior"].dtype) == "int64"


def test_empty_input(tmp_path):
    df = _load(tmp_path, pd.DataFrame(columns=[
        "game_id", "date", "team", "opp", "is_home", "ast", "fgm", "fga",
        "fg3m", "reb", "oreb", "dreb", "tov", "pts", "fta"]))
    assert list(df.columns) == list(OUTPUT_COLS)
    assert len(df) == 0
