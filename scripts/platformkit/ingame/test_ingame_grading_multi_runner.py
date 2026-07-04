"""Per-file tests for ingame_grading_multi_runner (injected fns, no real I/O).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_grading_multi_runner.py -q
"""
from __future__ import annotations

from scripts.platformkit.ingame import ingame_grading_multi_runner as runner


def test_tick_composes_both_steps(monkeypatch):
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)

    verdict_calls = []
    trust_calls = []

    def verdict_fn():
        verdict_calls.append(1)
        return {"tennis": {"n_labeled": 0, "better_segments": [], "worse_segments": []}}

    def trust_fn():
        trust_calls.append(1)
        return {"tennis": {"trusted": [], "adverse": []}}

    doc = runner.tick(now=1000.0, verdict_fn=verdict_fn, trust_fn=trust_fn)
    assert verdict_calls and trust_calls
    assert doc["component"] == "ingame_grading_multi"
    assert doc["edge_claimed"] is False
    assert doc["measurement_only"] is True
    assert doc["verdict_summary"]["tennis"]["n_labeled"] == 0


def test_tick_never_raises_when_a_step_fails(monkeypatch):
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)

    def _boom():
        raise RuntimeError("verdict exploded")

    doc = runner.tick(
        now=1000.0, verdict_fn=_boom,
        trust_fn=lambda: {"wnba": {"trusted": [], "adverse": []}},
    )
    assert "error" in doc["verdict_summary"]
    assert doc["trust_summary"]["wnba"]["trusted"] == []


def test_run_stops_after_max_ticks(monkeypatch):
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)
    monkeypatch.setattr(runner, "tick", lambda **kw: {"verdict_summary": {}, "trust_summary": {}})
    ticks = runner.run(max_ticks=3, clock=lambda: 1.0, sleep=lambda s: None)
    assert ticks == 3


def test_heartbeat_component_name_matches_registered_spec():
    assert runner.HEARTBEAT_COMPONENT == "m36_ingame_grading_multi"


def test_default_interval_matches_m25_cadence():
    assert runner.DEFAULT_INTERVAL_SEC == 900.0
