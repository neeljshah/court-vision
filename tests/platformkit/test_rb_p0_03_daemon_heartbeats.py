"""RB-P0-03 + readiness-coverage probes (non-gated fix verification).

Closes two unattended-readiness gaps WITHOUT crossing a human gate:

GAP 1 (stale-green): m1_paper (auto_loop) + m1_line_daemon (line_snapshot_daemon)
  used to boot readiness=NONE and emit NO heartbeat -- a hung loop read READY
  forever. They now BEAT their declared heartbeat every cycle and stack_specs
  flips them to kind=HEARTBEAT. These tests prove (a) the loops beat each cycle
  offline, (b) the spec is HEARTBEAT with the declared path, and (c) the
  supervisor's health.probe reads ABSENT and STALE heartbeats as NOT-READY (no
  stale-green) while a FRESH heartbeat reads ready.

GAP 2 (untested once-ticks): m6 live_loop.poll_once, m7 ingame_refresh run, and
  inplay_runner.run once-tick now have injected-clock heartbeat-emit probes
  mirroring the m4/m5 pattern, so their offline heartbeat-on-tick is verified.

NO real network, NO real sentinel, NO flag flip, NO money, NO process spawned.
Per-file test only. ASCII only.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------- #
# GAP 1a -- the two loops BEAT their heartbeat every cycle (offline, fake clock)
# --------------------------------------------------------------------------- #

def test_auto_loop_beats_m1_paper_heartbeat_each_cycle():
    from scripts.platformkit.pm_trading import auto_loop as al
    beats = []
    # monkeypatch the loop's _beat so we never touch the REAL heartbeat path.
    orig = al._beat
    al._beat = lambda now=None: beats.append(now)  # type: ignore
    try:
        t = [0.0]
        rc = al.main(["--forever", "--interval", "60"],
                     run_fn=lambda: {"summary": {"n": 0}},
                     sleep=lambda s: t.__setitem__(0, t[0] + s),
                     clock=lambda: t[0],
                     max_cycles=3)
        assert rc == 0
    finally:
        al._beat = orig  # type: ignore
    # boot beat (1) + one beat per cycle (3) = 4 beats; each cycle definitely beat.
    assert len(beats) >= 4, "auto_loop did not beat every cycle: %r" % beats
    assert al.HEARTBEAT_COMPONENT == "m1_paper"
    print("OK auto_loop: beats m1_paper heartbeat at boot + every cycle (offline)")


def test_line_daemon_beats_m1_line_daemon_heartbeat_each_tick():
    from scripts.platformkit.odds_provider import line_snapshot_daemon as d
    beats = []
    orig = d._beat
    d._beat = lambda now=None: beats.append(now)  # type: ignore
    try:
        base = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            ticks = d.serve_forever(
                interval=60, sports=("nba",),
                clock=lambda: base,
                sleep=lambda s: None,
                max_ticks=3, out_dir=Path(td),
                agg_fn=lambda sport, now=None: {"status": "ok", "events": []})
        assert len(ticks) == 3
    finally:
        d._beat = orig  # type: ignore
    # boot beat (1) + one per tick (3) = 4; never stale-green.
    assert len(beats) >= 4, "line daemon did not beat every tick: %r" % beats
    assert d.HEARTBEAT_COMPONENT == "m1_line_daemon"
    print("OK line_snapshot_daemon: beats m1_line_daemon at boot + every tick")


# --------------------------------------------------------------------------- #
# GAP 1b -- the supervisor spec is HEARTBEAT (not NONE) for both
# --------------------------------------------------------------------------- #

def test_stack_specs_paper_and_line_are_heartbeat_readiness():
    from supervisor.manifest import manifest, HEARTBEAT
    specs = {s.name: s for s in manifest("default")}
    for name, hb_leaf in (("m1_paper", "m1_paper.txt"),
                          ("m1_line_daemon", "m1_line_daemon.txt")):
        sp = specs[name]
        assert sp.readiness.kind == HEARTBEAT, "%s is not HEARTBEAT readiness" % name
        assert sp.readiness.heartbeat_path, "%s has no heartbeat_path" % name
        assert sp.readiness.heartbeat_path.endswith(hb_leaf)
        # fresh window must exceed each loop's slowest cadence (no flicker).
        assert sp.readiness.fresh_sec >= 2700.0
    print("OK stack_specs: m1_paper + m1_line_daemon are HEARTBEAT (no stale-green NONE)")


# --------------------------------------------------------------------------- #
# GAP 1c -- supervisor health.probe: absent/stale -> NOT-READY, fresh -> ready
# --------------------------------------------------------------------------- #

def test_health_probe_absent_and_stale_heartbeat_not_ready():
    from supervisor import health
    from supervisor.manifest import ProcSpec, ReadinessSpec, HEARTBEAT
    with tempfile.TemporaryDirectory() as td:
        hb = Path(td) / "m1_paper.txt"
        spec = ProcSpec(
            name="m1_paper", kind="py", module="x",
            readiness=ReadinessSpec(kind=HEARTBEAT, heartbeat_path=str(hb),
                                    fresh_sec=2700.0))
        now = 1_000_000.0
        # (1) ABSENT heartbeat -> not ready (fresh boot, not yet beating).
        r_absent = health.probe(spec, clock=lambda: now)
        assert r_absent["ready"] is False
        assert r_absent["detail"]["reason"] == "absent"
        # (2) FRESH heartbeat (mtime = now) -> ready.
        hb.write_text("2026-06-19T12:00:00Z", encoding="ascii")
        os.utime(str(hb), (now, now))
        r_fresh = health.probe(spec, clock=lambda: now + 10.0)
        assert r_fresh["ready"] is True, r_fresh
        # (3) STALE heartbeat (mtime far in the past = a hung loop) -> not ready.
        os.utime(str(hb), (now - 9999.0, now - 9999.0))
        r_stale = health.probe(spec, clock=lambda: now)
        assert r_stale["ready"] is False
        assert r_stale["detail"]["reason"] == "stale"
    print("OK health.probe: absent + stale heartbeat -> NOT-READY, fresh -> ready")


# --------------------------------------------------------------------------- #
# GAP 2 -- m6 / m7 / inplay once-tick heartbeat-emit (offline, injected clock)
# --------------------------------------------------------------------------- #

def test_m6_live_loop_poll_once_writes_heartbeat_offline():
    from scripts.platformkit.ingame import live_loop as ll
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        # empty fetch = quiet slate: still writes a (non-fabricated) heartbeat.
        hb = ll.poll_once(now="2026-06-19T12:00:00Z",
                          fetch=lambda sport: {"status": "ok", "games": []},
                          out_dir=out)
        assert isinstance(hb, dict)
        assert (out / "_heartbeat.json").exists(), "m6 did not write heartbeat on quiet slate"
    print("OK m6 live_loop.poll_once: writes heartbeat offline (quiet slate, no fab game)")


def test_m7_refresh_run_beats_heartbeat_each_cycle_offline():
    from scripts.platformkit.ingame import ingame_refresh_runner_svc as svc
    beats = []
    orig = svc._beat
    svc._beat = lambda now=None: beats.append(now)  # type: ignore
    try:
        t = [0.0]
        with tempfile.TemporaryDirectory() as td:
            svc.run(sports=("nba",),
                    settled_games_fn=lambda sport, **k: [],
                    cadence_sec=1.0,
                    clock=lambda: t[0],
                    sleep=lambda s: t.__setitem__(0, t[0] + s),
                    max_cycles=2,
                    ckpt_path=str(Path(td) / "ckpt.json"))
    finally:
        svc._beat = orig  # type: ignore
    assert len(beats) >= 2, "m7 did not beat each cycle: %r" % beats
    print("OK m7 ingame_refresh.run: beats heartbeat each cycle (offline, empty feed)")


def test_inplay_runner_run_beats_heartbeat_at_boot_offline():
    from scripts.platformkit.odds_provider import inplay_runner as ir
    beats = []
    orig = ir._beat
    ir._beat = lambda now=None: beats.append(now)  # type: ignore
    try:
        with tempfile.TemporaryDirectory() as td:
            # serve_inplay_forever's clock returns a datetime; the runner reuses it
            # for the heartbeat too, so pass a datetime-returning clock.
            fixed = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)
            ir.run(sports=("nba",), interval=1, idle_interval=1,
                   sleep=lambda s: None,
                   clock=lambda: fixed,
                   max_ticks=2, out_dir=Path(td),
                   fetch_fn=lambda sport: [])
    finally:
        ir._beat = orig  # type: ignore
    # boot beat (1) + one per wake boundary; the loop returns before sleeping
    # after the final tick, so max_ticks=2 -> boot + 1 wake-beat = 2 (>=2).
    assert len(beats) >= 2, "inplay_runner did not beat at boot + each tick: %r" % beats
    assert ir.HEARTBEAT_COMPONENT == "m2_inplay"
    print("OK inplay_runner.run: beats m2_inplay at boot + every tick (offline)")


# --------------------------------------------------------------------------- #
# REAL-SENTINEL / INERT re-confirm (defense-in-depth, no new sentinel created)
# --------------------------------------------------------------------------- #

def test_real_sentinel_absent_and_loop_stays_inert():
    from scripts.platformkit.improve.pipeline_flag import pipeline_enabled, SENTINEL_PATH
    assert not SENTINEL_PATH.exists(), "REAL sentinel present -- must stay absent"
    assert pipeline_enabled() is False
    print("OK sentinel ABSENT + pipeline INERT (no sentinel created by this fix)")
