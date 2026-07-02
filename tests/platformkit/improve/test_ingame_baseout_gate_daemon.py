"""Tests for the in-game base-out trigger daemon (loop + isolation, injected gate)."""
from __future__ import annotations

from scripts.platformkit.improve import ingame_baseout_gate_daemon as D


def test_sweep_isolates_failures():
    def boom(sport):
        raise RuntimeError("nope")
    out = D.sweep(("mlb", "soccer_intl"), gate_fn=boom)
    assert out["mlb"]["verdict"] == "ERROR"
    assert out["soccer_intl"]["verdict"] == "ERROR"


def test_run_honors_max_ticks_and_calls_gate():
    calls = []

    def fake_gate(sport):
        calls.append(sport)
        return {"sport": sport, "verdict": "INSUFFICIENT"}

    n = D.run(interval_sec=0.0, sports=("mlb",), gate_fn=fake_gate,
              sleep=lambda _s: None, max_ticks=3)
    assert n == 3
    assert calls == ["mlb", "mlb", "mlb"]


def test_run_stops_on_should_stop():
    n = D.run(interval_sec=0.0, gate_fn=lambda s: {"sport": s, "verdict": "REJECT"},
              sleep=lambda _s: None, should_stop=lambda: True, max_ticks=99)
    assert n == 0
