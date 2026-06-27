"""Per-file test for scripts.platformkit.bestbets.prop_settle_runner.

Focus: the M15 settle arm writes a fresh $-free status + advances its heartbeat
on EVERY tick (even when the sweep settles nothing or raises), never fabricates,
and the run loop honors max_ticks / should_stop -- all offline via an injected
settle_fn (no network, no real ledger touched).

Run: cd /c/Users/neelj/nba-ai-system && \
     python -m pytest scripts/platformkit/bestbets/test_prop_settle_runner.py -q
"""
from __future__ import annotations

import json

import scripts.platformkit.bestbets.prop_settle_runner as runner


def _sweep(n_settled=2, n_pending=5, n_open=7):
    return {
        "n_open_props": n_open, "n_settled_now": n_settled, "n_pending": n_pending,
        "settled": [{"market": "prop|x"}], "pending": [{"market": "prop|y"}],
        "executed": False, "edge_claimed": False,
    }


def test_tick_writes_status_and_beats(monkeypatch, tmp_path):
    status_p = tmp_path / "prop_settle_status.json"
    beats = []
    monkeypatch.setattr(runner, "_beat", lambda now=None: beats.append(now))
    doc = runner.tick(now=999.0, settle_fn=lambda: _sweep(),
                      status_path=status_p)
    assert doc["n_settled_now"] == 2
    assert doc["n_open_props"] == 7
    assert doc["executed"] is False and doc["edge_claimed"] is False
    assert beats == [999.0]                       # heartbeat advanced
    on_disk = json.loads(status_p.read_text(encoding="ascii"))
    assert on_disk["component"] == "m15_prop_settle"
    # the big settled/pending lists are NOT persisted in the compact status
    assert "settled" not in on_disk and "pending" not in on_disk


def test_status_is_dollar_free(monkeypatch, tmp_path):
    status_p = tmp_path / "s.json"
    monkeypatch.setattr(runner, "_beat", lambda now=None: None)
    runner.tick(now=1.0, settle_fn=lambda: _sweep(), status_path=status_p)
    doc = json.loads(status_p.read_text(encoding="ascii"))
    # scan the DATA fields (the honest_note disclaimer legitimately says "no $ field")
    doc.pop("honest_note", None)
    raw = json.dumps(doc).lower()
    for banned in ("$", "roi", "pnl", "dollar", "usd"):
        assert banned not in raw, "status leaked a money token: %r" % banned


def test_tick_never_raises_when_sweep_raises(monkeypatch, tmp_path):
    status_p = tmp_path / "s.json"
    beats = []
    monkeypatch.setattr(runner, "_beat", lambda now=None: beats.append(now))

    def _boom():
        raise RuntimeError("network down")

    doc = runner.tick(now=42.0, settle_fn=_boom, status_path=status_p)
    assert doc["n_settled_now"] == 0          # degraded, not fabricated
    assert beats == [42.0]                      # heartbeat STILL advances


def test_run_honors_max_ticks(monkeypatch, tmp_path):
    status_p = tmp_path / "s.json"
    monkeypatch.setattr(runner, "_beat", lambda now=None: None)
    calls = {"n": 0}

    def _settle():
        calls["n"] += 1
        return _sweep(n_settled=0)

    ticks = runner.run(settle_fn=_settle, status_path=status_p,
                       interval_sec=0.0, clock=lambda: 7.0,
                       sleep=lambda s: None, max_ticks=3)
    assert ticks == 3 and calls["n"] == 3


def test_run_honors_should_stop(monkeypatch, tmp_path):
    status_p = tmp_path / "s.json"
    monkeypatch.setattr(runner, "_beat", lambda now=None: None)
    ticks = runner.run(settle_fn=lambda: _sweep(), status_path=status_p,
                       interval_sec=0.0, clock=lambda: 1.0, sleep=lambda s: None,
                       should_stop=lambda: True, max_ticks=10)
    assert ticks == 0                           # stopped before first tick
