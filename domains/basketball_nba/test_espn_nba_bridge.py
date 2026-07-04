"""Per-file test for domains.basketball_nba.espn_nba_bridge -- fixture rows
only, no real corpus reads (fast, deterministic, no I/O dependency on the
on-disk parquet files). Covers: tricode normalization, one-season bridge_one
join correctness (match + non-match), and bridge_all_seasons' auto-pick of
the best-matching season per linescores file.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_espn_nba_bridge.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.espn_nba_bridge import (
    _norm_abbr,
    bridge_all_seasons,
    bridge_one,
)


def _linescores_fixture() -> pd.DataFrame:
    return pd.DataFrame([
        {"event_id": "401111", "home_abbr": "GS", "away_abbr": "SA",
         "home_q1": 25, "home_q2": 30, "home_q3": 28, "home_q4": 20,
         "away_q1": 22, "away_q2": 24, "away_q3": 26, "away_q4": 30,
         "date": "2024-11-01"},
        {"event_id": "401112", "home_abbr": "BOS", "away_abbr": "MIA",
         "home_q1": 20, "home_q2": 22, "home_q3": 24, "home_q4": 26,
         "away_q1": 18, "away_q2": 20, "away_q3": 22, "away_q4": 24,
         "date": "2024-11-02"},
        # deliberately unmatched: no corresponding box game on this date/pair
        {"event_id": "401113", "home_abbr": "NY", "away_abbr": "WSH",
         "home_q1": 25, "home_q2": 25, "home_q3": 25, "home_q4": 25,
         "away_q1": 20, "away_q2": 20, "away_q3": 20, "away_q4": 20,
         "date": "2024-11-03"},
    ])


def _boxscores_fixture() -> pd.DataFrame:
    rows = []
    # game 1: GSW (home) vs SAS (away) on 2024-11-01, season 2024-25
    for team, is_home in [("GSW", True), ("SAS", False)]:
        rows.append({"game_id": "0022400001", "date": "2024-11-01",
                      "season": "2024-25", "team": team, "is_home": is_home,
                      "player_id": 1, "player_name": "P1"})
    # game 2: BOS (home) vs MIA (away) on 2024-11-02, season 2024-25
    for team, is_home in [("BOS", True), ("MIA", False)]:
        rows.append({"game_id": "0022400002", "date": "2024-11-02",
                      "season": "2024-25", "team": team, "is_home": is_home,
                      "player_id": 2, "player_name": "P2"})
    # a 2025-26 season game that should NOT match the 2024-25 linescores fixture
    for team, is_home in [("NYK", True), ("WAS", False)]:
        rows.append({"game_id": "0022500099", "date": "2025-11-03",
                      "season": "2025-26", "team": team, "is_home": is_home,
                      "player_id": 3, "player_name": "P3"})
    return pd.DataFrame(rows)


def test_norm_abbr_maps_divergent_espn_tricodes():
    assert _norm_abbr("GS") == "GSW"
    assert _norm_abbr("NO") == "NOP"
    assert _norm_abbr("NY") == "NYK"
    assert _norm_abbr("SA") == "SAS"
    assert _norm_abbr("UTAH") == "UTA"
    assert _norm_abbr("WSH") == "WAS"
    # unmapped tricodes pass through unchanged
    assert _norm_abbr("BOS") == "BOS"
    assert _norm_abbr("mia") == "MIA"


def test_bridge_one_matches_only_real_overlaps():
    lines = _linescores_fixture()
    box = _boxscores_fixture()
    box_2425 = box[box["season"] == "2024-25"]

    out = bridge_one(lines, box_2425)

    # exactly 2 of the 3 linescores rows match (event_id 401113 is a genuine miss)
    assert len(out) == 2
    assert set(out["event_id"]) == {"401111", "401112"}
    assert set(out["game_id"]) == {"0022400001", "0022400002"}
    assert (out["match_confidence"] == "exact").all()


def test_bridge_one_is_outcome_free_join_key():
    """The join uses only tricode+date columns -- no score/outcome field is
    read as part of the merge keys (verifies no accidental leak column)."""
    lines = _linescores_fixture()
    box = _boxscores_fixture()
    out = bridge_one(lines, box[box["season"] == "2024-25"])
    # quarter-score columns are carried through untouched, not used as join keys
    row = out[out["event_id"] == "401111"].iloc[0]
    assert row["home_q1"] == 25
    assert row["away_q4"] == 30


def test_bridge_all_seasons_picks_best_matching_season(tmp_path):
    lines_path = tmp_path / "linescores_fixture.parquet"
    _linescores_fixture().to_parquet(lines_path, index=False)
    box = _boxscores_fixture()

    out, stats = bridge_all_seasons(linescores_paths=[str(lines_path)], box=box)

    assert len(out) == 2
    assert (out["season"] == "2024-25").all()
    fname = lines_path.name
    assert stats[fname]["best_season"] == "2024-25"
    assert stats[fname]["bridged"] == 2


def test_bridge_all_seasons_skips_nonexistent_file(tmp_path):
    missing = tmp_path / "does_not_exist.parquet"
    box = _boxscores_fixture()
    out, stats = bridge_all_seasons(linescores_paths=[str(missing)], box=box)
    assert len(out) == 0
    assert stats == {}
