"""tests for tier4-13: generate_html_dashboard.

5 tests:
  1. produces valid HTML doctype + closing tags
  2. empty data renders "(no active games)" placeholder
  3. mock 2 games + 3 open bets renders all sections
  4. mobile viewport meta tag present
  5. self-contained -- no external <link>/<script> URLs
"""
from __future__ import annotations

import os
import re
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from scripts import generate_html_dashboard as gh  # noqa: E402


@pytest.fixture
def empty_env(monkeypatch):
    monkeypatch.setattr(gh, "load_active_games", lambda d: [])
    monkeypatch.setattr(gh, "load_open_bets_with_live_edge", lambda g: [])
    monkeypatch.setattr(gh, "load_pnl_summary",
                        lambda: {"current_bankroll": 1000.0, "n_open": 0,
                                  "today_profit": 0.0, "today_settled": 0})
    monkeypatch.setattr(gh, "load_recommendations", lambda d, g: [])
    monkeypatch.setattr(gh, "load_ab_summary", lambda: [])


@pytest.fixture
def mock_env(monkeypatch):
    games = [
        {
            "game_id": "0022500001", "home_team": "LAL", "away_team": "BOS",
            "home_score": 58, "away_score": 60, "period": 2, "clock": "5:00",
            "status": "LIVE",
            "players": [
                {"name": "LeBron James", "team": "LAL", "stats": {
                    "pts": {"current": 14, "projected": 28.0},
                    "reb": {"current": 5, "projected": 10.5},
                    "ast": {"current": 6, "projected": 12.0},
                }},
                {"name": "Jayson Tatum", "team": "BOS", "stats": {
                    "pts": {"current": 18, "projected": 32.0},
                    "reb": {"current": 4, "projected": 8.0},
                    "ast": {"current": 3, "projected": 6.0},
                }},
            ],
        },
        {
            "game_id": "0022500002", "home_team": "DEN", "away_team": "OKC",
            "home_score": 30, "away_score": 28, "period": 1, "clock": "2:30",
            "status": "LIVE", "players": [],
        },
    ]
    bets = [
        {"player": "LeBron James", "team": "LAL", "stat": "pts",
         "line": 25.5, "side": "OVER", "book": "DK", "stake": 50,
         "current": 14, "projection": 28.0, "live_edge": 2.5, "status": "open"},
        {"player": "Jayson Tatum", "team": "BOS", "stat": "reb",
         "line": 9.5, "side": "UNDER", "book": "FD", "stake": 25,
         "current": 4, "projection": 8.0, "live_edge": -1.5, "status": "open"},
        {"player": "Nikola Jokic", "team": "DEN", "stat": "ast",
         "line": 10.5, "side": "OVER", "book": "MGM", "stake": 30,
         "current": None, "projection": None, "live_edge": None,
         "status": "open"},
    ]
    monkeypatch.setattr(gh, "load_active_games", lambda d: games)
    monkeypatch.setattr(gh, "load_open_bets_with_live_edge", lambda g: bets)
    monkeypatch.setattr(gh, "load_pnl_summary",
                        lambda: {"current_bankroll": 1234.56, "n_open": 3,
                                  "today_profit": 45.10, "today_settled": 2})
    monkeypatch.setattr(gh, "load_recommendations", lambda d, g: [])
    monkeypatch.setattr(gh, "load_ab_summary", lambda: [
        {"strategy": "pregame_only", "n_bets": 12, "n_settled": 10,
         "won": 6, "lost": 4, "roi": 0.12, "total_profit": 60.0,
         "bankroll_cap": 1000.0},
    ])


def test_valid_html_structure(empty_env):
    doc = gh.render_dashboard("2026-05-24")
    assert doc.startswith("<!DOCTYPE html>")
    assert "<html" in doc and "</html>" in doc
    assert "<head>" in doc and "</head>" in doc
    assert "<body>" in doc and "</body>" in doc
    assert "<title>" in doc


def test_empty_data_placeholder(empty_env):
    doc = gh.render_dashboard("2026-05-24")
    assert "(no active games)" in doc
    assert "(no open bets)" in doc


def test_mock_data_renders_all_sections(mock_env):
    doc = gh.render_dashboard("2026-05-24")
    # games
    assert "LeBron James" in doc
    assert "Jayson Tatum" in doc
    assert "LAL" in doc and "BOS" in doc
    # bets
    assert "Nikola Jokic" in doc
    assert "OVER" in doc and "UNDER" in doc
    # P&amp;L bar
    assert "1234.56" in doc
    # ab strategy
    assert "pregame_only" in doc


def test_mobile_viewport_meta(empty_env):
    doc = gh.render_dashboard("2026-05-24")
    assert re.search(
        r'<meta\s+name=[\'"]viewport[\'"]\s+content=[\'"]width=device-width',
        doc,
    ), "expected viewport meta tag"


def test_self_contained_no_external_urls(mock_env):
    doc = gh.render_dashboard("2026-05-24", refresh_sec=60)
    # No external <link rel="stylesheet" href="http...">
    assert not re.search(r'<link[^>]+href=[\'"]https?://', doc)
    # No external <script src="http...">
    assert not re.search(r'<script[^>]+src=[\'"]https?://', doc)
    # No <img src="http...">  (we don't use images, but defensive)
    assert not re.search(r'<img[^>]+src=[\'"]https?://', doc)
    # Refresh meta tag is present when refresh_sec set.
    assert 'http-equiv="refresh"' in doc
