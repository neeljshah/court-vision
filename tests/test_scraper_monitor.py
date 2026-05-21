"""
Tests for scraper_monitor.py and telegram_alerter.py.

Cases:
  1. Prometheus metric text format is valid for a known state
  2. Fresh scraper (succeeded recently) is NOT flagged as stale
  3. Stale scraper (last success >30min ago) IS flagged and alert fires
  4. telegram_alerter.send_alert() no-ops gracefully when env vars absent
  5. Stale scraper with NEVER-succeeded source is flagged
  6. _render_metrics emits both metric families for all sources
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from src.monitoring.scraper_monitor import (
    SourceState,
    _render_metrics,
    _query_states,
    check_and_alert,
)
from src.monitoring import telegram_alerter


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _make_db_with_runs(runs: list[dict]) -> str:
    """Create a temp SQLite DB with scraper_runs rows; return file path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = sqlite3.connect(tmp.name)
    conn.execute(
        """
        CREATE TABLE scraper_runs (
            id              TEXT PRIMARY KEY,
            sport           TEXT,
            source          TEXT,
            run_type        TEXT DEFAULT 'full',
            run_started_at  TEXT DEFAULT CURRENT_TIMESTAMP,
            run_finished_at TEXT,
            status          TEXT DEFAULT 'running',
            rows_written    INTEGER DEFAULT 0,
            last_key        TEXT,
            error_message   TEXT,
            run_config      TEXT
        )
        """
    )
    for r in runs:
        conn.execute(
            """
            INSERT INTO scraper_runs
              (id, sport, source, run_started_at, run_finished_at, status)
            VALUES (:id, :sport, :source, :run_started_at, :run_finished_at, :status)
            """,
            r,
        )
    conn.commit()
    conn.close()
    return tmp.name


def _ts(offset_sec: int = 0) -> str:
    """ISO timestamp relative to now; offset_sec < 0 means in the past."""
    from datetime import datetime, timezone, timedelta
    t = datetime.now(tz=timezone.utc) + timedelta(seconds=offset_sec)
    return t.strftime("%Y-%m-%d %H:%M:%S")


# ─────────────────────────────────────────────────────────────────
# Case 1 — Prometheus metric text format is correct
# ─────────────────────────────────────────────────────────────────

def test_metric_format_correct():
    """Rendered output contains required Prometheus header lines and gauge values."""
    now_ts = time.time()
    states = [
        SourceState(source="nba_api", last_success_ts=now_ts, last_status="success"),
        SourceState(source="odds_api", last_success_ts=0.0, last_status="error"),
    ]
    body = _render_metrics(states)

    # HELP and TYPE lines must be present
    assert "# HELP scraper_last_success_timestamp_seconds" in body
    assert "# TYPE scraper_last_success_timestamp_seconds gauge" in body
    assert "# HELP scraper_last_run_status" in body
    assert "# TYPE scraper_last_run_status gauge" in body

    # Gauge lines for both sources
    assert 'scraper_last_success_timestamp_seconds{source="nba_api"}' in body
    assert 'scraper_last_success_timestamp_seconds{source="odds_api"} 0.000' in body

    # Status labels present
    assert 'scraper_last_run_status{source="nba_api",status="success"} 1' in body
    assert 'scraper_last_run_status{source="nba_api",status="error"} 0' in body
    assert 'scraper_last_run_status{source="odds_api",status="error"} 1' in body
    assert 'scraper_last_run_status{source="odds_api",status="success"} 0' in body


# ─────────────────────────────────────────────────────────────────
# Case 2 — Fresh scraper is NOT alerted
# ─────────────────────────────────────────────────────────────────

def test_fresh_scraper_not_alerted():
    """A source that succeeded 5 minutes ago is not stale (threshold 30 min)."""
    now = time.time()
    states = [
        SourceState(source="nba_api", last_success_ts=now - 300, last_status="success"),
    ]
    with patch("src.monitoring.scraper_monitor.send_alert") as mock_alert:
        stale = check_and_alert(states, stale_seconds=1800, now=now)
    assert stale == []
    mock_alert.assert_not_called()


# ─────────────────────────────────────────────────────────────────
# Case 3 — Stale scraper IS alerted
# ─────────────────────────────────────────────────────────────────

def test_stale_scraper_alerted():
    """A source last succeeding 45 minutes ago triggers an alert."""
    now = time.time()
    states = [
        SourceState(
            source="odds_api",
            last_success_ts=now - 2700,  # 45 min
            last_status="error",
        ),
    ]
    with patch("src.monitoring.scraper_monitor.send_alert") as mock_alert:
        stale = check_and_alert(states, stale_seconds=1800, now=now)
    assert "odds_api" in stale
    mock_alert.assert_called_once()
    call_text: str = mock_alert.call_args[0][0]
    assert "odds_api" in call_text
    assert "stale" in call_text.lower()


# ─────────────────────────────────────────────────────────────────
# Case 4 — Alerter no-ops without env vars
# ─────────────────────────────────────────────────────────────────

def test_alerter_noop_without_env_vars():
    """send_alert() returns False and does not raise when env vars are absent."""
    # Ensure env vars are NOT set
    env = {k: v for k, v in os.environ.items()
           if k not in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")}
    with patch.dict(os.environ, env, clear=True):
        result = telegram_alerter.send_alert("test alert")
    assert result is False  # graceful no-op


# ─────────────────────────────────────────────────────────────────
# Case 5 — Never-succeeded source is flagged as stale
# ─────────────────────────────────────────────────────────────────

def test_never_succeeded_source_alerted():
    """A source with last_success_ts=0 (never succeeded) is always stale."""
    now = time.time()
    states = [
        SourceState(source="rotoworld", last_success_ts=0.0, last_status="running"),
    ]
    with patch("src.monitoring.scraper_monitor.send_alert") as mock_alert:
        stale = check_and_alert(states, stale_seconds=1800, now=now)
    assert "rotoworld" in stale
    mock_alert.assert_called_once()


# ─────────────────────────────────────────────────────────────────
# Case 6 — _query_states reads DB correctly
# ─────────────────────────────────────────────────────────────────

def test_query_states_from_db():
    """_query_states parses a real SQLite DB and returns correct SourceState."""
    runs = [
        {
            "id": "r1",
            "sport": "nba",
            "source": "nba_api",
            "run_started_at": _ts(-7200),   # 2h ago
            "run_finished_at": _ts(-600),   # 10 min ago
            "status": "success",
        },
        {
            "id": "r2",
            "sport": "nba",
            "source": "odds_api",
            "run_started_at": _ts(-3600),
            "run_finished_at": _ts(-3500),
            "status": "error",
        },
    ]
    db_path = _make_db_with_runs(runs)
    try:
        states = _query_states(db_path)
        by_source = {s.source: s for s in states}

        assert "nba_api" in by_source
        assert by_source["nba_api"].last_status == "success"
        assert by_source["nba_api"].last_success_ts > 0

        assert "odds_api" in by_source
        assert by_source["odds_api"].last_status == "error"
        # odds_api never succeeded
        assert by_source["odds_api"].last_success_ts == 0.0
    finally:
        os.unlink(db_path)
