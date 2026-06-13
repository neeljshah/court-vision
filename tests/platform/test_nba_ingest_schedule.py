"""tests/platform/test_nba_ingest_schedule.py — Offline unit tests for
domains/basketball_nba/ingest_schedule.py.

All core assertions use a SMALL synthetic schedule written to a tmp dir —
no dependency on the real 120-file corpus for pass/fail.
One optional real-data smoke test is skipped when data is absent.

Run: python -m pytest tests/platform/test_nba_ingest_schedule.py -q
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import List

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Synthetic fixture builder
# ---------------------------------------------------------------------------

def _write_schedule(tmp: Path, team: str, season: str, records: List[dict]) -> None:
    tmp.mkdir(parents=True, exist_ok=True)
    fname = f"schedule_{team}_{season}_v2.json"
    (tmp / fname).write_text(json.dumps(records), encoding="utf-8")


def _make_synthetic(tmp: Path) -> Path:
    """Write a minimal synthetic schedule set to tmp; return tmp."""
    # Game 1: ATL(home) vs BOS(away)  — home ATL wins
    _write_schedule(tmp, "ATL", "2024-25", [
        {"game_id": "G001", "date": "2024-10-23", "home": True,  "opponent": "BOS",
         "rest_days": 99, "back_to_back": False, "travel_miles": 0.0,
         "opponent_is_home": False, "wl": "W"},
        {"game_id": "G002", "date": "2024-10-26", "home": False, "opponent": "CLE",
         "rest_days": 2,  "back_to_back": False, "travel_miles": 740.0,
         "opponent_is_home": True,  "wl": "L"},
    ])
    _write_schedule(tmp, "BOS", "2024-25", [
        {"game_id": "G001", "date": "2024-10-23", "home": False, "opponent": "ATL",
         "rest_days": 3,  "back_to_back": False, "travel_miles": 1100.0,
         "opponent_is_home": True,  "wl": "L"},
    ])
    # Game 2: CLE(home) vs ATL(away) — away ATL loses (home CLE wins)
    _write_schedule(tmp, "CLE", "2024-25", [
        {"game_id": "G002", "date": "2024-10-26", "home": True,  "opponent": "ATL",
         "rest_days": 2,  "back_to_back": False, "travel_miles": 0.0,
         "opponent_is_home": False, "wl": "W"},
    ])
    # Game 3: NYK(home) vs MIA — NaN wl (future game)
    _write_schedule(tmp, "NYK", "2025-26", [
        {"game_id": "G003", "date": "2025-10-24", "home": True,  "opponent": "MIA",
         "rest_days": 5,  "back_to_back": True,  "travel_miles": 0.0,
         "opponent_is_home": False, "wl": None},
    ])
    _write_schedule(tmp, "MIA", "2025-26", [
        {"game_id": "G003", "date": "2025-10-24", "home": False, "opponent": "NYK",
         "rest_days": 4,  "back_to_back": False, "travel_miles": 1280.0,
         "opponent_is_home": True,  "wl": None},
    ])
    return tmp


@pytest.fixture(scope="module")
def synth_dir(tmp_path_factory) -> Path:
    return _make_synthetic(tmp_path_factory.mktemp("synth"))


@pytest.fixture(scope="module")
def synth_df(synth_dir) -> pd.DataFrame:
    from domains.basketball_nba.ingest_schedule import _parse_files, _dedup, GAMES_COLS
    raw = _parse_files(synth_dir)
    rows = _dedup(raw)
    df = pd.DataFrame(rows)[list(GAMES_COLS)]
    return df.sort_values(["date", "game_id"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 1. Dedup: one row per game_id
# ---------------------------------------------------------------------------

class TestDedup:
    def test_three_games_from_five_rows(self, synth_df):
        assert len(synth_df) == 3, f"Expected 3 games, got {len(synth_df)}"

    def test_game_ids_unique(self, synth_df):
        assert synth_df["game_id"].nunique() == 3

    def test_game_ids_present(self, synth_df):
        assert set(synth_df["game_id"]) == {"G001", "G002", "G003"}


# ---------------------------------------------------------------------------
# 2. home_win correctness (derived from home-perspective wl)
# ---------------------------------------------------------------------------

class TestHomeWin:
    def test_g001_atl_home_wins(self, synth_df):
        row = synth_df[synth_df["game_id"] == "G001"].iloc[0]
        assert row["home_team"] == "ATL"
        assert float(row["home_win"]) == 1.0

    def test_g002_cle_home_wins(self, synth_df):
        row = synth_df[synth_df["game_id"] == "G002"].iloc[0]
        assert row["home_team"] == "CLE"
        assert float(row["home_win"]) == 1.0

    def test_g003_future_game_is_nan(self, synth_df):
        row = synth_df[synth_df["game_id"] == "G003"].iloc[0]
        assert math.isnan(float(row["home_win"]))


# ---------------------------------------------------------------------------
# 3. home/away team assignment
# ---------------------------------------------------------------------------

class TestTeamAssignment:
    def test_g001_teams(self, synth_df):
        row = synth_df[synth_df["game_id"] == "G001"].iloc[0]
        assert row["home_team"] == "ATL"
        assert row["away_team"] == "BOS"

    def test_g002_teams(self, synth_df):
        row = synth_df[synth_df["game_id"] == "G002"].iloc[0]
        assert row["home_team"] == "CLE"
        assert row["away_team"] == "ATL"

    def test_g003_teams(self, synth_df):
        row = synth_df[synth_df["game_id"] == "G003"].iloc[0]
        assert row["home_team"] == "NYK"
        assert row["away_team"] == "MIA"


# ---------------------------------------------------------------------------
# 4. rest_days mapped to correct side and clipped
# ---------------------------------------------------------------------------

class TestRestDays:
    def test_g001_home_rest_clipped(self, synth_df):
        """ATL had rest_days=99 (season start) → clipped to REST_CAP=10."""
        row = synth_df[synth_df["game_id"] == "G001"].iloc[0]
        assert float(row["rest_days_home"]) == 10.0

    def test_g001_away_rest_correct(self, synth_df):
        """BOS had rest_days=3 → unchanged."""
        row = synth_df[synth_df["game_id"] == "G001"].iloc[0]
        assert float(row["rest_days_away"]) == 3.0

    def test_g002_away_rest(self, synth_df):
        """ATL (away in G002) had rest_days=2."""
        row = synth_df[synth_df["game_id"] == "G002"].iloc[0]
        assert float(row["rest_days_away"]) == 2.0

    def test_g003_rest_days(self, synth_df):
        row = synth_df[synth_df["game_id"] == "G003"].iloc[0]
        assert float(row["rest_days_home"]) == 5.0
        assert float(row["rest_days_away"]) == 4.0


# ---------------------------------------------------------------------------
# 5. b2b mapped to correct side
# ---------------------------------------------------------------------------

class TestB2B:
    def test_g003_home_b2b_true(self, synth_df):
        row = synth_df[synth_df["game_id"] == "G003"].iloc[0]
        assert bool(row["home_b2b"]) is True

    def test_g003_away_b2b_false(self, synth_df):
        row = synth_df[synth_df["game_id"] == "G003"].iloc[0]
        assert bool(row["away_b2b"]) is False

    def test_g001_home_b2b_false(self, synth_df):
        row = synth_df[synth_df["game_id"] == "G001"].iloc[0]
        assert bool(row["home_b2b"]) is False


# ---------------------------------------------------------------------------
# 6. travel mapped to correct side
# ---------------------------------------------------------------------------

class TestTravel:
    def test_g001_home_travel_zero(self, synth_df):
        row = synth_df[synth_df["game_id"] == "G001"].iloc[0]
        assert float(row["travel_home"]) == 0.0

    def test_g001_away_travel(self, synth_df):
        row = synth_df[synth_df["game_id"] == "G001"].iloc[0]
        assert float(row["travel_away"]) == 1100.0

    def test_g003_away_travel(self, synth_df):
        row = synth_df[synth_df["game_id"] == "G003"].iloc[0]
        assert float(row["travel_away"]) == 1280.0


# ---------------------------------------------------------------------------
# 7. Output schema exact
# ---------------------------------------------------------------------------

