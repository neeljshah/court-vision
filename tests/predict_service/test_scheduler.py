"""Offline test for predict_service.scheduler -- the always-on producer scheduler.

Runs with a FAKE clock (no real sleeping) and a FAKE produce_fn (no network, no
corpus). Asserts: 5 fake ticks drive 5 cycles, a sport that raises is isolated
(the others still run + still record last_ok), and the heartbeat is written
atomically (no torn/partial file ever observed by a reader).

Per-file run only:
    python -m pytest tests/predict_service/test_scheduler.py -q
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from predict_service import scheduler


# --- fakes ---------------------------------------------------------------- #
class FakeClock:
    """Deterministic clock: now() never moves on its own; sleep() advances it.

    No real time is ever consulted -- the tested path is fully synchronous.
    """

    def __init__(self, start: float = 1000.0) -> None:
        self.t = float(start)
        self.sleeps: List[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(float(seconds))
        self.t += float(seconds)


def _make_produce(calls: List[str], raise_for: str = ""):
    """A fake produce_fn that records each (sport) call and saves nothing real."""

    def _produce(sport: str, *, out_dir=None) -> str:
        calls.append(sport)
        if sport == raise_for:
            raise RuntimeError("boom in %s" % sport)
        return "%s/latest.json" % sport

    return _produce


# --- tests ---------------------------------------------------------------- #
def test_five_ticks_run_five_cycles(tmp_path):
    calls: List[str] = []
    clock = FakeClock()
    # large interval so per-sport cadence never re-gates within the 5 ticks;
    # every tick is due because last_run advances by the same interval each sleep
    ticks = scheduler.serve_forever(
        interval=10_000, clock=clock, out_dir=str(tmp_path),
        produce_fn=_make_produce(calls), sports=["nba"], max_ticks=5)
    assert ticks == 5
    # nba is due on every tick (interval >> its cadence), so 5 produce calls
    assert calls == ["nba"] * 5
    # 4 sleeps (the loop breaks before sleeping on the final tick)
    assert clock.sleeps == [10_000.0] * 4
    hb = scheduler.read_heartbeat(out_dir=str(tmp_path))
    assert hb["cycle_count"] == 5


def test_raising_sport_is_isolated(tmp_path):
    calls: List[str] = []
    produce_fn = _make_produce(calls, raise_for="mlb")
    hb = scheduler.run_cycle(
        ["nba", "mlb", "tennis"], out_dir=str(tmp_path),
        produce_fn=produce_fn, now_fn=lambda: 2000.0)
    # every sport was attempted despite mlb raising
    assert calls == ["nba", "mlb", "tennis"]
    assert hb["ok"] == 2
    assert hb["errors"] == 1
    assert hb["sports"]["mlb"]["status"] == "error"
    assert hb["sports"]["mlb"]["error"] == "RuntimeError"
    # the healthy sports recorded a fresh last_ok at the cycle timestamp
    assert hb["sports"]["nba"]["status"] == "ok"
    assert hb["sports"]["nba"]["last_ok"] == 2000.0
    assert hb["sports"]["tennis"]["last_ok"] == 2000.0
    # the failed sport has no last_ok (no prior success to preserve)
    assert hb["sports"]["mlb"]["last_ok"] is None


def test_error_preserves_prior_last_ok(tmp_path):
    calls: List[str] = []
    # cycle 1: mlb succeeds at t=100
    scheduler.run_cycle(
        ["mlb"], out_dir=str(tmp_path),
        produce_fn=_make_produce(calls), now_fn=lambda: 100.0)
    # cycle 2: mlb now raises at t=200 -- prior last_ok must be preserved
    hb = scheduler.run_cycle(
        ["mlb"], out_dir=str(tmp_path),
        produce_fn=_make_produce(calls, raise_for="mlb"), now_fn=lambda: 200.0)
    assert hb["sports"]["mlb"]["status"] == "error"
    assert hb["sports"]["mlb"]["last_ok"] == 100.0  # carried over, not lost
    assert hb["sports"]["mlb"]["last_run"] == 200.0


def test_heartbeat_is_atomic_and_complete(tmp_path):
    calls: List[str] = []
    scheduler.run_cycle(
        ["nba", "soccer"], out_dir=str(tmp_path),
        produce_fn=_make_produce(calls), now_fn=lambda: 555.0)
    path = scheduler.heartbeat_path(out_dir=str(tmp_path))
    # no leftover tmp file -- the atomic rename consumed it
    tmp = path.with_suffix(path.suffix + ".tmp")
    assert not tmp.exists()
    # the file on disk is COMPLETE, valid JSON (never a partial read)
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert isinstance(data, dict)
    assert set(data["sports_run"]) == {"nba", "soccer"}
    assert data["ok"] == 2
    assert "no $ edge" in data["note"]


def test_per_sport_cadence_gates_runs(tmp_path):
    calls: List[str] = []
    clock = FakeClock(start=0.0)
    # nba cadence is 600s; with a 100s loop interval, nba runs only on ticks
    # where >=600s has elapsed since its last run.
    scheduler.serve_forever(
        interval=100, clock=clock, out_dir=str(tmp_path),
        produce_fn=_make_produce(calls), sports=["nba"], max_ticks=8)
    # tick 1 (now=0) runs; next due when now>=600 -> tick 7 (now=600)
    assert calls == ["nba", "nba"]


def test_start_beat_written_before_first_cycle(tmp_path):
    """m13 two-layer-HB pattern: the boot beat must land BEFORE the first
    produce_fn call so a slow/blocking cycle 1 (e.g. a provider 429 boot
    storm) is judged fresh against the boot beat, not a stale updated_at left
    over from a prior crash."""
    seen: Dict[str, Any] = {}

    def _produce(sport: str, *, out_dir=None) -> str:
        # by the time the first sport is produced, the start beat must
        # already be on disk with a fresh updated_at and the boot note.
        hb = scheduler.read_heartbeat(out_dir=out_dir)
        seen["updated_at"] = hb.get("updated_at")
        seen["note"] = hb.get("note")
        return "%s/latest.json" % sport

    clock = FakeClock(start=5000.0)
    scheduler.serve_forever(
        interval=10_000, clock=clock, out_dir=str(tmp_path),
        produce_fn=_produce, sports=["nba"], max_ticks=1)

    assert seen["updated_at"] == 5000.0
    assert "boot-beat" in (seen["note"] or "")


def test_start_beat_shape_matches_run_cycle_payload(tmp_path):
    """The boot beat is written with run_cycle's own payload keys (no reader
    -- supervisor or frontend -- needs a special case for the boot state)."""
    scheduler._write_start_beat(str(tmp_path), now_fn=lambda: 42.0)
    hb = scheduler.read_heartbeat(out_dir=str(tmp_path))
    for key in ("updated_at", "cycle_count", "sports_run", "ok", "errors",
                "sports", "note"):
        assert key in hb
    assert hb["updated_at"] == 42.0
    assert hb["cycle_count"] == 0


def test_per_cycle_beat_still_fires_after_start_beat(tmp_path):
    """The start beat is a prelude, not a replacement -- run_cycle's own beat
    must still land (and supersede the boot note) once the cycle completes."""
    calls: List[str] = []
    clock = FakeClock(start=1000.0)
    scheduler.serve_forever(
        interval=10_000, clock=clock, out_dir=str(tmp_path),
        produce_fn=_make_produce(calls), sports=["nba"], max_ticks=1)
    hb = scheduler.read_heartbeat(out_dir=str(tmp_path))
    assert hb["cycle_count"] == 1
    assert hb["sports_run"] == ["nba"]
    assert "boot-beat" not in hb["note"]  # overwritten by the real cycle beat


def test_empty_sports_writes_clean_heartbeat(tmp_path):
    hb = scheduler.run_cycle(
        [], out_dir=str(tmp_path),
        produce_fn=_make_produce([]), now_fn=lambda: 9.0)
    assert hb["ok"] == 0
    assert hb["errors"] == 0
    assert hb["sports_run"] == []
    # still a valid, complete heartbeat on disk
    data = scheduler.read_heartbeat(out_dir=str(tmp_path))
    assert data["cycle_count"] == 1
