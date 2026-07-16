"""Per-file tests for http_wedge_reaper / http_wedge_reaper_io / http_wedge_probe
/ http_wedge_reaper_runner / http_wedge_supervisor_bridge.

NEVER kills or probes a real PID/socket -- everything is fakes/mocks/tmp_path.
Covers: below-threshold no-kill, exactly-threshold kill, port-not-listening
no-kill, CPU-low no-kill, state persistence across ticks, and the runner-level
orchestration (fake port/http/cpu/kill callables).

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_http_wedge_reaper.py -q
"""
from __future__ import annotations

from scripts.platformkit.autonomy.http_wedge_reaper import (
    CONSECUTIVE_TIMEOUT_THRESHOLD,
    CPU_PCT_THRESHOLD,
    CPU_SUSTAINED_SEC,
    DEADTIME_CEILING_SEC,
    KEEP,
    KILL,
    TIMEOUT_FLOOR_SEC,
    HttpWedgeReaper,
)
from scripts.platformkit.autonomy.http_wedge_reaper_io import (
    load_state_file,
    save_state_file,
    write_decisions,
)


def _clock(seq):
    """Returns a callable that yields successive values from *seq* (last value
    repeats once exhausted)."""
    it = iter(seq)
    state = {"last": seq[0] if seq else 0.0}

    def _c():
        try:
            state["last"] = next(it)
        except StopIteration:
            pass
        return state["last"]
    return _c


# --------------------------------------------------------------------------- #
# decision core: timeout streak + CPU sustain, both required for KILL
# --------------------------------------------------------------------------- #
def test_below_threshold_no_kill():
    r = HttpWedgeReaper(clock=lambda: 0.0)
    for _ in range(CONSECUTIVE_TIMEOUT_THRESHOLD - 1):
        v = r.observe("svc", port_listening=True, probe_timed_out=True,
                      probe_elapsed_sec=TIMEOUT_FLOOR_SEC + 1.0, cpu_pct=99.0)
    assert v["verdict"] == KEEP
    assert v["detail"]["consecutive_timeouts"] == CONSECUTIVE_TIMEOUT_THRESHOLD - 1


def test_exactly_threshold_kill_when_cpu_also_sustained():
    clk = _clock([0.0, 0.0, 0.0])
    r = HttpWedgeReaper(clock=clk)
    # First observation starts the CPU-high streak at t=0.
    r.observe("svc", port_listening=True, probe_timed_out=True,
              probe_elapsed_sec=TIMEOUT_FLOOR_SEC + 1.0, cpu_pct=99.0)
    # Advance the clock past the CPU sustain window while continuing timeouts.
    clk2 = _clock([CPU_SUSTAINED_SEC + 1.0])
    r2 = HttpWedgeReaper(clock=clk2)
    # Seed state directly to simulate "CPU has been high since t=0" and
    # "2 consecutive timeouts already recorded", then the 3rd timeout tick
    # (at t=CPU_SUSTAINED_SEC+1) should trip KILL.
    r2.load_state({"svc": {"name": "svc", "consecutive_timeouts": 2,
                           "cpu_high_since": 0.0, "last_verdict": KEEP,
                           "last_kill_at": None}})
    v = r2.observe("svc", port_listening=True, probe_timed_out=True,
                   probe_elapsed_sec=TIMEOUT_FLOOR_SEC + 1.0, cpu_pct=99.0)
    assert v["verdict"] == KILL
    assert v["detail"]["timeout_tripped"] is True
    assert v["detail"]["cpu_tripped"] is True
    # Post-kill bookkeeping resets streaks.
    dumped = r2.dump_state()["svc"]
    assert dumped["consecutive_timeouts"] == 0
    assert dumped["cpu_high_since"] is None


def test_port_not_listening_no_kill_resets_streaks():
    r = HttpWedgeReaper(clock=lambda: 0.0)
    r.load_state({"svc": {"name": "svc", "consecutive_timeouts": 5,
                          "cpu_high_since": 0.0, "last_verdict": KEEP,
                          "last_kill_at": None}})
    v = r.observe("svc", port_listening=False, probe_timed_out=True,
                  probe_elapsed_sec=999.0, cpu_pct=99.0)
    assert v["verdict"] == KEEP
    assert v["detail"]["reason"] == "port_not_listening"
    dumped = r.dump_state()["svc"]
    assert dumped["consecutive_timeouts"] == 0
    assert dumped["cpu_high_since"] is None


def test_cpu_low_no_kill_even_with_timeout_streak():
    clk = _clock([0.0, CPU_SUSTAINED_SEC + 10.0, CPU_SUSTAINED_SEC + 20.0])
    r = HttpWedgeReaper(clock=clk)
    for _ in range(CONSECUTIVE_TIMEOUT_THRESHOLD + 2):
        v = r.observe("svc", port_listening=True, probe_timed_out=True,
                      probe_elapsed_sec=TIMEOUT_FLOOR_SEC + 1.0, cpu_pct=10.0)
    assert v["verdict"] == KEEP
    assert v["detail"]["timeout_tripped"] is True
    assert v["detail"]["cpu_tripped"] is False


def test_timeout_at_floor_does_not_count():
    """probe_elapsed_sec exactly AT the floor (not strictly greater) must not
    count toward the streak -- the charter requires > 10s, not >= 10s."""
    r = HttpWedgeReaper(clock=lambda: 0.0)
    v = r.observe("svc", port_listening=True, probe_timed_out=True,
                  probe_elapsed_sec=TIMEOUT_FLOOR_SEC, cpu_pct=99.0)
    assert v["detail"]["consecutive_timeouts"] == 0


def test_cpu_unknown_never_counts_toward_kill():
    r = HttpWedgeReaper(clock=lambda: 0.0)
    for _ in range(CONSECUTIVE_TIMEOUT_THRESHOLD + 1):
        v = r.observe("svc", port_listening=True, probe_timed_out=True,
                      probe_elapsed_sec=TIMEOUT_FLOOR_SEC + 1.0, cpu_pct=None)
    assert v["verdict"] == KEEP
    assert v["detail"]["cpu_tripped"] is False


def test_observe_never_raises_on_malformed_input():
    r = HttpWedgeReaper(clock=lambda: 0.0)
    v = r.observe("svc", port_listening=True, probe_timed_out="not-a-bool",  # type: ignore[arg-type]
                  probe_elapsed_sec="bad", cpu_pct="bad")
    assert v["verdict"] == KEEP


def test_recovery_clears_timeout_streak():
    r = HttpWedgeReaper(clock=lambda: 0.0)
    r.observe("svc", port_listening=True, probe_timed_out=True,
              probe_elapsed_sec=TIMEOUT_FLOOR_SEC + 1.0, cpu_pct=99.0)
    v = r.observe("svc", port_listening=True, probe_timed_out=False,
                  probe_elapsed_sec=0.1, cpu_pct=99.0)
    assert v["detail"]["consecutive_timeouts"] == 0


def test_deadtime_ceiling_kills_low_cpu_wedge_after_ten_minutes():
    """2026-07-15 ceiling: low-CPU wedge (the real incident) still gets killed
    once the SAME unbroken timeout streak spans >= DEADTIME_CEILING_SEC, with
    cpu_pct staying low/None the whole time."""
    r = HttpWedgeReaper(clock=lambda: 0.0)
    r.observe("svc", port_listening=True, probe_timed_out=True,
              probe_elapsed_sec=TIMEOUT_FLOOR_SEC + 1.0, cpu_pct=None)

    r2 = HttpWedgeReaper(clock=lambda: DEADTIME_CEILING_SEC + 1.0)
    r2.load_state(r.dump_state())
    v = r2.observe("svc", port_listening=True, probe_timed_out=True,
                   probe_elapsed_sec=TIMEOUT_FLOOR_SEC + 1.0, cpu_pct=None)
    assert v["verdict"] == KILL
    assert v["detail"]["reason"] == "deadtime_ceiling"
    assert v["detail"]["cpu_tripped"] is False
    dumped = r2.dump_state()["svc"]
    assert dumped["consecutive_timeouts"] == 0
    assert dumped["timeout_streak_since"] is None


def test_healthy_port_never_hits_deadtime_ceiling():
    """A port that keeps responding fine never accrues a timeout streak, so the
    ceiling never trips even after a long observation window."""
    r = HttpWedgeReaper(clock=lambda: 0.0)
    r.observe("svc", port_listening=True, probe_timed_out=False,
              probe_elapsed_sec=0.05, cpu_pct=5.0)

    r2 = HttpWedgeReaper(clock=lambda: DEADTIME_CEILING_SEC * 10)
    r2.load_state(r.dump_state())
    v = r2.observe("svc", port_listening=True, probe_timed_out=False,
                   probe_elapsed_sec=0.05, cpu_pct=5.0)
    assert v["verdict"] == KEEP
    assert v["detail"]["deadtime_tripped"] is False


def test_brief_blip_single_timeout_never_kills():
    """A single timeout followed by recovery resets the streak -- one blip is
    never enough, even close to the ceiling window."""
    r = HttpWedgeReaper(clock=lambda: 0.0)
    r.observe("svc", port_listening=True, probe_timed_out=True,
              probe_elapsed_sec=TIMEOUT_FLOOR_SEC + 1.0, cpu_pct=None)

    r2 = HttpWedgeReaper(clock=lambda: DEADTIME_CEILING_SEC - 1.0)
    r2.load_state(r.dump_state())
    # Recovers before the ceiling -- streak resets, no kill.
    v = r2.observe("svc", port_listening=True, probe_timed_out=False,
                   probe_elapsed_sec=0.05, cpu_pct=None)
    assert v["verdict"] == KEEP
    assert v["detail"]["consecutive_timeouts"] == 0

    r3 = HttpWedgeReaper(clock=lambda: DEADTIME_CEILING_SEC + 1.0)
    r3.load_state(r2.dump_state())
    v3 = r3.observe("svc", port_listening=True, probe_timed_out=True,
                    probe_elapsed_sec=TIMEOUT_FLOOR_SEC + 1.0, cpu_pct=None)
    # Streak restarted at t=DEADTIME_CEILING_SEC-1's recovery point -> far from
    # the ceiling again, so still KEEP.
    assert v3["verdict"] == KEEP


def test_pid_cpu_percent_primed_then_numeric_on_second_tick():
    """The production CPU probe caches the psutil.Process handle per-pid so the
    SECOND call (a later reaper tick) reads a real delta instead of being
    perpetually null/0.0 (the audit's cpu_pct=null finding). Pure fake mod --
    never touches a real PID."""
    from scripts.platformkit.autonomy.http_wedge_probe import pid_cpu_percent

    calls = {"n": 0}

    class _FakeProc:
        def cpu_percent(self, interval=0.0):
            calls["n"] += 1
            return 0.0 if calls["n"] == 1 else 42.0

    class _FakeMod:
        def Process(self, pid):
            return _FakeProc()

    cache: dict = {}
    first = pid_cpu_percent(4242, psutil_mod=_FakeMod(), _cache=cache)
    second = pid_cpu_percent(4242, psutil_mod=_FakeMod(), _cache=cache)
    assert first == 0.0
    assert second == 42.0


# --------------------------------------------------------------------------- #
# persistence (tmp_path only)
# --------------------------------------------------------------------------- #
def test_state_persistence_across_ticks(tmp_path):
    state_path = tmp_path / "state.json"
    assert load_state_file(path=state_path) == {}

    r1 = HttpWedgeReaper(clock=lambda: 0.0)
    r1.observe("svc", port_listening=True, probe_timed_out=True,
               probe_elapsed_sec=TIMEOUT_FLOOR_SEC + 1.0, cpu_pct=99.0)
    assert save_state_file(r1.dump_state(), path=state_path) is True

    loaded = load_state_file(path=state_path)
    assert loaded["svc"]["consecutive_timeouts"] == 1

    r2 = HttpWedgeReaper(clock=lambda: 0.0)
    r2.load_state(loaded)
    v = r2.observe("svc", port_listening=True, probe_timed_out=True,
                   probe_elapsed_sec=TIMEOUT_FLOOR_SEC + 1.0, cpu_pct=99.0)
    assert v["detail"]["consecutive_timeouts"] == 2


def test_load_state_file_missing_returns_empty(tmp_path):
    assert load_state_file(path=tmp_path / "nope.json") == {}


def test_load_state_file_garbage_returns_empty(tmp_path):
    p = tmp_path / "garbage.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_state_file(path=p) == {}


def test_write_decisions_writes_honest_note(tmp_path):
    out = tmp_path / "decisions.json"
    ok = write_decisions({"svc": {"name": "svc", "verdict": KEEP, "detail": {}}},
                         out_path=out, now=100.0)
    assert ok is True
    import json
    doc = json.loads(out.read_text(encoding="ascii"))
    assert doc["generated_at"] == 100.0
    assert "honest_note" in doc
    assert "$" not in doc["honest_note"] or "no $ field" in doc["honest_note"]


# --------------------------------------------------------------------------- #
# runner-level orchestration: fake port/http/cpu/kill, never touches real I/O
# --------------------------------------------------------------------------- #
def test_runner_tick_keeps_when_healthy(tmp_path):
    from scripts.platformkit.autonomy.http_wedge_reaper_runner import _Target, tick

    kills = []
    rows = tick(
        now=0.0,
        targets=[_Target(name="svc", port=1234, http_path="/health",
                         match_pattern="fake.module")],
        port_check=lambda port: True,
        http_probe_fn=lambda url: {"timed_out": False, "elapsed_sec": 0.05},
        cpu_probe_fn=lambda pid: 5.0,
        pid_lookup_fn=lambda pattern: 4242,
        killer=lambda pattern: kills.append(pattern) or None,
        load_fn=lambda: {},
        save_fn=lambda state: True,
        write_fn=lambda rows, now=None: True,
    )
    assert rows[0]["verdict"] == KEEP
    assert kills == []


def test_runner_tick_kills_on_sustained_wedge(tmp_path):
    from scripts.platformkit.autonomy.http_wedge_reaper_runner import _Target, tick

    kills = []
    saved_states = {}
    seeded = {"svc": {"name": "svc", "consecutive_timeouts": 2,
                     "cpu_high_since": 0.0, "last_verdict": KEEP,
                     "last_kill_at": None}}
    rows = tick(
        now=CPU_SUSTAINED_SEC + 1.0,
        targets=[_Target(name="svc", port=1234, http_path="/health",
                         match_pattern="fake.module")],
        port_check=lambda port: True,
        http_probe_fn=lambda url: {"timed_out": True,
                                   "elapsed_sec": TIMEOUT_FLOOR_SEC + 1.0},
        cpu_probe_fn=lambda pid: 99.0,
        pid_lookup_fn=lambda pattern: 4242,
        killer=lambda pattern: (kills.append(pattern), 4242)[1],
        load_fn=lambda: seeded,
        save_fn=lambda state: saved_states.update(state) or True,
        write_fn=lambda rows, now=None: True,
    )
    assert rows[0]["verdict"] == KILL
    assert rows[0]["detail"]["killed_pid"] == 4242
    assert kills == ["fake.module"]
    # post-kill state reset persisted.
    assert saved_states["svc"]["consecutive_timeouts"] == 0


def test_runner_tick_port_closed_never_kills(tmp_path):
    from scripts.platformkit.autonomy.http_wedge_reaper_runner import _Target, tick

    kills = []
    rows = tick(
        now=0.0,
        targets=[_Target(name="svc", port=1234, http_path="/health",
                         match_pattern="fake.module")],
        port_check=lambda port: False,
        http_probe_fn=lambda url: {"timed_out": True, "elapsed_sec": 999.0},
        cpu_probe_fn=lambda pid: 99.0,
        pid_lookup_fn=lambda pattern: 4242,
        killer=lambda pattern: kills.append(pattern) or 4242,
        load_fn=lambda: {},
        save_fn=lambda state: True,
        write_fn=lambda rows, now=None: True,
    )
    assert rows[0]["verdict"] == KEEP
    assert kills == []


def test_runner_never_raises_on_target_exception():
    from scripts.platformkit.autonomy.http_wedge_reaper_runner import _Target, tick

    def boom(port):
        raise RuntimeError("socket exploded")

    rows = tick(
        now=0.0,
        targets=[_Target(name="svc", port=1234, http_path="/health",
                         match_pattern="fake.module")],
        port_check=boom,
        load_fn=lambda: {},
        save_fn=lambda state: True,
        write_fn=lambda rows, now=None: True,
    )
    assert rows[0]["verdict"] == KEEP


# --------------------------------------------------------------------------- #
# bridge (documented not-wired convenience function)
# --------------------------------------------------------------------------- #
def test_bridge_standalone_tick_never_raises_and_returns_list():
    from scripts.platformkit.autonomy.http_wedge_supervisor_bridge import (
        run_one_tick_standalone,
    )
    result = run_one_tick_standalone(now=0.0)
    assert isinstance(result, list)
