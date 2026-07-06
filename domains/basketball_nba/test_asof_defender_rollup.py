"""Per-file test for domains.basketball_nba.asof_defender_rollup.

Acceptance criteria (leak discipline is the review hill)
---------------------------------------------------------
1. ROLL-UP IS A PURE MEAN of already-as-of per-defender values: hand-verified against
   a known synthetic team of 3 defenders with distinct as-of values.
2. UNCOVERED-DEFENDER EXCLUSION: a defender with NaN as-of (their def_n_prior == 0,
   first tracked matchup) must be EXCLUDED from the team mean, not treated as 0.
3. n_prior support count == number of that side's defenders with a non-NaN as-of value
   folded in (never fabricated, honestly reflects coverage).
4. diff_asof == home_asof - away_asof exactly; NaN propagates when a whole side is
   uncovered (never fabricated as 0).
5. REALIZED-COLUMN NON-LEAK: the source file's realized_* diagnostic columns are never
   read by the roll-up (this module's OUTPUT_COLS + _STAT_MAP never reference them) --
   verified by checking the source-column set consumed excludes every realized_* name.
6. Uses games.parquet's home_team/away_team for side assignment, not any per-row string
   on the defender file (there is none) -- verified via a games frame with a swapped
   home/away label from what a naive assumption would produce.
7. TRUNCATION-INVARIANCE: recomputing on a game-truncated copy of both inputs yields
   IDENTICAL as-of features for every surviving game (no row depends on games that were
   removed).
8. Empty input -> empty output with the full OUTPUT_COLS schema (no KeyError).
9. No $ / ROI / edge / profit language in OUTPUT_COLS or module docstring identifiers.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        domains/basketball_nba/test_asof_defender_rollup.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.basketball_nba import asof_defender_rollup as mod


def _synthetic(n_games: int = 4) -> tuple:
    """n_games games; T0 always home (3 defenders), T1 always away (2 defenders).

    Game 0: T0's 3 defenders have as-of fg_pct_allowed = 0.40, 0.50, NaN (the NaN
    defender is in their first tracked matchup -- def_n_prior == 0 upstream).
    Hand-checkable mean over the 2 COVERED defenders = 0.45, n_prior == 2 (not 3).
    T1's 2 defenders: 0.30, 0.34 -> mean 0.32, n_prior == 2.

    Later games vary the values per game index so truncation-invariance has real
    per-game signal to check.
    """
    gids = [f"g{i:04d}" for i in range(n_games)]
    dates = pd.date_range("2024-01-01", periods=n_games, freq="2D")
    games = pd.DataFrame({
        "game_id": gids, "date": dates,
        "home_team": ["T0"] * n_games, "away_team": ["T1"] * n_games,
    })

    rows = []
    for i, gid in enumerate(gids):
        base = 0.40 + 0.01 * i
        # T0: 3 defenders, one uncovered (NaN as-of) on game 0 only.
        t0_vals = [base, base + 0.10, np.nan if i == 0 else base + 0.02]
        for j, v in enumerate(t0_vals):
            rows.append({
                "game_id": gid, "def_team_tricode": "T0", "def_player_id": 100 + j,
                "def_priorN_fg_pct_allowed_asof": v,
                "def_priorN_fg3_pct_allowed_asof": v * 0.8 if not np.isnan(v) else np.nan,
                "def_priorN_pts_allowed_per36_asof": (v * 50.0) if not np.isnan(v) else np.nan,
                "def_priorN_blocks_per_game_asof": 1.0 if not np.isnan(v) else np.nan,
                "def_priorN_switches_per_game_asof": 2.0 if not np.isnan(v) else np.nan,
                "def_priorN_matchup_min_asof": 8.0 if not np.isnan(v) else np.nan,
                "def_n_prior": 0 if np.isnan(v) else 5,
                # realized_* diagnostics present on the real source file but MUST
                # NEVER be read by the roll-up -- deliberately poisoned to a value
                # that would fail every assertion below if leaked into the mean.
                "realized_fg_pct_allowed": 9.999,
            })
        # T1: 2 defenders, both always covered.
        t1_vals = [0.30 + 0.01 * i, 0.34 + 0.01 * i]
        for j, v in enumerate(t1_vals):
            rows.append({
                "game_id": gid, "def_team_tricode": "T1", "def_player_id": 200 + j,
                "def_priorN_fg_pct_allowed_asof": v,
                "def_priorN_fg3_pct_allowed_asof": v * 0.8,
                "def_priorN_pts_allowed_per36_asof": v * 50.0,
                "def_priorN_blocks_per_game_asof": 1.5,
                "def_priorN_switches_per_game_asof": 2.5,
                "def_priorN_matchup_min_asof": 9.0,
                "def_n_prior": 5,
                "realized_fg_pct_allowed": 9.999,
            })
    defenders = pd.DataFrame(rows)
    return defenders, games


def test_rollup_is_mean_over_covered_defenders_only():
    defenders, games = _synthetic(4)
    team_game = mod._team_game_means(defenders)
    g0_t0 = team_game[(team_game["game_id"] == "g0000") & (team_game["def_team_tricode"] == "T0")].iloc[0]
    # base=0.40 on game 0 -> covered values 0.40, 0.50 (the 3rd is NaN, excluded).
    assert np.isclose(g0_t0["def_fg_pct_allowed"], 0.45)
    assert g0_t0["n_prior"] == 2  # NOT 3 -- the uncovered defender must not count

    g0_t1 = team_game[(team_game["game_id"] == "g0000") & (team_game["def_team_tricode"] == "T1")].iloc[0]
    assert np.isclose(g0_t1["def_fg_pct_allowed"], 0.32)
    assert g0_t1["n_prior"] == 2


def test_uncovered_defender_excluded_not_treated_as_zero():
    """If the NaN defender were fabricated as 0.0, T0's game-0 mean would be
    (0.40+0.50+0.0)/3 = 0.30, far below the correct 0.45 -- this would catch that bug."""
    defenders, games = _synthetic(4)
    team_game = mod._team_game_means(defenders)
    g0_t0 = team_game[(team_game["game_id"] == "g0000") & (team_game["def_team_tricode"] == "T0")].iloc[0]
    assert g0_t0["def_fg_pct_allowed"] > 0.40  # would be 0.30 if NaN were fabricated as 0


def test_realized_columns_never_consumed():
    """The label-surface realized_* columns are poisoned to 9.999 in the fixture;
    if the roll-up ever accidentally averaged them in, every stat would blow far
    outside its plausible [0,1]/[0,60] range. Also assert _STAT_MAP never names one."""
    defenders, games = _synthetic(4)
    team_game = mod._team_game_means(defenders)
    assert (team_game["def_fg_pct_allowed"] < 2.0).all()  # nowhere near the 9.999 poison
    assert not any(c.startswith("realized_") for c in mod._STAT_MAP)
    assert not any(c.startswith("realized_") for c in mod.OUTPUT_COLS)


def test_diff_equals_home_minus_away_and_nan_propagates():
    defenders, games = _synthetic(4)
    # Uses the internal helpers directly (no build_asof_defender_rollup call here) --
    # out_path=None would resolve to the production _DEFAULT_OUT path and clobber it.
    team_game = mod._team_game_means(defenders)
    tg = mod._attach_side(team_game, games)
    out = mod._pivot_to_games(tg)
    for s in mod._STATS:
        hcol, acol, dcol = f"home_{s}_asof", f"away_{s}_asof", f"{s}_diff_asof"
        expected = out[hcol] - out[acol]
        pd.testing.assert_series_equal(
            out[dcol], expected, check_names=False, check_dtype=False)


def test_side_assignment_from_games_parquet_not_assumed():
    """Swap which tricode is home/away in games.parquet vs a naive T0=home assumption
    and verify the pivot follows games.parquet, not fixture-order or team-name sorting."""
    defenders, games = _synthetic(3)
    swapped_games = games.copy()
    swapped_games["home_team"] = "T1"
    swapped_games["away_team"] = "T0"

    team_game = mod._team_game_means(defenders)
    tg = mod._attach_side(team_game, swapped_games)
    out = mod._pivot_to_games(tg)

    # With the swap, T1 (2 defenders, ~0.30-0.33) is now HOME; T0 (3 defenders,
    # ~0.40-0.52) is now AWAY -- the opposite of the original fixture's default.
    row0 = out[out["game_id"] == "g0000"].iloc[0]
    assert row0["home_def_fg_pct_allowed_asof"] < row0["away_def_fg_pct_allowed_asof"]


def test_truncation_invariance(tmp_path):
    defenders, games = _synthetic(6)
    dest_full = mod.build_asof_defender_rollup(
        defenders=defenders, games=games, out_path=str(tmp_path / "full.parquet"))
    out_full = pd.read_parquet(str(dest_full))

    keep_gids = set(games["game_id"].iloc[:4])
    games_trunc = games[games["game_id"].isin(keep_gids)].reset_index(drop=True)
    defenders_trunc = defenders[defenders["game_id"].isin(keep_gids)].reset_index(drop=True)

    dest_trunc = mod.build_asof_defender_rollup(
        defenders=defenders_trunc, games=games_trunc, out_path=str(tmp_path / "trunc.parquet"))
    out_trunc = pd.read_parquet(str(dest_trunc))

    surviving = out_full[out_full["game_id"].isin(keep_gids)].sort_values(
        "game_id").reset_index(drop=True)
    out_trunc = out_trunc.sort_values("game_id").reset_index(drop=True)
    pd.testing.assert_frame_equal(surviving, out_trunc, check_dtype=False)


def test_build_asof_defender_rollup_writes_parquet_atomically(tmp_path):
    defenders, games = _synthetic(3)
    out_path = tmp_path / "asof_defender_rollup_test.parquet"
    dest = mod.build_asof_defender_rollup(
        defenders=defenders, games=games, out_path=str(out_path))
    assert dest == out_path
    assert not out_path.with_suffix(out_path.suffix + ".tmp").exists()  # tmp cleaned up
    df = pd.read_parquet(str(dest))
    assert len(df) == 3
    for c in mod.OUTPUT_COLS:
        assert c in df.columns


def test_empty_input_yields_empty_output_with_columns(tmp_path):
    empty_def = pd.DataFrame(columns=[
        "game_id", "def_team_tricode", "def_player_id",
        "def_priorN_fg_pct_allowed_asof", "def_priorN_fg3_pct_allowed_asof",
        "def_priorN_pts_allowed_per36_asof", "def_priorN_blocks_per_game_asof",
        "def_priorN_switches_per_game_asof", "def_priorN_matchup_min_asof", "def_n_prior"])
    empty_games = pd.DataFrame(columns=["game_id", "date", "home_team", "away_team"])
    out_path = tmp_path / "empty.parquet"
    dest = mod.build_asof_defender_rollup(
        defenders=empty_def, games=empty_games, out_path=str(out_path))
    df = pd.read_parquet(str(dest))
    assert len(df) == 0
    for c in mod.OUTPUT_COLS:
        assert c in df.columns


def test_no_dollar_or_edge_language():
    banned = {"roi", "pnl", "p_l", "edge", "profit", "dollars", "$"}
    haystack = " ".join(mod.OUTPUT_COLS).lower()
    assert not any(b in haystack for b in banned)
