"""
tests/test_news_ingester.py — Unit tests for src.data.news_ingester.

All tests use an in-memory SQLite DB and mock refresh_rotowire so no live
network calls are made.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

# ── Fixtures / helpers ────────────────────────────────────────────────────────

_ROTOWIRE_ITEMS = [
    {
        "player_name":  "LeBron James",
        "team_abbrev":  "LAL",
        "headline":     "LeBron ruled out with ankle soreness",
        "summary":      "LeBron James is listed as out for tonight's game.",
        "published":    "Mon, 20 May 2024 10:00:00 +0000",
        "status_guess": "Out",
        "source":       "rotowire",
    },
    {
        "player_name":  "Anthony Davis",
        "team_abbrev":  "LAL",
        "headline":     "Davis available for Wednesday",
        "summary":      "Anthony Davis cleared all protocols.",
        "published":    "Mon, 20 May 2024 11:00:00 +0000",
        "status_guess": "Available",
        "source":       "rotowire",
    },
]


class _PersistentMemoryIngester:
    """
    Wraps NewsIngester but keeps a single :memory: connection open across
    calls (normally each call opens + closes its own connection).
    """

    def __init__(self):
        from src.data.news_ingester import NewsIngester, _CREATE_SQL

        self._con = sqlite3.connect(":memory:")
        self._con.execute(_CREATE_SQL)
        self._con.commit()
        self._ingester = NewsIngester(db_path=":memory:")
        # Patch _connect to always return our shared conn without closing it.
        self._ingester._connect = self._open  # type: ignore[method-assign]

    def _open(self) -> sqlite3.Connection:
        return _NoCloseConn(self._con)

    def ingest(self) -> int:
        return self._ingester.ingest()

    def query(self, sql: str):
        return self._con.execute(sql).fetchall()


class _NoCloseConn:
    """Proxy that forwards everything to the real connection but ignores close()."""

    def __init__(self, con: sqlite3.Connection):
        self._con = con

    def close(self):
        pass  # no-op — keep the shared in-memory DB alive

    def __getattr__(self, name: str):
        return getattr(self._con, name)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestNewsIngesterDedup:
    """Core dedup and count tests."""

    def test_first_call_inserts_two_rows(self):
        w = _PersistentMemoryIngester()
        with patch("src.data.injury_monitor.refresh_rotowire", return_value=_ROTOWIRE_ITEMS):
            n = w.ingest()
        assert n == 2

    def test_second_call_returns_zero(self):
        w = _PersistentMemoryIngester()
        with patch("src.data.injury_monitor.refresh_rotowire", return_value=_ROTOWIRE_ITEMS):
            w.ingest()
            n = w.ingest()
        assert n == 0

    def test_empty_feed_returns_zero(self):
        w = _PersistentMemoryIngester()
        with patch("src.data.injury_monitor.refresh_rotowire", return_value=[]):
            n = w.ingest()
        assert n == 0

    def test_row_fields(self):
        """Verify sport, source, player_id, game_id are set correctly."""
        w = _PersistentMemoryIngester()
        with patch("src.data.injury_monitor.refresh_rotowire", return_value=_ROTOWIRE_ITEMS):
            w.ingest()
        rows = w.query("SELECT sport, source, player_id, game_id FROM news_items LIMIT 1")
        sport, source, player_id, game_id = rows[0]
        assert sport == "basketball_nba"
        assert source == "rotowire"
        assert player_id is None
        assert game_id is None


class TestImpactMapping:
    """Impact label mapping tests (no DB needed)."""

    def test_out_maps_to_high(self):
        from src.data.news_ingester import _severity_to_impact
        assert _severity_to_impact("Out") == "HIGH"

    def test_available_maps_to_low(self):
        from src.data.news_ingester import _severity_to_impact
        assert _severity_to_impact("Available") == "LOW"

    def test_questionable_maps_to_medium(self):
        from src.data.news_ingester import _severity_to_impact
        assert _severity_to_impact("Questionable") == "MEDIUM"

    def test_doubtful_maps_to_medium(self):
        from src.data.news_ingester import _severity_to_impact
        assert _severity_to_impact("Doubtful") == "MEDIUM"

    def test_unknown_maps_to_low(self):
        from src.data.news_ingester import _severity_to_impact
        assert _severity_to_impact("Unknown") == "LOW"


class TestImpactPersistedInDB:
    """Verify impact values are correctly written for Out vs Available items."""

    def test_impact_out_and_available(self):
        w = _PersistentMemoryIngester()
        with patch("src.data.injury_monitor.refresh_rotowire", return_value=_ROTOWIRE_ITEMS):
            w.ingest()
        rows = w.query(
            "SELECT impact FROM news_items "
            "WHERE team_id = 'LAL' ORDER BY published_at"
        )
        impacts = [r[0] for r in rows]
        # LeBron (Out) → HIGH, Davis (Available) → LOW
        assert "HIGH" in impacts
        assert "LOW" in impacts


class TestIngestAllConvenience:
    """ingest_all() convenience function — uses a fresh :memory: each call."""

    def test_returns_two(self):
        """ingest_all with :memory: opens a fresh DB so always returns 2."""
        with patch("src.data.injury_monitor.refresh_rotowire", return_value=_ROTOWIRE_ITEMS):
            from src.data.news_ingester import ingest_all
            n = ingest_all(db_path=":memory:")
        assert n == 2
