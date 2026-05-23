"""
tests/test_news_ingest.py — Unit tests for the news / injury ingestion module.

All HTTP calls are mocked using unittest.mock.patch so tests run fully offline.
Fixture data lives in tests/fixtures/news/.

Test areas:
- NBA CDN parser: correct record count, valid status enum, valid date format
- ESPN parser: normalised status values, team abbreviation mapping
- Reddit parser: injury-keyword filter, player name extraction, status inference
- full fetch_all_injury_news: merge + dedup behaviour
- Player name → player_id resolver
- Cache freshness gating
"""

from __future__ import annotations

import json
import os
import sys
import time
import tempfile
from datetime import datetime, timezone
from typing import List
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is importable
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "news")

VALID_STATUSES = {"OUT", "DOUBTFUL", "QUESTIONABLE", "PROBABLE", "ACTIVE"}
DATE_FORMAT    = "%Y-%m-%d"


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

def _load_fixture(name: str) -> dict:
    with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def _make_mock_response(fixture_name: str, status_code: int = 200) -> MagicMock:
    """Return a mock requests.Response backed by fixture JSON."""
    data = _load_fixture(fixture_name)
    mock = MagicMock()
    mock.status_code = status_code
    mock.raise_for_status = MagicMock()
    mock.json = MagicMock(return_value=data)
    return mock


# ──────────────────────────────────────────────────────────────────────────────
# Helper: validate a single record
# ──────────────────────────────────────────────────────────────────────────────

def _assert_valid_record(rec: dict) -> None:
    """Assert a normalised injury record has all required fields with valid values."""
    assert "player_name" in rec and rec["player_name"], f"Missing player_name: {rec}"
    assert "status" in rec and rec["status"] in VALID_STATUSES, \
        f"Invalid status '{rec.get('status')}' in {rec}"
    assert "source" in rec and rec["source"], f"Missing source: {rec}"
    assert "reported_at" in rec and rec["reported_at"], f"Missing reported_at: {rec}"
    assert "game_date" in rec, f"Missing game_date: {rec}"

    # Validate date format
    if rec["game_date"]:
        try:
            datetime.strptime(rec["game_date"], DATE_FORMAT)
        except ValueError:
            pytest.fail(f"game_date '{rec['game_date']}' does not match YYYY-MM-DD in {rec}")


# ──────────────────────────────────────────────────────────────────────────────
# Tests: NBA CDN parser
# ──────────────────────────────────────────────────────────────────────────────

class TestNbaCdnParser:
    def _run_with_fixture(self, tmp_cache_dir: str) -> List[dict]:
        from src.data import news_ingest

        mock_resp = _make_mock_response("nba_cdn_injury.json")
        game_date = "2026-05-22"

        with patch("src.data.news_ingest._CACHE_DIR", tmp_cache_dir), \
             patch("requests.get", return_value=mock_resp), \
             patch("time.sleep"):
            # Patch resolve_player_id to avoid loading actual data files
            with patch.object(news_ingest, "resolve_player_id", return_value=None):
                records = news_ingest._fetch_nba_cdn(game_date)
        return records

    def test_record_count(self, tmp_path):
        records = self._run_with_fixture(str(tmp_path))
        # Fixture has 4 players across 3 teams
        assert len(records) == 4, f"Expected 4 records, got {len(records)}"

    def test_all_records_valid(self, tmp_path):
        for rec in self._run_with_fixture(str(tmp_path)):
            _assert_valid_record(rec)

    def test_out_status_normalised(self, tmp_path):
        records = self._run_with_fixture(str(tmp_path))
        out_recs = [r for r in records if r["player_name"] == "Steph Curry"]
        assert out_recs, "Steph Curry not found in records"
        assert out_recs[0]["status"] == "OUT"

    def test_questionable_normalised(self, tmp_path):
        records = self._run_with_fixture(str(tmp_path))
        quest = [r for r in records if r["player_name"] == "Klay Thompson"]
        assert quest, "Klay Thompson not found"
        assert quest[0]["status"] == "QUESTIONABLE"

    def test_doubtful_normalised(self, tmp_path):
        records = self._run_with_fixture(str(tmp_path))
        doubt = [r for r in records if r["player_name"] == "Jayson Tatum"]
        assert doubt, "Jayson Tatum not found"
        assert doubt[0]["status"] == "DOUBTFUL"

    def test_source_label(self, tmp_path):
        for rec in self._run_with_fixture(str(tmp_path)):
            assert rec["source"] == "nba_cdn"

    def test_team_abbreviations_present(self, tmp_path):
        records = self._run_with_fixture(str(tmp_path))
        teams = {r["team"] for r in records}
        assert "GSW" in teams
        assert "LAL" in teams
        assert "BOS" in teams


# ──────────────────────────────────────────────────────────────────────────────
# Tests: ESPN parser
# ──────────────────────────────────────────────────────────────────────────────

class TestEspnParser:
    def _run_with_fixture(self, tmp_cache_dir: str) -> List[dict]:
        from src.data import news_ingest

        mock_resp = _make_mock_response("espn_injury.json")
        game_date = "2026-05-22"

        with patch("src.data.news_ingest._CACHE_DIR", tmp_cache_dir), \
             patch("requests.get", return_value=mock_resp), \
             patch("time.sleep"), \
             patch.object(news_ingest, "resolve_player_id", return_value=None):
            records = news_ingest._fetch_espn(game_date)
        return records

    def test_record_count(self, tmp_path):
        records = self._run_with_fixture(str(tmp_path))
        # Fixture has 3 players
        assert len(records) == 3, f"Expected 3, got {len(records)}"

    def test_all_records_valid(self, tmp_path):
        for rec in self._run_with_fixture(str(tmp_path)):
            _assert_valid_record(rec)

    def test_out_status(self, tmp_path):
        records = self._run_with_fixture(str(tmp_path))
        curry = [r for r in records if "Curry" in r["player_name"]]
        assert curry, "Stephen Curry not found"
        assert curry[0]["status"] == "OUT"

    def test_espn_team_id_resolved(self, tmp_path):
        records = self._run_with_fixture(str(tmp_path))
        gsw = [r for r in records if r["team"] == "GSW"]
        assert len(gsw) == 2, f"Expected 2 GSW players, got {len(gsw)}"

    def test_source_label(self, tmp_path):
        for rec in self._run_with_fixture(str(tmp_path)):
            assert rec["source"] == "espn"


# ──────────────────────────────────────────────────────────────────────────────
# Tests: Reddit parser
# ──────────────────────────────────────────────────────────────────────────────

class TestRedditParser:
    def _run_with_fixture(self, tmp_cache_dir: str) -> List[dict]:
        from src.data import news_ingest

        mock_resp = _make_mock_response("reddit_hot.json")
        game_date = "2026-05-22"

        with patch("src.data.news_ingest._CACHE_DIR", tmp_cache_dir), \
             patch("requests.get", return_value=mock_resp), \
             patch("time.sleep"), \
             patch.object(news_ingest, "resolve_player_id", return_value=None):
            records = news_ingest._fetch_reddit(game_date)
        return records

    def test_filters_non_injury_posts(self, tmp_path):
        records = self._run_with_fixture(str(tmp_path))
        # "Game Thread" and "Daily Discussion" should NOT produce records
        titles = [r["reason"] for r in records]
        assert not any("Game Thread" in t for t in titles)
        assert not any("Daily Discussion" in t for t in titles)

    def test_all_records_valid(self, tmp_path):
        for rec in self._run_with_fixture(str(tmp_path)):
            _assert_valid_record(rec)

    def test_ruled_out_status(self, tmp_path):
        records = self._run_with_fixture(str(tmp_path))
        # "Stephen Curry ruled out" → OUT
        curry = [r for r in records if "Curry" in r["reason"]]
        assert curry, "Curry post not found"
        assert curry[0]["status"] == "OUT"

    def test_source_label(self, tmp_path):
        for rec in self._run_with_fixture(str(tmp_path)):
            assert rec["source"] == "reddit_nba"

    def test_at_least_one_record(self, tmp_path):
        records = self._run_with_fixture(str(tmp_path))
        assert len(records) >= 1, "Expected at least 1 injury-related Reddit post"


# ──────────────────────────────────────────────────────────────────────────────
# Tests: fetch_all_injury_news (integration-style with mocks)
# ──────────────────────────────────────────────────────────────────────────────

class TestFetchAllInjuryNews:
    def _build_side_effect(self):
        """Return a requests.get side_effect that routes by URL to correct fixture."""
        from src.data.news_ingest import _NBA_CDN_URL, _ESPN_URL, _REDDIT_URL

        def side_effect(url, **kwargs):
            if _NBA_CDN_URL in url:
                return _make_mock_response("nba_cdn_injury.json")
            if _ESPN_URL in url:
                return _make_mock_response("espn_injury.json")
            if "reddit.com" in url:
                return _make_mock_response("reddit_hot.json")
            raise ValueError(f"Unexpected URL: {url}")

        return side_effect

    def test_returns_list(self, tmp_path):
        from src.data import news_ingest
        with patch("src.data.news_ingest._CACHE_DIR", str(tmp_path)), \
             patch("requests.get", side_effect=self._build_side_effect()), \
             patch("time.sleep"), \
             patch.object(news_ingest, "resolve_player_id", return_value=None):
            records = news_ingest.fetch_all_injury_news("2026-05-22", force=True)
        assert isinstance(records, list)
        assert len(records) > 0

    def test_all_statuses_valid(self, tmp_path):
        from src.data import news_ingest
        with patch("src.data.news_ingest._CACHE_DIR", str(tmp_path)), \
             patch("requests.get", side_effect=self._build_side_effect()), \
             patch("time.sleep"), \
             patch.object(news_ingest, "resolve_player_id", return_value=None):
            records = news_ingest.fetch_all_injury_news("2026-05-22", force=True)
        for rec in records:
            _assert_valid_record(rec)

    def test_deduplication(self, tmp_path):
        """Same player from multiple sources should not be double-counted per source."""
        from src.data import news_ingest
        with patch("src.data.news_ingest._CACHE_DIR", str(tmp_path)), \
             patch("requests.get", side_effect=self._build_side_effect()), \
             patch("time.sleep"), \
             patch.object(news_ingest, "resolve_player_id", return_value=None):
            records = news_ingest.fetch_all_injury_news("2026-05-22", force=True)

        # Count unique (player_name, source) combos
        combos = [(r["player_name"], r["source"]) for r in records]
        assert len(combos) == len(set(combos)), "Duplicates found: same player+source appears twice"

    def test_writes_cache(self, tmp_path):
        from src.data import news_ingest
        with patch("src.data.news_ingest._CACHE_DIR", str(tmp_path)), \
             patch("requests.get", side_effect=self._build_side_effect()), \
             patch("time.sleep"), \
             patch.object(news_ingest, "resolve_player_id", return_value=None):
            news_ingest.fetch_all_injury_news("2026-05-22", force=True)

        cache_file = os.path.join(str(tmp_path), "2026-05-22.json")
        assert os.path.exists(cache_file), "Cache file not written"

    def test_cache_avoids_re_fetch(self, tmp_path):
        from src.data import news_ingest
        call_count = {"n": 0}

        def counting_side_effect(url, **kwargs):
            call_count["n"] += 1
            return self._build_side_effect()(url, **kwargs)

        with patch("src.data.news_ingest._CACHE_DIR", str(tmp_path)), \
             patch("requests.get", side_effect=counting_side_effect), \
             patch("time.sleep"), \
             patch.object(news_ingest, "resolve_player_id", return_value=None):
            # First call — should hit network
            news_ingest.fetch_all_injury_news("2026-05-22", force=True)
            first_call_count = call_count["n"]

            # Second call — cache fresh, should NOT hit network
            news_ingest.fetch_all_injury_news("2026-05-22", force=False)
            second_call_count = call_count["n"]

        assert first_call_count > 0, "First call made no HTTP requests"
        assert second_call_count == first_call_count, \
            "Second call should have used cache but made network requests"

    def test_one_source_failure_does_not_crash(self, tmp_path):
        """If ESPN returns 500, we should still get results from other sources."""
        from src.data import news_ingest
        from requests.exceptions import HTTPError

        def partial_fail(url, **kwargs):
            from src.data.news_ingest import _ESPN_URL
            if _ESPN_URL in url:
                mock = MagicMock()
                mock.raise_for_status.side_effect = HTTPError("500 Server Error")
                return mock
            return self._build_side_effect()(url, **kwargs)

        with patch("src.data.news_ingest._CACHE_DIR", str(tmp_path)), \
             patch("requests.get", side_effect=partial_fail), \
             patch("time.sleep"), \
             patch.object(news_ingest, "resolve_player_id", return_value=None):
            # Should not raise
            records = news_ingest.fetch_all_injury_news("2026-05-22", force=True)

        assert isinstance(records, list), "Expected list even when one source fails"


# ──────────────────────────────────────────────────────────────────────────────
# Tests: Player name → player_id resolver
# ──────────────────────────────────────────────────────────────────────────────

class TestPlayerIdResolver:
    def test_known_player_from_nba_api_static(self):
        """resolve_player_id should return an int for a well-known active player."""
        from src.data import news_ingest

        # Reset cached lookup so it rebuilds
        news_ingest._id_lookup = None

        # Mock nba_api static players
        mock_players = [
            {"full_name": "LeBron James", "id": 2544},
            {"full_name": "Stephen Curry", "id": 201939},
        ]

        with patch("nba_api.stats.static.players.get_players", return_value=mock_players):
            pid = news_ingest.resolve_player_id("LeBron James")

        assert pid == 2544, f"Expected 2544, got {pid}"

    def test_case_insensitive(self):
        from src.data import news_ingest

        news_ingest._id_lookup = None
        mock_players = [{"full_name": "LeBron James", "id": 2544}]

        with patch("nba_api.stats.static.players.get_players", return_value=mock_players):
            pid1 = news_ingest.resolve_player_id("LeBron James")
            news_ingest._id_lookup = None  # Reset again for second call
            with patch("nba_api.stats.static.players.get_players", return_value=mock_players):
                pid2 = news_ingest.resolve_player_id("lebron james")

        assert pid1 == pid2 == 2544

    def test_unknown_player_returns_none(self):
        from src.data import news_ingest

        news_ingest._id_lookup = None
        mock_players = [{"full_name": "LeBron James", "id": 2544}]

        with patch("nba_api.stats.static.players.get_players", return_value=mock_players):
            pid = news_ingest.resolve_player_id("Fake Player Name")

        assert pid is None

    def test_stephen_curry_alias(self):
        """Both 'Steph Curry' and 'Stephen Curry' should resolve or gracefully miss."""
        from src.data import news_ingest

        news_ingest._id_lookup = None
        mock_players = [{"full_name": "Stephen Curry", "id": 201939}]

        with patch("nba_api.stats.static.players.get_players", return_value=mock_players):
            pid = news_ingest.resolve_player_id("Stephen Curry")

        assert pid == 201939


# ──────────────────────────────────────────────────────────────────────────────
# Tests: Status normalisation
# ──────────────────────────────────────────────────────────────────────────────

class TestStatusNormalisation:
    def test_out_variants(self):
        from src.data.news_ingest import _norm_status
        for raw in ("Out", "OUT", "out", "ruled out"):
            assert _norm_status(raw) == "OUT", f"Expected OUT for '{raw}'"

    def test_doubtful(self):
        from src.data.news_ingest import _norm_status
        assert _norm_status("Doubtful") == "DOUBTFUL"
        assert _norm_status("DOUBTFUL") == "DOUBTFUL"

    def test_questionable(self):
        from src.data.news_ingest import _norm_status
        assert _norm_status("Questionable") == "QUESTIONABLE"
        assert _norm_status("Day-To-Day") == "QUESTIONABLE"
        assert _norm_status("day-to-day") == "QUESTIONABLE"

    def test_probable(self):
        from src.data.news_ingest import _norm_status
        assert _norm_status("Probable") == "PROBABLE"

    def test_active_variants(self):
        from src.data.news_ingest import _norm_status
        for raw in ("Available", "Active", "Healthy"):
            assert _norm_status(raw) == "ACTIVE", f"Expected ACTIVE for '{raw}'"

    def test_unknown_defaults_to_active(self):
        from src.data.news_ingest import _norm_status
        # Unknown statuses should not raise; map to ACTIVE
        result = _norm_status("Some weird status")
        assert result == "ACTIVE"
