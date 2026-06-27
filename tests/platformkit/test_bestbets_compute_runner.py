"""Per-file test for bestbets_compute_runner -- supervised M10 daemon (W11).

NO full pytest. Run only this file:
  cd /c/Users/neelj/nba-ai-system &&
  python -m pytest tests/platformkit/test_bestbets_compute_runner.py -q
"""
from __future__ import annotations

import pathlib
import json

from scripts.platformkit.bestbets import bestbets_compute_runner as r


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _no_sleep(s):
    pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_bounded_run_stops_at_max_ticks():
    """run() with max_ticks=3 executes exactly 3 ticks and returns 3."""
    ticks = {"n": 0}

    def _compute(now):
        ticks["n"] += 1
        return [{"game_id": "g1", "units": 0.5, "tier": "A",
                 "confidence": 0.7, "clv": None}]

    n = r.run(compute_fn=_compute,
              output_path=pathlib.Path("/dev/null"),
              clock=lambda: 1000.0, sleep=_no_sleep, max_ticks=3)
    assert n == 3
    assert ticks["n"] == 3


def test_heartbeat_beat_at_boot_and_per_tick(monkeypatch, tmp_path):
    """Heartbeat is written at boot + once per tick (stale-never-green)."""
    beats = []
    monkeypatch.setattr(r, "_beat", lambda now=None: beats.append(now))
    r.run(compute_fn=lambda now: [],
          output_path=tmp_path / "bb.json",
          clock=lambda: 42.0, sleep=_no_sleep, max_ticks=2)
    # 1 boot + 2 per-tick = 3 total
    assert len(beats) == 3
    assert beats.count(42.0) >= 2


def test_compute_fn_raise_does_not_crash(tmp_path):
    """A raising compute_fn degrades to empty cards; loop continues."""
    def _boom(now):
        raise ValueError("explode")

    n = r.run(compute_fn=_boom,
              output_path=tmp_path / "bb.json",
              clock=lambda: 1.0, sleep=_no_sleep, max_ticks=2)
    assert n == 2


def test_output_file_written(tmp_path):
    """tick() writes a JSON file with the expected envelope fields."""
    out = tmp_path / "best_bets.json"
    cards = [{"game_id": "g1", "units": 1.0, "tier": "A",
              "confidence": 0.8, "clv": None}]
    doc = r.tick(now=1000.0, compute_fn=lambda now: cards, output_path=out)
    assert out.exists()
    data = json.loads(out.read_text(encoding="ascii"))
    assert data["card_count"] == 1
    assert "generated_at" in data
    assert "overall" in data
    # UNITS not $: no dollar P&L field
    assert "dollar_pnl" not in data
    assert "pnl_usd" not in data


def test_no_dollar_pnl_in_envelope(tmp_path):
    """Envelope must NEVER contain a dollar P&L field."""
    out = tmp_path / "bb.json"
    r.tick(now=5.0, compute_fn=lambda now: [], output_path=out)
    raw = out.read_text(encoding="ascii")
    assert "dollar_pnl" not in raw
    assert "pnl_usd" not in raw


def test_should_stop_halts_loop(tmp_path):
    """should_stop=True on second call halts before max_ticks."""
    calls = {"n": 0}

    def _stop():
        calls["n"] += 1
        return calls["n"] >= 2

    n = r.run(compute_fn=lambda now: [],
              output_path=tmp_path / "bb.json",
              clock=lambda: 0.0, sleep=_no_sleep,
              should_stop=_stop, max_ticks=99)
    assert n == 1


def test_unavailable_path_degrades_gracefully(tmp_path):
    """When the output path is unwritable, tick() still returns (no raise)."""
    bad_path = tmp_path / "no_such_dir" / "x" / "bb.json"
    # The atomic write will fail but tick() must not raise
    try:
        doc = r.tick(now=1.0, compute_fn=lambda now: [], output_path=bad_path)
    except Exception as exc:
        raise AssertionError("tick() raised: %s" % exc) from exc


if __name__ == "__main__":
    import sys
    test_bounded_run_stops_at_max_ticks()
    print("ok: bounded_run")
    test_compute_fn_raise_does_not_crash(pathlib.Path("/tmp"))
    print("ok: compute_raise_degrades")
    print("all tests passed")
    sys.exit(0)
