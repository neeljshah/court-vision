"""Tests for scripts/send_daily_slate.py."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.send_daily_slate import format_slate_message, send_daily_slate


# ---------------------------------------------------------------------------
# 1. Empty bets
# ---------------------------------------------------------------------------
def test_format_empty_bets() -> None:
    msg = format_slate_message([], "2026-05-21")
    assert "No bets" in msg


# ---------------------------------------------------------------------------
# 2. Bets table contains expected fields
# ---------------------------------------------------------------------------
def test_format_bets_table() -> None:
    bets = [
        {
            "player": "LeBron James",
            "stat": "PTS",
            "direction": "OVER",
            "line": 25.5,
            "edge_pct": 0.08,
        }
    ]
    msg = format_slate_message(bets, "2026-05-21")
    assert "LeBron James" in msg
    assert "PTS" in msg
    assert "edge" in msg


# ---------------------------------------------------------------------------
# 3. No Telegram creds — must not raise, must return False
# ---------------------------------------------------------------------------
def test_send_no_creds() -> None:
    env_clean = {k: v for k, v in os.environ.items()
                 if k not in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")}
    with patch.dict(os.environ, env_clean, clear=True):
        # Pass a future date that won't have a real slate file
        result = send_daily_slate("2099-01-01")
    assert result is False


# ---------------------------------------------------------------------------
# 4. Missing slate file — must not raise, must return False
# ---------------------------------------------------------------------------
def test_send_with_missing_slate() -> None:
    with patch("src.monitoring.telegram_alerter.send_alert", return_value=False):
        result = send_daily_slate("2099-12-31")
    assert result is False
