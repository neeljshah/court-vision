"""Per-file unit tests for prop_underdog (NETWORK-FREE).

Run ONLY this file (full pytest freezes the box):
    python -m pytest scripts/platformkit/odds_provider/test_prop_underdog.py -q

Canned payload mirrors the REAL over_under_lines shape probed 2026-06-17 (trimmed):
one FIFA (World Cup) soccer player with two O/U lines + one MLB row that must be
filtered out. http_get is injected; nothing here touches the network.
"""
from __future__ import annotations

from scripts.platformkit.odds_provider.base import is_unavailable
from scripts.platformkit.odds_provider.prop_underdog import (
    UnderdogProvider, parse_props)


# Trimmed canned payload (real shape: over_under_lines / appearances / players /
# games). One FIFA player (Luis Diaz, Colombia) with 2 lines + one MLB row.
CANNED = {
    "players": [
        {"id": "P_FIFA", "first_name": "Luis", "last_name": "Diaz",
         "sport_id": "FIFA", "team_id": "T_COL"},
        {"id": "P_MLB", "first_name": "Some", "last_name": "Slugger",
         "sport_id": "MLB", "team_id": "T_MLB"},
    ],
    "appearances": [
        {"id": "A_FIFA", "player_id": "P_FIFA", "team_id": "T_COL",
         "match_id": 157095},
        {"id": "A_MLB", "player_id": "P_MLB", "team_id": "T_MLB",
         "match_id": 999},
    ],
    "games": [
        {"id": 157095, "full_team_names_title": "Uzbekistan vs Colombia",
         "short_title": "Uzbekistan vs Colombia",
         "home_team_id": "T_UZB", "away_team_id": "T_COL", "sport_id": "FIFA"},
        {"id": 999, "full_team_names_title": "A vs B",
         "home_team_id": "T_MLB", "away_team_id": "T_X", "sport_id": "MLB"},
    ],
    "over_under_lines": [
        {"id": "L1", "stat_value": 2.5,
         "options": [
             {"choice": "higher", "decimal_price": "1.53", "payout_multiplier": "0.75"},
             {"choice": "lower", "decimal_price": "2.57", "payout_multiplier": "1.13"},
         ],
         "over_under": {"appearance_stat": {
             "appearance_id": "A_FIFA", "display_stat": "Shots Attempted",
             "stat": "period_1_2_shots_attempted"}}},
        {"id": "L2", "stat_value": 1.5,
         "options": [
             {"choice": "higher", "decimal_price": "2.38"},
             {"choice": "lower", "decimal_price": "1.59"},
         ],
         "over_under": {"appearance_stat": {
             "appearance_id": "A_FIFA", "display_stat": "Shots on Target",
             "stat": "period_1_2_shots_on_target"}}},
        # MLB row -- must be filtered out for soccer_intl.
        {"id": "L_MLB", "stat_value": 0.5,
         "options": [{"choice": "higher", "decimal_price": "1.9"}],
         "over_under": {"appearance_stat": {
             "appearance_id": "A_MLB", "display_stat": "Home Runs",
             "stat": "hr"}}},
    ],
}


def test_parse_props_soccer_rows_only():
    rows = parse_props(CANNED, "soccer_intl", "FIFA")
    assert isinstance(rows, list)
    assert len(rows) == 2  # MLB filtered out
    by_stat = {r.stat: r for r in rows}
    assert set(by_stat) == {"Shots", "Shots On Target"}

    shots = by_stat["Shots"]
    assert shots.player == "Luis Diaz"
    assert shots.team == "Colombia"
    assert shots.match == "Uzbekistan vs Colombia"
    assert shots.line == 2.5
    assert shots.over_price == 1.53
    assert shots.under_price == 2.57
    assert shots.payout_type == "sportsbook"
    assert shots.source == "underdog"
    assert shots.as_of is not None


def test_provider_injected_http_get():
    prov = UnderdogProvider(http_get=lambda url: CANNED)
    rows = prov.fetch_props("soccer_intl")
    assert isinstance(rows, list)
    assert all(r.sport == "soccer_intl" for r in rows)
    assert all(r.player and r.stat and r.line is not None for r in rows)


def test_unsupported_sport_unavailable():
    prov = UnderdogProvider(http_get=lambda url: CANNED)
    res = prov.fetch_props("cricket")
    assert is_unavailable(res)


def test_injected_failure_degrades_no_raise():
    def boom(url):
        raise RuntimeError("network down")

    prov = UnderdogProvider(http_get=boom)
    res = prov.fetch_props("soccer_intl")
    assert is_unavailable(res)


def test_empty_body_unavailable():
    prov = UnderdogProvider(http_get=lambda url: {})
    res = prov.fetch_props("soccer_intl")
    assert is_unavailable(res)


def test_no_soccer_rows_unavailable():
    only_mlb = {k: v for k, v in CANNED.items()}
    only_mlb["players"] = [CANNED["players"][1]]
    res = parse_props(only_mlb, "soccer_intl", "FIFA")
    assert is_unavailable(res)


# Canned MLB payload mirroring the real sport_id "MLB" shape (probed 2026-06-18):
# one batter (two lines incl. the spaced "Hits + Runs + RBIs") + one pitcher
# ("Strikeouts" -> Pitcher Strikeouts; "Earned Runs Allowed" -> Earned Runs).
CANNED_MLB = {
    "players": [
        {"id": "P_BAT", "first_name": "Aaron", "last_name": "Judge",
         "sport_id": "MLB", "team_id": "T_NYY"},
        {"id": "P_PIT", "first_name": "Gerrit", "last_name": "Cole",
         "sport_id": "MLB", "team_id": "T_NYY"},
        {"id": "P_FIFA2", "first_name": "Some", "last_name": "Winger",
         "sport_id": "FIFA", "team_id": "T_X"},
    ],
    "appearances": [
        {"id": "A_BAT", "player_id": "P_BAT", "team_id": "T_NYY",
         "match_id": 5001},
        {"id": "A_PIT", "player_id": "P_PIT", "team_id": "T_NYY",
         "match_id": 5001},
        {"id": "A_FIFA2", "player_id": "P_FIFA2", "team_id": "T_X",
         "match_id": 6001},
    ],
    "games": [
        {"id": 5001, "full_team_names_title": "Boston Red Sox vs New York Yankees",
         "home_team_id": "T_BOS", "away_team_id": "T_NYY", "sport_id": "MLB"},
        {"id": 6001, "full_team_names_title": "A vs B", "sport_id": "FIFA"},
    ],
    "over_under_lines": [
        {"id": "M1", "stat_value": 1.5,
         "options": [
             {"choice": "higher", "decimal_price": "1.80"},
             {"choice": "lower", "decimal_price": "1.95"},
         ],
         "over_under": {"appearance_stat": {
             "appearance_id": "A_BAT", "display_stat": "Hits + Runs + RBIs"}}},
        {"id": "M2", "stat_value": 0.5,
         "options": [{"choice": "higher", "payout_multiplier": "0.9"}],
         "over_under": {"appearance_stat": {
             "appearance_id": "A_BAT", "display_stat": "Home Runs"}}},
        {"id": "M3", "stat_value": 6.5,
         "options": [
             {"choice": "higher", "decimal_price": "1.91"},
             {"choice": "lower", "decimal_price": "1.83"},
         ],
         "over_under": {"appearance_stat": {
             "appearance_id": "A_PIT", "display_stat": "Strikeouts"}}},
        {"id": "M4", "stat_value": 2.5,
         "options": [{"choice": "higher", "decimal_price": "2.10"}],
         "over_under": {"appearance_stat": {
             "appearance_id": "A_PIT", "display_stat": "Earned Runs Allowed"}}},
    ],
}


def test_parse_props_mlb_rows_canonical_stats():
    rows = parse_props(CANNED_MLB, "mlb", "MLB")
    assert isinstance(rows, list)
    assert len(rows) == 4  # FIFA player has no lines; all 4 MLB lines kept
    by_stat = {r.stat: r for r in rows}
    assert set(by_stat) == {
        "Hits+Runs+RBIs", "Home Runs", "Pitcher Strikeouts", "Earned Runs"}

    hrr = by_stat["Hits+Runs+RBIs"]
    assert hrr.player == "Aaron Judge"
    assert hrr.team == "New York Yankees"
    assert hrr.match == "Boston Red Sox vs New York Yankees"
    assert hrr.line == 1.5
    assert hrr.over_price == 1.80
    assert hrr.under_price == 1.95
    assert hrr.payout_type == "sportsbook"
    assert hrr.source == "underdog"

    # pick'em row (only a payout_multiplier, no decimal_price) -> no fabricated price
    hr = by_stat["Home Runs"]
    assert hr.over_price is None and hr.under_price is None
    assert hr.payout_type == "dfs_pickem"

    # bare "Strikeouts" on a pitcher disambiguates to Pitcher Strikeouts
    assert by_stat["Pitcher Strikeouts"].player == "Gerrit Cole"


def test_provider_fetch_mlb_injected():
    prov = UnderdogProvider(http_get=lambda url: CANNED_MLB)
    rows = prov.fetch_props("mlb")
    assert isinstance(rows, list)
    assert all(r.sport == "mlb" for r in rows)
    assert all(r.player and r.stat and r.line is not None for r in rows)


def test_nba_sport_wired_offseason_empty():
    # NBA id is wired; off-season payload (no BASKETBALL rows) -> UNAVAILABLE,
    # not an error, and not an unsupported-sport rejection.
    prov = UnderdogProvider(http_get=lambda url: CANNED_MLB)
    res = prov.fetch_props("nba")
    assert is_unavailable(res)
    assert "unsupported" not in res.get("reason", "")
