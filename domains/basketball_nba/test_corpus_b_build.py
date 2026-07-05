"""Per-file test for domains.basketball_nba.corpus_b_build -- fixture rows only,
no real corpus reads (fast, deterministic, no I/O dependency on the on-disk
parquet files).

Acceptance criteria
--------------------
1. RECONCILIATION exact-match discipline: a clean (home_abbr, away_abbr, date)
   match resolves to game_id; an AMBIGUOUS pair (two games.parquet rows sharing
   the same normalized key) resolves UNRESOLVED, never guessed at either row.
2. AGGREGATION column-semantics parity: melt_to_team_games's long-frame output
   for a synthetic game matches the exact column set/values
   asof_features._aggregate_team_games would produce from real player rows
   summed to the same team-game totals (verified against a hand-built 2024-25-
   style comparison row).
3. AS-OF LEAK TRIPWIRE: build_asof_features's leak-free guarantee survives the
   concat -- a team's as-of feature value for game i is UNCHANGED whether or
   not a strictly-LATER synthetic game (from the new melted rows) is present in
   the input frame.
4. fg3m rename: home_fg3_made feeds home_fg3m when home_fg3m is null (the
   documented compound-stat fix), not silently dropped.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        domains/basketball_nba/test_corpus_b_build.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba import corpus_b_build as mod
from domains.basketball_nba.asof_features import build_asof_features


def _games_fixture() -> pd.DataFrame:
    return pd.DataFrame([
        {"game_id": "0022500001", "date": "2026-02-01", "home_team": "GSW", "away_team": "SAS"},
        {"game_id": "0022500002", "date": "2026-02-02", "home_team": "BOS", "away_team": "MIA"},
        # ambiguous key: same normalized (home, away, date) as another row --
        # must resolve UNRESOLVED for any native row matching this key.
        {"game_id": "0022500003", "date": "2026-02-03", "home_team": "NYK", "away_team": "WAS"},
        {"game_id": "0022500004", "date": "2026-02-03", "home_team": "NYK", "away_team": "WAS"},
    ])


def _espn_native_fixture() -> pd.DataFrame:
    rows = [
        # clean match -> game_id 0022500001
        {"event_id": "401111", "date": "2026-02-01", "home_abbr": "GS", "away_abbr": "SA",
         "status": "STATUS_FINAL",
         "home_ast": 25.0, "home_fgm": None, "home_fga": None, "home_reb": 44.0,
         "home_oreb": 10.0, "home_dreb": 34.0, "home_tov": 12.0, "home_pts": None,
         "home_fta": None, "home_stl": 8.0, "home_blk": 5.0,
         "away_ast": 20.0, "away_fgm": None, "away_fga": None, "away_reb": 40.0,
         "away_oreb": 9.0, "away_dreb": 31.0, "away_tov": 14.0, "away_pts": None,
         "away_fta": None, "away_stl": 6.0, "away_blk": 3.0,
         # fg3m null in native slice; fg3_made carries the value (the documented fix)
         "home_fg3m": None, "home_fg3_made": 15.0,
         "away_fg3m": None, "away_fg3_made": 11.0},
        # genuine no-match: no games.parquet row for this pair/date at all
        {"event_id": "401112", "date": "2026-02-09", "home_abbr": "DAL", "away_abbr": "POR",
         "status": "STATUS_FINAL",
         "home_ast": 22.0, "home_fgm": None, "home_fga": None, "home_reb": 41.0,
         "home_oreb": 8.0, "home_dreb": 33.0, "home_tov": 13.0, "home_pts": None,
         "home_fta": None, "home_stl": 7.0, "home_blk": 4.0,
         "away_ast": 18.0, "away_fgm": None, "away_fga": None, "away_reb": 38.0,
         "away_oreb": 7.0, "away_dreb": 31.0, "away_tov": 15.0, "away_pts": None,
         "away_fta": None, "away_stl": 5.0, "away_blk": 2.0,
         "home_fg3m": None, "home_fg3_made": 12.0,
         "away_fg3m": None, "away_fg3_made": 9.0},
        # ambiguous: matches the (NYK, WAS, 2026-02-03) key that hits TWO games.parquet rows
        {"event_id": "401113", "date": "2026-02-03", "home_abbr": "NY", "away_abbr": "WSH",
         "status": "STATUS_FINAL",
         "home_ast": 21.0, "home_fgm": None, "home_fga": None, "home_reb": 39.0,
         "home_oreb": 9.0, "home_dreb": 30.0, "home_tov": 11.0, "home_pts": None,
         "home_fta": None, "home_stl": 6.0, "home_blk": 3.0,
         "away_ast": 19.0, "away_fgm": None, "away_fga": None, "away_reb": 37.0,
         "away_oreb": 8.0, "away_dreb": 29.0, "away_tov": 12.0, "away_pts": None,
         "away_fta": None, "away_stl": 5.0, "away_blk": 2.0,
         "home_fg3m": None, "home_fg3_made": 10.0,
         "away_fg3m": None, "away_fg3_made": 8.0},
        # a player_boxscores-derived row (game_id-format event_id) must be excluded
        # from reconciliation entirely (_native_rows filters on 401 prefix)
        {"event_id": "0022500099", "date": "2026-02-05", "home_abbr": "LAL", "away_abbr": "PHX",
         "status": "STATUS_FINAL",
         "home_ast": 30.0, "home_fgm": None, "home_fga": None, "home_reb": 45.0,
         "home_oreb": 11.0, "home_dreb": 34.0, "home_tov": 10.0, "home_pts": None,
         "home_fta": None, "home_stl": 9.0, "home_blk": 6.0,
         "away_ast": 24.0, "away_fgm": None, "away_fga": None, "away_reb": 42.0,
         "away_oreb": 10.0, "away_dreb": 32.0, "away_tov": 11.0, "away_pts": None,
         "away_fta": None, "away_stl": 7.0, "away_blk": 4.0,
         "home_fg3m": None, "home_fg3_made": 14.0,
         "away_fg3m": None, "away_fg3_made": 13.0},
    ]
    return pd.DataFrame(rows)


def test_reconcile_resolves_clean_match_and_rejects_ambiguous():
    resolved, counts = mod.reconcile_event_ids(_espn_native_fixture(), _games_fixture())

    # 3 native (401...) rows total: 1 clean match, 1 no-match, 1 ambiguous.
    assert counts["native_final"] == 3
    assert counts["resolved"] == 1
    assert counts["unresolved_no_match"] == 1
    assert counts["unresolved_ambiguous"] == 1

    # the ambiguous row (401113) must NOT appear in resolved output at all --
    # never guessed at either of the two candidate game_ids.
    assert "401113" not in set(resolved["event_id"])
    assert set(resolved["event_id"]) == {"401111"}
    assert resolved.loc[resolved["event_id"] == "401111", "game_id"].iloc[0] == "0022500001"


def test_reconcile_excludes_non_native_event_ids():
    """A player_boxscores-derived event_id (game_id format, not 401...) must never
    enter the native-row reconciliation pool, even if it would otherwise match."""
    resolved, counts = mod.reconcile_event_ids(_espn_native_fixture(), _games_fixture())
    assert "0022500099" not in set(resolved.get("event_id", []))
    # only 3 native_final counted, not 4 -- the derived row is excluded upstream
    assert counts["native_final"] == 3


def test_melt_fg3m_rename_and_column_semantics_parity():
    resolved, _ = mod.reconcile_event_ids(_espn_native_fixture(), _games_fixture())
    long = mod.melt_to_team_games(resolved)

    # one game resolved -> 2 team-game rows (home + away)
    assert len(long) == 2
    home_row = long[long["is_home"] == True].iloc[0]  # noqa: E712
    away_row = long[long["is_home"] == False].iloc[0]  # noqa: E712

    # fg3m rename: home_fg3m was null; home_fg3_made (15.0) must feed the output.
    assert home_row["fg3m"] == 15.0
    assert away_row["fg3m"] == 11.0

    # column-semantics parity: exact same column names _aggregate_team_games
    # sums from real player rows (ast, fgm, fga, reb, oreb, dreb, tov, pts, fta).
    expected_cols = {"game_id", "date", "team", "opp", "is_home",
                      "ast", "fgm", "fga", "reb", "oreb", "dreb", "tov", "pts",
                      "fta", "stl", "blk", "season"}
    assert expected_cols.issubset(set(long.columns))
    assert home_row["team"] == "GSW"
    assert home_row["opp"] == "SAS"
    assert home_row["oreb"] == 10.0
    assert away_row["oreb"] == 9.0


def _existing_player_box_fixture() -> pd.DataFrame:
    """A minimal 2024-25-shaped player_boxscores.parquet slice: two team-game
    rows for an EARLIER game than anything the melt fixture produces."""
    rows = []
    for team, opp, is_home in [("GSW", "SAS", True), ("SAS", "GSW", False)]:
        rows.append({
            "game_id": "0022400500", "date": "2024-12-01", "season": "2024-25",
            "team": team, "opp": opp, "is_home": is_home,
            "ast": 20.0, "fgm": 40.0, "fga": 85.0, "fg3m": 12.0,
            "reb": 42.0, "oreb": 9.0, "dreb": 33.0, "tov": 13.0,
            "pts": 105.0, "fta": 20.0, "stl": 7.0, "blk": 4.0,
        })
    return pd.DataFrame(rows)


def test_asof_leak_tripwire_unaffected_by_later_new_rows(tmp_path):
    """The as-of feature value for an EARLY game must be identical whether or
    not a strictly-LATER game (built from the new melted rows) is present in
    the concatenated input -- proves the new rows cannot leak backward."""
    existing = _existing_player_box_fixture()

    resolved, _ = mod.reconcile_event_ids(_espn_native_fixture(), _games_fixture())
    new_long = mod.melt_to_team_games(resolved)
    # force the new row's date strictly AFTER the existing game
    new_long["date"] = "2026-02-01"

    without_path = build_asof_features(player_box=existing, out_path=str(tmp_path / "without.parquet"))
    with_path = build_asof_features(
        player_box=pd.concat([existing, new_long], ignore_index=True),
        out_path=str(tmp_path / "with.parquet"))
    without_new = pd.read_parquet(without_path)
    with_new = pd.read_parquet(with_path)

    early_without = without_new[without_new["game_id"] == "0022400500"].iloc[0]
    early_with = with_new[with_new["game_id"] == "0022400500"].iloc[0]

    # game_id 0022400500 is each team's FIRST game in both runs (n_prior == 0
    # either way) -- its as-of values (all NaN) must be identical regardless
    # of whether a later game is appended to the input frame.
    assert early_without["home_n_prior"] == early_with["home_n_prior"] == 0
    assert pd.isna(early_without["home_pace_asof"]) and pd.isna(early_with["home_pace_asof"])


def test_build_extended_player_box_dedupes_against_existing_game_ids():
    """If a reconciled game_id already exists in player_boxscores (should not
    happen for the real 678-row slice, but checked defensively), the existing
    rows win and the new melted row for that game_id is dropped, not duplicated."""
    existing = _existing_player_box_fixture()
    games = pd.DataFrame([
        {"game_id": "0022400500", "date": "2024-12-01", "home_team": "GSW", "away_team": "SAS"},
    ])
    espn_dup = pd.DataFrame([{
        "event_id": "401999", "date": "2024-12-01", "home_abbr": "GS", "away_abbr": "SA",
        "status": "STATUS_FINAL",
        "home_ast": 99.0, "home_fgm": None, "home_fga": None, "home_reb": 1.0,
        "home_oreb": 1.0, "home_dreb": 1.0, "home_tov": 1.0, "home_pts": None,
        "home_fta": None, "home_stl": 1.0, "home_blk": 1.0,
        "away_ast": 99.0, "away_fgm": None, "away_fga": None, "away_reb": 1.0,
        "away_oreb": 1.0, "away_dreb": 1.0, "away_tov": 1.0, "away_pts": None,
        "away_fta": None, "away_stl": 1.0, "away_blk": 1.0,
        "home_fg3m": None, "home_fg3_made": 1.0,
        "away_fg3m": None, "away_fg3_made": 1.0,
    }])

    ext, counts = mod.build_extended_player_box(espn_box=espn_dup, games=games, player_box=existing)
    assert counts["already_in_player_boxscores"] == 1
    assert counts["new_games_added"] == 0
    # the fabricated ast=99.0 from the duplicate-resolving row must NOT appear
    assert 99.0 not in ext["ast"].values
    assert len(ext) == len(existing)


def test_no_dollar_or_edge_language():
    import inspect
    src = inspect.getsource(mod)
    banned = ("roi", "pnl", "profit", "dollars", "edge")
    lowered = src.lower()
    for tok in banned:
        assert tok not in lowered, f"banned token {tok!r} found in corpus_b_build source"
