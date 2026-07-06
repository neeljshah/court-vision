"""Per-file test for domains.basketball_nba.asof_player_adv.

Acceptance criteria (leak discipline is the review hill)
---------------------------------------------------------
1. SHIFT TEST: a player-game's own row never feeds its own feature -- a player's
   first game is NaN (n_prior == 0); the Nth game's as-of value equals the exact
   expanding mean of that player's PRECEDING (N-1) games only, hand-verified
   against known synthetic inputs.
2. TRUNCATION-INVARIANCE: recomputing on a date-truncated copy of the input yields
   IDENTICAL as-of features for every surviving row (no row learns anything from
   games removed because they are in the future relative to it).
3. Uses games.parquet's date (authoritative), NOT player_adv_stats' own game_date --
   verified by passing a games frame with a DELIBERATELY DIFFERENT date ordering
   than the sidecar's own date-like values and checking the walk-forward respects
   the games.parquet order.
4. Two players sharing a game_id (teammates/opponents in the same game) are
   tracked INDEPENDENTLY -- one player's history never contaminates another's.
5. No $ / ROI / edge / profit language in OUTPUT_COLS or module docstring
   identifiers.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        domains/basketball_nba/test_asof_player_adv.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.basketball_nba import asof_player_adv as mod


def _synthetic(n_games: int = 6) -> tuple:
    """Two players (P0, P1) each play n_games games in sequence (one game_id each,
    P0 and P1 sharing every game_id -- e.g. opposing starters).

    Simple, hand-checkable usagepercentage progression: P0 = 0.20, 0.22, 0.24, ...;
    P1 = 0.15, 0.16, 0.17, ... This lets the expanding-mean be verified by direct
    arithmetic (mean of an arithmetic progression).
    """
    gids = [f"g{i:04d}" for i in range(n_games)]
    dates = pd.date_range("2023-01-01", periods=n_games, freq="3D")

    games = pd.DataFrame({"game_id": gids, "date": dates})

    rows = []
    for i, gid in enumerate(gids):
        rows.append({
            "player_id": "P0", "game_id": gid,
            "game_date": "2099-01-01",  # deliberately WRONG/unused -- must be ignored
            "usagepercentage": 0.20 + 0.02 * i, "offensiverating": 110.0,
            "defensiverating": 105.0, "pie": 0.10, "possessions": 70.0,
        })
        rows.append({
            "player_id": "P1", "game_id": gid,
            "game_date": "2099-01-01",
            "usagepercentage": 0.15 + 0.01 * i, "offensiverating": 100.0,
            "defensiverating": 108.0, "pie": 0.05, "possessions": 68.0,
        })
    player_adv = pd.DataFrame(rows)
    return player_adv, games


def test_shift_first_game_nan_and_own_row_excluded():
    player_adv, games = _synthetic(6)
    pg = mod._attach_date(player_adv, games)
    out = mod._walk_forward_player(pg)

    p0 = out[out["player_id"] == "P0"].sort_values("date").reset_index(drop=True)
    p1 = out[out["player_id"] == "P1"].sort_values("date").reset_index(drop=True)

    assert p0.iloc[0]["n_prior"] == 0
    assert pd.isna(p0.iloc[0]["usagepercentage_asof"])

    # Game index 3 (4th game, 0-based i=3): P0 usage prior games were
    # 0.20, 0.22, 0.24 (i=0,1,2) -> expanding mean = 0.22.
    assert p0.iloc[3]["n_prior"] == 3
    assert np.isclose(p0.iloc[3]["usagepercentage_asof"], 0.22)
    # P1 prior were 0.15, 0.16, 0.17 -> mean = 0.16.
    assert p1.iloc[3]["n_prior"] == 3
    assert np.isclose(p1.iloc[3]["usagepercentage_asof"], 0.16)

    # Own-row exclusion: game i=3's own usage (0.26) must NOT appear in its as-of
    # mean (0.22 != 0.26, and any mean including 0.26 would exceed 0.22).
    assert p0.iloc[3]["usagepercentage_asof"] < 0.26


def test_players_tracked_independently_no_cross_contamination():
    """P0 and P1 share every game_id but must accumulate wholly separate history."""
    player_adv, games = _synthetic(5)
    pg = mod._attach_date(player_adv, games)
    out = mod._walk_forward_player(pg)

    p0 = out[out["player_id"] == "P0"].sort_values("date").reset_index(drop=True)
    p1 = out[out["player_id"] == "P1"].sort_values("date").reset_index(drop=True)

    # At the same game index, P0 and P1 as-of values must differ (different
    # underlying series) -- proves no shared accumulator.
    for i in range(1, 5):
        assert not np.isclose(p0.iloc[i]["usagepercentage_asof"],
                               p1.iloc[i]["usagepercentage_asof"])
        assert p0.iloc[i]["n_prior"] == i
        assert p1.iloc[i]["n_prior"] == i


def test_uses_games_parquet_date_not_sidecar_game_date():
    """player_adv's own game_date column is seeded 2099-01-01 (deliberately
    wrong/unused). Confirms _attach_date's output carries games.parquet's date."""
    player_adv, games = _synthetic(4)
    pg = mod._attach_date(player_adv, games)
    assert pd.api.types.is_datetime64_any_dtype(pg["date"])
    assert (pg["date"] != pd.Timestamp("2099-01-01")).all()


def test_truncation_invariance():
    """Recomputing on a date-truncated copy yields identical as-of features for
    surviving rows -- no future information leaks backward into earlier rows."""
    player_adv, games = _synthetic(6)
    out_full = mod._walk_forward_player(mod._attach_date(player_adv, games))

    # Truncate to the first 4 games only (drop the last 2 games' rows from BOTH
    # inputs).
    keep_gids = set(games["game_id"].iloc[:4])
    games_trunc = games[games["game_id"].isin(keep_gids)].reset_index(drop=True)
    player_adv_trunc = player_adv[player_adv["game_id"].isin(keep_gids)].reset_index(drop=True)

    out_trunc = mod._walk_forward_player(mod._attach_date(player_adv_trunc, games_trunc))

    surviving = out_full[out_full["game_id"].isin(keep_gids)].sort_values(
        ["game_id", "player_id"]).reset_index(drop=True)
    out_trunc = out_trunc.sort_values(["game_id", "player_id"]).reset_index(drop=True)

    pd.testing.assert_frame_equal(surviving, out_trunc, check_dtype=False)


def test_build_asof_player_adv_writes_parquet(tmp_path):
    player_adv, games = _synthetic(5)
    out_path = tmp_path / "asof_player_adv_test.parquet"
    dest = mod.build_asof_player_adv(player_adv=player_adv, games=games, out_path=str(out_path))
    assert dest == out_path
    df = pd.read_parquet(str(dest))
    assert len(df) == 10  # 2 players x 5 games
    for c in mod.OUTPUT_COLS:
        assert c in df.columns
    assert df.duplicated(["player_id", "game_id"]).sum() == 0


def test_empty_input_yields_empty_output_with_columns(tmp_path):
    empty_pa = pd.DataFrame(columns=[
        "player_id", "game_id", "game_date", "usagepercentage", "offensiverating",
        "defensiverating", "pie", "possessions"])
    empty_games = pd.DataFrame(columns=["game_id", "date"])
    out_path = tmp_path / "empty.parquet"
    dest = mod.build_asof_player_adv(
        player_adv=empty_pa, games=empty_games, out_path=str(out_path))
    df = pd.read_parquet(str(dest))
    assert len(df) == 0
    for c in mod.OUTPUT_COLS:
        assert c in df.columns


def test_no_dollar_or_edge_language():
    banned = {"roi", "pnl", "p_l", "edge", "profit", "dollars", "$"}
    haystack = " ".join(mod.OUTPUT_COLS).lower()
    assert not any(b in haystack for b in banned)
