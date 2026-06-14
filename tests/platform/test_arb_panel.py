"""tests/platform/test_arb_panel.py — fully offline tests for arb_panel.py.

No network, no real odds feed, no real snapshots.
Uses fake OddsFeed subclasses + MultiFeed + tmp_path as root.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.frontend.feed import GameOdds, OddsFeed, Quote
from scripts.platformkit.frontend.feed_multi import MultiFeed
from scripts.platformkit.frontend.snapshot_scheduler import capture_once
import scripts.platformkit.frontend.arb_panel as arb_panel
from scripts.platformkit.frontend.arb_panel import (
    SPORTS,
    to_platform_id,
    build_arb_panel,
    build_all_arb,
    build_clv_panel,
    build_all_clv,
    render_arb_html,
    attach_money_routes,
)

# ── fake feeds ────────────────────────────────────────────────────────────────

class EmptyFeed(OddsFeed):
    name = "empty"
    note = "test empty"
    def fetch(self, sport: str, *, date=None) -> List[GameOdds]:
        return []
    def is_live(self) -> bool:
        return False


def _make_game(sport: str, book: str, home_odds: float, away_odds: float) -> GameOdds:
    """One game with h2h quotes from a single book."""
    return GameOdds(
        game_id=f"{sport}:2026-06-14:away@home",
        sport=sport,
        home="home",
        away="away",
        commence_time="2026-06-14T20:00:00Z",
        quotes=[
            Quote(book=book, market="h2h", side="home", decimal_odds=home_odds),
            Quote(book=book, market="h2h", side="away", decimal_odds=away_odds),
        ],
        source=book,
    )


class SingleBookFeed(OddsFeed):
    """Returns one game with one book's h2h odds."""
    def __init__(self, sport: str, book: str, home_odds: float, away_odds: float):
        self._sport = sport
        self._book = book
        self._home = home_odds
        self._away = away_odds
        self.name = book
        self.note = f"single-book {book}"

    def fetch(self, sport: str, *, date=None) -> List[GameOdds]:
        if sport != self._sport:
            return []
        return [_make_game(sport, self._book, self._home, self._away)]

    def is_live(self) -> bool:
        return False


def _make_arb_feeds(sport: str) -> MultiFeed:
    """Two feeds on the same game with a genuine h2h arb (sum(1/d)<1)."""
    # bookA: home 2.20 -> 1/2.20=0.4545; bookB: away 2.20 -> 1/2.20=0.4545
    # sum = 0.909 < 1  =>  arb exists
    feed_a = SingleBookFeed(sport, "bookA", home_odds=2.20, away_odds=1.60)
    feed_b = SingleBookFeed(sport, "bookB", home_odds=1.60, away_odds=2.20)
    return MultiFeed([feed_a, feed_b])


# ── to_platform_id ────────────────────────────────────────────────────────────

def test_to_platform_id_friendly():
    assert to_platform_id("nba") == "basketball_nba"
    assert to_platform_id("mlb") == "mlb_sbro"
    assert to_platform_id("soccer") == "soccer_fd"
    assert to_platform_id("tennis") == "tennis_atp"


def test_to_platform_id_pass_through():
    for pid in SPORTS:
        assert to_platform_id(pid) == pid


def test_to_platform_id_unknown():
    assert to_platform_id("cricket") == "cricket"


# ── empty feed -> dormant ──────────────────────────────────────────────────────

def test_build_all_arb_empty_dormant():
    feed = EmptyFeed()
    result = build_all_arb(feed)
    assert result["status"] == "dormant"
    assert result["rows"] == []
    assert result["edge_claimed"] is False


def test_build_all_clv_empty_dormant(tmp_path):
    result = build_all_clv(root=tmp_path)
    assert result["status"] == "dormant"
    assert result["rows"] == []
    assert result["edge_claimed"] is False


def test_build_arb_panel_empty(tmp_path):
    feed = EmptyFeed()
    panel = build_arb_panel("basketball_nba", feed)
    assert panel["status"] == "dormant"
    assert panel["n_games"] == 0
    assert panel["edge_claimed"] is False


def test_build_clv_panel_empty(tmp_path):
    panel = build_clv_panel("basketball_nba", root=tmp_path)
    assert panel["status"] == "dormant"
    assert panel["n_candidates"] == 0
    assert panel["candidates"] == []
    assert panel["edge_claimed"] is False


# ── synthetic arb -> active ───────────────────────────────────────────────────

def test_build_arb_panel_active_single_sport():
    sport = "basketball_nba"
    multi = _make_arb_feeds(sport)
    panel = build_arb_panel(sport, multi)
    assert panel["status"] == "active", f"expected active, got {panel['status']}; note={panel['note']}"
    assert len(panel["arbitrage"]) > 0
    assert panel["edge_claimed"] is False
    assert "NO model edge" in panel["banner"]


def test_build_all_arb_active():
    sport = "basketball_nba"
    multi = _make_arb_feeds(sport)
    # Only basketball_nba has arb; others get empty feed from same MultiFeed
    result = build_all_arb(multi, sports=(sport,))
    assert result["status"] == "active"
    assert len(result["rows"]) > 0
    assert result["edge_claimed"] is False
    # rows must carry sport field
    assert all("sport" in r for r in result["rows"])


def test_banner_has_no_model_edge():
    sport = "basketball_nba"
    multi = _make_arb_feeds(sport)
    panel = build_arb_panel(sport, multi)
    assert "NO model edge" in panel["banner"]


def test_edge_claimed_always_false_all_paths():
    feed = EmptyFeed()
    assert build_all_arb(feed)["edge_claimed"] is False
    assert build_arb_panel("basketball_nba", feed)["edge_claimed"] is False


# ── CLV active (2 snapshots) ──────────────────────────────────────────────────

def test_build_clv_panel_active_after_two_snapshots(tmp_path):
    """Two captures at different timestamps -> n_candidates > 0 -> status active."""
    sport = "basketball_nba"
    feed = SingleBookFeed(sport, "bookA", home_odds=2.0, away_odds=1.9)
    # First capture
    capture_once(sports=[sport], feed=feed, root=tmp_path, ts_utc="2026-06-14T10:00:00Z")
    # Second capture (price changed slightly)
    feed2 = SingleBookFeed(sport, "bookA", home_odds=1.95, away_odds=1.95)
    capture_once(sports=[sport], feed=feed2, root=tmp_path, ts_utc="2026-06-14T12:00:00Z")
    panel = build_clv_panel(sport, root=tmp_path)
    assert panel["status"] == "active", f"expected active; n_candidates={panel['n_candidates']}"
    assert panel["n_candidates"] > 0
    assert panel["edge_claimed"] is False


def test_build_all_clv_active_after_snapshots(tmp_path):
    sport = "basketball_nba"
    feed = SingleBookFeed(sport, "bookA", home_odds=2.0, away_odds=1.9)
    capture_once(sports=[sport], feed=feed, root=tmp_path, ts_utc="2026-06-14T10:00:00Z")
    capture_once(sports=[sport], feed=feed, root=tmp_path, ts_utc="2026-06-14T11:00:00Z")
    result = build_all_clv(sports=(sport,), root=tmp_path)
    assert result["status"] == "active"
    assert len(result["rows"]) > 0
    assert result["edge_claimed"] is False


# ── render_arb_html ───────────────────────────────────────────────────────────

_BANNED_HTML = ("roi", "profit", "guaranteed", "beat the market")


def test_render_arb_html_contains_no_model_edge():
    panel = build_arb_panel("basketball_nba", EmptyFeed())
    h = render_arb_html(panel)
    assert "NO model edge" in h


def test_render_arb_html_is_html():
    panel = build_arb_panel("basketball_nba", EmptyFeed())
    h = render_arb_html(panel)
    assert h.startswith("<!DOCTYPE html>")
    assert "<html" in h


def test_render_arb_html_no_banned_tokens():
    sport = "basketball_nba"
    multi = _make_arb_feeds(sport)
    panel = build_arb_panel(sport, multi)
    h = render_arb_html(panel).lower()
    for bad in _BANNED_HTML:
        assert bad not in h, f"banned token {bad!r} found in rendered HTML"


def test_render_arb_html_escapes_special_chars():
    """Panel with special chars in note doesn't produce raw HTML injection."""
    panel = {
        "sport": "basketball_nba",
        "banner": "<script>alert(1)</script>",
        "status": "dormant",
        "n_games": 0,
        "n_multibook_games": 0,
        "arbitrage": [],
        "middles": [],
        "note": "<b>bad</b>",
        "edge_claimed": False,
    }
    h = render_arb_html(panel)
    assert "<script>" not in h
    assert "&lt;script&gt;" in h or "script" not in h.lower().split("style")[0]


# ── attach_money_routes via TestClient ────────────────────────────────────────

def test_attach_money_routes_all_endpoints(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    sport = "basketball_nba"
    multi = _make_arb_feeds(sport)
    app2 = FastAPI()
    attach_money_routes(app2, multi, root=tmp_path)

    with TestClient(app2, raise_server_exceptions=False) as c:
        # /api/arb -> active (has arb rows from two-book feed for nba)
        r = c.get("/api/arb")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "active"
        assert len(body["rows"]) > 0

        # /api/arb/{sport} -> 200
        r2 = c.get(f"/api/arb/{sport}")
        assert r2.status_code == 200
        b2 = r2.json()
        assert b2["status"] == "active"
        assert b2["edge_claimed"] is False

        # /arb/{sport}.html -> 200 text/html
        r3 = c.get(f"/arb/{sport}.html")
        assert r3.status_code == 200
        assert "text/html" in r3.headers.get("content-type", "")
        assert "NO model edge" in r3.text

        # /api/clv -> 200 (dormant ok — no snapshots in tmp_path yet)
        r4 = c.get("/api/clv")
        assert r4.status_code == 200
        b4 = r4.json()
        assert "status" in b4

        # /api/clv/{sport} -> 200
        r5 = c.get(f"/api/clv/{sport}")
        assert r5.status_code == 200
        b5 = r5.json()
        assert b5["edge_claimed"] is False
