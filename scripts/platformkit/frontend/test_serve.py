"""Per-file tests for scripts.platformkit.frontend.serve + slate.

Stubs the predictor entirely so NO live corpus is required. Verifies /health, the
slate-shaping logic (ok / unavailable / unknown-sport paths), the honest verdict
derivation, and that the intent log writes a non-binding paper record.

Run (per-file ONLY -- full pytest freezes this box):
  cd /c/Users/neelj/nba-ai-system && \
    python -m pytest scripts/platformkit/frontend/test_serve.py -q
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from scripts.platformkit.frontend import serve as serve_mod
from scripts.platformkit.frontend import slate as slate_mod


class _StubPredictor:
    """A minimal stand-in for a domain predictor: only .predict() is exercised by
    predict_matchup.build_result for a pregame-only Namespace."""

    def __init__(self, p_home=0.62, note="Moneyline matches the devigged close."):
        self._p = p_home
        self._note = note

    def predict(self, home, away, **kwargs):  # noqa: ANN001
        return {"p_home_win": self._p, "total_mean": 221.5, "margin_home": 3.2,
                "honest_note": self._note}


def _stub_factory_ok(sport):  # noqa: ANN001
    return _StubPredictor()


def _stub_factory_none(sport):  # noqa: ANN001
    return None


def test_health():
    client = TestClient(serve_mod.create_app())
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_slate_ok_shape():
    payload = slate_mod.build_slate(
        "nba",
        matchups=[{"home": "BOS", "away": "LAL"}],
        predictor_factory=_stub_factory_ok,
    )
    assert payload["status"] == "ok"
    assert payload["predictor_available"] is True
    assert len(payload["rows"]) == 1
    row = payload["rows"][0]
    assert row["matchup"] == "BOS vs LAL"
    assert row["status"] == "ok"
    assert row["verdict"] == "MATCH"  # derived from the honest_note text
    assert "P(home)=62.0%" in row["model"]
    assert "NO $ edge" in payload["honest_note"]


def test_slate_market_edge_and_behind_verdict():
    def market_lookup(sport, home, away):  # noqa: ANN001
        return {"line": "BOS -3.5 (-110)", "p_home_implied": 0.55}

    payload = slate_mod.build_slate(
        "nba",
        matchups=[{"home": "BOS", "away": "LAL"}],
        predictor_factory=lambda s: _StubPredictor(
            p_home=0.62, note="totals model is ~1 RMSE behind the close"),
        market_lookup=market_lookup,
    )
    row = payload["rows"][0]
    assert row["market"] == "BOS -3.5 (-110)"
    assert abs(row["edge"] - (0.62 - 0.55)) < 1e-9  # 0.62 model - 0.55 market
    assert row["verdict"] == "BEHIND"


def test_slate_unavailable_is_honest():
    payload = slate_mod.build_slate(
        "nba",
        matchups=[{"home": "BOS", "away": "LAL"}],
        predictor_factory=_stub_factory_none,
    )
    assert payload["status"] == "unavailable"
    assert payload["predictor_available"] is False
    row = payload["rows"][0]
    assert row["status"] == "unavailable"
    assert row["model"] is None          # never fabricates a number
    assert row["verdict"] == "UNAVAILABLE"


def test_unknown_sport():
    payload = slate_mod.build_slate("cricket", predictor_factory=_stub_factory_ok)
    assert payload["status"] == "unknown_sport"
    assert payload["rows"] == []


def test_intent_log_is_paper_only(tmp_path):
    log = tmp_path / "intents.jsonl"
    app = serve_mod.create_app(intent_log=log)
    client = TestClient(app)
    r = client.post("/api/intent", json={"sport": "nba", "matchup": "BOS vs LAL",
                                          "edge": 0.07})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "logged"
    assert body["record"]["executed"] is False           # invariant: never a real bet
    assert body["record"]["channel"] == "manual_human"
    # the record is on disk as one JSONL line
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["matchup"] == "BOS vs LAL"
    assert rec["executed"] is False


def test_slate_endpoint_uses_real_factory_gracefully():
    # The live endpoint uses the REAL factory; on a fresh clone it degrades to
    # status in {ok, unavailable} but must never 500.
    client = TestClient(serve_mod.create_app())
    r = client.get("/api/slate?sport=nba")
    assert r.status_code == 200
    payload = r.json()
    assert payload["status"] in {"ok", "unavailable"}
    assert "honest_note" in payload


# ---------------------------------------------------------------------------
# m13-breaker-bypass (bare-caller close-out, wave-36): /api/props' live-compute
# fallback used to call build_prop_board(sport) BARE, which re-derives
# cfg.default_providers() UN-GATED inside prop_edge.py -- re-dispatching to a
# provider the circuit breaker just opened. The fix routes it through the SAME
# breaker_filtered_providers() helper the wave-35 prop_cards.py fix uses.
# ---------------------------------------------------------------------------

def test_api_props_live_compute_uses_breaker_filtered_providers(monkeypatch):
    calls = []

    def fake_board(sport, **kw):  # noqa: ANN001
        calls.append((sport, kw))
        return {"sport": sport, "status": "ok", "edges": []}
    monkeypatch.setattr(serve_mod, "_build_prop_board", fake_board)
    monkeypatch.setattr(serve_mod, "_read_snapshot_part", lambda sport, part: None)

    class _FakeProvider:
        name = "fake_survivor"

    filtered_calls = []

    def fake_breaker_filtered(sport):  # noqa: ANN001
        filtered_calls.append(sport)
        return [_FakeProvider()]

    import scripts.platformkit.bestbets.prop_cards_circuit_io as pcio
    monkeypatch.setattr(pcio, "breaker_filtered_providers", fake_breaker_filtered)

    client = TestClient(serve_mod.create_app())
    r = client.get("/api/props?sport=mlb")
    assert r.status_code == 200
    assert filtered_calls == ["mlb"]
    assert len(calls) == 1
    sport_arg, kwargs = calls[0]
    assert sport_arg == "mlb"
    assert [getattr(p, "name", None) for p in kwargs.get("providers", [])] == ["fake_survivor"]


def test_api_props_never_calls_bare_unfiltered_providers(monkeypatch):
    # Even if the breaker helper is unavailable (returns None), the fallback must
    # pass an explicit EMPTY providers list -- never omit providers / let
    # build_prop_board fall back to cfg.default_providers() un-gated.
    calls = []

    def fake_board(sport, **kw):  # noqa: ANN001
        calls.append((sport, kw))
        return {"sport": sport, "status": "ok", "edges": []}
    monkeypatch.setattr(serve_mod, "_build_prop_board", fake_board)
    monkeypatch.setattr(serve_mod, "_read_snapshot_part", lambda sport, part: None)

    import scripts.platformkit.bestbets.prop_cards_circuit_io as pcio
    monkeypatch.setattr(pcio, "breaker_filtered_providers", lambda sport: None)

    client = TestClient(serve_mod.create_app())
    r = client.get("/api/props?sport=mlb")
    assert r.status_code == 200
    assert len(calls) == 1
    _, kwargs = calls[0]
    assert kwargs.get("providers") == []


def _fake_ps_env(generated_at, sport="mlb"):
    from datetime import datetime, timezone  # noqa: PLC0415
    from predict_service.contracts import PredictionRecord, SnapshotEnvelope  # noqa: PLC0415
    return SnapshotEnvelope(
        sport=sport,
        generated_at=generated_at,
        status="ok",
        predictions=[PredictionRecord(sport=sport, game_id="g1", home="NYY", away="BOS")],
    )


class _FakePsStore:
    def __init__(self, env):
        self._env = env

    def read_latest(self, sport):  # noqa: ANN001
        return self._env


def test_read_ps_store_slate_fresh_envelope_is_served(monkeypatch):
    from datetime import datetime, timezone  # noqa: PLC0415
    fresh = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(serve_mod, "_ps_store", _FakePsStore(_fake_ps_env(fresh)))
    out = serve_mod._read_ps_store_slate("mlb")
    assert out is not None
    assert out["served_from"] == "predict_service_store"


def test_read_ps_store_slate_stale_envelope_is_a_miss(monkeypatch):
    # golive_hardening_backlog #13: a stalled producer's hours-old envelope must
    # degrade to a cache miss (fall back to live compute), not serve as status='ok'.
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415
    stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    monkeypatch.setattr(serve_mod, "_ps_store", _FakePsStore(_fake_ps_env(stale)))
    assert serve_mod._read_ps_store_slate("mlb") is None
