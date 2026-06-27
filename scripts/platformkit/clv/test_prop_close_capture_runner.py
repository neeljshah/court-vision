"""Per-file test for scripts.platformkit.clv.prop_close_capture_runner.

Focus: the M16 capture arm writes a fresh $-free status + advances its heartbeat
on EVERY tick (even when the sweep captures nothing or raises), never fabricates,
and the run loop honors max_ticks / should_stop -- all offline via an injected
capture_fn (no network, no real store touched).

Run: cd /c/Users/neelj/nba-ai-system && \
     python -m pytest scripts/platformkit/clv/test_prop_close_capture_runner.py -q
"""
from __future__ import annotations

import json

import scripts.platformkit.clv.prop_close_capture_runner as runner


def _sweep(captured=4, open_props=10, no_live=6):
    return {
        "captured": captured,
        "by_sport": {"mlb": {"sport": "mlb", "open_props": open_props,
                             "captured": captured, "no_live_price": no_live}},
    }


def test_tick_writes_status_and_beats(monkeypatch, tmp_path):
    status_p = tmp_path / "prop_close_capture_status.json"
    beats = []
    monkeypatch.setattr(runner, "_beat", lambda now=None: beats.append(now))
    doc = runner.tick(now=999.0, capture_fn=lambda sp: _sweep(),
                      status_path=status_p)
    assert doc["captured"] == 4
    assert doc["open_props"] == 10 and doc["no_live_price"] == 6
    assert doc["executed"] is False and doc["edge_claimed"] is False
    assert beats == [999.0]                       # heartbeat advanced
    on_disk = json.loads(status_p.read_text(encoding="ascii"))
    assert on_disk["component"] == "m16_prop_close_capture"


def test_status_is_dollar_free(monkeypatch, tmp_path):
    status_p = tmp_path / "s.json"
    monkeypatch.setattr(runner, "_beat", lambda now=None: None)
    runner.tick(now=1.0, capture_fn=lambda sp: _sweep(), status_path=status_p)
    doc = json.loads(status_p.read_text(encoding="ascii"))
    doc.pop("honest_note", None)   # the disclaimer legitimately says "no $ field"
    raw = json.dumps(doc).lower()
    for banned in ("$", "roi", "pnl", "dollar", "usd"):
        assert banned not in raw, "status leaked a money token: %r" % banned


def test_tick_never_raises_when_sweep_raises(monkeypatch, tmp_path):
    status_p = tmp_path / "s.json"
    beats = []
    monkeypatch.setattr(runner, "_beat", lambda now=None: beats.append(now))

    def _boom(sp):
        raise RuntimeError("draftkings 403")

    doc = runner.tick(now=42.0, capture_fn=_boom, status_path=status_p)
    assert doc["captured"] == 0                # degraded, not fabricated
    assert beats == [42.0]                       # heartbeat STILL advances


def test_tick_passes_sports_through(monkeypatch, tmp_path):
    status_p = tmp_path / "s.json"
    monkeypatch.setattr(runner, "_beat", lambda now=None: None)
    seen = {}

    def _cap(sports):
        seen["sports"] = list(sports)
        return _sweep()

    runner.tick(now=1.0, sports=("mlb", "soccer"), capture_fn=_cap,
                status_path=status_p)
    assert seen["sports"] == ["mlb", "soccer"]


def test_run_honors_max_ticks(monkeypatch, tmp_path):
    status_p = tmp_path / "s.json"
    monkeypatch.setattr(runner, "_beat", lambda now=None: None)
    calls = {"n": 0}

    def _cap(sp):
        calls["n"] += 1
        return _sweep(captured=0)

    ticks = runner.run(capture_fn=_cap, status_path=status_p, interval_sec=0.0,
                       clock=lambda: 7.0, sleep=lambda s: None, max_ticks=3)
    assert ticks == 3 and calls["n"] == 3


def test_run_honors_should_stop(monkeypatch, tmp_path):
    status_p = tmp_path / "s.json"
    monkeypatch.setattr(runner, "_beat", lambda now=None: None)
    ticks = runner.run(capture_fn=lambda sp: _sweep(), status_path=status_p,
                       interval_sec=0.0, clock=lambda: 1.0, sleep=lambda s: None,
                       should_stop=lambda: True, max_ticks=10)
    assert ticks == 0                           # stopped before first tick
