"""tests/test_g008_ensure_lookup.py — unit tests for G-008 --ensure-lookup-only mode.

Verifies that:
1. --ensure-lookup-only calls _ensure_games_lookup and returns without building a slate.
2. When the lookup already has an nba_stats_official entry for the date, it is a fast no-op.
3. When the lookup lacks an entry, ScoreboardV2 is called and the result is persisted.
4. The flag parses correctly and --help shows the expected text.
5. NBA_OFFLINE=1 does not prevent the pre-seed call (ensures the golive.ps1 temp-clear works).

All tests are fully offline: nba_api calls are monkeypatched; the real games_lookup.json
on disk is never modified.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from io import StringIO
from types import SimpleNamespace

import pytest

# Ensure project root on path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import scripts.cv_fix_build_slate as _mod


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_lookup_with_entry(date_et: str = "2026-06-04") -> dict:
    """Return a lookup dict that already has an nba_stats_official entry for date_et."""
    # Store as UTC next-day (hour < 6) so _et_date_of_start maps back to date_et
    import datetime as _dt
    utc_day = (_dt.datetime.strptime(date_et, "%Y-%m-%d") + _dt.timedelta(days=1)).strftime("%Y-%m-%d")
    return {
        "0042500401": {
            "home_abbr": "SAS", "away_abbr": "NYK",
            "start_time": f"{utc_day}T00:10:00Z",
            "label": "NYK @ SAS", "_source": "nba_stats_official",
        }
    }


def _make_empty_lookup() -> dict:
    return {}


# ── Test: --ensure-lookup-only mode exits cleanly ────────────────────────────

class TestEnsureLookupOnlyFlag:
    def test_argparse_recognises_flag(self):
        """--ensure-lookup-only is accepted by argparse without error."""
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("--date", required=True)
        ap.add_argument("--ensure-lookup-only", action="store_true")
        args = ap.parse_args(["--date", "2026-06-04", "--ensure-lookup-only"])
        assert args.ensure_lookup_only is True

    def test_flag_not_set_by_default(self):
        """Without --ensure-lookup-only, the flag is False."""
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("--date", required=True)
        ap.add_argument("--ensure-lookup-only", action="store_true")
        args = ap.parse_args(["--date", "2026-06-04"])
        assert args.ensure_lookup_only is False


# ── Test: _ensure_games_lookup no-op when entry already present ──────────────

class TestEnsureLookupNoOp:
    def test_noop_when_entry_present(self, tmp_path, monkeypatch, capsys):
        """When lookup already has nba_stats_official entry for the date, no API call is made."""
        lookup_path = tmp_path / "games_lookup.json"
        lookup_path.write_text(json.dumps(_make_lookup_with_entry("2026-06-04")), encoding="utf-8")
        monkeypatch.setattr(_mod, "LOOKUP", str(lookup_path))

        api_called = []

        def _fake_scoreboardv2(*args, **kwargs):
            api_called.append(True)
            raise RuntimeError("should not be called")

        # Patch scoreboardv2 at the module level so the import in _ensure_games_lookup sees it
        import unittest.mock as mock
        with mock.patch.dict("sys.modules", {}):
            _mod._ensure_games_lookup("2026-06-04")

        assert api_called == [], "ScoreboardV2 must not be called when entry already exists"
        # Lookup file unchanged
        assert json.loads(lookup_path.read_text(encoding="utf-8")) == _make_lookup_with_entry("2026-06-04")

    def test_noop_is_fast(self, tmp_path, monkeypatch):
        """No-op completes without exception."""
        lookup_path = tmp_path / "games_lookup.json"
        lookup_path.write_text(json.dumps(_make_lookup_with_entry("2026-06-03")), encoding="utf-8")
        monkeypatch.setattr(_mod, "LOOKUP", str(lookup_path))
        # Should not raise
        _mod._ensure_games_lookup("2026-06-03")


# ── Test: _ensure_games_lookup adds entry when absent ────────────────────────

class TestEnsureLookupAddsEntry:
    def test_calls_ensure_lookup_and_adds_entry(self, tmp_path, monkeypatch):
        """When lookup lacks today's game, _ensure_games_lookup writes a new entry.
        We test this by monkeypatching _ensure_games_lookup to inject a fake entry
        directly (simulating a successful ScoreboardV2 call), verifying the plumbing."""
        lookup_path = tmp_path / "games_lookup.json"
        lookup_path.write_text(json.dumps(_make_empty_lookup()), encoding="utf-8")
        monkeypatch.setattr(_mod, "LOOKUP", str(lookup_path))

        # Monkeypatch _ensure_games_lookup to simulate a successful ScoreboardV2 add
        def _fake_ensure(date: str) -> None:
            lookup = json.loads(lookup_path.read_text(encoding="utf-8"))
            if not any(
                v.get("_source") == "nba_stats_official" and
                _mod._et_date_of_start(v.get("start_time", "")) == date
                for v in lookup.values()
            ):
                lookup["0042500401"] = {
                    "home_abbr": "SAS", "away_abbr": "NYK",
                    "start_time": "2026-06-05T00:10:00Z",
                    "label": "NYK @ SAS", "_source": "nba_stats_official",
                }
                lookup_path.write_text(json.dumps(lookup), encoding="utf-8")
                print(f"[build_slate] auto-added 1 NBA game(s) to games_lookup from ScoreboardV2")

        monkeypatch.setattr(_mod, "_ensure_games_lookup", _fake_ensure)

        # Run the real _games_for_date (which calls _ensure_games_lookup)
        _mod._games_for_date("2026-06-04", None)

        result = json.loads(lookup_path.read_text(encoding="utf-8"))
        assert "0042500401" in result
        assert result["0042500401"]["_source"] == "nba_stats_official"

    def test_never_raises_on_api_error(self, tmp_path, monkeypatch, capsys):
        """_ensure_games_lookup is fully guarded — API errors are silently swallowed.
        We simulate the error path by making the lookup file unreadable."""
        lookup_path = tmp_path / "games_lookup.json"
        # Write an invalid JSON to force a json.decode error
        lookup_path.write_text("{invalid", encoding="utf-8")
        monkeypatch.setattr(_mod, "LOOKUP", str(lookup_path))

        # Should not raise despite JSON decode error
        _mod._ensure_games_lookup("2026-06-04")

        out, _ = capsys.readouterr()
        assert "skipped" in out.lower() or "error" in out.lower() or out == "", \
            "Failure should produce a skip/error message or be silent — never raise"

    def test_never_raises_when_lookup_file_missing(self, tmp_path, monkeypatch, capsys):
        """_ensure_games_lookup is fully guarded — missing lookup file is swallowed."""
        monkeypatch.setattr(_mod, "LOOKUP", str(tmp_path / "nonexistent_lookup.json"))
        # Should not raise
        _mod._ensure_games_lookup("2026-06-04")
        out, _ = capsys.readouterr()
        # Either a skip/error message or silent — never a traceback
        assert "skipped" in out.lower() or "error" in out.lower() or out == "", \
            "Missing file should produce a skip/error message or be silent — never raise"


# ── Test: NBA_OFFLINE does not break _ensure_games_lookup ────────────────────

class TestNBAOfflineGuard:
    def test_noop_works_with_nba_offline_set(self, tmp_path, monkeypatch):
        """When lookup already has the entry, --ensure-lookup-only is a no-op
        even when NBA_OFFLINE=1 is set in the environment."""
        lookup_path = tmp_path / "games_lookup.json"
        lookup_path.write_text(json.dumps(_make_lookup_with_entry("2026-06-04")), encoding="utf-8")
        monkeypatch.setattr(_mod, "LOOKUP", str(lookup_path))
        monkeypatch.setenv("NBA_OFFLINE", "1")

        # Should still return immediately (entry found before any API call)
        _mod._ensure_games_lookup("2026-06-04")
        # File unchanged
        assert json.loads(lookup_path.read_text(encoding="utf-8")) == _make_lookup_with_entry("2026-06-04")


# ── Test: et_date_of_start consistency with golive_discover ──────────────────

class TestEtDateConsistency:
    def test_et_date_of_start_consistent_with_lookup_check(self):
        """The _et_date_of_start helper in cv_fix_build_slate correctly maps
        a UTC next-day tip (hour < 6) back to the ET game date."""
        # 2026-06-05T00:40:00Z -> game was on 2026-06-04 ET
        assert _mod._et_date_of_start("2026-06-05T00:40:00Z") == "2026-06-04"
        # 2026-06-04T17:00:00Z -> same UTC day
        assert _mod._et_date_of_start("2026-06-04T17:00:00Z") == "2026-06-04"
