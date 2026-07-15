"""Tests for the bridge/slate/machine Proof Room builders.

Runs against the real repo data read-only (per SPEC, this is acceptable when
practical) plus a couple of monkeypatched missing-source cases.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.platformkit.showcase.rooms import bridge, machine, slate


def _is_unavailable(d: dict) -> bool:
    return d.get("status") == "unavailable"


def test_bridge_build_shape():
    result = bridge.build()
    if _is_unavailable(result):
        assert "reason" in result
        return
    assert set(result.keys()) >= {"heartbeat", "funnel", "heroes"}
    hb = result["heartbeat"]
    assert "daemons_ready" in hb and "daemons_total" in hb and "last_tick_utc" in hb
    assert isinstance(result["funnel"], list)
    for stage in result["funnel"]:
        assert {"stage", "count", "unit", "receipt"} <= stage.keys()
        assert "label" in stage["receipt"] and "claim" in stage["receipt"]
    assert len(result["heroes"]) == 3
    for hero in result["heroes"]:
        assert {"claim", "value", "label", "artifact", "asof"} <= hero.keys()


def test_bridge_unavailable_when_no_sources(monkeypatch, tmp_path):
    fake_frontend = tmp_path / "frontend"
    fake_frontend.mkdir()
    monkeypatch.setattr(bridge, "FRONTEND", fake_frontend)
    monkeypatch.setattr(bridge, "BOT_STATE", tmp_path / "nope.json")
    monkeypatch.setattr(bridge, "CALIBRATION", fake_frontend / "ops" / "calibration_scoreboard_latest.json")
    result = bridge.build()
    assert _is_unavailable(result)


def test_slate_build_shape():
    result = slate.build()
    if _is_unavailable(result):
        assert "reason" in result
        return
    assert set(result.keys()) >= {"slates", "graded_yesterday", "paper_day"}
    assert isinstance(result["slates"], list)
    for card in result["slates"]:
        assert "delta_vs_market" in card
        assert "edge_vs_market" not in card


def test_slate_maps_edge_to_delta(monkeypatch, tmp_path):
    fake = tmp_path / "best_bets.json"
    fake.write_text(json.dumps({"cards": [{
        "game_id": "g1", "sport": "mlb", "matchup": "A vs B",
        "market_type": "moneyline", "side": "home", "model_prob": 0.55,
        "market_prob": 0.5, "best_book": "kalshi", "edge_vs_market": 0.05,
        "confidence": 0.5, "tier": "A", "decision": "bet", "clv": {},
        "honest_note": "n/a", "tipoff_utc": None,
    }]}), encoding="utf-8")
    monkeypatch.setattr(slate, "BEST_BETS", fake)
    monkeypatch.setattr(slate, "GRADE_SUMMARY", tmp_path / "missing_grade.json")
    monkeypatch.setattr(slate, "PAPER_TODAY", tmp_path / "missing_paper.json")
    result = slate.build()
    assert result["slates"][0]["delta_vs_market"] == 0.05
    assert "edge_vs_market" not in result["slates"][0]
    assert result["graded_yesterday"] == {"note": "grade_summary.json missing"}
    assert result["paper_day"] == {"note": "paper_today.json missing"}


def test_slate_unavailable_when_best_bets_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(slate, "BEST_BETS", tmp_path / "nope.json")
    result = slate.build()
    assert _is_unavailable(result)


def test_machine_build_shape():
    result = machine.build()
    if _is_unavailable(result):
        assert "reason" in result
        return
    assert set(result.keys()) >= {"daemons", "build", "loop"}
    assert isinstance(result["daemons"], list)
    assert "commits" in result["build"] and "model_roles" in result["build"]
    assert "recent_verdicts" in result["loop"]
    assert len(result["loop"]["recent_verdicts"]) <= 10
    for v in result["loop"]["recent_verdicts"]:
        assert set(v.keys()) == {"ts", "sport", "signal", "verdict", "reason"}


def test_machine_unavailable_when_no_sources(monkeypatch, tmp_path):
    monkeypatch.setattr(machine, "AUTONOMY", tmp_path / "nope.json")
    monkeypatch.setattr(machine, "FRONTEND", tmp_path / "frontend_empty")
    monkeypatch.setattr(machine, "REJECT_LEDGER", tmp_path / "no_ledger.jsonl")
    result = machine.build()
    assert _is_unavailable(result)
