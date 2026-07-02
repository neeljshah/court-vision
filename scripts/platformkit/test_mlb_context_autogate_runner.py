"""Per-file tests for scripts.platformkit.mlb_context_autogate_runner (M32).

Offline only: injected sp_gate_fn/weather_gate_fn + fake clock/sleep. No
network, no real gate execution, no real heartbeat dependency (heartbeat
_beat never raises). Composed-doc writes go to the real
data/frontend/ops/mlb_context_autogate.json path (small JSON, matches the
m31/m29 pattern of other ops daemons); cleaned up after each test that writes it.

Run ONLY this file:
  python -m pytest scripts/platformkit/test_mlb_context_autogate_runner.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

import scripts.platformkit.mlb_context_autogate_runner as _runner_mod  # noqa: E402
from scripts.platformkit.mlb_context_autogate_runner import (  # noqa: E402
    DEFAULT_INTERVAL_SEC, HEARTBEAT_COMPONENT, _AUTOGATE_OUT, run, tick,
)


@pytest.fixture(autouse=True)
def _no_real_heartbeat(monkeypatch):
    """Tests pass synthetic clocks; a REAL _beat would stamp epoch-era timestamps
    into the live heartbeat file and make the healthy daemon read stale."""
    monkeypatch.setattr(_runner_mod, "_beat", lambda now_epoch=None: None)


def _cleanup_out():
    try:
        if _AUTOGATE_OUT.exists():
            _AUTOGATE_OUT.unlink()
    except OSError:
        pass


def test_component_and_cadence_contract():
    assert HEARTBEAT_COMPONENT == "m32_mlb_context_autogate"
    assert DEFAULT_INTERVAL_SEC == 86400.0


def test_tick_composes_doc_and_ship_review_list():
    _cleanup_out()
    doc = tick(
        now=1000.0,
        sp_gate_fn=lambda: {"name": "sp_elo_offset_2026_forward", "verdict": "SHIP-READY",
                             "verdict_reason": "does not regress", "n": 400},
        weather_gate_fn=lambda: {"name": "weather_totals", "verdict": "REJECT",
                                  "verdict_reason": "fails half2", "n": 900, "n_scorable": 800},
    )
    assert len(doc["candidates"]) == 2
    names = {c["name"] for c in doc["candidates"]}
    assert names == {"sp_elo_offset_2026_forward", "weather_totals"}
    assert doc["ship_review"] == ["sp_elo_offset_2026_forward"]
    assert "no $ edge claimed" in doc["honest_note"]
    assert _AUTOGATE_OUT.exists()
    on_disk = json.loads(_AUTOGATE_OUT.read_text(encoding="utf-8"))
    assert on_disk["ship_review"] == ["sp_elo_offset_2026_forward"]
    _cleanup_out()


def test_tick_both_ship_review_variants_recognized():
    _cleanup_out()
    doc = tick(
        now=1000.0,
        sp_gate_fn=lambda: {"name": "sp_elo_offset_2026_forward", "verdict": "SHIP_REVIEW"},
        weather_gate_fn=lambda: {"name": "weather_totals", "verdict": "SHIP-READY"},
    )
    assert set(doc["ship_review"]) == {"sp_elo_offset_2026_forward", "weather_totals"}
    _cleanup_out()


def test_tick_survives_raising_gate_and_marks_error():
    _cleanup_out()

    def _boom():
        raise RuntimeError("planted gate failure")

    doc = tick(
        now=1000.0,
        sp_gate_fn=_boom,
        weather_gate_fn=lambda: {"name": "weather_totals", "verdict": "INCONCLUSIVE", "n": 50},
    )
    assert len(doc["candidates"]) == 2
    sp_entry = next(c for c in doc["candidates"] if c["name"] == "sp_elo_offset_2026_forward")
    assert sp_entry["verdict"] == "ERROR"
    assert "planted gate failure" in sp_entry["verdict_reason"]
    weather_entry = next(c for c in doc["candidates"] if c["name"] == "weather_totals")
    assert weather_entry["verdict"] == "INCONCLUSIVE"
    assert doc["ship_review"] == []
    # doc still written even though one gate raised.
    assert _AUTOGATE_OUT.exists()
    _cleanup_out()


def test_tick_both_gates_raise_still_writes_doc():
    _cleanup_out()

    def _boom():
        raise ValueError("boom")

    doc = tick(now=1000.0, sp_gate_fn=_boom, weather_gate_fn=_boom)
    assert all(c["verdict"] == "ERROR" for c in doc["candidates"])
    assert doc["ship_review"] == []
    assert _AUTOGATE_OUT.exists()
    _cleanup_out()


def test_run_max_ticks_and_should_stop():
    _cleanup_out()
    calls = {"n": 0}

    def _sp():
        calls["n"] += 1
        return {"name": "sp_elo_offset_2026_forward", "verdict": "REJECT"}

    slept = []
    ticks = run(interval_sec=5.0,
                sp_gate_fn=_sp,
                weather_gate_fn=lambda: {"name": "weather_totals", "verdict": "REJECT"},
                clock=lambda: 123.0,
                sleep=slept.append,
                max_ticks=3)
    assert ticks == 3
    assert calls["n"] == 3
    assert slept == [5.0, 5.0]  # no sleep after the final tick
    _cleanup_out()

    ticks = run(interval_sec=5.0,
                sp_gate_fn=_sp,
                weather_gate_fn=lambda: {"name": "weather_totals", "verdict": "REJECT"},
                clock=lambda: 123.0,
                sleep=lambda s: None,
                should_stop=lambda: True)
    assert ticks == 0
    _cleanup_out()
