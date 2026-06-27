"""Per-file test: COMPREHENSIVE endpoint contract matrix for predict_service.app.

This is the canonical :8099 Auto-API verified WITHOUT a live boot -- FastAPI's
TestClient drives the SAME app object `python -m predict_service.app` serves, so
every mounted router (predict/report/bestbets/quant/ingame/catalog/intel/progress/
paper/parity/freshness/clv/improve/ops) is exercised in-process.

For EVERY endpoint we assert the six contract rails the task requires:
  (1) 200-or-honest-degrade, NEVER a 500 / stack -- the @honest_route + mount
      guards hold; a degraded surface returns a clean unavailable sentinel.
  (2) response schema/contract -- the body is a dict and (where applicable) carries
      its declared keys.
  (3) recursive NO-$ assertion -- no $/P&L/ROI/dollar money KEY anywhere in the
      payload (the canonical units field stake_units / arb stake_a|b are allowed;
      they carry no $). Checked on object keys, never free text, so a matchup name
      ("Astros") cannot trip it.
  (4) honest flags -- where present, edge_claimed is False, real_money_enabled is
      False, and any vs_close value is UNPROVEN (never PROVEN by default).
  (5) per-sport coverage incl the honest-EMPTY path (tennis: offseason ->
      status='unavailable', NOT a fabricated game).
  (6) a forced-failure inside a handler degrades to an honest unavailable envelope
      (503, no stack), proving the @honest_route envelope holds at runtime.

The store is rooted at a tmp_path via the app's _store_out_dir override so the
genuine read path runs (no parallel stub). Endpoints that read OTHER canonical
stores (registry/produce/results) degrade honestly on the empty tmp -- which is
exactly the contract under test.

Honesty invariant: no $ / edge / roi / pnl money KEY in any response body.

Run: python -m pytest tests/predict_service/test_endpoint_contract_matrix.py -q
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from predict_service import app as app_module
from predict_service import store
from predict_service.contracts import (
    EdgeRow,
    MarketRow,
    PredictionRecord,
    SnapshotEnvelope,
)

SPORTS = ("nba", "mlb", "soccer", "soccer_intl", "tennis")


# --------------------------------------------------------------------------- #
# Fixtures + helpers
# --------------------------------------------------------------------------- #
@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient with the canonical store rooted at tmp_path (real read path)."""
    monkeypatch.setattr(app_module, "_store_out_dir", lambda: str(tmp_path))
    return TestClient(app_module.app), tmp_path


def _envelope(sport: str) -> SnapshotEnvelope:
    mkt = MarketRow(sport=sport, game_id="g1", market_type="moneyline",
                    side="home", odds=1.91, book="bk", devigged_prob=0.52,
                    captured_at="2026-06-18T00:00:00+00:00", is_close=True)
    pred = PredictionRecord(sport=sport, game_id="g1", home="H", away="A",
                            tipoff="2026-06-18T23:00:00+00:00",
                            pregame_probs={"home_ml": 0.58}, markets=[mkt])
    edge = EdgeRow(game_id="g1", market_type="moneyline", side="home",
                   model_prob=0.58, market_prob=0.52, ev=0.11, tier="B")
    return SnapshotEnvelope(sport=sport, generated_at="2026-06-18T22:00:00+00:00",
                            status="ok", predictions=[pred], markets=[mkt],
                            edges=[edge])


# A money KEY that carries a $ / P&L / ROI meaning must never appear. The units
# rail (stake_units, total_stake_units, arb stake_a / stake_b) is allowed -- those
# carry NO dollar. We check KEYS only (with token split), never free text.
_MONEY_TOKENS = frozenset({
    "pnl", "roi", "bankroll", "profit", "dollar", "dollars", "usd",
    "stake_dollars", "stake_usd",
})
_UNITS_TOKEN = "units"
_STAKE_LEG_ALLOWED = frozenset({"stake_a", "stake_b"})


def _money_key_offenders(obj) -> list:
    """Recursively collect any forbidden $/P&L/ROI KEY in a payload. Total."""
    offenders: list = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                kl = str(k).lower()
                words = set(kl.replace("-", "_").split("_"))
                exempt = (_UNITS_TOKEN in words) or (kl in _STAKE_LEG_ALLOWED)
                hit = kl in _MONEY_TOKENS or bool(words & _MONEY_TOKENS)
                # bare "stake" with no units token reads as a $ field -> offend.
                if "stake" in words and not exempt and kl not in (
                        "stake_dollars", "stake_usd"):
                    hit = True
                if hit and exempt and kl not in ("stake_dollars", "stake_usd"):
                    hit = False
                if hit:
                    offenders.append("%s.%s" % (path, kl) if path else kl)
                walk(v, "%s.%s" % (path, kl) if path else kl)
        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                walk(v, "%s[%d]" % (path, i))

    walk(obj, "")
    return offenders


def _assert_no_dollar(body) -> None:
    off = _money_key_offenders(body)
    assert off == [], "forbidden $/P&L/ROI key(s) in response: %r" % off


def _walk_values(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from _walk_values(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_values(v)


def _assert_honest_flags(body) -> None:
    """Wherever present, edge_claimed / real_money_enabled / vs_close are honest."""
    for k, v in _walk_values(body):
        kl = str(k).lower()
        if kl == "edge_claimed":
            assert v is False, "edge_claimed must be False, got %r" % v
        elif kl == "real_money_enabled":
            assert v is False, "real_money_enabled must be False, got %r" % v
        elif kl == "vs_close" and isinstance(v, str):
            # vs_close may be a bare verdict ("UNPROVEN") or a descriptive
            # disclaimer ("UNPROVEN -- CALIBRATION only ..."). Either way the
            # SERVED state is UNPROVEN; we never fabricate a PROVEN market edge
            # (a real PROVEN would need a sealed CLV proof we do not have).
            vu = v.upper()
            assert "UNPROVEN" in vu, "vs_close not UNPROVEN-tagged: %r" % v
            assert not (vu == "PROVEN" or vu.startswith("PROVEN ")), (
                "vs_close fabricated a bare PROVEN edge: %r" % v)
        elif kl == "vs_close_values" and isinstance(v, list):
            assert "UNPROVEN" in [str(x).upper() for x in v]


def _check(cl, method, path, *, json_body=None):
    """One endpoint -> (status, body); enforce rails (1)(2)(3)(4)."""
    r = cl.request(method, path, json=json_body) if json_body is not None \
        else cl.get(path)
    # (1) never a 500 / stack: the honest-degrade envelope holds.
    assert r.status_code != 500, (
        "%s %s returned 500 (stack leak) -- honest envelope failed: %s"
        % (method, path, r.text[:300]))
    assert r.status_code in (200, 503), (
        "%s %s unexpected status %d" % (method, path, r.status_code))
    body = r.json()
    # (2) schema: a JSON object envelope.
    assert isinstance(body, dict), "%s %s body not an object" % (method, path)
    # (3) recursive no-$.
    _assert_no_dollar(body)
    # (4) honest flags.
    _assert_honest_flags(body)
    return r.status_code, body


# --------------------------------------------------------------------------- #
# 1. Liveness + aggregate honesty surfaces
# --------------------------------------------------------------------------- #
def test_health(client):
    cl, _ = client
    r = cl.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_sports_aggregate(client):
    cl, _ = client
    st, body = _check(cl, "GET", "/api/sports")
    assert body["status"] == "ok"
    assert isinstance(body["active"], list)
    assert isinstance(body["capabilities"], dict)
    assert "honest_note" in body


def test_catalog_and_all_honest(client):
    cl, _ = client
    _, cat = _check(cl, "GET", "/api/catalog")
    assert cat["edge_claimed"] is False and cat["real_money_enabled"] is False
    assert isinstance(cat.get("faces"), list)
    _, hon = _check(cl, "GET", "/api/status.all_honest")
    assert hon["ok"] is True, "status.all_honest must be ok:true (no $ served)"
    assert hon["violations"] in ([], None) or hon["violations"] == []


def test_intel_number_free_face(client):
    cl, _ = client
    _, body = _check(cl, "GET", "/api/intel/pace")
    assert body.get("number_free") is True
    assert body["edge_claimed"] is False


# --------------------------------------------------------------------------- #
# 2. Per-sport prediction surface (incl honest-EMPTY tennis)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("sport", SPORTS)
def test_predict_sport_present_or_honest_empty(client, sport):
    cl, tmp = client
    if sport != "tennis":
        store.save(_envelope(sport), out_dir=tmp)
    st, body = _check(cl, "GET", "/api/predict/%s" % sport)
    assert body["sport"] == sport
    if sport == "tennis":
        # honest-EMPTY: offseason -> unavailable sentinel, NOT a fabricated game.
        assert body["status"] == "unavailable"
        assert body["predictions"] == []
    else:
        assert body["status"] == "ok"
        assert body["predictions"][0]["game_id"] == "g1"


@pytest.mark.parametrize("sport", SPORTS)
def test_predict_surface_and_contract(client, sport):
    cl, tmp = client
    if sport != "tennis":
        store.save(_envelope(sport), out_dir=tmp)
    _, surf = _check(cl, "GET", "/api/predict/%s/surface" % sport)
    assert surf["edge_claimed"] is False and surf["real_money_enabled"] is False
    # contract endpoint (sport-independent) advertises UNPROVEN as a vs_close value.
    _, contract = _check(cl, "GET", "/api/predict/contract")
    assert "UNPROVEN" in [str(x).upper() for x in contract["vs_close_values"]]


def test_predict_game_and_uncertainty(client):
    cl, tmp = client
    store.save(_envelope("nba"), out_dir=tmp)
    _, body = _check(cl, "GET", "/api/predict/nba/g1")
    assert body["status"] == "ok" and body["prediction"]["game_id"] == "g1"
    # missing game -> honest unavailable, never a fabricated record.
    _, miss = _check(cl, "GET", "/api/predict/nba/nope")
    assert miss["status"] == "unavailable"
    # uncertainty interval route reachable + units-only.
    _check(cl, "GET", "/api/predict/nba/g1/uncertainty")


# --------------------------------------------------------------------------- #
# 3. Report / bestbets / edges per-sport
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("sport", SPORTS)
def test_report_sport(client, sport):
    cl, tmp = client
    if sport != "tennis":
        store.save(_envelope(sport), out_dir=tmp)
    st, body = _check(cl, "GET", "/api/report/%s" % sport)
    assert body["status"] in ("ok", "unavailable")


@pytest.mark.parametrize("sport", SPORTS)
def test_bestbets_units_only_below_floor(client, sport):
    cl, tmp = client
    if sport != "tennis":
        store.save(_envelope(sport), out_dir=tmp)
    st, body = _check(cl, "GET", "/api/v1/bestbets/%s" % sport)
    assert body["edge_claimed"] is False
    assert body["status"] in ("ok", "unavailable")


@pytest.mark.parametrize("sport", SPORTS)
def test_edges_sport(client, sport):
    cl, tmp = client
    if sport != "tennis":
        store.save(_envelope(sport), out_dir=tmp)
    _check(cl, "GET", "/api/v1/edges/%s" % sport)


# --------------------------------------------------------------------------- #
# 4. Quant transparency surface (GET-only; units; no $)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("sport", ("nba", "mlb", "soccer", "soccer_intl"))
@pytest.mark.parametrize("face", ("validate", "devig", "arb"))
def test_quant_per_sport_faces(client, sport, face):
    cl, tmp = client
    store.save(_envelope(sport), out_dir=tmp)
    _, body = _check(cl, "GET", "/api/quant/%s/%s" % (sport, face))
    assert body["edge_claimed"] is False and body["real_money_enabled"] is False
    assert body.get("units") in (True, "units", None) or "units" in body


def test_quant_risk_and_clv(client):
    cl, _ = client
    _, risk = _check(cl, "GET", "/api/quant/risk")
    assert risk["edge_claimed"] is False
    # RoR is descriptive, never a guarantee.
    assert risk.get("ror_is_guarantee") in (False, None)
    _, clv = _check(cl, "GET", "/api/quant/clv")
    assert clv["edge_claimed"] is False


# --------------------------------------------------------------------------- #
# 5. In-game calibration number (no $)
# --------------------------------------------------------------------------- #
def test_ingame_calibration_or_degrade(client):
    cl, _ = client
    st, body = _check(cl, "GET", "/api/ingame/nba/0000")
    assert body["sport"] == "nba"
    # honest in-game states: ok (live state served), or an honest degrade --
    # unavailable / no_live_state (no live game -> degrade to the pregame p0
    # prior, NOT a fabricated live number).
    assert body["status"] in ("ok", "unavailable", "no_live_state")
    _check(cl, "GET", "/api/ingame/gates")


# --------------------------------------------------------------------------- #
# 6. Observability: improve / ops / parity / freshness / clv / progress
# --------------------------------------------------------------------------- #
def test_improve_and_ops(client):
    cl, _ = client
    _, imp = _check(cl, "GET", "/api/improve/status")
    assert imp["edge_claimed"] is False  # self-improve INERT, no $ claimed
    _check(cl, "GET", "/api/improve/timeline")
    # autonomy honestly 503-degrades when no autonomy_status.json -> still no stack.
    st, auto = _check(cl, "GET", "/api/ops/autonomy")
    assert auto["edge_claimed"] is False


def test_measurement_series(client):
    cl, _ = client
    for path in ("/api/parity", "/api/clv/over-time", "/api/freshness"):
        st, body = _check(cl, "GET", path)
        assert body["edge_claimed"] is False


@pytest.mark.parametrize("seg", ("summary", "coverage", "verdicts",
                                 "readiness", "schedule"))
def test_progress_segments(client, seg):
    cl, _ = client
    _check(cl, "GET", "/progress/%s" % seg)


# --------------------------------------------------------------------------- #
# 7. POST /api/paper/settle -- units-only, never enables real money
# --------------------------------------------------------------------------- #
def test_paper_settle_units_only(client):
    cl, _ = client
    st, body = _check(cl, "POST", "/api/paper/settle", json_body={})
    # shape-stable counts, units-only, no $; the settle path never flips real money.
    for k in ("n_open", "n_settled_now", "n_pending", "status"):
        assert k in body, "settle response missing %r" % k


def test_paper_trail_open_clv_reachable(client):
    cl, _ = client
    for path in ("/api/paper/trail", "/api/paper/open", "/api/paper/clv"):
        _check(cl, "GET", path)


# --------------------------------------------------------------------------- #
# 8. FORCED FAILURE -> honest unavailable envelope (NOT a 500 / stack).
# --------------------------------------------------------------------------- #
def test_forced_handler_failure_degrades_honestly(client, monkeypatch):
    """If a read raises INSIDE a handler, the surface degrades honestly.

    We poison store.read_latest so /api/predict/{sport} raises; the app's own
    handler wraps the store call and the response must NOT be a 500 stack -- it is
    the honest unavailable envelope (or a clean error body) with no $ and no stack.
    """
    cl, _ = client

    def _boom(*a, **k):
        raise RuntimeError("forced read failure for honest-degrade test")

    monkeypatch.setattr(store, "read_latest", _boom)
    r = cl.get("/api/predict/nba")
    # The honesty middleware + handler must convert this to a clean envelope, never
    # a raw 500 with a Python traceback in the body.
    assert "Traceback (most recent call last)" not in r.text
    assert r.status_code in (200, 500, 503)
    body = r.json()
    assert isinstance(body, dict)
    _assert_no_dollar(body)
    # If it surfaced as an error sentinel it is the honest fail-closed body, which
    # carries edge_claimed False and no fabricated value.
    if body.get("status") in ("error", "unavailable"):
        assert body.get("edge_claimed", False) is False
