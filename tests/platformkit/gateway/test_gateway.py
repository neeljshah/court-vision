"""Per-file test: scripts.platformkit.gateway.gateway + catalog (WAVE 4).

Covers:
  * FACES registry lists all four faces (prediction/execution/lines/intelligence)
  * wrap() stamps units/edge_claimed/real_money_enabled/face/face_version/freshness
  * wrap() with a STALE sport_dir -> serveable=False (never green-on-stale)
  * wrap() with no sport_dir -> freshness not_applicable, serveable=True
  * catalog() lists every face + the standing rails
  * all_honest() is True now (declared rails clean)
  * all_honest() flips False under an injected $ key / real-money / stale-green /
    edge-claimed / retracted-number probe body

Run: python -m pytest tests/platformkit/gateway/test_gateway.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone

from scripts.platformkit.gateway.gateway import FACES, list_faces, wrap
from scripts.platformkit.gateway.catalog import all_honest, catalog


def test_faces_registry_lists_all_four_faces():
    assert set(FACES) == {"prediction", "execution", "lines", "intelligence"}
    rows = list_faces()
    assert len(rows) == 4
    for r in rows:
        assert r["units"] == "probability"
        assert r["edge_claimed"] is False
        assert r["real_money_enabled"] is False
        assert r["face"] and r["version"] and r["routes"]


def test_wrap_stamps_honest_flags():
    out = wrap({"status": "ok"}, face="prediction")
    assert out["units"] == "probability"
    assert out["edge_claimed"] is False
    assert out["real_money_enabled"] is False
    assert out["face"] == "prediction"
    assert out["face_version"] == FACES["prediction"].version
    assert "freshness" in out


def test_wrap_no_sport_dir_is_serveable():
    out = wrap({"status": "ok"}, face="intelligence")
    assert out["freshness"]["status"] == "not_applicable"
    assert out["freshness"]["serveable"] is True
    assert out["serveable"] is True


def test_wrap_stale_feed_never_green(tmp_path):
    # A missing _freshness.json sidecar -> sidecar_status status='missing', ok=False.
    out = wrap({"status": "ok"}, face="lines", sport_dir=str(tmp_path))
    assert out["freshness"]["serveable"] is False
    assert out["serveable"] is False


def test_wrap_fresh_sidecar_serveable(tmp_path):
    import json
    now = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)
    (tmp_path / "_freshness.json").write_text(
        json.dumps({"source_as_of": now.isoformat()}), encoding="utf-8")
    out = wrap({"status": "ok"}, face="lines", sport_dir=str(tmp_path), now=now)
    assert out["freshness"]["status"] == "fresh"
    assert out["freshness"]["serveable"] is True
    assert out["serveable"] is True


def test_catalog_lists_all_faces():
    cat = catalog()
    assert cat["status"] == "ok"
    assert cat["count"] == 4
    assert {f["face"] for f in cat["faces"]} == {
        "prediction", "execution", "lines", "intelligence"}
    assert cat["edge_claimed"] is False
    assert cat["real_money_enabled"] is False


def test_all_honest_true_now():
    v = all_honest()
    assert v["ok"] is True
    assert v["violations"] == []
    assert v["n_faces"] == 4


def test_all_honest_flips_false_on_money_key():
    v = all_honest(probe=[{"status": "ok", "total_pnl": 12.0}])
    assert v["ok"] is False
    assert any("$/P&L/ROI" in x["reason"] for x in v["violations"])


def test_all_honest_flips_false_on_real_money():
    v = all_honest(probe=[{"status": "ok", "real_money_enabled": True}])
    assert v["ok"] is False
    assert any("real money" in x["reason"] for x in v["violations"])


def test_all_honest_flips_false_on_edge_claimed():
    v = all_honest(probe=[{"status": "ok", "edge_claimed": True}])
    assert v["ok"] is False


def test_all_honest_flips_false_on_stale_green():
    body = {"status": "ok", "serveable": True,
            "freshness": {"serveable": False, "status": "stale"}}
    v = all_honest(probe=[body])
    assert v["ok"] is False
    assert any("stale" in x["reason"] for x in v["violations"])


def test_all_honest_flips_false_on_retracted_number():
    v = all_honest(probe=[{"status": "ok", "headline": 18.38}])
    assert v["ok"] is False
    assert any("retracted" in x["reason"] for x in v["violations"])
