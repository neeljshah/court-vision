"""Per-file test: frontend routers AS MOUNTED in the canonical predict_service.app.

The per-router tests (test_quant_routes, test_bestbets, test_paper_routes, ...)
each mount ONE router on a throwaway app. This test closes the integration gap:
it drives the frontend-origin endpoints through the REAL predict_service.app --
i.e. WITH the runtime honesty-linter middleware, the CORS layer, and the mount
guards all active together -- and asserts the units-only rail holds end to end:

  * never a 500 / stack: every endpoint is 200 or an honest 503 degrade;
  * recursive NO-$: no $/P&L/ROI/dollar money KEY anywhere in the payload
    (the units rail stake_units / arb stake_a|b is allowed -- it carries no $);
  * honest flags: edge_claimed False, real_money_enabled False wherever present;
  * the all_honest bit is True (the single honesty bit the middleware backs);
  * POST /api/paper/settle is units-only and never enables real money.

This proves the frontend routers stay honest under the SAME middleware stack the
:8099 service serves, not just on a bare app.

Run: python -m pytest tests/frontend/test_mounted_in_predict_service_contract.py -q
"""
from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from predict_service import app as app_module  # noqa: E402
from predict_service import store  # noqa: E402
from predict_service.contracts import (  # noqa: E402
    EdgeRow,
    MarketRow,
    PredictionRecord,
    SnapshotEnvelope,
)

# Frontend-origin endpoints mounted into predict_service.app (catalog/intel/quant/
# bestbets/edges/paper/ops/improve/autonomy). game_id-free forms only.
_GET_ENDPOINTS = (
    "/api/catalog",
    "/api/status.all_honest",
    "/api/intel/pace",
    "/api/v1/bestbets/nba",
    "/api/v1/edges/nba",
    "/api/quant/nba/validate",
    "/api/quant/nba/devig",
    "/api/quant/nba/arb",
    "/api/quant/risk",
    "/api/quant/clv",
    "/api/paper/trail",
    "/api/paper/open",
    "/api/paper/clv",
    "/api/improve/status",
    "/api/improve/timeline",
    "/api/ops/autonomy",
)

_MONEY_TOKENS = frozenset({
    "pnl", "roi", "bankroll", "profit", "dollar", "dollars", "usd",
    "stake_dollars", "stake_usd",
})


def _money_offenders(obj, path=""):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            words = set(kl.replace("-", "_").split("_"))
            exempt = ("units" in words) or kl in ("stake_a", "stake_b")
            hit = kl in _MONEY_TOKENS or bool(words & _MONEY_TOKENS)
            if "stake" in words and not exempt and kl not in (
                    "stake_dollars", "stake_usd"):
                hit = True
            if hit and exempt and kl not in ("stake_dollars", "stake_usd"):
                hit = False
            if hit:
                out.append(("%s.%s" % (path, kl)).lstrip("."))
            out += _money_offenders(v, "%s.%s" % (path, kl))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            out += _money_offenders(v, "%s[%d]" % (path, i))
    return out


def _walk(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk(v)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "_store_out_dir", lambda: str(tmp_path))
    # Seed an nba snapshot so the bestbets/quant/edges faces have a real envelope.
    mkt = MarketRow(sport="nba", game_id="g1", market_type="moneyline",
                    side="home", odds=1.91, book="bk", devigged_prob=0.52,
                    captured_at="2026-06-18T00:00:00+00:00", is_close=True)
    pred = PredictionRecord(sport="nba", game_id="g1", home="H", away="A",
                            tipoff="2026-06-18T23:00:00+00:00",
                            pregame_probs={"home_ml": 0.58}, markets=[mkt])
    edge = EdgeRow(game_id="g1", market_type="moneyline", side="home",
                   model_prob=0.58, market_prob=0.52, ev=0.11, tier="B")
    env = SnapshotEnvelope(sport="nba", generated_at="2026-06-18T22:00:00+00:00",
                           status="ok", predictions=[pred], markets=[mkt],
                           edges=[edge])
    store.save(env, out_dir=tmp_path)
    return TestClient(app_module.app)


@pytest.mark.parametrize("path", _GET_ENDPOINTS)
def test_endpoint_units_only_and_no_stack(client, path):
    r = client.get(path)
    assert r.status_code != 500, "%s leaked a 500: %s" % (path, r.text[:200])
    assert r.status_code in (200, 503), "%s status %d" % (path, r.status_code)
    body = r.json()
    assert isinstance(body, dict)
    off = _money_offenders(body)
    assert off == [], "%s has $/P&L/ROI key(s): %r" % (path, off)
    for k, v in _walk(body):
        kl = str(k).lower()
        if kl == "edge_claimed":
            assert v is False, "%s edge_claimed must be False" % path
        elif kl == "real_money_enabled":
            assert v is False, "%s real_money_enabled must be False" % path


def test_all_honest_bit_true_under_middleware(client):
    r = client.get("/api/status.all_honest")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True, "the single honesty bit flipped: %r" % body
    assert body.get("violations") in ([], None)


def test_paper_settle_units_only_no_real_money(client):
    r = client.post("/api/paper/settle", json={})
    assert r.status_code in (200, 503)
    body = r.json()
    assert _money_offenders(body) == []
    for k in ("n_open", "n_settled_now", "n_pending", "status"):
        assert k in body
