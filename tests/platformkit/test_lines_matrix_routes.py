"""Per-file unit tests for lines_matrix_routes (NETWORK-FREE).

Tests:
 - matrix shape: markets dict has expected structure for each market type
 - best-line: sportsbook-only best price wins; PM price excluded from best[]
 - PM separation: PM venue tagged is_pm=True; sportsbook tagged is_pm=False
 - empty->UNAVAILABLE: missing game_id, unavailable slate -> correct 404/503 shape
 - prop_aggregate: best_line_props dedup and gather_props pass-through

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_lines_matrix_routes.py -q
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from predict_service.frontend.lines_matrix_routes import router

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    return a


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


# Canned aggregate payload with one well-formed event and PM venue.
_AGG_OK = {
    "sport": "nba",
    "status": "ok",
    "as_of": "2026-06-19T12:00:00+00:00",
    "sources": {"espn": "ok"},
    "events": [
        {
            "event_id": "nba_401",
            "sport": "nba",
            "home": "Boston Celtics",
            "away": "New York Knicks",
            "prices": {
                "espn:DraftKings": {
                    "home": 1.50,
                    "away": 2.60,
                    "draw": None,
                    "spread": {
                        "home": {"line": -5.5, "odds": 1.91},
                        "away": {"line": 5.5, "odds": 1.91},
                    },
                    "total": {
                        "over": {"line": 220.5, "odds": 1.95},
                        "under": {"line": 220.5, "odds": 1.87},
                    },
                },
                # PM venue: higher odds than the book but must NOT win best[]
                "kalshi": {
                    "home": 1.65,
                    "away": 2.45,
                },
            },
        },
    ],
}

_AGG_UNAVAILABLE = {"sport": "nba", "status": "unavailable", "sources": {}}


# ------------------------------------------------------------------
# 1. Matrix shape
# ------------------------------------------------------------------

class TestMatrixShape:
    def test_ok_response_has_markets_and_best(self, client):
        with patch(
            "predict_service.frontend.lines_matrix_routes.aggregate",
            return_value=_AGG_OK,
        ):
            resp = client.get("/api/lines/nba/nba_401")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["game_id"] == "nba_401"
        assert body["home"] == "Boston Celtics"
        assert body["away"] == "New York Knicks"
        assert "markets" in body
        assert "best" in body

    def test_moneyline_matrix_has_home_and_away(self, client):
        with patch(
            "predict_service.frontend.lines_matrix_routes.aggregate",
            return_value=_AGG_OK,
        ):
            resp = client.get("/api/lines/nba/nba_401")
        body = resp.json()
        ml = body["markets"].get("moneyline", {})
        assert "home" in ml
        assert "away" in ml

    def test_spread_matrix_has_home_and_away(self, client):
        with patch(
            "predict_service.frontend.lines_matrix_routes.aggregate",
            return_value=_AGG_OK,
        ):
            resp = client.get("/api/lines/nba/nba_401")
        body = resp.json()
        sp = body["markets"].get("spread", {})
        assert "home" in sp
        assert "away" in sp

    def test_total_matrix_has_over_and_under(self, client):
        with patch(
            "predict_service.frontend.lines_matrix_routes.aggregate",
            return_value=_AGG_OK,
        ):
            resp = client.get("/api/lines/nba/nba_401")
        body = resp.json()
        tot = body["markets"].get("total", {})
        assert "over" in tot
        assert "under" in tot

    def test_no_dollar_field(self, client):
        with patch(
            "predict_service.frontend.lines_matrix_routes.aggregate",
            return_value=_AGG_OK,
        ):
            resp = client.get("/api/lines/nba/nba_401")
        body = resp.json()
        # Recursively check no $ key
        def _has_dollar(obj):
            if isinstance(obj, dict):
                return any(k in ("dollar", "pnl", "roi", "profit")
                           or "$" in str(k)
                           for k in obj) or any(_has_dollar(v) for v in obj.values())
            if isinstance(obj, list):
                return any(_has_dollar(i) for i in obj)
            return False
        assert not _has_dollar(body)


# ------------------------------------------------------------------
# 2. Best-line: sportsbook wins; PM excluded from best[]
# ------------------------------------------------------------------

class TestBestLine:
    def test_best_moneyline_home_is_sportsbook_not_pm(self, client):
        """kalshi has higher home odds (1.65 vs 1.50) but must NOT win best[]."""
        with patch(
            "predict_service.frontend.lines_matrix_routes.aggregate",
            return_value=_AGG_OK,
        ):
            resp = client.get("/api/lines/nba/nba_401")
        body = resp.json()
        best_ml = body["best"].get("moneyline", {})
        # best home must come from a non-PM book
        if "home" in best_ml:
            assert best_ml["home"]["book"] != "kalshi"

    def test_best_moneyline_sportsbook_odds_value(self, client):
        with patch(
            "predict_service.frontend.lines_matrix_routes.aggregate",
            return_value=_AGG_OK,
        ):
            resp = client.get("/api/lines/nba/nba_401")
        body = resp.json()
        best_ml = body["best"].get("moneyline", {})
        if "home" in best_ml:
            # DK home odds is 1.50 (the only sportsbook)
            assert abs(best_ml["home"]["odds"] - 1.50) < 0.001


# ------------------------------------------------------------------
# 3. PM separation
# ------------------------------------------------------------------

class TestPmSeparation:
    def test_kalshi_tagged_is_pm_true(self, client):
        with patch(
            "predict_service.frontend.lines_matrix_routes.aggregate",
            return_value=_AGG_OK,
        ):
            resp = client.get("/api/lines/nba/nba_401")
        body = resp.json()
        ml = body["markets"].get("moneyline", {})
        all_rows = [r for side_rows in ml.values() for r in side_rows]
        kalshi_rows = [r for r in all_rows if r["book"] == "kalshi"]
        assert kalshi_rows, "expected at least one kalshi row"
        for r in kalshi_rows:
            assert r["is_pm"] is True, f"kalshi row must be is_pm=True: {r}"

    def test_sportsbook_tagged_is_pm_false(self, client):
        with patch(
            "predict_service.frontend.lines_matrix_routes.aggregate",
            return_value=_AGG_OK,
        ):
            resp = client.get("/api/lines/nba/nba_401")
        body = resp.json()
        ml = body["markets"].get("moneyline", {})
        all_rows = [r for side_rows in ml.values() for r in side_rows]
        sb_rows = [r for r in all_rows if "DraftKings" in r["book"]]
        assert sb_rows, "expected at least one DraftKings row"
        for r in sb_rows:
            assert r["is_pm"] is False, f"DK row must be is_pm=False: {r}"


# ------------------------------------------------------------------
# 4. Empty/UNAVAILABLE paths
# ------------------------------------------------------------------

class TestUnavailablePaths:
    def test_missing_game_id_returns_404(self, client):
        with patch(
            "predict_service.frontend.lines_matrix_routes.aggregate",
            return_value=_AGG_OK,
        ):
            resp = client.get("/api/lines/nba/nonexistent_game")
        assert resp.status_code == 404
        body = resp.json()
        assert body["status"] == "UNAVAILABLE"
        assert body["edge_claimed"] is False

    def test_unavailable_slate_returns_503(self, client):
        with patch(
            "predict_service.frontend.lines_matrix_routes.aggregate",
            return_value=_AGG_UNAVAILABLE,
        ):
            resp = client.get("/api/lines/nba/nba_401")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "UNAVAILABLE"

    def test_aggregate_exception_returns_503(self, client):
        with patch(
            "predict_service.frontend.lines_matrix_routes.aggregate",
            side_effect=RuntimeError("network down"),
        ):
            resp = client.get("/api/lines/nba/nba_401")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "UNAVAILABLE"

    def test_nba_props_unavailable_offseason(self, client):
        """NBA props degrade to UNAVAILABLE when providers return empty."""
        mock_cfg = MagicMock()
        mock_cfg.default_providers.return_value = []
        mock_cfg.extra = {"offseason_empty": True}

        # get_config is imported inside the route function, so patch the source.
        with patch(
            "scripts.platformkit.prop_edge_config.get_config",
            return_value=mock_cfg,
        ):
            resp = client.get("/api/props/nba")
        # With empty providers, it should return 503 UNAVAILABLE
        assert resp.status_code in (503, 404)
        body = resp.json()
        assert body["status"] == "UNAVAILABLE"

    def test_unknown_sport_props_returns_unavailable(self, client):
        resp = client.get("/api/props/curling")
        # curling is not registered in prop_edge_config, so should be 404
        assert resp.status_code in (404, 503)
        body = resp.json()
        assert body["status"] == "UNAVAILABLE"


# ------------------------------------------------------------------
# 5. prop_aggregate unit tests (NETWORK-FREE, no TestClient)
# ------------------------------------------------------------------

class TestPropAggregate:
    """Unit tests for prop_aggregate pure functions."""

    def _make_prop(self, player="Alice", stat="Points", line=20.5,
                   over_price=1.91, under_price=1.91,
                   payout_type="sportsbook", source="underdog"):
        from scripts.platformkit.odds_provider.prop_base import PropLine
        return PropLine(
            sport="nba",
            event_id="nba_401",
            match="BOS vs NYK",
            player=player,
            team="BOS",
            stat=stat,
            line=line,
            over_price=over_price,
            under_price=under_price,
            payout_type=payout_type,
            source=source,
            as_of="2026-06-19T12:00:00+00:00",
        )

    def test_gather_props_collects_from_providers(self):
        from scripts.platformkit.odds_provider.prop_aggregate import gather_props
        prop = self._make_prop()
        prov = MagicMock()
        prov.fetch_props.return_value = [prop]
        result = gather_props([prov], "nba")
        assert len(result) == 1
        assert result[0].player == "Alice"

    def test_gather_props_skips_unavailable(self):
        from scripts.platformkit.odds_provider.prop_aggregate import gather_props
        from scripts.platformkit.odds_provider.base import UNAVAILABLE
        prov = MagicMock()
        prov.fetch_props.return_value = UNAVAILABLE
        result = gather_props([prov], "nba")
        assert result == []

    def test_gather_props_skips_provider_exception(self):
        from scripts.platformkit.odds_provider.prop_aggregate import gather_props
        prov = MagicMock()
        prov.fetch_props.side_effect = RuntimeError("boom")
        result = gather_props([prov], "nba")
        assert result == []

    def test_best_line_props_dedup_picks_higher_over_price(self):
        """When two providers quote the same prop, best over_price wins."""
        from scripts.platformkit.odds_provider.prop_aggregate import best_line_props
        p1 = self._make_prop(over_price=1.85, source="underdog")
        p2 = self._make_prop(over_price=1.92, source="prizepicks")
        prov1, prov2 = MagicMock(), MagicMock()
        prov1.fetch_props.return_value = [p1]
        prov2.fetch_props.return_value = [p2]
        result = best_line_props([prov1, prov2], "nba")
        assert len(result) == 1
        assert abs(result[0].over_price - 1.92) < 0.001

    def test_best_line_props_dedup_distinct_players_kept(self):
        from scripts.platformkit.odds_provider.prop_aggregate import best_line_props
        p1 = self._make_prop(player="Alice")
        p2 = self._make_prop(player="Bob")
        prov = MagicMock()
        prov.fetch_props.return_value = [p1, p2]
        result = best_line_props([prov], "nba")
        assert len(result) == 2

    def test_best_line_props_sportsbook_beats_pickem(self):
        """A sportsbook row replaces a pick'em row for the same key."""
        from scripts.platformkit.odds_provider.prop_aggregate import best_line_props
        pickem = self._make_prop(over_price=None, payout_type="dfs_pickem",
                                 source="prizepicks")
        sb = self._make_prop(over_price=1.88, payout_type="sportsbook",
                             source="underdog")
        prov = MagicMock()
        prov.fetch_props.return_value = [pickem, sb]
        result = best_line_props([prov], "nba")
        assert len(result) == 1
        assert result[0].over_price is not None
        assert result[0].payout_type == "sportsbook"

    def test_prop_best_line_summary_no_dollar_field(self):
        from scripts.platformkit.odds_provider.prop_aggregate import (
            prop_best_line_summary)
        prop = self._make_prop()
        summary = prop_best_line_summary(prop)
        for k in summary:
            assert "$" not in k
            assert k not in ("dollar", "pnl", "roi", "profit")
        assert summary["is_pm"] is False

    def test_prop_best_line_summary_shape(self):
        from scripts.platformkit.odds_provider.prop_aggregate import (
            prop_best_line_summary)
        prop = self._make_prop()
        s = prop_best_line_summary(prop)
        for key in ("player", "stat", "line", "over_price", "under_price",
                    "payout_type", "is_pm", "event_id", "sport"):
            assert key in s, f"missing key {key!r}"


# ------------------------------------------------------------------
# 6. prop_edge_config NBA entry
# ------------------------------------------------------------------

class TestPropEdgeConfigNba:
    def test_nba_in_supported_sports(self):
        from scripts.platformkit.prop_edge_config import supported_sports
        assert "nba" in supported_sports()

    def test_get_config_nba_returns_config(self):
        from scripts.platformkit.prop_edge_config import get_config
        cfg = get_config("nba")
        assert cfg is not None
        assert cfg.sport == "nba"

    def test_nba_config_providers_are_list(self):
        from scripts.platformkit.prop_edge_config import get_config
        cfg = get_config("nba")
        assert cfg is not None
        providers = cfg.default_providers()
        assert isinstance(providers, list)

    def test_nba_engine_raises_not_implemented(self):
        from scripts.platformkit.prop_edge_config import get_config
        cfg = get_config("nba")
        assert cfg is not None
        with pytest.raises(NotImplementedError):
            cfg.engine_distribution(None, None, None, None)

    def test_nba_canonical_stats_is_frozenset(self):
        from scripts.platformkit.prop_edge_config import get_config
        cfg = get_config("nba")
        assert isinstance(cfg.canonical_stats, frozenset)
        assert len(cfg.canonical_stats) > 0
