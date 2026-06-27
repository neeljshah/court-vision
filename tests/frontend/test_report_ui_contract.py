"""Per-file test: GameReport UI contract validation.

Validates the report JSON shape that GameReport / ReportPregame / ReportMarkets /
ReportLive / ReportIntel consume from GET /api/report/{sport}/{game_id}.

Because the project has no JS test runner (no jest/vitest), this Python test
verifies the backend contract matches the TypeScript prop types defined in the
React components. Any shape drift here breaks the report panel.

Component prop types being validated:
  GameReport            <- full ReportData
  ReportPregame         <- pregame: PregameData | null
  ReportMarkets         <- markets: MarketRow[], edges: EdgeRow[]
  ReportLive            <- live: LiveData | null
  ReportIntel           <- intel: IntelData | null

Run: python -m pytest tests/frontend/test_report_ui_contract.py -q
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from predict_service import store
from predict_service.contracts import (
    EdgeRow,
    MarketRow,
    PredictionRecord,
    SnapshotEnvelope,
)
import frontend.report as report_mod
from frontend.report import build_report

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SPORT = "nba"
_GID = "0042500401"
_FORBIDDEN = ("$", "dollar", "roi", "pnl", "profit", "stake", "bankroll")

# ---------------------------------------------------------------------------
# Prop-type field sets (must match the TypeScript interfaces exactly)
# ---------------------------------------------------------------------------

# GameReport.ReportData top-level keys (status='ok' variant)
_REPORT_OK_KEYS = {
    "status",
    "sport",
    "game_id",
    "pregame",
    "markets",
    "edges",
    "live",
    "intel",
    "meta",
}

# GameReport.ReportData top-level keys (status='unavailable' variant)
_REPORT_UNAVAILABLE_KEYS = {
    "status",
    "sport",
    "game_id",
    "reason",
    "pregame",
    "markets",
    "edges",
    "live",
    "intel",
    "meta",
}

# ReportPregame.PregameData
_PREGAME_KEYS = {
    "home",
    "away",
    "tipoff",
    "model_probs",
    "leak_guard",
    "produced_at",
    "note",
}

# ReportMarkets.MarketRow (one entry from markets[])
_MARKET_ROW_KEYS = {
    "sport",
    "game_id",
    "market_type",
    "side",
    "line",
    "odds",
    "book",
    "devigged_prob",
    "captured_at",
    "is_close",
    "clv_is_proxy",
}

# ReportMarkets.EdgeRow (one entry from edges[])
_EDGE_ROW_KEYS = {
    "game_id",
    "market_type",
    "side",
    "model_prob",
    "market_prob",
    "ev",
    "tier",
    "book",
    "line",
    "clv_is_proxy",
}

# ReportLive.LiveData (live block -- status is always present; others optional)
_LIVE_REQUIRED_KEYS = {"status"}

# ReportIntel.IntelData (intel block)
_INTEL_REQUIRED_KEYS = {"home", "away", "matchup", "status", "note"}

# MetaData block
_META_KEYS = {
    "as_of",
    "honest_note",
    "schema_version",
    "clv_is_proxy",
    "snapshot_generated_at",
    "freshness",
}

# FreshnessData block
_FRESHNESS_KEYS = {"status", "age_sec"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stub_envelope() -> SnapshotEnvelope:
    """Canonical stub envelope for one NBA game."""
    market = MarketRow(
        sport=_SPORT,
        game_id=_GID,
        market_type="moneyline",
        side="home",
        line=None,
        odds=1.71,
        book="espn:DK",
        devigged_prob=0.57,
        captured_at="2026-06-18T22:00:00+00:00",
        is_close=False,
        clv_is_proxy=True,
    )
    record = PredictionRecord(
        sport=_SPORT,
        game_id=_GID,
        home="San Antonio Spurs",
        away="New York Knicks",
        tipoff="2026-06-18T23:30:00+00:00",
        pregame_probs={"home_ml": 0.55, "away_ml": 0.45},
        markets=[market],
        leak_guard={"in_sample": False},
        produced_at="2026-06-18T21:00:00+00:00",
    )
    edge = EdgeRow(
        game_id=_GID,
        market_type="moneyline",
        side="home",
        model_prob=0.55,
        market_prob=0.53,
        ev=0.037,
        tier="B",
        book="espn:DK",
        line=None,
        clv_is_proxy=True,
    )
    return SnapshotEnvelope(
        sport=_SPORT,
        generated_at="2026-06-18T22:01:00+00:00",
        status="ok",
        predictions=[record],
        markets=[market],
        edges=[edge],
    )


def _assert_no_money(obj: Any, path: str = "root") -> None:
    """Recursively assert no forbidden $ / roi / pnl key appears anywhere.

    Checks KEY names only (not values, since honest_note may mention 'no $ edge').
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            for bad in _FORBIDDEN:
                assert bad not in kl, (
                    "Forbidden key %r found at path %r -- no $ fields in report"
                    % (k, path)
                )
            _assert_no_money(v, path="%s.%s" % (path, k))
    elif isinstance(obj, list):
        for i, it in enumerate(obj):
            _assert_no_money(it, path="%s[%d]" % (path, i))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store_dir(tmp_path, monkeypatch):
    """Write stub envelope to temp store; stub live board to avoid network."""
    store.save(_stub_envelope(), out_dir=tmp_path, append=False)
    monkeypatch.setattr(
        report_mod,
        "_live",
        lambda *a, **k: {"status": "unavailable", "reason": "stubbed in test"},
    )
    return tmp_path


@pytest.fixture()
def report_ok(store_dir):
    """The full ok-variant report dict."""
    return build_report(_SPORT, _GID, store_out_dir=store_dir)


@pytest.fixture()
def report_unavailable(store_dir):
    """The unavailable-variant report dict (unknown game_id)."""
    return build_report(_SPORT, "UNKNOWN_GAME_XYZ", store_out_dir=store_dir)


# ---------------------------------------------------------------------------
# Test 1: Top-level shape -- ok variant
# ---------------------------------------------------------------------------


def test_ok_top_level_keys_match_react_interface(report_ok):
    """GameReport.ReportData ok-variant must have all required keys."""
    missing = _REPORT_OK_KEYS - set(report_ok.keys())
    assert not missing, "Missing top-level keys in ok report: %s" % sorted(missing)
    assert report_ok["status"] == "ok"


# ---------------------------------------------------------------------------
# Test 2: Top-level shape -- unavailable variant
# ---------------------------------------------------------------------------


def test_unavailable_top_level_keys_match_react_interface(report_unavailable):
    """GameReport.ReportData unavailable-variant must have all required keys."""
    missing = _REPORT_UNAVAILABLE_KEYS - set(report_unavailable.keys())
    assert not missing, (
        "Missing top-level keys in unavailable report: %s" % sorted(missing)
    )
    assert report_unavailable["status"] == "unavailable"
    assert report_unavailable["pregame"] is None
    assert report_unavailable["markets"] == []
    assert report_unavailable["edges"] == []
    assert report_unavailable["intel"] is None
    assert "reason" in report_unavailable and report_unavailable["reason"]


# ---------------------------------------------------------------------------
# Test 3: ReportPregame.PregameData shape
# ---------------------------------------------------------------------------


def test_pregame_keys_match_react_interface(report_ok):
    """ReportPregame.PregameData must expose all fields the component reads."""
    pre = report_ok["pregame"]
    assert pre is not None, "pregame must not be null in the ok variant"
    missing = _PREGAME_KEYS - set(pre.keys())
    assert not missing, "Missing pregame keys: %s" % sorted(missing)
    assert isinstance(pre["model_probs"], dict)
    assert isinstance(pre["leak_guard"], dict)
    assert "in_sample" in pre["leak_guard"]


def test_pregame_home_away_are_strings(report_ok):
    """ReportPregame renders home/away team names directly."""
    pre = report_ok["pregame"]
    assert isinstance(pre["home"], str) and pre["home"]
    assert isinstance(pre["away"], str) and pre["away"]


def test_pregame_leak_guard_in_sample_is_bool(report_ok):
    """ReportPregame shows the leak-free badge when in_sample=False."""
    lg = report_ok["pregame"]["leak_guard"]
    assert isinstance(lg["in_sample"], bool)


# ---------------------------------------------------------------------------
# Test 4: ReportMarkets.MarketRow shape
# ---------------------------------------------------------------------------


def test_market_rows_match_react_interface(report_ok):
    """Each MarketRow in markets[] must expose all fields ReportMarkets reads."""
    assert len(report_ok["markets"]) >= 1, "Expected at least one market row"
    for m in report_ok["markets"]:
        missing = _MARKET_ROW_KEYS - set(m.keys())
        assert not missing, "MarketRow missing keys: %s" % sorted(missing)
        assert isinstance(m["is_close"], bool)
        assert isinstance(m["clv_is_proxy"], bool)


# ---------------------------------------------------------------------------
# Test 5: ReportMarkets.EdgeRow shape
# ---------------------------------------------------------------------------


def test_edge_rows_match_react_interface(report_ok):
    """Each EdgeRow in edges[] must expose all fields ReportMarkets renders."""
    assert len(report_ok["edges"]) >= 1, "Expected at least one edge row"
    for e in report_ok["edges"]:
        missing = _EDGE_ROW_KEYS - set(e.keys())
        assert not missing, "EdgeRow missing keys: %s" % sorted(missing)
        assert isinstance(e["model_prob"], float)
        assert isinstance(e["market_prob"], float)
        assert isinstance(e["ev"], float)
        assert isinstance(e["clv_is_proxy"], bool)


def test_edge_rows_no_dollar_field(report_ok):
    """HONESTY: EdgeRow must never carry a $-edge / dollar amount field."""
    for e in report_ok["edges"]:
        for k in e.keys():
            for bad in _FORBIDDEN:
                assert bad not in k.lower(), (
                    "Forbidden key %r in EdgeRow -- no $ fields allowed" % k
                )


# ---------------------------------------------------------------------------
# Test 6: ReportLive.LiveData shape
# ---------------------------------------------------------------------------


def test_live_block_has_status(report_ok):
    """ReportLive.LiveData must always carry a status key."""
    live = report_ok["live"]
    assert isinstance(live, dict), "live must be a dict, not null"
    missing = _LIVE_REQUIRED_KEYS - set(live.keys())
    assert not missing, "Missing live keys: %s" % sorted(missing)
    assert live["status"] in ("ok", "unavailable")


def test_live_unavailable_has_no_fabricated_scores(report_ok):
    """When live is unavailable, no score fields should be fabricated."""
    live = report_ok["live"]
    if live["status"] == "unavailable":
        for score_key in ("home_score", "away_score"):
            assert score_key not in live or live[score_key] is None


# ---------------------------------------------------------------------------
# Test 7: ReportIntel.IntelData shape
# ---------------------------------------------------------------------------


def test_intel_block_has_required_keys(report_ok):
    """ReportIntel.IntelData must expose home/away/matchup/status/note."""
    intel = report_ok["intel"]
    assert isinstance(intel, dict), "intel must be a dict in the ok variant"
    missing = _INTEL_REQUIRED_KEYS - set(intel.keys())
    assert not missing, "Missing intel keys: %s" % sorted(missing)
    assert intel["status"] in ("ok", "unavailable")


def test_intel_edge_claim_is_false_when_matchup_present(report_ok):
    """MatchupBlurb.edge_claim must always be false -- never claim an edge."""
    intel = report_ok["intel"]
    matchup = intel.get("matchup")
    if matchup is not None and isinstance(matchup, dict):
        assert matchup.get("edge_claim") is False, (
            "matchup.edge_claim must be False -- no edge claims in scouting intel"
        )


def test_intel_team_blurbs_null_or_dict(report_ok):
    """home/away blurbs are either null or a dict with expected structure."""
    intel = report_ok["intel"]
    for side in ("home", "away"):
        blurb = intel.get(side)
        if blurb is not None:
            assert isinstance(blurb, dict)
            for required in ("tricode", "label", "strengths", "weaknesses"):
                assert required in blurb, (
                    "TeamBlurb missing field %r for side %r" % (required, side)
                )
            assert isinstance(blurb["strengths"], list)
            assert isinstance(blurb["weaknesses"], list)


# ---------------------------------------------------------------------------
# Test 8: MetaData shape
# ---------------------------------------------------------------------------


def test_meta_keys_match_react_interface(report_ok):
    """MetaData must expose all fields the component reads."""
    meta = report_ok["meta"]
    missing = _META_KEYS - set(meta.keys())
    assert not missing, "Missing meta keys: %s" % sorted(missing)
    assert meta["honest_note"], "honest_note must be non-empty"
    assert meta["schema_version"]
    assert isinstance(meta["clv_is_proxy"], bool)


def test_meta_freshness_shape(report_ok):
    """FreshnessData inside meta must carry status and age_sec."""
    freshness = report_ok["meta"]["freshness"]
    missing = _FRESHNESS_KEYS - set(freshness.keys())
    assert not missing, "Missing freshness keys: %s" % sorted(missing)
    assert freshness["status"] in ("fresh", "stale", "unknown")


# ---------------------------------------------------------------------------
# Test 9: No $ / money keys anywhere (recursively)
# ---------------------------------------------------------------------------


def test_no_dollar_keys_ok_variant(report_ok):
    """HONESTY: no forbidden money key appears anywhere in the ok report."""
    _assert_no_money(report_ok)


def test_no_dollar_keys_unavailable_variant(report_unavailable):
    """HONESTY: no forbidden money key appears in the unavailable report either."""
    _assert_no_money(report_unavailable)


# ---------------------------------------------------------------------------
# Test 10: unavailable partial pieces are represented correctly
# ---------------------------------------------------------------------------


def test_unavailable_live_is_dict_with_status(report_ok):
    """live block is always a dict with status -- never null. Component checks status."""
    live = report_ok.get("live")
    assert live is not None, "live must never be null -- use {'status':'unavailable'}"
    assert "status" in live


def test_intel_null_in_unavailable_variant(report_unavailable):
    """In the unavailable top-level variant, intel is null (not a dict)."""
    assert report_unavailable["intel"] is None


def test_markets_empty_list_not_null_in_unavailable(report_unavailable):
    """markets and edges are [] not null in the unavailable variant."""
    assert report_unavailable["markets"] == []
    assert report_unavailable["edges"] == []


# ---------------------------------------------------------------------------
# Test 11: API route contract (via TestClient on predict_service.app)
# ---------------------------------------------------------------------------


@pytest.fixture()
def api_client(store_dir, monkeypatch):
    """TestClient for the full app with stubbed store + live board."""
    monkeypatch.setenv("PREDICT_SERVICE_STORE_DIR", str(store_dir))
    from predict_service.app import app  # noqa: PLC0415
    return TestClient(app)


def test_api_report_game_response_shape(api_client):
    """GET /api/report/{sport}/{game_id} returns the full ok shape."""
    r = api_client.get("/api/report/%s/%s" % (_SPORT, _GID))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    missing = _REPORT_OK_KEYS - set(body.keys())
    assert not missing, "API response missing keys: %s" % sorted(missing)


def test_api_report_unavailable_shape(api_client):
    """GET /api/report/{sport}/UNKNOWN returns the clean unavailable shape."""
    r = api_client.get("/api/report/%s/UNKNOWN_GAME_ZZZ" % _SPORT)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "unavailable"
    missing = _REPORT_UNAVAILABLE_KEYS - set(body.keys())
    assert not missing, "Unavailable API response missing keys: %s" % sorted(missing)


def test_api_report_no_money_keys(api_client):
    """No forbidden money keys in the API response (recursive)."""
    r = api_client.get("/api/report/%s/%s" % (_SPORT, _GID))
    _assert_no_money(r.json())


def test_api_browse_list_shape(api_client):
    """GET /api/report/{sport} returns game_ids list with expected shape."""
    r = api_client.get("/api/report/%s" % _SPORT)
    assert r.status_code == 200
    body = r.json()
    for key in ("status", "sport", "game_ids", "count", "honest_note"):
        assert key in body, "browse list missing key %r" % key
    assert isinstance(body["game_ids"], list)
    assert isinstance(body["count"], int)
    assert body["honest_note"]
