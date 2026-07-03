"""Per-file tests for ingame_tail_multi_runner (injected fns, no real I/O).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_tail_multi_runner.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import ingame_tail_multi_runner as runner


def test_tick_composes_all_three_steps(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_SUMMARY_OUT", tmp_path / "summary.json")
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)

    scan_calls = []
    gate_calls = []
    latency_calls = []

    def scan_fn():
        scan_calls.append(1)
        return {"tennis": {"sport_verdict": "INSUFFICIENT_N", "n_games_graded": 0}}

    def gate_fn():
        gate_calls.append(1)
        return [{"sport": "tennis", "verdict": "PENDING_FORWARD", "verdict_reason": "n=0"}]

    def latency_fn():
        latency_calls.append(1)
        return {"overall_verdict": "INSUFFICIENT_DATA", "by_sport": {"tennis": {}}}

    doc = runner.tick(now=1000.0, scan_fn=scan_fn, gate_fn=gate_fn, latency_fn=latency_fn)
    assert scan_calls and gate_calls and latency_calls
    assert doc["component"] == "ingame_tail_multi"
    assert doc["edge_claimed"] is False
    assert doc["ship_review"] == []
    written = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert written["scan_summary"]["tennis"]["sport_verdict"] == "INSUFFICIENT_N"


def test_tick_ship_review_roster_populated(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_SUMMARY_OUT", tmp_path / "summary.json")
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)
    doc = runner.tick(
        now=1000.0,
        scan_fn=lambda: {},
        gate_fn=lambda: [{"sport": "soccer_intl", "verdict": "SHIP_REVIEW",
                          "verdict_reason": "H1 confirmed"}],
        latency_fn=lambda: {"overall_verdict": "GREEN", "by_sport": {}},
    )
    assert doc["ship_review"] == ["soccer_intl"]


def test_tick_never_raises_when_a_step_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_SUMMARY_OUT", tmp_path / "summary.json")
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)

    def _boom():
        raise RuntimeError("scan exploded")

    doc = runner.tick(
        now=1000.0, scan_fn=_boom,
        gate_fn=lambda: [{"sport": "tennis", "verdict": "PENDING_FORWARD"}],
        latency_fn=lambda: {"overall_verdict": "GREEN", "by_sport": {}},
    )
    assert "error" in doc["scan_summary"]
    assert doc["gate_headlines"][0]["sport"] == "tennis"


def test_run_stops_after_max_ticks(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_SUMMARY_OUT", tmp_path / "summary.json")
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)
    monkeypatch.setattr(runner, "tick", lambda **kw: {"ship_review": []})
    ticks = runner.run(max_ticks=3, clock=lambda: 1.0, sleep=lambda s: None)
    assert ticks == 3


def test_heartbeat_component_name_matches_registered_spec():
    assert runner.HEARTBEAT_COMPONENT == "m35_ingame_tail_multi"
