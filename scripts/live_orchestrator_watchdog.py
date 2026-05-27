"""live_orchestrator_watchdog.py - guardian for the in-game live daemon stack.

Why this exists (iter-27)
-------------------------
Iter-26 forensics found the in-game system was COMPLETELY DARK during WCF G7
(00:35-02:50 UTC). live_orchestrator / pbp_poller / box_snapshot_poller /
lineup_tracker / middle_finder_daemon / clv_tracker_daemon were all silent.
The headline product (in-play edge at +80% ROI vs +42% pregame) sat unused.

This watchdog mirrors the closing_capture_watchdog.py pattern: poll heartbeat
files, respawn any silently-dead daemon via subprocess.Popen, and log to
data/cache/daemon_heartbeats/watchdog.log. It is idempotent — if a healthy PID
exists in tasklist we never respawn.

Heartbeat schema quirk
----------------------
Some heartbeat files contain ISO timestamps (e.g. clv_tracker_daemon.txt =
"2026-05-26T21:11:57Z"). Others contain a unix-epoch int written by
live_orchestrator._heartbeat_loop (~1.78e9). A third flavour is a small tick
counter (pbp_poller / lineup_tracker write monotonically-increasing ints like
207743). _heartbeat_age_seconds() disambiguates by magnitude:
  * value > 1e9  -> treat as unix epoch
  * looks like ISO (contains "T" or "-") -> parse with fromisoformat
  * otherwise treat as tick counter -> fall back to file mtime for age, AND
    remember the previous tick value so a non-incrementing counter also flags.

CLI
---
    # Watch the in-play stack for tonight's game (auto-detect game id):
    python scripts/live_orchestrator_watchdog.py

    # Pin a specific game:
    python scripts/live_orchestrator_watchdog.py --game-id 0042500317

    # Smoke test — print status RIGHT NOW, do not respawn:
    python scripts/live_orchestrator_watchdog.py --smoke-test
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_HEARTBEAT_DIR = _ROOT / "data" / "cache" / "daemon_heartbeats"
_WATCHDOG_LOG = _HEARTBEAT_DIR / "watchdog.log"

# Daemons in the in-game critical set. Maps heartbeat-file stem -> script path.
# These are the daemons that, if dead during an active window, cause the
# in-play edge to disappear (this is exactly the failure iter-26 documented).
_CRITICAL: Dict[str, Path] = {
    "live_orchestrator":    _HERE / "live_orchestrator.py",
    "pbp_poller":           _HERE / "pbp_poller.py",
    "box_snapshot_poller":  _HERE / "box_snapshot_poller.py",
    "lineup_tracker":       _HERE / "lineup_tracker.py",
    "middle_finder_daemon": _HERE / "middle_finder_daemon.py",
    "clv_tracker_daemon":   _HERE / "clv_tracker_daemon.py",
}

# Tick-counter memory across watchdog ticks so we can detect frozen counters.
_TICK_MEMORY: Dict[str, Tuple[int, float]] = {}

DEFAULT_STALE_SEC = 300        # 5 min
DEFAULT_POLL_SEC = 60          # 1 min
DEFAULT_WINDOW_HOURS = 4.0     # fallback if no tipoff detected


# ── logging ──────────────────────────────────────────────────────────────
def _log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).isoformat()}] {msg}"
    print(line, flush=True)
    try:
        _HEARTBEAT_DIR.mkdir(parents=True, exist_ok=True)
        with _WATCHDOG_LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:  # noqa: BLE001
        pass


# ── heartbeat parsing (handles all 3 schemas) ────────────────────────────
def _heartbeat_age_seconds(name: str) -> Tuple[Optional[float], str]:
    """Return (age_in_seconds, schema_tag) for the given daemon's heartbeat.

    schema_tag is one of: "iso", "epoch", "tick", "tick-frozen", "missing".
    age_in_seconds is None if unreadable.

    For tick counters: compares the current tick value against the value
    last seen on a previous watchdog tick. If unchanged AND the file mtime
    hasn't moved forward, we synthesize a large "age" so the caller flags it.
    """
    path = _HEARTBEAT_DIR / f"{name}.txt"
    if not path.exists():
        return None, "missing"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001
        return None, "missing"
    if not text:
        return None, "missing"

    # 1) ISO timestamp?
    if "T" in text and ("-" in text or ":" in text):
        try:
            iso = text.split("\t", 1)[0].rstrip("Z")
            ts = datetime.fromisoformat(iso)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - ts).total_seconds(), "iso"
        except Exception:  # noqa: BLE001
            pass

    # 2) Numeric — could be epoch or tick.
    try:
        val = int(float(text))
    except Exception:  # noqa: BLE001
        # Unknown format; fall back to mtime.
        age = time.time() - path.stat().st_mtime
        return age, "mtime-fallback"

    now = time.time()
    if val > 1_000_000_000:  # > year 2001 in unix epoch == real epoch
        return now - val, "epoch"

    # Tick counter. Compare against memory.
    prev = _TICK_MEMORY.get(name)
    mtime = path.stat().st_mtime
    _TICK_MEMORY[name] = (val, mtime)
    if prev is None:
        # First sighting — use mtime so we don't over-respawn on cold start.
        return now - mtime, "tick"
    prev_val, prev_mtime = prev
    if val > prev_val:
        # Counter is moving — daemon alive. Age = now - mtime.
        return now - mtime, "tick"
    # Counter frozen since last watchdog tick. Age = seconds since we
    # first noticed the freeze (== now - prev_mtime).
    return now - prev_mtime, "tick-frozen"


# ── process detection ────────────────────────────────────────────────────
def _running_pids(script_basename: str) -> List[int]:
    """Return python.exe PIDs whose command-line mentions `script_basename`.

    Prefers psutil if installed. Falls back to PowerShell Get-WmiObject so
    we don't introduce a pip dependency.
    """
    try:
        import psutil  # type: ignore
        pids: List[int] = []
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = (p.info.get("name") or "").lower()
                if "python" not in name:
                    continue
                cmd = " ".join(p.info.get("cmdline") or [])
                if script_basename in cmd:
                    pids.append(p.info["pid"])
            except Exception:  # noqa: BLE001
                continue
        return pids
    except ImportError:
        pass

    # Fallback: PowerShell WMI query (same approach as closing_capture_watchdog).
    try:
        out = subprocess.check_output(
            [
                "powershell", "-NoProfile", "-Command",
                (
                    "Get-WmiObject Win32_Process -Filter \"Name='python.exe'\" "
                    f"| Where-Object {{ $_.CommandLine -like '*{script_basename}*' }} "
                    "| Select-Object -ExpandProperty ProcessId"
                ),
            ],
            stderr=subprocess.STDOUT,
            timeout=20,
        ).decode(errors="ignore")
        return [int(x.strip()) for x in out.splitlines() if x.strip().isdigit()]
    except Exception as exc:  # noqa: BLE001
        _log(f"pid lookup failed for {script_basename}: {exc}")
        return []


# ── respawn ──────────────────────────────────────────────────────────────
def _respawn(name: str, script: Path, game_id: Optional[str]) -> Optional[int]:
    py = sys.executable or "python"
    cmd: List[str] = [py, "-u", str(script)]
    # live_orchestrator + the in-game daemons accept --game-id; pass it when known.
    if game_id and name in (
        "live_orchestrator", "pbp_poller", "box_snapshot_poller",
        "lineup_tracker", "middle_finder_daemon", "clv_tracker_daemon",
    ):
        cmd += ["--game-id", game_id]
    if name == "live_orchestrator":
        cmd += ["--headless"]
    try:
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        creationflags = (DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
        proc = subprocess.Popen(
            cmd,
            cwd=str(_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            creationflags=creationflags,
        )
        _log(f"RESPAWN {name}: pid={proc.pid} cmd={' '.join(cmd)}")
        return proc.pid
    except Exception as exc:  # noqa: BLE001
        _log(f"RESPAWN FAILED {name}: {exc} cmd={' '.join(cmd)}")
        return None


# ── game window detection ────────────────────────────────────────────────
def _autodetect_game(date_str: str) -> Tuple[Optional[str], Optional[datetime]]:
    """Inspect tonight_bets_registered.json for game id + tipoff. NO NBA API."""
    p = _ROOT / "data" / "cache" / f"intel_{date_str}" / "tonight_bets_registered.json"
    if not p.exists():
        return None, None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None, None
    gid = data.get("game_id")
    tip = data.get("tip_off_utc")
    tip_dt: Optional[datetime] = None
    if tip:
        try:
            tip_dt = datetime.fromisoformat(tip.rstrip("Z")).replace(tzinfo=timezone.utc)
        except Exception:  # noqa: BLE001
            tip_dt = None
    return gid, tip_dt


def _compute_window(tip_dt: Optional[datetime]) -> Tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if tip_dt is None:
        # Fallback 4h window starting now.
        return now, now + timedelta(hours=DEFAULT_WINDOW_HOURS)
    start = tip_dt - timedelta(minutes=30)
    # 3h game + 15min grace ≈ final_buzzer + 15 = tip + 3h15m.
    end = tip_dt + timedelta(hours=3, minutes=15)
    return start, end


# ── one watchdog tick ────────────────────────────────────────────────────
def _tick(stale_after: int, smoke: bool,
          game_id: Optional[str]) -> List[Tuple[str, str, Optional[float], List[int], bool]]:
    """Inspect every critical daemon. Returns rows of:
       (name, schema_tag, age_sec, pids, respawned).
    """
    rows: List[Tuple[str, str, Optional[float], List[int], bool]] = []
    for name, script in _CRITICAL.items():
        age, schema = _heartbeat_age_seconds(name)
        pids = _running_pids(script.name)
        dead = False
        if not pids:
            if age is None:
                dead = True  # missing heartbeat AND no PID
            elif schema == "tick-frozen":
                dead = True
            elif age > stale_after:
                dead = True

        respawned = False
        if dead and not smoke:
            new_pid = _respawn(name, script, game_id)
            respawned = new_pid is not None
        rows.append((name, schema, age, pids, respawned))
    return rows


def _write_watchdog_heartbeat() -> None:
    date_str = datetime.now(timezone.utc).date().isoformat()
    path = _HEARTBEAT_DIR / f"watchdog_{date_str}.txt"
    try:
        _HEARTBEAT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(
            datetime.now(timezone.utc).isoformat() + "Z\n",
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001
        pass


# ── CLI ──────────────────────────────────────────────────────────────────
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-id", default=None,
                    help="NBA game ID. Auto-detected from "
                         "intel_<today>/tonight_bets_registered.json if omitted.")
    ap.add_argument("--poll-interval", type=int, default=DEFAULT_POLL_SEC)
    ap.add_argument("--stale-after", type=int, default=DEFAULT_STALE_SEC)
    ap.add_argument("--smoke-test", action="store_true",
                    help="Run one inspection pass and print, no respawns.")
    ap.add_argument("--date", default=None,
                    help="Slate date YYYY-MM-DD; default today UTC.")
    args = ap.parse_args(argv)

    date_str = args.date or datetime.now(timezone.utc).date().isoformat()
    game_id = args.game_id
    tip_dt: Optional[datetime] = None
    if game_id is None:
        gid, tip_dt = _autodetect_game(date_str)
        game_id = gid
        if game_id:
            _log(f"auto-detected game_id={game_id} tipoff_utc={tip_dt}")
        else:
            _log("no game_id from intel/tonight_bets_registered.json; "
                 "watchdog will still poll with no respawn args.")
    else:
        _, tip_dt = _autodetect_game(date_str)

    # ── smoke mode: one pass, print table, exit ──────────────────────────
    if args.smoke_test:
        rows = _tick(args.stale_after, smoke=True, game_id=game_id)
        print()
        print(f"{'DAEMON':<24} {'SCHEMA':<12} {'AGE_SEC':>10} {'PIDS':<14} STATUS")
        print("-" * 78)
        for name, schema, age, pids, _r in rows:
            age_str = f"{age:.0f}" if age is not None else "  --"
            pid_str = ",".join(str(p) for p in pids) if pids else "(none)"
            if pids:
                status = "ALIVE"
            elif age is None:
                status = "DEAD (no heartbeat)"
            elif schema == "tick-frozen":
                status = "DEAD (counter frozen)"
            elif age > args.stale_after:
                status = f"DEAD (stale {age:.0f}s > {args.stale_after}s)"
            else:
                status = "MAYBE (no pid, hb fresh)"
            print(f"{name:<24} {schema:<12} {age_str:>10} {pid_str:<14} {status}")
        print()
        return 0

    # ── normal mode: poll across active window ───────────────────────────
    start, end = _compute_window(tip_dt)
    hard_stop = end + timedelta(minutes=15)
    _log(f"watchdog start: pid={os.getpid()} game={game_id} "
         f"window={start.isoformat()} -> {end.isoformat()} "
         f"hard_stop={hard_stop.isoformat()} poll={args.poll_interval}s "
         f"stale_after={args.stale_after}s")

    while True:
        now = datetime.now(timezone.utc)
        if now > hard_stop:
            _log("past hard_stop — watchdog exiting cleanly.")
            return 0

        in_window = start <= now <= end
        if not in_window and now < start:
            wait = min(int((start - now).total_seconds()), args.poll_interval * 5)
            _log(f"pre-window sleep {wait}s (window opens at {start.isoformat()})")
            time.sleep(max(wait, 1))
            continue

        rows = _tick(args.stale_after, smoke=False, game_id=game_id)
        _write_watchdog_heartbeat()
        alive = sum(1 for _, _, _, pids, _r in rows if pids)
        respawned = sum(1 for _, _, _, _, r in rows if r)
        _log(f"tick: {alive}/{len(rows)} alive, {respawned} respawned this tick")
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    sys.exit(main())
