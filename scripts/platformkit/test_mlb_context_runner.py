"""Per-file tests for scripts.platformkit.mlb_context_runner (M31).

Offline only: injected probables/injuries fns + fake clock/sleep. No network,
no parquet writes, no real heartbeat dependency (heartbeat _beat never raises).

Run ONLY this file:
  python -m pytest scripts/platformkit/test_mlb_context_runner.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

import scripts.platformkit.mlb_context_runner as _runner_mod  # noqa: E402
from scripts.platformkit.mlb_context_runner import (  # noqa: E402
    DEFAULT_INTERVAL_SEC, HEARTBEAT_COMPONENT, run, tick,
)


@pytest.fixture(autouse=True)
def _no_real_heartbeat(monkeypatch):
    """Tests pass synthetic clocks; a REAL _beat would stamp epoch-era timestamps
    into the live heartbeat file and make the healthy daemon read stale."""
    monkeypatch.setattr(_runner_mod, "_beat", lambda now_epoch=None: None)


def test_component_and_cadence_contract():
    assert HEARTBEAT_COMPONENT == "m31_mlb_context"
    assert DEFAULT_INTERVAL_SEC == 21600.0


def test_tick_merges_all_sources():
    doc = tick(now=1000.0,
               probables_fn=lambda: 12,
               injuries_fn=lambda: {"injury_rows": 280, "edge_facts": 160},
               umpires_fn=lambda: 52)
    assert doc["probable_rows"] == 12
    assert doc["injury_rows"] == 280
    assert doc["edge_facts"] == 160
    assert doc["umpire_rows"] == 52


def test_tick_never_raises_when_all_sources_raise():
    def _boom():
        raise RuntimeError("planted")
    doc = tick(now=1000.0, probables_fn=_boom, injuries_fn=_boom, umpires_fn=_boom)
    # degraded but alive: zeros, no exception out of tick()
    assert doc["probable_rows"] == 0
    assert doc["injury_rows"] == 0
    assert doc["edge_facts"] == 0
    assert doc["umpire_rows"] == 0


def test_run_max_ticks_and_should_stop():
    calls = {"n": 0}

    def _probables():
        calls["n"] += 1
        return 1

    slept = []
    ticks = run(interval_sec=5.0,
                probables_fn=_probables,
                injuries_fn=lambda: {"injury_rows": 0, "edge_facts": 0},
                umpires_fn=lambda: 0,
                clock=lambda: 123.0,
                sleep=slept.append,
                max_ticks=3)
    assert ticks == 3
    assert calls["n"] == 3
    assert slept == [5.0, 5.0]  # no sleep after the final tick

    ticks = run(interval_sec=5.0,
                probables_fn=_probables,
                injuries_fn=lambda: {"injury_rows": 0, "edge_facts": 0},
                umpires_fn=lambda: 0,
                clock=lambda: 123.0,
                sleep=lambda s: None,
                should_stop=lambda: True)
    assert ticks == 0
