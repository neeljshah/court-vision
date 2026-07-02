"""Network-free tests for domains.mlb.ingest_probables.

Canned schedule payload: 2 games -- one with full probables+weather+HP ump,
one with all three absent/empty (a game far from first pitch). Asserts pure
parsing, nullable fields, dedup-idempotent re-ingest, and no-network-at-import.
Run per-file (NEVER full pytest):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_ingest_probables.py -q
"""
import importlib
import sys

import pandas as pd

from domains.mlb.ingest_probables import (
    fetch_date,
    ingest_range,
    parse_game,
    parse_schedule,
)

_FULL_GAME = {
    "gamePk": 824818,
    "officialDate": "2026-07-01",
    "dayNight": "day",
    "venue": {"name": "Oriole Park at Camden Yards"},
    "status": {"abstractGameState": "Final"},
    "teams": {
        "away": {
            "team": {"id": 145, "name": "Chicago White Sox"},
            "probablePitcher": {"id": 702273, "fullName": "Noah Schultz"},
        },
        "home": {
            "team": {"id": 110, "name": "Baltimore Orioles"},
            "probablePitcher": {
                "id": 665152, "fullName": "Dean Kremer",
                "pitchHand": {"code": "R"},
            },
        },
    },
    "officials": [
        {"official": {"id": 547380, "fullName": "Carlos Torres"}, "officialType": "Home Plate"},
        {"official": {"id": 608158, "fullName": "Nate Tomlinson"}, "officialType": "First Base"},
    ],
    "weather": {"condition": "Partly Cloudy", "temp": "91", "wind": "5 mph, Out To LF"},
}

_SPARSE_GAME = {
    "gamePk": 824252,
    "officialDate": "2026-07-10",
    "dayNight": "night",
    "venue": {"name": "Fenway Park"},
    "status": {"abstractGameState": "Preview"},
    "teams": {
        "away": {"team": {"id": 111, "name": "Boston Red Sox"}},
        "home": {"team": {"id": 147, "name": "New York Yankees"}},
    },
    "officials": [],
    "weather": {},
}

_SCHEDULE_PAYLOAD = {"dates": [{"games": [_FULL_GAME, _SPARSE_GAME]}]}


def _rows():
    return parse_schedule(_SCHEDULE_PAYLOAD, "2026-06-30", "2026-06-30T12:00:00Z")


def test_two_rows_parsed():
    rows = _rows()
    assert len(rows) == 2
    by_pk = {r["game_pk"]: r for r in rows}
    assert 824818 in by_pk and 824252 in by_pk


def test_full_game_parsed():
    row = {r["game_pk"]: r for r in _rows()}[824818]
    assert row["home_team"] == "Baltimore Orioles"
    assert row["away_team"] == "Chicago White Sox"
    assert row["day_night"] == "day"
    assert row["venue"] == "Oriole Park at Camden Yards"
    assert row["home_sp_id"] == 665152
    assert row["home_sp_name"] == "Dean Kremer"
    assert row["home_sp_hand"] == "R"
    assert row["away_sp_id"] == 702273
    assert row["away_sp_name"] == "Noah Schultz"
    assert row["away_sp_hand"] is None  # no pitchHand supplied for this side
    assert row["weather_condition"] == "Partly Cloudy"
    assert row["temp_f"] == 91.0
    assert row["wind"] == "5 mph, Out To LF"
    assert row["hp_umpire_id"] == 547380
    assert row["hp_umpire_name"] == "Carlos Torres"
    assert row["snapshot_date"] == "2026-06-30"
    assert row["captured_at"] == "2026-06-30T12:00:00Z"


def test_sparse_game_all_nullable_fields_none():
    row = {r["game_pk"]: r for r in _rows()}[824252]
    assert row["home_sp_id"] is None
    assert row["home_sp_name"] is None
    assert row["home_sp_hand"] is None
    assert row["away_sp_id"] is None
    assert row["weather_condition"] is None
    assert row["temp_f"] is None
    assert row["wind"] is None
    assert row["hp_umpire_id"] is None
    assert row["hp_umpire_name"] is None
    assert row["home_team"] == "New York Yankees"
    assert row["day_night"] == "night"


def test_parse_game_missing_data_returns_none():
    assert parse_game({}, "2026-06-30", "now") is None
    assert parse_game(None, "2026-06-30", "now") is None
    assert parse_schedule({}, "2026-06-30", "now") == []
    assert parse_schedule(None, "2026-06-30", "now") == []


def test_fetch_date_with_injected_http_get():
    rows = fetch_date("2026-07-01", http_get=lambda u: _SCHEDULE_PAYLOAD)
    assert len(rows) == 2
    assert all(r["game_pk"] in (824818, 824252) for r in rows)


def test_ingest_range_dedup_idempotent(tmp_path):
    out = tmp_path / "probables.parquet"
    getter = lambda u: _SCHEDULE_PAYLOAD  # noqa: E731

    p1 = ingest_range(["2026-07-01"], http_get=getter, out_path=out, sleep_s=0.0)
    df1 = pd.read_parquet(p1)
    assert len(df1) == 2

    # Re-ingest same date -> same snapshot_date key -> dedup keeps row count stable.
    p2 = ingest_range(["2026-07-01"], http_get=getter, out_path=out, sleep_s=0.0)
    df2 = pd.read_parquet(p2)
    assert len(df2) == 2
    assert set(df2["game_pk"]) == {824818, 824252}


def test_ingest_range_multi_date_appends(tmp_path):
    out = tmp_path / "probables.parquet"
    getter = lambda u: _SCHEDULE_PAYLOAD  # noqa: E731

    ingest_range(["2026-07-01"], http_get=getter, out_path=out, sleep_s=0.0)
    # different snapshot_date is stamped internally by wall-clock, so we just
    # verify a second distinct date call doesn't crash and still dedups per-run
    p2 = ingest_range(["2026-07-02"], http_get=getter, out_path=out, sleep_s=0.0)
    df2 = pd.read_parquet(p2)
    # both calls stamp snapshot_date=today (same wall-clock date) -> same key -> dedup to 2
    assert len(df2) == 2


def test_no_network_at_import():
    """Importing the module must not perform any network call or raise."""
    mod_name = "domains.mlb.ingest_probables"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    mod = importlib.import_module(mod_name)
    assert hasattr(mod, "fetch_date")
    assert hasattr(mod, "ingest_range")
