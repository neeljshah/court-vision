"""Per-file tests for ingame_tail_gate (injected scans; no real data).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_tail_gate.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import ingame_tail_gate as tg


def _band(verdict: str) -> dict:
    return {"n_ticks": 500, "n_games": 20, "mean_market": 0.15, "realized_rate": 0.25,
            "venue_gap": 0.10, "venue_verdict": verdict, "model_verdict": "MATCH",
            "delta_brier": -0.01}


def _scan_fn(fwd_h1: str, fwd_h2: str):
    def fake(since=None, **kw):
        if since is None:
            return {"n_games_resolved": 95, "bands": {
                "[0.10,0.20)": _band("CALIBRATED"), "[0.65,0.80)": _band("VENUE_OVERPRICES")}}
        return {"n_games_resolved": 30, "bands": {
            "[0.10,0.20)": _band(fwd_h1), "[0.65,0.80)": _band(fwd_h2)}}
    return fake


def test_confirmed_forward_promotes_ship_review(tmp_path):
    out = tmp_path / "v.json"
    h = tg.run_gate(scan_fn=_scan_fn("VENUE_UNDERPRICES", "CALIBRATED"), verdict_out=out)
    assert h["verdict"] == "SHIP_REVIEW"
    assert h["name"] == "ingame_tail_bands"
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["edge_claimed"] is False
    ids = {r["id"]: r["forward_verdict"] for r in doc["hypotheses"]}
    assert ids["H1_longshot_underpriced"] == "CONFIRMED_FORWARD"
    assert ids["H2_midfav_overpriced"] == "PENDING_FORWARD"


def test_all_rejected_forward(tmp_path):
    h = tg.run_gate(scan_fn=_scan_fn("VENUE_OVERPRICES", "VENUE_UNDERPRICES"),
                    verdict_out=tmp_path / "v.json")
    assert h["verdict"] == "REJECT"


def test_insufficient_forward_pends(tmp_path):
    h = tg.run_gate(scan_fn=_scan_fn("INSUFFICIENT_DATA", "INSUFFICIENT_DATA"),
                    verdict_out=tmp_path / "v.json")
    assert h["verdict"] == "PENDING_FORWARD"
    assert "INSUFFICIENT_FORWARD" in h["verdict_reason"]


def test_missing_forward_band_is_insufficient(tmp_path):
    def fake(since=None, **kw):
        return {"n_games_resolved": 0, "bands": {}}
    h = tg.run_gate(scan_fn=fake, verdict_out=tmp_path / "v.json")
    assert h["verdict"] == "PENDING_FORWARD"
    assert h["n"] == 0


def test_registration_constants_pinned():
    assert tg.REGISTERED_AT == "2026-07-03T00:00:00Z"
    bands = {h["band"] for h in tg.HYPOTHESES}
    assert bands == {"[0.10,0.20)", "[0.65,0.80)"}
