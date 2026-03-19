"""
test_data_sources.py — Tests for all new external data scrapers and NBA API endpoints.

Coverage:
  - src/data/nba_tracking_stats.py  (3 tests)
  - src/data/bbref_scraper.py        (4 tests)
  - src/data/odds_scraper.py         (3 tests)
  - src/data/props_scraper.py        (3 tests)
  - src/data/contracts_scraper.py    (4 tests)
  - src/data/injury_monitor.py       (3 tests — RotoWire + NBA official extensions)
  - src/features/feature_engineering.py — add_external_player_features (3 tests)

All tests use monkeypatch / tmp_path — no real API or network calls.
"""

from __future__ import annotations

import json
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _make_old(path: str) -> None:
    """Set mtime 25 hours in the past to simulate stale cache."""
    os.utime(path, (time.time() - 25 * 3600, time.time() - 25 * 3600))


# ── Fixture data ──────────────────────────────────────────────────────────────

_HUSTLE_RECORDS = [
    {
        "player_id": 2544, "player_name": "LeBron James",
        "team_abbreviation": "LAL", "games_played": 60, "minutes": 35.1,
        "contested_shots": 210, "deflections": 48, "loose_balls_recovered": 12,
        "charges_drawn": 5, "screen_assists": 0,
        "deflections_pg": 0.80, "charges_per_game": 0.08,
    },
    {
        "player_id": 203999, "player_name": "Nikola Jokic",
        "team_abbreviation": "DEN", "games_played": 75, "minutes": 34.0,
        "contested_shots": 145, "deflections": 52, "loose_balls_recovered": 20,
        "charges_drawn": 12, "screen_assists": 5,
        "deflections_pg": 0.69, "charges_per_game": 0.16,
    },
]

_ON_OFF_RECORDS = [
    {
        "player_id": 2544, "player_name": "LeBron James",
        "team_abbreviation": "LAL", "on_court_net_rtg": 8.2,
        "off_court_net_rtg": -1.5, "on_off_diff": 9.7, "minutes_on": 35.1,
        "on_court_plus_minus": 4.1, "off_court_plus_minus": -0.9,
    },
]

_BBREF_ADV_RECORDS = [
    {
        "player_name": "LeBron James", "team": "LAL", "age": 39,
        "games_played": 60, "minutes": 2100,
        "bpm": 5.2, "obpm": 3.1, "dbpm": 2.1, "vorp": 3.5,
        "win_shares": 8.1, "ws_per_48": 0.185,
        "usg_pct": 28.5, "ts_pct": 0.601,
        "per": 24.5, "season": "2024-25", "season_year": 2025,
    },
    {
        "player_name": "Nikola Jokic", "team": "DEN", "age": 29,
        "games_played": 75, "minutes": 2500,
        "bpm": 12.1, "obpm": 8.5, "dbpm": 3.6, "vorp": 7.8,
        "win_shares": 15.2, "ws_per_48": 0.292,
        "usg_pct": 31.2, "ts_pct": 0.685,
        "per": 31.4, "season": "2024-25", "season_year": 2025,
    },
]

_CONTRACTS = [
    {
        "player_name": "LeBron James", "team": "LAL",
        "current_salary": 47_607_350, "years_remaining": 1,
        "cap_hit": 47_607_350, "cap_hit_pct": 0.337,
        "contract_type": "player_option", "contract_year": False,
    },
    {
        "player_name": "Jimmy Butler", "team": "GSW",
        "current_salary": 22_000_000, "years_remaining": 0,
        "cap_hit": 22_000_000, "cap_hit_pct": 0.156,
        "contract_type": "guaranteed", "contract_year": True,
    },
]

_PROPS_DK = [
    {
        "player_name": "LeBron James", "prop_type": "points",
        "line": 25.5, "over_odds": -115, "under_odds": -105,
        "book": "draftkings", "fetched_at": "2026-03-18T12:00:00Z",
    },
    {
        "player_name": "LeBron James", "prop_type": "rebounds",
        "line": 7.5, "over_odds": -110, "under_odds": -110,
        "book": "draftkings", "fetched_at": "2026-03-18T12:00:00Z",
    },
    {
        "player_name": "Nikola Jokic", "prop_type": "points",
        "line": 28.5, "over_odds": -120, "under_odds": +100,
        "book": "draftkings", "fetched_at": "2026-03-18T12:00:00Z",
    },
]

_LINES = [
    {
        "home_team": "BOS", "away_team": "LAL",
        "home_score": 115, "away_score": 108,
        "home_ml": 1.65, "away_ml": 2.30,
        "closing_spread": -5.5, "closing_total": 223.5,
        "open_spread": -4.0, "open_total": 221.0,
        "date": "2025-01-15", "game_id": "0022400500",
    },
]

_ROTOWIRE_NEWS = [
    {
        "player_name": "LeBron James", "team_abbrev": "LAL",
        "headline": "Listed questionable with knee soreness",
        "summary": "James is listed Q for tonight's game.",
        "published": "Wed, 18 Mar 2026 14:00:00 GMT",
        "status_guess": "Questionable",
        "source": "rotowire",
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# nba_tracking_stats tests
# ══════════════════════════════════════════════════════════════════════════════

class TestNBATrackingStats:

    def test_cache_hit_hustle_stats(self, tmp_path, monkeypatch):
        """Cache hit: get_hustle_stats returns cached data without API call."""
        import src.data.nba_tracking_stats as ts
        monkeypatch.setattr(ts, "_NBA_CACHE", str(tmp_path))

        cache_file = tmp_path / "hustle_stats_2024-25.json"
        _write_json(str(cache_file), _HUSTLE_RECORDS)

        with patch("nba_api.stats.endpoints.leaguehustlestatsplayer") as mock_api:
            result = ts.get_hustle_stats("2024-25")
        mock_api.assert_not_called()
        assert len(result) == 2
        assert result[0]["player_name"] == "LeBron James"
        assert result[0]["deflections_pg"] == 0.80

    def test_cache_miss_on_off_calls_api(self, tmp_path, monkeypatch):
        """Cache miss: get_on_off_splits uses TeamPlayerOnOffSummary and caches result."""
        import src.data.nba_tracking_stats as ts
        monkeypatch.setattr(ts, "_NBA_CACHE", str(tmp_path))

        # Frame 0 = team summary, Frame 1 = player on-court, Frame 2 = player off-court
        frame0 = pd.DataFrame([{"TEAM_ID": 1610612747}])
        frame1 = pd.DataFrame([{
            "VS_PLAYER_ID": 2544, "VS_PLAYER_NAME": "LeBron James",
            "COURT_STATUS": "On", "PLUS_MINUS": 4.1, "MIN": 35.1,
        }])
        frame2 = pd.DataFrame([{
            "VS_PLAYER_ID": 2544, "VS_PLAYER_NAME": "LeBron James",
            "COURT_STATUS": "Off", "PLUS_MINUS": -0.9, "MIN": 12.0,
        }])

        mock_resp = MagicMock()
        mock_resp.get_data_frames.return_value = [frame0, frame1, frame2]

        fake_teams = [{"id": 1610612747, "abbreviation": "LAL"}]

        with patch("src.data.nba_tracking_stats._nba_rate_limit"):
            with patch("nba_api.stats.static.teams.get_teams", return_value=fake_teams):
                with patch(
                    "nba_api.stats.endpoints.teamplayeronoffsummary.TeamPlayerOnOffSummary",
                    return_value=mock_resp,
                ):
                    result = ts.get_on_off_splits("2024-25")

        assert len(result) >= 1
        r = next(x for x in result if x["player_id"] == 2544)
        assert r["on_off_diff"] == round(4.1 - (-0.9), 2)
        # Verify cache written
        assert (tmp_path / "on_off_2024-25.json").exists()

    def test_schema_hustle_stats(self, tmp_path, monkeypatch):
        """Schema: hustle stat records contain required keys."""
        import src.data.nba_tracking_stats as ts
        monkeypatch.setattr(ts, "_NBA_CACHE", str(tmp_path))

        cache_file = tmp_path / "hustle_stats_2024-25.json"
        _write_json(str(cache_file), _HUSTLE_RECORDS)

        result = ts.get_hustle_stats("2024-25")
        required = {
            "player_id", "player_name", "team_abbreviation",
            "deflections", "charges_drawn", "deflections_pg",
        }
        for r in result:
            assert required.issubset(set(r.keys())), f"Missing keys in: {r}"


# ══════════════════════════════════════════════════════════════════════════════
# bbref_scraper tests
# ══════════════════════════════════════════════════════════════════════════════

class TestBBRefScraper:

    def test_cache_hit_advanced_stats(self, tmp_path, monkeypatch):
        """Cache hit: get_advanced_stats returns cached data without HTTP."""
        import src.data.bbref_scraper as bb
        monkeypatch.setattr(bb, "_EXT_CACHE", str(tmp_path))

        cache_file = tmp_path / "bbref_advanced_2024-25.json"
        _write_json(str(cache_file), _BBREF_ADV_RECORDS)

        with patch("requests.get") as mock_get:
            result = bb.get_advanced_stats("2024-25")
        mock_get.assert_not_called()
        assert len(result) == 2

    def test_normalise_record(self):
        """_normalise_record converts raw BBRef dict to internal schema."""
        from src.data.bbref_scraper import _normalise_record

        raw = {
            "player": "LeBron James", "tm": "LAL", "age": 39.0,
            "g": 60.0, "mp": 2100.0,
            "bpm": 5.2, "vorp": 3.5, "ws": 8.1, "ws_per_48": 0.185,
            "usg_pct": 28.5, "ts_pct": 0.601,
        }
        result = _normalise_record(raw, year=2025)
        assert result["player_name"] == "LeBron James"
        assert result["bpm"] == 5.2
        assert result["vorp"] == 3.5
        assert result["season"] == "2024-25"

    def test_get_player_bpm_found(self, tmp_path, monkeypatch):
        """get_player_bpm returns correct BPM/VORP for a known player."""
        import src.data.bbref_scraper as bb
        monkeypatch.setattr(bb, "_EXT_CACHE", str(tmp_path))

        cache_file = tmp_path / "bbref_advanced_2024-25.json"
        _write_json(str(cache_file), _BBREF_ADV_RECORDS)

        result = bb.get_player_bpm("LeBron James", "2024-25")
        assert result["found"] is True
        assert result["bpm"] == 5.2
        assert result["vorp"] == 3.5

    def test_get_player_bpm_not_found(self, tmp_path, monkeypatch):
        """get_player_bpm returns found=False for unknown players."""
        import src.data.bbref_scraper as bb
        monkeypatch.setattr(bb, "_EXT_CACHE", str(tmp_path))

        cache_file = tmp_path / "bbref_advanced_2024-25.json"
        _write_json(str(cache_file), _BBREF_ADV_RECORDS)

        result = bb.get_player_bpm("Jane Doe", "2024-25")
        assert result["found"] is False
        assert result["bpm"] == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# odds_scraper tests
# ══════════════════════════════════════════════════════════════════════════════

class TestOddsScraper:

    def test_cache_hit_historical_lines(self, tmp_path, monkeypatch):
        """Cache hit: get_historical_lines returns cached data."""
        import src.data.odds_scraper as os_sc
        monkeypatch.setattr(os_sc, "_EXT_CACHE", str(tmp_path))

        cache_file = tmp_path / "historical_lines_2024-25.json"
        _write_json(str(cache_file), _LINES)

        with patch("requests.get") as mock_get:
            result = os_sc.get_historical_lines("2024-25")
        mock_get.assert_not_called()
        assert len(result) == 1
        assert result[0]["home_team"] == "BOS"

    def test_get_game_lines_match(self, tmp_path, monkeypatch):
        """get_game_lines returns correct line for matching home/away teams."""
        import src.data.odds_scraper as os_sc
        monkeypatch.setattr(os_sc, "_EXT_CACHE", str(tmp_path))

        cache_file = tmp_path / "historical_lines_2024-25.json"
        _write_json(str(cache_file), _LINES)

        result = os_sc.get_game_lines("BOS", "LAL", season="2024-25")
        assert result["closing_spread"] == -5.5
        assert result["closing_total"] == 223.5

    def test_schema_historical_lines(self, tmp_path, monkeypatch):
        """Schema: historical line records contain required keys."""
        import src.data.odds_scraper as os_sc
        monkeypatch.setattr(os_sc, "_EXT_CACHE", str(tmp_path))

        cache_file = tmp_path / "historical_lines_2024-25.json"
        _write_json(str(cache_file), _LINES)

        result = os_sc.get_historical_lines("2024-25")
        required = {"home_team", "away_team", "closing_spread", "closing_total", "date"}
        for r in result:
            assert required.issubset(set(r.keys())), f"Missing keys: {r.keys()}"


# ══════════════════════════════════════════════════════════════════════════════
# props_scraper tests
# ══════════════════════════════════════════════════════════════════════════════

class TestPropsScraper:

    def test_cache_hit_props(self, tmp_path, monkeypatch):
        """Cache hit: get_current_props returns cached data without fetching."""
        import src.data.props_scraper as ps
        monkeypatch.setattr(ps, "_EXT_CACHE", str(tmp_path))

        cache_file = tmp_path / "current_props_draftkings.json"
        _write_json(str(cache_file), _PROPS_DK)

        with patch("requests.get") as mock_get:
            result = ps.get_current_props("draftkings")
        mock_get.assert_not_called()
        assert len(result) == 3

    def test_get_player_props_filter(self, tmp_path, monkeypatch):
        """get_player_props returns only props for the specified player."""
        import src.data.props_scraper as ps
        monkeypatch.setattr(ps, "_EXT_CACHE", str(tmp_path))

        cache_file = tmp_path / "current_props_draftkings.json"
        _write_json(str(cache_file), _PROPS_DK)

        result = ps.get_player_props("LeBron James", "draftkings")
        assert len(result) == 2
        assert all(p["player_name"] == "LeBron James" for p in result)

    def test_schema_props(self, tmp_path, monkeypatch):
        """Schema: prop records have required keys and correct types."""
        import src.data.props_scraper as ps
        monkeypatch.setattr(ps, "_EXT_CACHE", str(tmp_path))

        cache_file = tmp_path / "current_props_draftkings.json"
        _write_json(str(cache_file), _PROPS_DK)

        result = ps.get_current_props("draftkings")
        required = {"player_name", "prop_type", "line", "book"}
        for r in result:
            assert required.issubset(set(r.keys()))
            assert isinstance(r["line"], (int, float))


# ══════════════════════════════════════════════════════════════════════════════
# contracts_scraper tests
# ══════════════════════════════════════════════════════════════════════════════

class TestContractsScraper:

    def test_cache_hit_contracts(self, tmp_path, monkeypatch):
        """Cache hit: get_all_contracts returns cached data."""
        import src.data.contracts_scraper as cs
        monkeypatch.setattr(cs, "_EXT_CACHE", str(tmp_path))

        cache_file = tmp_path / "contracts_2024-25.json"
        _write_json(str(cache_file), _CONTRACTS)

        with patch("requests.get") as mock_get:
            result = cs.get_all_contracts("2024-25")
        mock_get.assert_not_called()
        assert len(result) == 2

    def test_get_player_contract_found(self, tmp_path, monkeypatch):
        """get_player_contract returns correct data for a known player."""
        import src.data.contracts_scraper as cs
        monkeypatch.setattr(cs, "_EXT_CACHE", str(tmp_path))

        cache_file = tmp_path / "contracts_2024-25.json"
        _write_json(str(cache_file), _CONTRACTS)

        result = cs.get_player_contract("LeBron James", "2024-25")
        assert result["current_salary"] == 47_607_350
        assert result["team"] == "LAL"

    def test_is_contract_year(self, tmp_path, monkeypatch):
        """is_contract_year: True for walk-year players, False for others."""
        import src.data.contracts_scraper as cs
        monkeypatch.setattr(cs, "_EXT_CACHE", str(tmp_path))

        cache_file = tmp_path / "contracts_2024-25.json"
        _write_json(str(cache_file), _CONTRACTS)

        assert cs.is_contract_year("Jimmy Butler") is True
        assert cs.is_contract_year("LeBron James") is False

    def test_schema_contracts(self, tmp_path, monkeypatch):
        """Schema: contract records contain required keys."""
        import src.data.contracts_scraper as cs
        monkeypatch.setattr(cs, "_EXT_CACHE", str(tmp_path))

        cache_file = tmp_path / "contracts_2024-25.json"
        _write_json(str(cache_file), _CONTRACTS)

        result = cs.get_all_contracts("2024-25")
        required = {
            "player_name", "team", "current_salary",
            "years_remaining", "contract_type", "contract_year",
        }
        for r in result:
            assert required.issubset(set(r.keys()))


# ══════════════════════════════════════════════════════════════════════════════
# injury_monitor RotoWire + NBA official extension tests
# ══════════════════════════════════════════════════════════════════════════════

class TestInjuryMonitorExtensions:

    def test_rotowire_cache_hit(self, tmp_path, monkeypatch):
        """refresh_rotowire returns cached news without network call."""
        import src.data.injury_monitor as im

        cache_file = tmp_path / "rotowire_news.json"
        _write_json(str(cache_file), _ROTOWIRE_NEWS)
        monkeypatch.setattr(im, "_ROTOWIRE_CACHE", str(cache_file))

        result = im.refresh_rotowire(force=False)
        assert len(result) == 1
        assert result[0]["player_name"] == "LeBron James"

    def test_get_rotowire_news_filter(self, tmp_path, monkeypatch):
        """get_rotowire_news filters to a specific player."""
        import src.data.injury_monitor as im
        monkeypatch.setattr(im, "_ROTOWIRE_CACHE", str(tmp_path / "rotowire_news.json"))

        cache_file = tmp_path / "rotowire_news.json"
        _write_json(str(cache_file), _ROTOWIRE_NEWS)

        result = im.get_rotowire_news("LeBron James")
        assert len(result) == 1

        result_empty = im.get_rotowire_news("Jane Doe")
        assert result_empty == []

    def test_nba_official_cache_hit(self, tmp_path, monkeypatch):
        """refresh_nba_official_injury returns cached data without network call."""
        import src.data.injury_monitor as im

        official_data = [{
            "player_name": "Anthony Davis", "team_abbrev": "LAL",
            "status": "Out", "reason": "Knee",
            "game_date": "2026-03-18", "source": "nba_official",
        }]
        cache_file = tmp_path / "nba_official_injury.json"
        _write_json(str(cache_file), official_data)
        monkeypatch.setattr(im, "_NBA_PDF_CACHE", str(cache_file))

        with patch("requests.get") as mock_get:
            result = im.refresh_nba_official_injury(force=False)
        mock_get.assert_not_called()
        assert len(result) == 1
        assert result[0]["player_name"] == "Anthony Davis"


# ══════════════════════════════════════════════════════════════════════════════
# feature_engineering — add_external_player_features tests
# ══════════════════════════════════════════════════════════════════════════════

class TestExternalPlayerFeatures:

    def _make_df(self) -> pd.DataFrame:
        return pd.DataFrame([
            {
                "frame": 1, "player_id": 0, "player_name": "LeBron James",
                "team": "LAL", "ball_possession": 0, "velocity": 5.0,
                "x_position": 100.0, "y_position": 50.0,
            },
            {
                "frame": 1, "player_id": 1, "player_name": "Nikola Jokic",
                "team": "DEN", "ball_possession": 0, "velocity": 4.0,
                "x_position": 200.0, "y_position": 60.0,
            },
        ])

    def test_columns_added_when_bbref_cache_available(self, tmp_path, monkeypatch):
        """add_external_player_features adds BBRef columns when cache present."""
        from src.features.feature_engineering import add_external_player_features
        import src.data.bbref_scraper as bb
        monkeypatch.setattr(bb, "_EXT_CACHE", str(tmp_path))

        cache_file = tmp_path / "bbref_advanced_2024-25.json"
        _write_json(str(cache_file), _BBREF_ADV_RECORDS)

        df = self._make_df()
        result = add_external_player_features(df, season="2024-25")

        assert "bbref_bpm" in result.columns
        assert "bbref_vorp" in result.columns
        assert "bbref_ws" in result.columns
        lebron_row = result[result["player_name"] == "LeBron James"].iloc[0]
        assert lebron_row["bbref_bpm"] == 5.2

    def test_columns_added_when_contract_cache_available(self, tmp_path, monkeypatch):
        """add_external_player_features adds contract columns when cache present."""
        from src.features.feature_engineering import add_external_player_features
        import src.data.contracts_scraper as cs
        monkeypatch.setattr(cs, "_EXT_CACHE", str(tmp_path))

        cache_file = tmp_path / "contracts_2024-25.json"
        _write_json(str(cache_file), _CONTRACTS)

        df = self._make_df()
        result = add_external_player_features(df, season="2024-25")

        assert "contract_year_flag" in result.columns
        assert "cap_hit_pct" in result.columns
        # LeBron is not in a contract year per our fixture
        lebron_row = result[result["player_name"] == "LeBron James"].iloc[0]
        assert lebron_row["contract_year_flag"] == 0

    def test_graceful_fallback_on_missing_cache(self):
        """add_external_player_features works even if all caches are absent."""
        from src.features.feature_engineering import add_external_player_features

        df = self._make_df()
        # Should not raise even without any cache files
        result = add_external_player_features(df, season="2024-25")

        # All external columns should be present (zero-filled defaults)
        assert "bbref_bpm" in result.columns
        assert "injury_status_multiplier" in result.columns
        assert result["bbref_bpm"].isna().sum() == 0
