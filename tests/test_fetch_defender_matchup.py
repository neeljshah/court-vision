"""tests/test_fetch_defender_matchup.py — offline unit tests for the
per-game defender-matchup scraper.

All tests run offline in <5s. Network is never touched. The nba_api endpoint
is monkey-patched with a synthetic DataFrame that mimics the shape of
`BoxScoreMatchupsV3.get_data_frames()[0]` observed live on 2026-05-24.

Run:
    python -m pytest tests/test_fetch_defender_matchup.py -v
"""
from __future__ import annotations

import json
import os
import sys
import time
from unittest.mock import patch

import pandas as pd
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from scripts import fetch_defender_matchup as fdm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _synthetic_matchups_df() -> pd.DataFrame:
    """Mimic the live BoxScoreMatchupsV3 frame: 4 rows, 2 defenders."""
    return pd.DataFrame([
        {
            # LeBron guarded by Tatum
            "gameId": "0099999999", "teamTricode": "BOS",
            "personIdOff": 2544, "firstNameOff": "LeBron", "familyNameOff": "James",
            "personIdDef": 1628369, "firstNameDef": "Jayson", "familyNameDef": "Tatum",
            "matchupMinutes": "5:30", "partialPossessions": 42.0,
            "switchesOn": 1, "playerPoints": 8,
            "matchupAssists": 0, "matchupTurnovers": 1, "matchupBlocks": 0,
            "matchupFieldGoalsMade": 3, "matchupFieldGoalsAttempted": 7,
            "matchupFieldGoalsPercentage": 0.429,
            "matchupThreePointersMade": 1, "matchupThreePointersAttempted": 3,
            "matchupThreePointersPercentage": 0.333,
            "helpBlocks": 0,
            "matchupFreeThrowsMade": 1, "matchupFreeThrowsAttempted": 2,
            "shootingFouls": 0,
        },
        {
            # LeBron guarded by Brown
            "gameId": "0099999999", "teamTricode": "BOS",
            "personIdOff": 2544, "firstNameOff": "LeBron", "familyNameOff": "James",
            "personIdDef": 1627759, "firstNameDef": "Jaylen", "familyNameDef": "Brown",
            "matchupMinutes": "2:00", "partialPossessions": 18.0,
            "switchesOn": 0, "playerPoints": 4,
            "matchupAssists": 1, "matchupTurnovers": 0, "matchupBlocks": 1,
            "matchupFieldGoalsMade": 2, "matchupFieldGoalsAttempted": 4,
            "matchupFieldGoalsPercentage": 0.500,
            "matchupThreePointersMade": 0, "matchupThreePointersAttempted": 1,
            "matchupThreePointersPercentage": 0.000,
            "helpBlocks": 1,
            "matchupFreeThrowsMade": 0, "matchupFreeThrowsAttempted": 0,
            "shootingFouls": 1,
        },
        {
            # Davis guarded by Tatum (same defender, different offensive player)
            "gameId": "0099999999", "teamTricode": "BOS",
            "personIdOff": 203076, "firstNameOff": "Anthony", "familyNameOff": "Davis",
            "personIdDef": 1628369, "firstNameDef": "Jayson", "familyNameDef": "Tatum",
            "matchupMinutes": "3:00", "partialPossessions": 22.0,
            "switchesOn": 0, "playerPoints": 6,
            "matchupAssists": 0, "matchupTurnovers": 0, "matchupBlocks": 0,
            "matchupFieldGoalsMade": 3, "matchupFieldGoalsAttempted": 5,
            "matchupFieldGoalsPercentage": 0.600,
            "matchupThreePointersMade": 0, "matchupThreePointersAttempted": 0,
            "matchupThreePointersPercentage": 0.000,
            "helpBlocks": 0,
            "matchupFreeThrowsMade": 0, "matchupFreeThrowsAttempted": 0,
            "shootingFouls": 0,
        },
        {
            # Unmatched row (no def player) — should be filtered out
            "gameId": "0099999999", "teamTricode": "BOS",
            "personIdOff": 999, "firstNameOff": "Bench", "familyNameOff": "Player",
            "personIdDef": None, "firstNameDef": "", "familyNameDef": "",
            "matchupMinutes": "", "partialPossessions": 0.0,
            "switchesOn": 0, "playerPoints": 0,
            "matchupAssists": 0, "matchupTurnovers": 0, "matchupBlocks": 0,
            "matchupFieldGoalsMade": 0, "matchupFieldGoalsAttempted": 0,
            "matchupFieldGoalsPercentage": 0.0,
            "matchupThreePointersMade": 0, "matchupThreePointersAttempted": 0,
            "matchupThreePointersPercentage": 0.0,
            "helpBlocks": 0,
            "matchupFreeThrowsMade": 0, "matchupFreeThrowsAttempted": 0,
            "shootingFouls": 0,
        },
    ])


class _FakeBoxScoreMatchupsV3:
    def __init__(self, game_id: str, timeout: int = 20) -> None:
        self.game_id = game_id
        self._df = _synthetic_matchups_df()

    def get_data_frames(self):
        return [self._df]


# ---------------------------------------------------------------------------
# Test 1 — Parser produces canonical schema + stitched player names.
# ---------------------------------------------------------------------------

def test_parse_matchups_frame_normalizes_schema() -> None:
    df = _synthetic_matchups_df()
    records = fdm._parse_matchups_frame(df)

    # 4 rows in / 4 rows out — _parse does not filter (summarize does).
    assert len(records) == 4

    # Schema check: required snake_case keys exist
    sample = records[0]
    required = {
        "game_id", "off_player_id", "def_player_id",
        "off_player_name", "def_player_name", "matchup_minutes",
        "matchup_minutes_float", "partial_possessions", "player_points",
        "matchup_fg_made", "matchup_fg_attempted", "matchup_fg_pct",
        "matchup_3pm", "matchup_3pa", "help_blocks",
    }
    missing = required - set(sample.keys())
    assert not missing, f"missing keys: {missing}"

    # Stitched name from first + last
    assert sample["off_player_name"] == "LeBron James"
    assert sample["def_player_name"] == "Jayson Tatum"

    # Clock parse "5:30" → 5.5 minutes
    assert sample["matchup_minutes_float"] == 5.5

    # No raw camelCase leakage
    assert "personIdOff" not in sample
    assert "_off_first" not in sample


# ---------------------------------------------------------------------------
# Test 2 — Defender summary aggregates rows correctly + computes percentages.
# ---------------------------------------------------------------------------

def test_summarize_defender_aggregates_and_computes_pct() -> None:
    df = _synthetic_matchups_df()
    raw = fdm._parse_matchups_frame(df)
    summary = fdm.summarize_defender(
        raw, game_id="0099999999", season="2024-25", game_date="2024-12-25",
    )

    # 2 distinct defenders (Tatum, Brown) — the None-defender row drops out.
    assert len(summary) == 2

    # Tatum guarded BOTH LeBron and Davis → 2 matchups, 5.5 + 3.0 = 8.5 min
    tatum = next(r for r in summary if r["def_player_id"] == 1628369)
    assert tatum["matchups_count"] == 2
    assert tatum["matchup_minutes_total"] == 8.5
    # PTS allowed: 8 + 6 = 14
    assert tatum["points_allowed"] == 14
    # FG: (3+3) / (7+5) = 6/12 = 0.5
    assert tatum["fg_made_allowed"] == 6
    assert tatum["fg_attempted_allowed"] == 12
    assert tatum["fg_pct_allowed"] == 0.5
    # 3PT: 1/3
    assert tatum["fg3_pct_allowed"] == round(1 / 3, 4)
    # Metadata propagation
    assert tatum["game_id"] == "0099999999"
    assert tatum["season"] == "2024-25"
    assert tatum["game_date"] == "2024-12-25"
    assert tatum["def_team_tricode"] == "BOS"

    # Brown: 1 matchup, divide-by-zero guard on 3PT% (0 attempts ≠ NaN)
    brown = next(r for r in summary if r["def_player_id"] == 1627759)
    assert brown["matchups_count"] == 1
    assert brown["points_allowed"] == 4
    assert brown["fg3_pct_allowed"] == 0.0   # 0/1 attempt → 0.0, not NaN
    assert brown["help_blocks"] == 1


# ---------------------------------------------------------------------------
# Test 3 — Cache write-through + fresh-cache short-circuit (no network).
# ---------------------------------------------------------------------------

def test_fetch_game_matchups_uses_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(fdm, "_RAW_CACHE_DIR", str(tmp_path))
    cache_path = tmp_path / "raw_0011111111.json"

    # Pre-seed cache with sentinel data — fetch must short-circuit.
    canned = [{"def_player_id": 999, "def_player_name": "Cached Defender",
               "matchup_minutes_float": 1.0}]
    cache_path.write_text(json.dumps(canned))

    # Sentinel: if the cache is bypassed the import path runs and we want
    # to assert it never reaches nba_api. Patch the import target to raise.
    def _explode(*_a, **_kw):
        raise AssertionError("nba_api should not be hit when cache is fresh")

    with patch("nba_api.stats.endpoints.boxscorematchupsv3."
               "BoxScoreMatchupsV3", _explode):
        records = fdm.fetch_game_matchups("0011111111")

    assert records == canned


# ---------------------------------------------------------------------------
# Test 4 — Fetcher falls back gracefully on API error (no exception, [] out).
# ---------------------------------------------------------------------------

def test_fetch_game_matchups_handles_api_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(fdm, "_RAW_CACHE_DIR", str(tmp_path))
    # Force zero rate-limit so the test stays fast.
    monkeypatch.setattr(fdm, "_rate_limit", lambda *a, **kw: None)

    class _Boom:
        def __init__(self, *a, **kw):
            raise RuntimeError("simulated 429 rate limit")

    with patch("nba_api.stats.endpoints.boxscorematchupsv3."
               "BoxScoreMatchupsV3", _Boom):
        records = fdm.fetch_game_matchups("0022222222", force=True)

    assert records == []
    # No cache file written on failure (preserves perpetual cache integrity)
    assert not (tmp_path / "raw_0022222222.json").exists()


# ---------------------------------------------------------------------------
# Test 5 — End-to-end (mocked): fetch → summarize → cache writes records.
# ---------------------------------------------------------------------------

def test_end_to_end_mocked_writes_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(fdm, "_RAW_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(fdm, "_rate_limit", lambda *a, **kw: None)

    with patch("nba_api.stats.endpoints.boxscorematchupsv3."
               "BoxScoreMatchupsV3", _FakeBoxScoreMatchupsV3):
        records = fdm.fetch_game_matchups("0033333333", force=True)

    assert len(records) == 4

    # Cache was written
    cache_file = tmp_path / "raw_0033333333.json"
    assert cache_file.exists()
    on_disk = json.loads(cache_file.read_text())
    assert len(on_disk) == 4
    assert on_disk[0]["off_player_name"] == "LeBron James"

    # Roll-up downstream still works
    summary = fdm.summarize_defender(records, game_id="0033333333",
                                     season="2024-25")
    assert len(summary) == 2
    # Sorted by matchup_minutes_total descending
    assert summary[0]["matchup_minutes_total"] >= summary[1]["matchup_minutes_total"]


# ---------------------------------------------------------------------------
# Test 6 — _parse_clock handles weird inputs without crashing.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("5:30",  5.5),
    ("0:00",  0.0),
    ("",      0.0),
    (None,    0.0),
    ("nan",   0.0),
    ("12.5",  12.5),
    ("not a time", 0.0),
    ("10:45", 10.75),
])
def test_parse_clock_robust(raw, expected) -> None:
    assert fdm._parse_clock(raw) == expected


# ---------------------------------------------------------------------------
# Test runtime guard — whole module must complete in < 5s offline.
# ---------------------------------------------------------------------------

def test_suite_runs_fast() -> None:
    """Sanity guard: smoke-execute the public paths and confirm they
    return quickly without any network access."""
    t0 = time.time()
    df = _synthetic_matchups_df()
    for _ in range(10):
        raw = fdm._parse_matchups_frame(df)
        fdm.summarize_defender(raw, game_id="0099999999", season="2024-25")
    elapsed = time.time() - t0
    assert elapsed < 5.0, f"hot loop too slow: {elapsed:.2f}s"
