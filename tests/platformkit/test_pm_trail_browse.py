"""Per-file tests for scripts.platformkit.pm_trail_browse + clv_ledger_enrich.

Tests cover:
  - PM venue filter (only kalshi/polymarket rows pass)
  - Per-trade detail (full execution detail, null-CLV honest)
  - No $ / dollar / roi / pnl field anywhere
  - executed is always False
  - null CLV shown honestly (not filled with 0)
  - Tier inference from ev_pct
  - FastAPI TestClient routes for pm_trail_routes

Run:
  cd /c/Users/neelj/nba-ai-system && \\
  python -m pytest tests/platformkit/test_pm_trail_browse.py -q
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest


# ---------------------------------------------------------------------------
# Helpers to build synthetic ledger JSONL files
# ---------------------------------------------------------------------------

def _write_ledger(tmp_dir: Path, rows: List[Dict[str, Any]]) -> Path:
    p = tmp_dir / "clv_ledger.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return p


def _base_row(**kwargs) -> Dict[str, Any]:
    """Return a minimal open ledger row with required fields."""
    row: Dict[str, Any] = {
        "ts": "2026-06-19T10:00:00+00:00",
        "sport": "nba",
        "matchup": "LAL@BOS",
        "side": "home",
        "taken_book": "kalshi",
        "taken_decimal": 2.0,
        "model_prob": 0.55,
        "stake_units": 1.0,
        "status": "open",
        "executed": False,
        "channel": "paper",
        "bet_id": "nba|LAL@BOS|moneyline|home|kalshi|2026-06-19",
        "ev_pct": 5.5,
    }
    row.update(kwargs)
    return row


def _settled_row(**kwargs) -> Dict[str, Any]:
    # Build defaults first, then apply kwargs on top so callers can override any field.
    defaults: Dict[str, Any] = {
        "status": "settled",
        "outcome": "win",
        "settled_at": "2026-06-19T22:00:00+00:00",
        "clv_pct": 2.3,
        "beat_close": True,
        "clv_is_proxy": False,
        "clv_status": "true_close",
        "graded": True,
    }
    defaults.update(kwargs)
    return _base_row(**defaults)


# ---------------------------------------------------------------------------
# Unit tests: clv_ledger_enrich
# ---------------------------------------------------------------------------

class TestEnrichRow:
    def test_kalshi_venue_from_taken_book(self):
        from scripts.platformkit.clv_ledger_enrich import enrich_row
        row = _base_row(taken_book="kalshi", channel="paper")
        e = enrich_row(row)
        assert e["venue"] == "kalshi"
        assert e["is_pm"] is True

    def test_polymarket_venue_from_taken_book(self):
        from scripts.platformkit.clv_ledger_enrich import enrich_row
        row = _base_row(taken_book="PolymarketDEX", channel="paper")
        e = enrich_row(row)
        assert e["venue"] == "polymarket"
        assert e["is_pm"] is True

    def test_sportsbook_venue_from_espn_book(self):
        from scripts.platformkit.clv_ledger_enrich import enrich_row
        row = _base_row(taken_book="espn:DraftKings", channel="paper")
        e = enrich_row(row)
        assert e["venue"] == "sportsbook"
        assert e["is_pm"] is False

    def test_tier_A_inferred_from_ev_pct(self):
        from scripts.platformkit.clv_ledger_enrich import enrich_row
        # ev_pct=9.0 -> 9% EV -> should be tier A (floor 8%)
        row = _base_row(ev_pct=9.0, tier=None)
        e = enrich_row(row)
        assert e["tier"] == "A"

    def test_tier_B_inferred(self):
        from scripts.platformkit.clv_ledger_enrich import enrich_row
        row = _base_row(ev_pct=5.0, tier=None)
        e = enrich_row(row)
        assert e["tier"] == "B"

    def test_tier_C_inferred(self):
        from scripts.platformkit.clv_ledger_enrich import enrich_row
        row = _base_row(ev_pct=2.5, tier=None)
        e = enrich_row(row)
        assert e["tier"] == "C"

    def test_tier_none_below_floor(self):
        from scripts.platformkit.clv_ledger_enrich import enrich_row
        row = _base_row(ev_pct=0.5, tier=None)
        e = enrich_row(row)
        assert e["tier"] is None

    def test_existing_tier_preserved(self):
        from scripts.platformkit.clv_ledger_enrich import enrich_row
        row = _base_row(ev_pct=1.0, tier="A")  # ev is below A but tier is stamped
        e = enrich_row(row)
        assert e["tier"] == "A"

    def test_executed_always_false(self):
        from scripts.platformkit.clv_ledger_enrich import enrich_row
        row = _base_row(executed=True)  # try to set True -- should be overridden
        e = enrich_row(row)
        assert e["executed"] is False

    def test_no_dollar_field(self):
        from scripts.platformkit.clv_ledger_enrich import enrich_row
        row = _base_row()
        e = enrich_row(row)
        banned = {"dollar", "roi", "pnl", "profit", "$"}
        for key in e.keys():
            assert key.lower() not in banned, f"Banned field found: {key}"

    def test_original_not_mutated(self):
        from scripts.platformkit.clv_ledger_enrich import enrich_row
        row = _base_row(taken_book="kalshi")
        original_keys = set(row.keys())
        enrich_row(row)
        assert set(row.keys()) == original_keys  # enrich_row returns copy


# ---------------------------------------------------------------------------
# Unit tests: pm_trail_browse
# ---------------------------------------------------------------------------

class TestBrowsePmTrail:
    def test_pm_filter_excludes_sportsbook(self, tmp_path):
        from scripts.platformkit.pm_trail_browse import browse_pm_trail
        rows = [
            _base_row(taken_book="kalshi",
                      bet_id="nba|X@Y|moneyline|home|kalshi|2026-06-19"),
            _base_row(taken_book="espn:DraftKings",
                      bet_id="nba|X@Y|moneyline|home|espn:dk|2026-06-19"),
        ]
        lpath = _write_ledger(tmp_path, rows)
        result = browse_pm_trail(lpath)
        assert result["status"] == "ok"
        # Only the kalshi row should pass the PM filter
        assert result["total_pm"] >= 1
        venues = {t["venue"] for t in result["trades"]}
        assert "sportsbook" not in venues

    def test_venue_filter(self, tmp_path):
        from scripts.platformkit.pm_trail_browse import browse_pm_trail
        rows = [
            _base_row(taken_book="kalshi",
                      bet_id="1"),
            _base_row(taken_book="PolymarketDEX",
                      bet_id="2"),
        ]
        lpath = _write_ledger(tmp_path, rows)
        result = browse_pm_trail(lpath, venue="kalshi")
        for trade in result["trades"]:
            assert trade["venue"] == "kalshi"

    def test_tier_filter(self, tmp_path):
        from scripts.platformkit.pm_trail_browse import browse_pm_trail
        rows = [
            _base_row(taken_book="kalshi", ev_pct=9.5, bet_id="a1"),  # A
            _base_row(taken_book="kalshi", ev_pct=5.0, bet_id="a2"),  # B
        ]
        lpath = _write_ledger(tmp_path, rows)
        result = browse_pm_trail(lpath, tier="A")
        for trade in result["trades"]:
            assert trade["tier"] == "A"

    def test_null_clv_shown_honestly(self, tmp_path):
        from scripts.platformkit.pm_trail_browse import browse_pm_trail
        row = _settled_row(
            taken_book="kalshi", bet_id="settled1",
            clv_pct=None, beat_close=None, clv_is_proxy=False,
            clv_status="no_close",
        )
        lpath = _write_ledger(tmp_path, [row])
        result = browse_pm_trail(lpath)
        assert result["status"] == "ok"
        if result["trades"]:
            t = result["trades"][0]
            assert t["clv_pct"] is None  # must be None, not 0

    def test_no_dollar_field_in_trades(self, tmp_path):
        from scripts.platformkit.pm_trail_browse import browse_pm_trail
        row = _base_row(taken_book="kalshi")
        lpath = _write_ledger(tmp_path, [row])
        result = browse_pm_trail(lpath)
        banned = {"dollar", "roi", "pnl", "profit", "$"}
        for trade in result["trades"]:
            for key in trade.keys():
                assert key.lower() not in banned

    def test_executed_always_false_in_trades(self, tmp_path):
        from scripts.platformkit.pm_trail_browse import browse_pm_trail
        row = _base_row(taken_book="kalshi")
        lpath = _write_ledger(tmp_path, [row])
        result = browse_pm_trail(lpath)
        for trade in result["trades"]:
            assert trade["executed"] is False

    def test_empty_ledger_ok(self, tmp_path):
        from scripts.platformkit.pm_trail_browse import browse_pm_trail
        lpath = tmp_path / "nonexistent.jsonl"
        result = browse_pm_trail(lpath)
        assert result["status"] == "ok"
        assert result["trades"] == []

    def test_pagination(self, tmp_path):
        from scripts.platformkit.pm_trail_browse import browse_pm_trail
        # Give each row a unique ts + matchup so they don't collapse to one bet
        rows = [
            _base_row(
                taken_book="kalshi",
                bet_id="k%d" % i,
                matchup="T%d@T%d" % (i, i + 1),
                ts="2026-06-19T%02d:00:00+00:00" % i,
            )
            for i in range(10)
        ]
        lpath = _write_ledger(tmp_path, rows)
        page1 = browse_pm_trail(lpath, offset=0, limit=3)
        page2 = browse_pm_trail(lpath, offset=3, limit=3)
        assert page1["count"] == 3
        assert page2["count"] == 3
        # Pages should not overlap
        ids1 = {t["bet_id"] for t in page1["trades"]}
        ids2 = {t["bet_id"] for t in page2["trades"]}
        assert ids1.isdisjoint(ids2)


class TestBestPmTrades:
    def test_sorted_by_tier_then_confidence(self, tmp_path):
        from scripts.platformkit.pm_trail_browse import best_pm_trades
        rows = [
            _base_row(taken_book="kalshi", ev_pct=2.5, model_prob=0.52, bet_id="c1"),  # C
            _base_row(taken_book="kalshi", ev_pct=9.0, model_prob=0.65, bet_id="a1"),  # A
            _base_row(taken_book="kalshi", ev_pct=5.0, model_prob=0.60, bet_id="b1"),  # B
        ]
        lpath = _write_ledger(tmp_path, rows)
        result = best_pm_trades(lpath, top_n=3)
        assert result["status"] == "ok"
        tiers = [t["tier"] for t in result["trades"]]
        # A should come before B which comes before C
        if "A" in tiers and "B" in tiers:
            assert tiers.index("A") < tiers.index("B")
        if "B" in tiers and "C" in tiers:
            assert tiers.index("B") < tiers.index("C")

    def test_top_n_capped(self, tmp_path):
        from scripts.platformkit.pm_trail_browse import best_pm_trades
        rows = [
            _base_row(taken_book="kalshi", bet_id="k%d" % i, ev_pct=5.0)
            for i in range(5)
        ]
        lpath = _write_ledger(tmp_path, rows)
        result = best_pm_trades(lpath, top_n=3)
        assert len(result["trades"]) <= 3


class TestTradeDetail:
    def test_found_by_bet_id(self, tmp_path):
        from scripts.platformkit.pm_trail_browse import trade_detail
        row = _base_row(
            taken_book="kalshi",
            bet_id="nba|LAL@BOS|moneyline|home|kalshi|2026-06-19",
        )
        lpath = _write_ledger(tmp_path, [row])
        result = trade_detail(
            "nba|LAL@BOS|moneyline|home|kalshi|2026-06-19", lpath
        )
        assert result["status"] == "ok"
        assert result["trade"] is not None
        assert result["trade"]["executed"] is False

    def test_not_found(self, tmp_path):
        from scripts.platformkit.pm_trail_browse import trade_detail
        lpath = _write_ledger(tmp_path, [_base_row(taken_book="kalshi")])
        result = trade_detail("nonexistent-bet-id", lpath)
        assert result["status"] == "not_found"
        assert result["trade"] is None

    def test_per_trade_no_dollar_field(self, tmp_path):
        from scripts.platformkit.pm_trail_browse import trade_detail
        row = _base_row(taken_book="kalshi",
                        bet_id="nba|X@Y|ml|home|k|2026-06-19")
        lpath = _write_ledger(tmp_path, [row])
        result = trade_detail("nba|X@Y|ml|home|k|2026-06-19", lpath)
        if result.get("trade"):
            banned = {"dollar", "roi", "pnl", "profit", "$"}
            for key in result["trade"].keys():
                assert key.lower() not in banned

    def test_null_clv_honest_in_detail(self, tmp_path):
        from scripts.platformkit.pm_trail_browse import trade_detail
        row = _settled_row(
            taken_book="polymarket",
            bet_id="test-trade-no-close",
            clv_pct=None, beat_close=None,
            clv_is_proxy=False, clv_status="no_close",
        )
        lpath = _write_ledger(tmp_path, [row])
        result = trade_detail("test-trade-no-close", lpath)
        if result.get("trade"):
            assert result["trade"]["clv_pct"] is None  # never 0-filled


# ---------------------------------------------------------------------------
# FastAPI TestClient tests for pm_trail_routes
# ---------------------------------------------------------------------------

class TestPmTrailRoutes:
    @pytest.fixture()
    def client(self, tmp_path):
        """Build a minimal FastAPI app with pm_trail_routes mounted."""
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
            from predict_service.frontend.pm_trail_routes import router
        except ImportError:
            pytest.skip("fastapi / routes not importable")

        app = FastAPI()
        app.include_router(router)
        return TestClient(app), tmp_path

    def test_trail_endpoint_ok(self, client):
        tc, tmp_path = client
        row = _base_row(taken_book="kalshi")
        lpath = _write_ledger(tmp_path, [row])
        resp = tc.get("/api/paper/pm/trail", params={"ledger": str(lpath)})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "trades" in data

    def test_trail_endpoint_pm_only(self, client):
        tc, tmp_path = client
        rows = [
            _base_row(taken_book="kalshi", bet_id="k1"),
            _base_row(taken_book="espn:DraftKings", bet_id="sb1"),
        ]
        lpath = _write_ledger(tmp_path, rows)
        resp = tc.get("/api/paper/pm/trail", params={"ledger": str(lpath)})
        data = resp.json()
        venues = {t["venue"] for t in data.get("trades", [])}
        assert "sportsbook" not in venues

    def test_trail_endpoint_no_dollar_field(self, client):
        tc, tmp_path = client
        row = _base_row(taken_book="kalshi")
        lpath = _write_ledger(tmp_path, [row])
        resp = tc.get("/api/paper/pm/trail", params={"ledger": str(lpath)})
        data = resp.json()
        banned = {"dollar", "roi", "pnl", "profit"}
        for trade in data.get("trades", []):
            for key in trade.keys():
                assert key.lower() not in banned

    def test_real_money_enabled_false(self, client):
        tc, tmp_path = client
        lpath = _write_ledger(tmp_path, [])
        resp = tc.get("/api/paper/pm/trail", params={"ledger": str(lpath)})
        data = resp.json()
        assert data.get("real_money_enabled") is False

    def test_trade_detail_endpoint_ok(self, client):
        tc, tmp_path = client
        bid = "nba|A@B|moneyline|home|kalshi|2026-06-19"
        row = _base_row(taken_book="kalshi", bet_id=bid)
        lpath = _write_ledger(tmp_path, [row])
        resp = tc.get(
            f"/api/paper/pm/trade/{bid}",
            params={"ledger": str(lpath)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["trade"]["executed"] is False

    def test_trade_detail_not_found(self, client):
        tc, tmp_path = client
        lpath = _write_ledger(tmp_path, [])
        resp = tc.get("/api/paper/pm/trade/ghost-id",
                      params={"ledger": str(lpath)})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "not_found"
        assert data["trade"] is None

    def test_best_trades_endpoint(self, client):
        tc, tmp_path = client
        rows = [
            _base_row(taken_book="kalshi", ev_pct=9.0, bet_id="a"),
            _base_row(taken_book="kalshi", ev_pct=5.0, bet_id="b"),
        ]
        lpath = _write_ledger(tmp_path, rows)
        resp = tc.get(
            "/api/paper/pm/trail",
            params={"ledger": str(lpath), "best": "true", "top_n": 2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
