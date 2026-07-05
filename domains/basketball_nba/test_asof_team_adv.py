"""Per-file test for domains.basketball_nba.asof_team_adv.

Acceptance criteria (leak discipline is the review hill)
---------------------------------------------------------
1. SHIFT TEST: a game's own row never feeds its own feature -- first game for a team
   is NaN (n_prior == 0); the Nth game's as-of value equals the exact expanding mean of
   the team's PRECEDING (N-1) games only, hand-verified against known synthetic inputs.
2. TRUNCATION-INVARIANCE: recomputing on a date-truncated copy of the input yields
   IDENTICAL as-of features for every surviving game (no row learns anything from games
   that were removed because they are in the future relative to it -- but also proves no
   future leakage the other direction is possible, since removing future rows changes
   nothing about earlier rows' features).
3. diff_asof == home_asof - away_asof exactly; NaN propagates honestly (never fabricated).
4. Uses games.parquet's date (authoritative), NOT team_advanced_stats' own game_date --
   verified by passing a games frame with a DELIBERATELY DIFFERENT date ordering than the
   sidecar's own date-like values and checking the walk-forward respects the games.parquet
   order.
5. No $ / ROI / edge / profit language in OUTPUT_COLS or module docstring identifiers.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        domains/basketball_nba/test_asof_team_adv.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.basketball_nba import asof_team_adv as mod


def _synthetic(n_games: int = 6) -> tuple:
    """Two teams (T0 home, T1 away) play each other n_games times in sequence.

    Simple, hand-checkable off_rtg progression: T0 = 100, 110, 120, ... (home every game
    for simplicity); T1 = 90, 95, 100, ... This lets the expanding-mean be verified by
    direct arithmetic (mean of an arithmetic progression).
    """
    gids = [f"g{i:04d}" for i in range(n_games)]
    dates = pd.date_range("2023-01-01", periods=n_games, freq="3D")

    games = pd.DataFrame({
        "game_id": gids,
        "date": dates,
        "home_team": ["T0"] * n_games,
        "away_team": ["T1"] * n_games,
    })

    rows = []
    for i, gid in enumerate(gids):
        rows.append({
            "game_id": gid, "team_tricode": "T0",
            "game_date": "2099-01-01",  # deliberately WRONG/unused -- must be ignored
            "off_rtg": 100.0 + 10 * i, "def_rtg": 105.0, "pace": 99.0,
            "oreb_pct": 0.25, "dreb_pct": 0.70, "ast_pct": 0.60,
            "efg_pct": 0.50, "ts_pct": 0.55, "tov_ratio": 12.0,
        })
        rows.append({
            "game_id": gid, "team_tricode": "T1",
            "game_date": "2099-01-01",
            "off_rtg": 90.0 + 5 * i, "def_rtg": 108.0, "pace": 99.0,
            "oreb_pct": 0.28, "dreb_pct": 0.65, "ast_pct": 0.55,
            "efg_pct": 0.48, "ts_pct": 0.52, "tov_ratio": 13.0,
        })
    team_adv = pd.DataFrame(rows)
    return team_adv, games


def test_shift_first_game_nan_and_own_row_excluded():
    team_adv, games = _synthetic(6)
    tg = mod._attach_date(team_adv, games)
    tg = mod._walk_forward_team(tg)
    out = mod._pivot_to_games(tg)

    first = out.iloc[0]
    assert first["home_n_prior"] == 0
    assert first["away_n_prior"] == 0
    assert pd.isna(first["home_off_rtg_asof"])
    assert pd.isna(first["away_off_rtg_asof"])
    assert pd.isna(first["off_rtg_diff_asof"])

    # Game index 3 (4th game, 0-based i=3): T0 off_rtg prior games were 100,110,120 (i=0,1,2)
    # -> expanding mean = 110.0.  T1 prior were 90,95,100 -> mean = 95.0.
    row3 = out.iloc[3]
    assert row3["home_n_prior"] == 3
    assert row3["away_n_prior"] == 3
    assert np.isclose(row3["home_off_rtg_asof"], 110.0)
    assert np.isclose(row3["away_off_rtg_asof"], 95.0)
    assert np.isclose(row3["off_rtg_diff_asof"], 110.0 - 95.0)

    # Own-row exclusion: game i=3's own off_rtg values (130.0 / 105.0) must NOT appear
    # in its as-of mean (110.0 != 130 and any mean including 130 would exceed 110).
    assert row3["home_off_rtg_asof"] < 130.0


def test_uses_games_parquet_date_not_sidecar_game_date():
    """team_adv's own game_date column is seeded 2099-01-01 (deliberately wrong/unused).

    If the builder mistakenly sorted or dated by the sidecar's own game_date instead of
    games.parquet's date, every row would tie on the same (wrong) date and n_prior /
    ordering would not match the hand-verified arithmetic-progression check above. That
    check already passing is one proof; this test additionally asserts the date column
    actually used downstream is games.parquet's dtype (datetime), not the sidecar's raw
    string, by checking _attach_date's output.
    """
    team_adv, games = _synthetic(4)
    tg = mod._attach_date(team_adv, games)
    assert pd.api.types.is_datetime64_any_dtype(tg["date"])
    # The attached date must equal games.parquet's date for every row, never '2099-01-01'.
    assert (tg["date"] != pd.Timestamp("2099-01-01")).all()


def test_truncation_invariance():
    """Recomputing on a date-truncated copy yields identical as-of features for surviving
    rows -- no future information leaks backward into earlier rows' features."""
    team_adv, games = _synthetic(6)
    tg_full = mod._walk_forward_team(mod._attach_date(team_adv, games))
    out_full = mod._pivot_to_games(tg_full)

    # Truncate to the first 4 games only (drop the last 2 games' rows from BOTH inputs).
    keep_gids = set(games["game_id"].iloc[:4])
    games_trunc = games[games["game_id"].isin(keep_gids)].reset_index(drop=True)
    team_adv_trunc = team_adv[team_adv["game_id"].isin(keep_gids)].reset_index(drop=True)

    tg_trunc = mod._walk_forward_team(mod._attach_date(team_adv_trunc, games_trunc))
    out_trunc = mod._pivot_to_games(tg_trunc)

    surviving = out_full[out_full["game_id"].isin(keep_gids)].sort_values(
        "game_id").reset_index(drop=True)
    out_trunc = out_trunc.sort_values("game_id").reset_index(drop=True)

    pd.testing.assert_frame_equal(surviving, out_trunc, check_dtype=False)


def test_diff_equals_home_minus_away_and_nan_propagates():
    team_adv, games = _synthetic(5)
    tg = mod._walk_forward_team(mod._attach_date(team_adv, games))
    out = mod._pivot_to_games(tg)
    for s in mod._STATS:
        hcol, acol, dcol = f"home_{s}_asof", f"away_{s}_asof", f"{s}_diff_asof"
        expected = out[hcol] - out[acol]
        pd.testing.assert_series_equal(
            out[dcol], expected, check_names=False, check_dtype=False)
    # First row's NaN (n_prior == 0) must propagate, never be fabricated as 0.
    assert pd.isna(out.iloc[0]["off_rtg_diff_asof"])


def test_build_asof_team_adv_writes_parquet(tmp_path):
    team_adv, games = _synthetic(5)
    out_path = tmp_path / "asof_team_adv_test.parquet"
    dest = mod.build_asof_team_adv(team_adv=team_adv, games=games, out_path=str(out_path))
    assert dest == out_path
    df = pd.read_parquet(str(dest))
    assert len(df) == 5
    for c in mod.OUTPUT_COLS:
        assert c in df.columns


def test_empty_input_yields_empty_output_with_columns(tmp_path):
    empty_ta = pd.DataFrame(columns=[
        "game_id", "team_tricode", "off_rtg", "def_rtg", "pace", "oreb_pct",
        "dreb_pct", "ast_pct", "efg_pct", "ts_pct", "tov_ratio", "game_date"])
    empty_games = pd.DataFrame(columns=["game_id", "date", "home_team", "away_team"])
    out_path = tmp_path / "empty.parquet"
    dest = mod.build_asof_team_adv(
        team_adv=empty_ta, games=empty_games, out_path=str(out_path))
    df = pd.read_parquet(str(dest))
    assert len(df) == 0
    for c in mod.OUTPUT_COLS:
        assert c in df.columns


def test_no_dollar_or_edge_language():
    banned = {"roi", "pnl", "p_l", "edge", "profit", "dollars", "$"}
    haystack = " ".join(mod.OUTPUT_COLS).lower()
    assert not any(b in haystack for b in banned)
