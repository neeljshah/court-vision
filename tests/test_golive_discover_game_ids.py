"""tests/test_golive_discover_game_ids.py — unit tests for G-001 game-id discovery.

Tests are fully offline: they pass a synthetic lookup dict directly and never
call the NBA API or touch the real games_lookup.json on disk.
"""
from __future__ import annotations

import importlib
import sys
import os

import pytest

# Ensure project root is importable
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import scripts.golive_discover_game_ids as _mod


# ---------------------------------------------------------------------------
# _et_date_of_start
# ---------------------------------------------------------------------------

class TestEtDateOfStart:
    def test_evening_tip_UTC_next_day(self):
        """A tip stored as next-UTC-day midnight resolves to the prior ET date."""
        assert _mod._et_date_of_start("2026-06-04T00:40:00Z") == "2026-06-03"

    def test_afternoon_tip_same_day(self):
        """An afternoon UTC tip (hour>=6) stays on the same calendar date."""
        assert _mod._et_date_of_start("2026-06-03T17:00:00Z") == "2026-06-03"

    def test_exactly_6am_utc(self):
        """Hour==6 is NOT < 6 so no subtraction — stays same day."""
        assert _mod._et_date_of_start("2026-06-03T06:00:00Z") == "2026-06-03"

    def test_just_before_6am_utc(self):
        """Hour==5 (< 6) triggers the subtraction — resolves to prior date."""
        assert _mod._et_date_of_start("2026-06-03T05:59:00Z") == "2026-06-02"

    def test_malformed_falls_back_to_slice(self):
        """Non-standard formats fall back to the first-10-char slice."""
        assert _mod._et_date_of_start("2026-06-03") == "2026-06-03"
        assert _mod._et_date_of_start("bad") == "bad"


# ---------------------------------------------------------------------------
# _gids_from_lookup
# ---------------------------------------------------------------------------

_SAMPLE_LOOKUP = {
    # NBA official entry for 2026-06-03 ET (stored as UTC next-day)
    "0042500401": {
        "home_abbr": "SAS", "away_abbr": "NYK",
        "start_time": "2026-06-04T00:40:00Z",
        "label": "NYK @ SAS", "_source": "nba_stats_official",
    },
    # Odds-API hex key for the same game — should be ignored (not nba_stats_official)
    "1aae688472781f1a1aaf3efdb38e884b": {
        "home_abbr": "SAS", "away_abbr": "NYK",
        "start_time": "2026-06-04T00:40:00Z",
        "label": "NYK @ SAS", "_source": "the_odds_api",
    },
    # Book alias — should be ignored
    "34210820": {
        "home_abbr": "SAS", "away_abbr": "NYK",
        "start_time": "2026-06-04T00:40:00Z",
        "_source": "book_alias",
    },
    # WCF G7 — different ET date
    "0042500317": {
        "home_abbr": "OKC", "away_abbr": "SAS",
        "start_time": "2026-05-31T00:10:00Z",
        "label": "SAS @ OKC", "_source": "nba_stats_official",
    },
}


class TestGidsFromLookup:
    def test_returns_only_nba_official_for_date(self):
        gids = _mod._gids_from_lookup(_SAMPLE_LOOKUP, "2026-06-03")
        assert gids == ["0042500401"]

    def test_old_game_not_returned_for_today(self):
        gids = _mod._gids_from_lookup(_SAMPLE_LOOKUP, "2026-06-03")
        assert "0042500317" not in gids

    def test_correct_date_for_old_game(self):
        gids = _mod._gids_from_lookup(_SAMPLE_LOOKUP, "2026-05-30")
        assert gids == ["0042500317"]

    def test_no_games_for_unknown_date(self):
        gids = _mod._gids_from_lookup(_SAMPLE_LOOKUP, "2025-01-01")
        assert gids == []

    def test_hex_key_ignored(self):
        gids = _mod._gids_from_lookup(_SAMPLE_LOOKUP, "2026-06-03")
        assert "1aae688472781f1a1aaf3efdb38e884b" not in gids

    def test_book_alias_ignored(self):
        gids = _mod._gids_from_lookup(_SAMPLE_LOOKUP, "2026-06-03")
        assert "34210820" not in gids

    def test_entry_missing_abbr_excluded(self):
        """An nba_stats_official entry with missing home_abbr is silently excluded."""
        lookup_bad = {
            "0042500999": {
                "home_abbr": "", "away_abbr": "NYK",
                "start_time": "2026-06-04T00:40:00Z",
                "_source": "nba_stats_official",
            }
        }
        assert _mod._gids_from_lookup(lookup_bad, "2026-06-03") == []


# ---------------------------------------------------------------------------
# discover() — offline via monkeypatching
# ---------------------------------------------------------------------------

class TestDiscover:
    def test_returns_comma_separated(self, monkeypatch, tmp_path):
        """discover() returns a comma-separated string of 10-digit ids."""
        monkeypatch.setattr(_mod, "_load_lookup", lambda: dict(_SAMPLE_LOOKUP))
        result = _mod.discover("2026-06-03")
        assert result == "0042500401"

    def test_deduplicates(self, monkeypatch):
        """Duplicate game ids are deduplicated while preserving first occurrence."""
        dup_lookup = {
            "0042500401": {**_SAMPLE_LOOKUP["0042500401"]},
            "0042500402": {**_SAMPLE_LOOKUP["0042500401"], "away_abbr": "BOS"},
        }
        monkeypatch.setattr(_mod, "_load_lookup", lambda: dup_lookup)
        result = _mod.discover("2026-06-03")
        ids = result.split(",")
        assert len(ids) == len(set(ids))

    def test_empty_string_when_no_games_and_api_fails(self, monkeypatch):
        """discover() returns '' when lookup is empty and ScoreboardV2 fails."""
        monkeypatch.setattr(_mod, "_load_lookup", lambda: {})
        monkeypatch.setattr(_mod, "_fetch_via_scoreboardv2",
                            lambda date, lookup: (_ for _ in ()).throw(
                                RuntimeError("network offline")))
        result = _mod.discover("2026-06-03")
        assert result == ""

    def test_skips_api_when_lookup_has_games(self, monkeypatch):
        """ScoreboardV2 is NOT called when the lookup already has today's games."""
        api_called = []

        def _fake_api(date, lookup):
            api_called.append(date)
            return []

        monkeypatch.setattr(_mod, "_load_lookup", lambda: dict(_SAMPLE_LOOKUP))
        monkeypatch.setattr(_mod, "_fetch_via_scoreboardv2", _fake_api)
        _mod.discover("2026-06-03")
        assert api_called == [], "ScoreboardV2 should not be called when lookup has games"

    def test_never_returns_hardcoded_wcf_id_for_today(self, monkeypatch):
        """G-001 regression: 0042500317 (WCF G7) must not appear for 2026-06-03."""
        monkeypatch.setattr(_mod, "_load_lookup", lambda: dict(_SAMPLE_LOOKUP))
        result = _mod.discover("2026-06-03")
        assert "0042500317" not in result
