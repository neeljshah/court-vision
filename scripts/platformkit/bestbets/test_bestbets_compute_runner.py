"""Tests for bestbets_compute_runner tick(): slow-tick liveness + deadline.

Covers the 2026-07-15 fix: a compute slower than the supervisor's heartbeat
window must keep beating (fresh stamps) while it runs, and a compute past the
deadline must yield a degraded envelope instead of blocking forever.
"""
from __future__ import annotations

import json
import time

import scripts.platformkit.bestbets.bestbets_compute_runner as runner


def _patch(monkeypatch, *, slice_sec, deadline_sec, beats):
    monkeypatch.setattr(runner, "_BEAT_SLICE_SEC", slice_sec)
    monkeypatch.setattr(runner, "_COMPUTE_DEADLINE_SEC", deadline_sec)
    monkeypatch.setattr(runner, "_beat", lambda *a, **k: beats.append(time.time()))


def test_slow_tick_beats_while_computing_and_completes(monkeypatch, tmp_path):
    beats = []
    _patch(monkeypatch, slice_sec=0.05, deadline_sec=10.0, beats=beats)

    def slow_compute(now):
        time.sleep(0.3)
        return [{"card": 1}]

    out = tmp_path / "best_bets.json"
    env = runner.tick(now=time.time(), compute_fn=slow_compute, output_path=out)
    assert env["overall"] == "ok"
    assert len(env["cards"]) == 1
    # at least one intra-tick beat plus the final fresh beat
    assert len(beats) >= 2
    assert json.loads(out.read_text())["overall"] == "ok"


def test_deadline_yields_degraded_envelope_fast(monkeypatch, tmp_path):
    beats = []
    _patch(monkeypatch, slice_sec=0.05, deadline_sec=0.15, beats=beats)

    def hung_compute(now):
        time.sleep(30)
        return [{"never": True}]

    out = tmp_path / "best_bets.json"
    t0 = time.time()
    env = runner.tick(now=time.time(), compute_fn=hung_compute, output_path=out)
    assert time.time() - t0 < 5  # returned promptly, did not wait out the hang
    assert env["overall"] == "degraded"
    assert env["note"] == "compute_deadline"
    assert env["cards"] == []
