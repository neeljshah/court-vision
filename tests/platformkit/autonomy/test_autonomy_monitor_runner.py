"""tests for scripts.platformkit.autonomy.autonomy_monitor_runner (M5).

MEASUREMENT-ONLY autonomy monitor: every cycle composes the ONE canonical
autonomy status and ATOMICALLY publishes data/frontend/ops/autonomy_status.json
+ beats a heartbeat. The rails under test:
  * single-shot writes a VALID status doc atomically (no torn file).
  * compose-raises -> a DEGRADED envelope is published (never green, never crash).
  * the heartbeat advances each tick.

All offline: injected clock, stub compose, isolated status_path + heartbeat dir.
Run ONLY this file:
    python -m pytest tests/platformkit/autonomy/test_autonomy_monitor_runner.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.autonomy import autonomy_monitor_runner as amr  # noqa: E402

NOW = 1_000_000.0


def _good_compose(**kw):
    """A stub composer returning a green-ish canonical doc echoing the clock."""
    return {
        "generated_at": "2026-06-19T00:00:00Z",
        "overall": "ok",
        "services": [],
        "loop": {},
        "ratchet": {},
        "high_water": {},
        "idle_reason": None,
        "notes": [],
        "honest_note": "stub",
        "_now_echo": kw.get("now"),
    }


def _boom_compose(**kw):
    raise RuntimeError("composer exploded")


# --------------------------------------------------------------------------- #
# single-shot: a valid status doc is published atomically.
# --------------------------------------------------------------------------- #
def test_single_shot_writes_valid_status_atomically(tmp_path, monkeypatch):
    from ops import liveness as lv
    monkeypatch.setattr(lv, "_DAEMON_HB_DIR", tmp_path / "hb")
    out = tmp_path / "autonomy_status.json"
    ticks = amr.run(compose=_good_compose, status_path=out, max_ticks=1,
                    clock=lambda: NOW, sleep=lambda _s: None)
    assert ticks == 1
    assert out.exists()
    # No torn temp file left behind (atomic replace consumed it).
    assert not (out.with_suffix(out.suffix + ".tmp")).exists()
    doc = json.loads(out.read_text(encoding="ascii"))
    assert doc["overall"] == "ok"
    # All canonical blocks survive into the published file.
    for key in ("services", "loop", "ratchet", "high_water", "idle_reason",
                "notes", "honest_note"):
        assert key in doc, key
    # Monitor provenance stamped, compose_ok True, clock threaded through.
    assert doc["monitor"]["component"] == amr.HEARTBEAT_COMPONENT
    assert doc["monitor"]["compose_ok"] is True
    assert doc["monitor"]["wrote_at"] == NOW
    assert doc["_now_echo"] == NOW


def test_published_file_is_ascii_and_parseable(tmp_path, monkeypatch):
    from ops import liveness as lv
    monkeypatch.setattr(lv, "_DAEMON_HB_DIR", tmp_path / "hb")
    out = tmp_path / "autonomy_status.json"
    amr.tick(now=NOW, compose=_good_compose, status_path=out)
    raw = out.read_text(encoding="ascii")  # ascii decode proves ASCII-only
    assert json.loads(raw)["overall"] == "ok"


# --------------------------------------------------------------------------- #
# compose raises -> DEGRADED written, never green, never crash.
# --------------------------------------------------------------------------- #
def test_compose_raises_writes_degraded_not_green(tmp_path, monkeypatch):
    from ops import liveness as lv
    monkeypatch.setattr(lv, "_DAEMON_HB_DIR", tmp_path / "hb")
    out = tmp_path / "autonomy_status.json"
    # run() must NOT propagate the composer error.
    ticks = amr.run(compose=_boom_compose, status_path=out, max_ticks=1,
                    clock=lambda: NOW, sleep=lambda _s: None)
    assert ticks == 1
    assert out.exists()
    doc = json.loads(out.read_text(encoding="ascii"))
    assert doc["overall"] == amr.DEGRADED
    assert doc["overall"] != "ok"
    assert doc["monitor"]["compose_ok"] is False
    assert any("compose raised" in n for n in doc["notes"])


def test_compose_returns_non_dict_degrades(tmp_path, monkeypatch):
    from ops import liveness as lv
    monkeypatch.setattr(lv, "_DAEMON_HB_DIR", tmp_path / "hb")
    out = tmp_path / "autonomy_status.json"
    amr.tick(now=NOW, compose=lambda **kw: ["not", "a", "dict"], status_path=out)
    doc = json.loads(out.read_text(encoding="ascii"))
    assert doc["overall"] == amr.DEGRADED
    assert doc["monitor"]["compose_ok"] is False


# --------------------------------------------------------------------------- #
# heartbeat advances each tick (using the real ops.liveness against a tmp dir).
# --------------------------------------------------------------------------- #
def test_heartbeat_advances_each_tick(tmp_path, monkeypatch):
    from ops import liveness as lv
    hb_dir = tmp_path / "hb"
    monkeypatch.setattr(lv, "_DAEMON_HB_DIR", hb_dir)
    out = tmp_path / "autonomy_status.json"

    amr.tick(now=NOW, compose=_good_compose, status_path=out)
    hb_path = hb_dir / (amr.HEARTBEAT_COMPONENT + ".txt")
    assert hb_path.exists()
    first = hb_path.read_text(encoding="ascii").strip()

    later = NOW + 120.0
    amr.tick(now=later, compose=_good_compose, status_path=out)
    second = hb_path.read_text(encoding="ascii").strip()
    assert second != first  # heartbeat timestamp moved forward
    # And the monitor reads live at the later time, stale long after.
    assert lv.is_live(amr.HEARTBEAT_COMPONENT, max_age_sec=300.0,
                      now=later + 10.0, path=hb_path) is True
    assert lv.is_live(amr.HEARTBEAT_COMPONENT, max_age_sec=300.0,
                      now=later + 99999.0, path=hb_path) is False


# --------------------------------------------------------------------------- #
# multi-tick + should_stop: loop is bounded and honors the stop hook.
# --------------------------------------------------------------------------- #
def test_should_stop_halts_loop(tmp_path, monkeypatch):
    from ops import liveness as lv
    monkeypatch.setattr(lv, "_DAEMON_HB_DIR", tmp_path / "hb")
    out = tmp_path / "autonomy_status.json"
    calls = {"n": 0}

    def _stop():
        calls["n"] += 1
        return calls["n"] > 3  # allow 3 ticks then stop

    ticks = amr.run(compose=_good_compose, status_path=out,
                    clock=lambda: NOW, sleep=lambda _s: None,
                    should_stop=_stop, max_ticks=100)
    assert ticks == 3


def test_max_ticks_bounds_loop(tmp_path, monkeypatch):
    from ops import liveness as lv
    monkeypatch.setattr(lv, "_DAEMON_HB_DIR", tmp_path / "hb")
    out = tmp_path / "autonomy_status.json"
    slept = {"n": 0}

    def _sleep(_s):
        slept["n"] += 1

    ticks = amr.run(compose=_good_compose, status_path=out, max_ticks=2,
                    clock=lambda: NOW, sleep=_sleep)
    assert ticks == 2
    # The last tick does NOT sleep (loop breaks on max_ticks before sleeping).
    assert slept["n"] == 1
