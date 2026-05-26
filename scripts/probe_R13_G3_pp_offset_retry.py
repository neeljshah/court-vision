"""Probe R13_G3: PrizePicks systematic-offset retry harness.

Followup to R12_F4 (BLK z=5.7, STL z=4.5, PTS z=-4.2; n<100 per stat blocked
ship gate). C2 launched the PP scraper daemon (PID 22608 reference); this
probe checks whether enough snapshots have accumulated to satisfy the formal
ship gate (n_obs_per_stat >= 100 AND |mean_offset| >= 2 * sterr).

Behavior
--------
1. Check whether the PrizePicks scraper daemon is still alive (process scan
   for fetch_live_prop_lines).
2. Aggregate PP snapshots in data/lines/*_pp.csv: count unique (player_name,
   stat) per stat.
3. If every monitored stat has n >= 100, re-invoke R12_F4
   (probe_R12_F4_pp_systematic_offset) and ship if it does. On SHIP, copy the
   resulting offset profile to data/models/pp_systematic_offset_v2.json and
   append a one-line coordination_log update.
4. If any stat still has n < 100, emit a data-shortfall report estimating
   days_until_n100_at_current_cadence (15min interval -> ~96 snaps/day).
5. If the daemon is dead, relaunch it via nohup using the same pattern as
   probe_R9_C2_multibook_scraper (book=pp, interval-min=15).

Diagnostic only -- no production code paths modified. Writes:
    data/cache/probe_R13_G3_pp_offset_retry_results.json
    data/models/pp_systematic_offset_v2.json   (only on SHIP)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
LINES_DIR = PROJECT_DIR / "data" / "lines"
RESULT_PATH = PROJECT_DIR / "data" / "cache" / "probe_R13_G3_pp_offset_retry_results.json"
R12_RESULT_PATH = PROJECT_DIR / "data" / "cache" / "probe_R12_F4_pp_systematic_offset_results.json"
R12_PROFILE_PATH = PROJECT_DIR / "data" / "models" / "pp_systematic_offset_v1.json"
SHIP_PROFILE_PATH = PROJECT_DIR / "data" / "models" / "pp_systematic_offset_v2.json"
COORD_LOG = PROJECT_DIR / "scripts" / "coordination_log.md"
SCRAPER_LOG = PROJECT_DIR / "vault" / "Improvements" / "live_prop_scraper.log"

MONITORED_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
N_REQUIRED = 100
DAEMON_INTERVAL_MIN = 15
SNAPS_PER_DAY = int((60 * 24) / DAEMON_INTERVAL_MIN)  # 96


def _daemon_alive() -> Dict:
    """ps-scan for fetch_live_prop_lines processes."""
    try:
        out = subprocess.check_output(["ps", "-eo", "pid,cmd"], text=True)
    except Exception as e:
        return {"alive": False, "pids": [], "error": str(e)}
    pids: List[int] = []
    cmds: List[str] = []
    for line in out.splitlines()[1:]:
        if "fetch_live_prop_lines" in line and "grep" not in line:
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                try:
                    pids.append(int(parts[0]))
                    cmds.append(parts[1])
                except ValueError:
                    continue
    return {"alive": len(pids) > 0, "pids": pids, "cmds": cmds}


def _relaunch_daemon() -> Dict:
    """nohup-launch the PP scraper daemon (book=pp, interval-min=15)."""
    SCRAPER_LOG.parent.mkdir(parents=True, exist_ok=True)
    py = shutil.which("python") or sys.executable
    cmd = (
        f"nohup {py} {PROJECT_DIR}/scripts/fetch_live_prop_lines.py "
        f"--book pp --interval-min {DAEMON_INTERVAL_MIN} "
        f">> {SCRAPER_LOG} 2>&1 &"
    )
    try:
        subprocess.Popen(
            cmd,
            shell=True,
            executable="/bin/bash",
            cwd=str(PROJECT_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {"relaunched": True, "cmd": cmd}
    except Exception as e:
        return {"relaunched": False, "cmd": cmd, "error": str(e)}


def _load_all_pp_snapshots() -> pd.DataFrame:
    """Union every data/lines/*_pp.csv into a single DataFrame."""
    files = sorted(LINES_DIR.glob("*_pp.csv"))
    frames: List[pd.DataFrame] = []
    for f in files:
        try:
            df = pd.read_csv(f, on_bad_lines="skip")
            df["__src"] = f.name
            frames.append(df)
        except Exception as e:
            print(f"[probe_R13_G3] WARN failed to read {f}: {e}")
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _per_stat_unique_counts(pp: pd.DataFrame) -> Dict[str, int]:
    counts: Dict[str, int] = {s: 0 for s in MONITORED_STATS}
    if pp.empty or "stat" not in pp.columns or "player_name" not in pp.columns:
        return counts
    pp = pp[pp["stat"].isin(MONITORED_STATS)].copy()
    uniq = pp.drop_duplicates(subset=["player_name", "stat"])
    for stat, n in uniq.groupby("stat").size().items():
        counts[str(stat)] = int(n)
    return counts


def _days_until_n100(current_counts: Dict[str, int]) -> Dict[str, float]:
    """Estimate days at 15min cadence to reach n=100 per stat.

    Heuristic: assume the slate refreshes ~daily and ~30-37 distinct
    (player, stat) rows appear per stat per day (observed 2026-05-25).
    Days needed = ceil((100 - current) / per_day_obs_per_stat).
    """
    per_day = {
        "pts": 37, "reb": 35, "ast": 35, "fg3m": 32,
        "stl": 36, "blk": 35, "tov": 35,
    }
    out: Dict[str, float] = {}
    for s, n in current_counts.items():
        deficit = max(0, N_REQUIRED - n)
        rate = max(1, per_day.get(s, 30))
        out[s] = round(deficit / rate, 2)
    return out


def _rerun_r12_f4() -> Dict:
    """Invoke probe_R12_F4_pp_systematic_offset.py and read the JSON it writes."""
    py = sys.executable
    script = PROJECT_DIR / "scripts" / "probe_R12_F4_pp_systematic_offset.py"
    print(f"[probe_R13_G3] re-running R12_F4: {script}")
    try:
        proc = subprocess.run(
            [py, str(script)],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            timeout=300,
        )
        print(proc.stdout[-2000:] if proc.stdout else "")
        if proc.returncode != 0:
            print(f"[probe_R13_G3] R12_F4 exited {proc.returncode}: {proc.stderr[-2000:]}")
    except Exception as e:
        return {"rerun_ok": False, "error": str(e)}
    if not R12_RESULT_PATH.exists():
        return {"rerun_ok": False, "error": "R12_F4 result file missing"}
    with open(R12_RESULT_PATH, "r", encoding="utf-8") as fh:
        return {"rerun_ok": True, "r12_result": json.load(fh)}


def _ship_to_v2_and_log(r12_result: Dict) -> Dict:
    """Copy v1 offset profile -> v2 and append a coord_log line."""
    actions = {"v2_written": False, "coord_log_appended": False}
    if R12_PROFILE_PATH.exists():
        shutil.copyfile(R12_PROFILE_PATH, SHIP_PROFILE_PATH)
        actions["v2_written"] = True
        actions["v2_path"] = str(SHIP_PROFILE_PATH)
    headline = r12_result.get("headline", "<no headline>")
    line = (
        f"[{datetime.now().strftime('%Y-%m-%d')} S2] SHIP — R13_G3: "
        f"PP systematic-offset retry passes n>=100 ship gate. {headline} "
        f"Offset profile written to data/models/pp_systematic_offset_v2.json.\n"
    )
    try:
        COORD_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(COORD_LOG, "a", encoding="utf-8") as fh:
            fh.write(line)
        actions["coord_log_appended"] = True
        actions["coord_log_line"] = line.strip()
    except Exception as e:
        actions["coord_log_error"] = str(e)
    return actions


def main():
    print(f"[probe_R13_G3] PP offset retry harness | {datetime.now().isoformat()}")
    daemon = _daemon_alive()
    print(f"[probe_R13_G3] daemon alive: {daemon['alive']} pids={daemon.get('pids')}")

    relaunch_info: Optional[Dict] = None
    if not daemon["alive"]:
        relaunch_info = _relaunch_daemon()
        print(f"[probe_R13_G3] relaunched daemon: {relaunch_info}")

    pp = _load_all_pp_snapshots()
    n_files = len(list(LINES_DIR.glob("*_pp.csv")))
    n_rows_total = int(len(pp))
    print(f"[probe_R13_G3] pp csv files: {n_files}, total rows: {n_rows_total}")

    counts = _per_stat_unique_counts(pp)
    print(f"[probe_R13_G3] per-stat unique (player,stat) counts: {counts}")

    all_ready = all(counts.get(s, 0) >= N_REQUIRED for s in MONITORED_STATS)

    result: Dict = {
        "probe_id": "R13_G3_pp_offset_retry",
        "timestamp": datetime.now().isoformat(),
        "daemon_alive": bool(daemon["alive"]),
        "daemon_pids_before_relaunch": daemon.get("pids", []),
        "daemon_relaunched": relaunch_info is not None and relaunch_info.get("relaunched", False),
        "relaunch_info": relaunch_info,
        "n_pp_csv_files": n_files,
        "n_pp_rows_total": n_rows_total,
        "n_obs_per_stat": counts,
        "n_required_per_stat": N_REQUIRED,
        "all_stats_ready": bool(all_ready),
    }

    if all_ready:
        rerun = _rerun_r12_f4()
        result["rerun"] = rerun
        if rerun.get("rerun_ok"):
            r12 = rerun["r12_result"]
            ship_status = r12.get("status", "UNKNOWN")
            result["ship_status"] = ship_status
            # surface key z-scores
            zmap = {row["stat"]: row.get("z") for row in r12.get("per_stat", [])}
            result["blk_z"] = zmap.get("blk")
            result["stl_z"] = zmap.get("stl")
            result["pts_z"] = zmap.get("pts")
            if ship_status == "SHIP":
                actions = _ship_to_v2_and_log(r12)
                result["ship_actions"] = actions
        else:
            result["ship_status"] = "BLOCKED_RERUN_FAILED"
    else:
        # data-shortfall report
        days = _days_until_n100(counts)
        # at current cadence headline = max stat-deficit
        max_days = max(days.values()) if days else None
        result["ship_status"] = "WAITING_FOR_DATA"
        result["days_until_n100_at_current_cadence"] = days
        result["days_to_n100_headline"] = max_days
        # carry forward last known z-scores from R12 for context
        if R12_RESULT_PATH.exists():
            with open(R12_RESULT_PATH, "r", encoding="utf-8") as fh:
                r12_prev = json.load(fh)
            zmap = {row["stat"]: row.get("z") for row in r12_prev.get("per_stat", [])}
            result["blk_z"] = zmap.get("blk")
            result["stl_z"] = zmap.get("stl")
            result["pts_z"] = zmap.get("pts")
            result["r12_prev_status"] = r12_prev.get("status")

    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULT_PATH, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
    print(f"[probe_R13_G3] wrote: {RESULT_PATH}")
    print(f"[probe_R13_G3] ship_status: {result['ship_status']}")
    if result["ship_status"] == "WAITING_FOR_DATA":
        print(f"[probe_R13_G3] days_to_n100 (max stat): {result['days_to_n100_headline']}")
        print(f"[probe_R13_G3] per-stat days_to_n100: {result['days_until_n100_at_current_cadence']}")


if __name__ == "__main__":
    main()
