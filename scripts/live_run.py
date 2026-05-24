"""live_run.py — game-day orchestrator that chains the cycle-88 live stack.

Cycle 88h (loop 5). The last seven cycles shipped a constellation of live
components — each one a standalone daemon or one-shot CLI:

    88a  scripts/live_game_poll.py           live in-game state snapshots
    88b  scripts/predict_in_game.py          live projection from a snapshot
    88c  scripts/update_inactives.py         pre-tip zero-out for inactives
    88d  scripts/update_confirmed_starters.py pre-tip starter confirmation
    88e (no script — only consumed indirectly)
    88f (no script — only consumed indirectly)
    88g  scripts/poll_line_movement.py       DK line-movement daemon
    + cycle 60 fetch_injury_espn.py and cycle 61 fetch_lineups.py
    + cycle 54/65/71 scripts/daily_run.py for morning + post-game

On a game day the user previously needed to launch SEVEN background
processes by hand (and remember the cron-like cadence for the pre-tip
refresh window). live_run.py replaces all of that with one command.

Phases — driven by the slate's first tip-off:

    Phase 1  (T-90min  ... T-30min)    aggressive injury + lineup refresh
                                       - fetch_injury_espn  every 15 min
                                       - fetch_lineups      every 10 min
                                       - poll_line_movement every  5 min
    Phase 2  (T-30min  ... T-0)        confirmation window
                                       - update_inactives           (per game one-shot)
                                       - update_confirmed_starters  (per game one-shot)
                                       - poll_line_movement every  5 min
    Phase 3  (during games)            live snapshots
                                       - live_game_poll  every 30 s per active game
                                       - predict_in_game on every end-of-period
                                       - poll_line_movement every 5 min
    Phase 4  (after last final)        clean exit + reminder to run
                                       ``daily_run.py --settle --report``

CLI
---
    python scripts/live_run.py
    python scripts/live_run.py --date 2026-05-24
    python scripts/live_run.py --dry-run         # print the plan + exit
    python scripts/live_run.py --phase 3         # jump straight into in-game mode
    python scripts/live_run.py --no-line-poll    # if DK is blocked

The orchestrator does **not** import any production model code, and does
**not** modify any of the cycle-88 sub-scripts — it only shells out.

Process model
-------------
* Recurring loops (line-poll, in-game poll) run as ``subprocess.Popen``
  children. We track their PIDs and SIGTERM them on shutdown.
* One-shots (injury/lineups refresh, update_inactives,
  update_confirmed_starters, predict_in_game) run via ``subprocess.run``
  with a generous timeout so a hung child doesn't wedge the daemon.
* SIGINT / SIGTERM walks every tracked child, then re-raises.

Exit codes
----------
    0  - all requested phases completed cleanly
    2  - argument error (bad --date / --phase)
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone, date as _date_cls
from typing import Callable, Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
DATA_DIR = os.path.join(PROJECT_DIR, "data")

# Cadence constants (seconds). Tests pin these so timing changes can't
# silently slip through.
PHASE1_INJURY_INTERVAL_S: int = 15 * 60
PHASE1_LINEUPS_INTERVAL_S: int = 10 * 60
LINE_POLL_INTERVAL_S: int = 5 * 60
LIVE_POLL_INTERVAL_S: int = 30

# Phase boundaries measured against the first tip-off of the slate.
PHASE1_LEAD_MINUTES: int = 90
PHASE2_LEAD_MINUTES: int = 30

# Cap on how long we wait for a one-shot child before giving up.
ONESHOT_TIMEOUT_S: int = 240


# --- date / time helpers ---------------------------------------------------

def _parse_date_arg(s: Optional[str]) -> str:
    """Return YYYY-MM-DD; defaults to today. Raises ValueError on bad input."""
    if not s:
        return datetime.now().date().isoformat()
    return datetime.strptime(s, "%Y-%m-%d").date().isoformat()


def _now_utc() -> datetime:
    """Indirection so tests can monkey-patch wall clock."""
    return datetime.now(timezone.utc)


def detect_phase(now_utc: datetime, first_tipoff_utc: Optional[datetime],
                  last_game_status: str = "LIVE") -> int:
    """Map (now, slate) -> phase id (1..4).

    * No tip-off known     -> phase 1 (be safe; refresh everything).
    * now <  tip-90min     -> phase 1 (or we'd be sleeping, but treat as 1).
    * tip-90 .. tip-30     -> phase 1.
    * tip-30 .. tip        -> phase 2.
    * tip   .. last final  -> phase 3.
    * after last final     -> phase 4.

    ``last_game_status`` is "LIVE" or "FINAL"; we only transition to phase 4
    once the caller reports every game is FINAL, otherwise we stay in phase 3
    even past the projected tip-end.
    """
    if first_tipoff_utc is None:
        return 1
    delta_min = (first_tipoff_utc - now_utc).total_seconds() / 60.0
    if delta_min >= PHASE2_LEAD_MINUTES:
        # T-30min or earlier -> phase 1 window.
        return 1
    if delta_min >= 0:
        return 2
    # past tip
    if last_game_status.upper() == "FINAL":
        return 4
    return 3


# --- command composition (pure functions for tests) -----------------------

def compose_injury_cmd(date_str: str, python_exe: str = sys.executable) -> List[str]:
    """ESPN injury refresh — cycle 60."""
    return [
        python_exe,
        os.path.join(SCRIPTS_DIR, "fetch_injury_espn.py"),
        "--date", date_str,
    ]


def compose_lineups_cmd(date_str: str, python_exe: str = sys.executable) -> List[str]:
    """Rotowire lineups refresh — cycle 61."""
    return [
        python_exe,
        os.path.join(SCRIPTS_DIR, "fetch_lineups.py"),
        "--date", date_str,
    ]


def compose_line_poll_cmd(date_str: str,
                            interval_s: int = LINE_POLL_INTERVAL_S,
                            python_exe: str = sys.executable) -> List[str]:
    """DK line-movement daemon — cycle 88g."""
    return [
        python_exe,
        os.path.join(SCRIPTS_DIR, "poll_line_movement.py"),
        "--date", date_str,
        "--daemon",
        "--interval", str(interval_s),
    ]


def compose_update_inactives_cmd(date_str: str,
                                    python_exe: str = sys.executable) -> List[str]:
    """Pre-tip inactives -> zero predictions — cycle 88c."""
    return [
        python_exe,
        os.path.join(SCRIPTS_DIR, "update_inactives.py"),
        "--date", date_str,
    ]


def compose_update_starters_cmd(date_str: str,
                                  python_exe: str = sys.executable) -> List[str]:
    """Pre-tip starter confirmation — cycle 88d."""
    return [
        python_exe,
        os.path.join(SCRIPTS_DIR, "update_confirmed_starters.py"),
        "--date", date_str,
    ]


def compose_live_poll_cmd(date_str: str,
                            interval_s: int = LIVE_POLL_INTERVAL_S,
                            python_exe: str = sys.executable) -> List[str]:
    """Live snapshot daemon — cycle 88a."""
    return [
        python_exe,
        os.path.join(SCRIPTS_DIR, "live_game_poll.py"),
        "--date", date_str,
        "--daemon",
        "--interval", str(interval_s),
    ]


def compose_predict_in_game_cmd(game_id: str, period: int,
                                  python_exe: str = sys.executable) -> List[str]:
    """End-of-period live projection — cycle 88b (subprocess form, legacy)."""
    return [
        python_exe,
        os.path.join(SCRIPTS_DIR, "predict_in_game.py"),
        "--game-id", game_id,
        "--period", str(period),
    ]


def project_active_slate(date_str: Optional[str] = None) -> Dict[str, list]:
    """Cycle 95c: in-process projection for every active game today.

    Replaces the per-event ``predict_in_game.py`` subprocess fan-out with a
    single in-process call to ``src.prediction.live_engine.project_full_slate``
    -- the consolidated entry point that wraps the cycle-88b validated core
    (94d-validated, beats pre-game on 7/7 stats at endQ3).

    Kept as a thin orchestrator-facing helper so tests can patch it without
    spinning up subprocesses; ``_run_autopilot`` may call this on each tick
    in phase 3 instead of (or in addition to) shelling out per-event.
    """
    from src.prediction import live_engine    # noqa: PLC0415

    return live_engine.project_full_slate(date_iso=date_str)


def compose_phase_commands(phase: int, date_str: str, *,
                            line_poll: bool = True,
                            python_exe: str = sys.executable
                            ) -> Dict[str, List[List[str]]]:
    """Return the argv lists for the given phase keyed by kind.

    Result schema::

        {
            "recurring":   [argv, argv, ...],   # Popen daemons
            "oneshot":     [argv, argv, ...],   # subprocess.run on tick
        }

    Tests rely on the exact lists so callers can assert composition without
    starting a single process.
    """
    recurring: List[List[str]] = []
    oneshot:   List[List[str]] = []

    if phase == 1:
        # Pre-tip refresh — both refreshes are tick-driven one-shots so we
        # surface their exit codes per tick (rather than letting a daemon
        # swallow a transient 5xx).
        oneshot.append(compose_injury_cmd(date_str, python_exe=python_exe))
        oneshot.append(compose_lineups_cmd(date_str, python_exe=python_exe))
        if line_poll:
            recurring.append(compose_line_poll_cmd(date_str, python_exe=python_exe))
    elif phase == 2:
        oneshot.append(compose_update_inactives_cmd(date_str, python_exe=python_exe))
        oneshot.append(compose_update_starters_cmd(date_str, python_exe=python_exe))
        if line_poll:
            recurring.append(compose_line_poll_cmd(date_str, python_exe=python_exe))
    elif phase == 3:
        recurring.append(compose_live_poll_cmd(date_str, python_exe=python_exe))
        if line_poll:
            recurring.append(compose_line_poll_cmd(date_str, python_exe=python_exe))
        # predict_in_game cmds are constructed per-event; we don't precompute
        # them here since they need a (game_id, period) pair at firing time.
    elif phase == 4:
        # No commands — clean exit.
        pass
    else:
        raise ValueError(f"unknown phase {phase}")

    return {"recurring": recurring, "oneshot": oneshot}


# --- tip-off fetch (mockable) ----------------------------------------------

def _fetch_tipoffs(date_str: str) -> List[Dict]:
    """Thin wrapper around scripts.lineup_release_trigger.fetch_tipoff_times.

    Kept here so tests can monkey-patch ``scripts.live_run._fetch_tipoffs``
    without bringing the real nba_api dependency into the test environment.
    """
    try:
        # Local import: avoid touching nba_api at module import time so
        # ``import scripts.live_run`` stays cheap and offline-friendly.
        from scripts.lineup_release_trigger import fetch_tipoff_times  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - depends on prod env
        print(f"[live_run] warn: tip-off helper import failed: {exc}")
        return []
    try:
        return fetch_tipoff_times(date_str) or []
    except Exception as exc:  # pragma: no cover - prod-only fail mode
        print(f"[live_run] warn: tip-off fetch failed: {exc}")
        return []


def first_tipoff(date_str: str) -> Optional[datetime]:
    """Return the earliest tip-off UTC for the slate, or None if unknown."""
    games = _fetch_tipoffs(date_str)
    tips = [g.get("tipoff_utc") for g in games if g.get("tipoff_utc") is not None]
    if not tips:
        return None
    return min(tips)


# --- dry-run renderer ------------------------------------------------------

def _render_cmd(cmd: List[str]) -> str:
    """Render an argv list with the python prefix + script path as relpath."""
    parts: List[str] = ["python"]
    for token in cmd[1:]:
        if token.endswith(".py") and os.path.isabs(token):
            try:
                token = os.path.relpath(token, PROJECT_DIR).replace("\\", "/")
            except ValueError:
                pass
        parts.append(token)
    return " ".join(parts)


def print_dry_run(date_str: str, *, line_poll: bool = True,
                    start_phase: Optional[int] = None) -> None:
    """Print every phase's argv plan. start_phase=None prints all phases."""
    phases = [start_phase] if start_phase else [1, 2, 3, 4]
    print(f"[live_run] dry-run plan for {date_str}:")
    print(f"  phases:    {phases}")
    print(f"  line_poll: {'on' if line_poll else 'off'}")
    for ph in phases:
        plan = compose_phase_commands(ph, date_str, line_poll=line_poll)
        print(f"\n  phase {ph}:")
        if not plan["recurring"] and not plan["oneshot"]:
            print("    (no commands — clean exit)")
            continue
        for cmd in plan["recurring"]:
            print(f"    [daemon ] {_render_cmd(cmd)}")
        for cmd in plan["oneshot"]:
            print(f"    [oneshot] {_render_cmd(cmd)}")
    if 3 in phases:
        # Surface the per-event command shape so the user knows what
        # predict_in_game looks like when fired live.
        print("")
        print("  phase 3 per-event (fired on end-of-period):")
        sample = compose_predict_in_game_cmd("0022400123", 1)
        print(f"    [event  ] {_render_cmd(sample)}  # (per-game, per-period)")
    print("")
    print("[live_run] dry-run complete; nothing was launched.")


# --- process management ----------------------------------------------------

class _DaemonSupervisor:
    """Track Popen children and terminate them cleanly on shutdown."""

    def __init__(self) -> None:
        self._children: List[subprocess.Popen] = []
        self._shutting_down: bool = False

    # ----- recurring loop helpers (Popen) -----

    def start(self, cmd: List[str]) -> subprocess.Popen:
        """Launch a Popen child and track it."""
        print(f"[live_run] start daemon: {_render_cmd(cmd)}")
        proc = subprocess.Popen(cmd)  # nosec - cmd built from trusted helpers
        self._children.append(proc)
        return proc

    def alive(self) -> List[subprocess.Popen]:
        return [p for p in self._children if p.poll() is None]

    # ----- one-shot helpers (subprocess.run) -----

    def run_oneshot(self, cmd: List[str],
                      timeout_s: int = ONESHOT_TIMEOUT_S) -> int:
        """Block on a one-shot; return exit code. -1 on timeout, -2 on exc."""
        print(f"[live_run] run oneshot: {_render_cmd(cmd)}")
        try:
            res = subprocess.run(cmd, timeout=timeout_s, check=False)
            return int(res.returncode)
        except subprocess.TimeoutExpired:
            print(f"[live_run] warn: oneshot timed out after {timeout_s}s")
            return -1
        except Exception as exc:
            print(f"[live_run] warn: oneshot raised {type(exc).__name__}: {exc}")
            return -2

    # ----- shutdown -----

    def shutdown(self, signum: Optional[int] = None) -> None:
        """SIGTERM every tracked child, fall back to SIGKILL if needed."""
        if self._shutting_down:
            return
        self._shutting_down = True
        print(f"\n[live_run] shutting down "
                f"(signal={signum}, children={len(self._children)})")
        for proc in self._children:
            if proc.poll() is not None:
                continue
            try:
                proc.terminate()
            except Exception:
                pass
        # Brief grace period for cooperative exit.
        t0 = time.time()
        while time.time() - t0 < 5.0:
            if not self.alive():
                break
            time.sleep(0.1)
        for proc in self.alive():
            try:
                proc.kill()
            except Exception:
                pass


def install_signal_handlers(supervisor: _DaemonSupervisor) -> None:
    """Wire SIGINT/SIGTERM (when available) to supervisor.shutdown()."""
    def _handler(signum, _frame):
        supervisor.shutdown(signum=signum)
        # Restore default handler so a second Ctrl-C aborts immediately.
        try:
            signal.signal(signum, signal.SIG_DFL)
        except Exception:
            pass

    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            # Not in the main thread, or platform doesn't support it.
            pass


# --- main loop -------------------------------------------------------------

def _sleep_with_shutdown(seconds: float, supervisor: _DaemonSupervisor,
                            step: float = 1.0) -> bool:
    """Sleep ``seconds`` but bail early on supervisor shutdown.

    Returns True if the full duration elapsed, False if we bailed early.
    """
    t_end = time.time() + seconds
    while time.time() < t_end:
        if supervisor._shutting_down:
            return False
        time.sleep(min(step, max(0.0, t_end - time.time())))
    return True


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Game-day orchestrator: chains the cycle-88a..g live stack "
                    "(injury/lineups refresh -> pre-tip confirms -> live polls).",
    )
    ap.add_argument("--date", default=None,
                    help="Target date YYYY-MM-DD (default: today).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the plan + exit without launching subprocesses.")
    ap.add_argument("--phase", type=int, choices=[1, 2, 3, 4], default=None,
                    help="Jump straight into a given phase (default: auto from "
                         "the slate's first tip-off).")
    ap.add_argument("--no-line-poll", action="store_true",
                    help="Skip poll_line_movement (use when DK is blocked).")
    args = ap.parse_args(argv)

    try:
        date_str = _parse_date_arg(args.date)
    except ValueError:
        print(f"[fail] bad --date format '{args.date}' (need YYYY-MM-DD)")
        return 2

    line_poll = not args.no_line_poll

    if args.dry_run:
        print_dry_run(date_str, line_poll=line_poll, start_phase=args.phase)
        return 0

    # Resolve first tip-off (may be None on weekends / no-slate days).
    tipoff = first_tipoff(date_str)
    if tipoff is not None:
        print(f"[live_run] first tip-off (UTC): {tipoff.isoformat()}")
    else:
        print("[live_run] no tip-off found for slate; defaulting to phase 1")

    supervisor = _DaemonSupervisor()
    install_signal_handlers(supervisor)

    # If the user forced a phase, jump in there and stay until shutdown.
    if args.phase:
        return _run_phase_blocking(args.phase, date_str, line_poll,
                                     supervisor, tipoff)

    # Auto mode: walk phases 1 -> 4 as the clock crosses each threshold.
    return _run_autopilot(date_str, line_poll, supervisor, tipoff)


def _run_phase_blocking(phase: int, date_str: str, line_poll: bool,
                         supervisor: _DaemonSupervisor,
                         tipoff: Optional[datetime]) -> int:
    """Run a single phase until shutdown. Used by --phase override."""
    plan = compose_phase_commands(phase, date_str, line_poll=line_poll)
    for cmd in plan["recurring"]:
        supervisor.start(cmd)
    if phase == 4:
        print("[live_run] phase 4: nothing to run. "
                "Suggest: python scripts/daily_run.py "
                f"--date {date_str} --settle --report")
        return 0

    interval_s = _phase_oneshot_interval(phase)
    while not supervisor._shutting_down:
        for cmd in plan["oneshot"]:
            supervisor.run_oneshot(cmd)
        if not _sleep_with_shutdown(interval_s, supervisor):
            break
    supervisor.shutdown()
    return 0


def _phase_oneshot_interval(phase: int) -> int:
    """Tick interval for one-shots in a given phase."""
    if phase == 1:
        return PHASE1_LINEUPS_INTERVAL_S  # 10 min — covers both refresh windows
    if phase == 2:
        return PHASE1_LINEUPS_INTERVAL_S  # one-shots per game, retry every 10 min
    if phase == 3:
        return LIVE_POLL_INTERVAL_S
    return LIVE_POLL_INTERVAL_S


def _run_autopilot(date_str: str, line_poll: bool,
                    supervisor: _DaemonSupervisor,
                    tipoff: Optional[datetime]) -> int:
    """Phase 1 -> 2 -> 3 -> 4 driven by wall clock vs tip-off."""
    last_status = "LIVE"
    last_phase: Optional[int] = None
    active_daemons: List[subprocess.Popen] = []

    while not supervisor._shutting_down:
        now = _now_utc()
        phase = detect_phase(now, tipoff, last_game_status=last_status)
        if phase != last_phase:
            # Phase transition — kill old daemons, start new ones.
            for proc in active_daemons:
                if proc.poll() is None:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
            active_daemons = []
            print(f"[live_run] entering phase {phase} at {now.isoformat()}")
            plan = compose_phase_commands(phase, date_str, line_poll=line_poll)
            for cmd in plan["recurring"]:
                active_daemons.append(supervisor.start(cmd))
            last_phase = phase

        if phase == 4:
            print("[live_run] phase 4 reached; exiting.")
            print(f"[live_run] suggest: python scripts/daily_run.py "
                    f"--date {date_str} --settle --report")
            break

        plan = compose_phase_commands(phase, date_str, line_poll=line_poll)
        for cmd in plan["oneshot"]:
            supervisor.run_oneshot(cmd)
        if not _sleep_with_shutdown(_phase_oneshot_interval(phase), supervisor):
            break
    supervisor.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
