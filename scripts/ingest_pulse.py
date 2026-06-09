#!/usr/bin/env python3
"""ingest_pulse.py — One-shot system pulse for the 100-game ingest loop.

Reports at-a-glance state of the autonomous batch:
  * Pod SSH alive
  * Pod disk free (/root, /workspace)
  * GPU memory + utilization
  * Currently-running pipelines on the pod (PID, elapsed, frame progress)
  * Last 5 rows of the local .ingest_log.csv
  * Local backup directory size + game count
  * Any suspiciously small game outputs (< 1000 tracking rows)

Use while a long-running batch is in progress. Safe to run repeatedly
(read-only, no side effects).

Usage:
    python scripts/ingest_pulse.py
    python scripts/ingest_pulse.py --json
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

import os as _os
POD_IP   = _os.environ.get("NBA_POD_IP",   "213.192.2.86")
POD_PORT = _os.environ.get("NBA_POD_PORT", "40045")
POD_USER = _os.environ.get("NBA_POD_USER", "root")
POD_REPO = _os.environ.get("NBA_POD_REPO", "/workspace/nba-ai-system")

LOCAL_BACKUP   = Path(r"C:\Users\neelj\nba-data-backup")
LOCAL_TRACKING = LOCAL_BACKUP / "tracking"
INGEST_LOG     = LOCAL_BACKUP / ".ingest_log.csv"

SSH_OPTS = ["-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            "-o", "ServerAliveInterval=60"]


def _ssh(cmd: str, timeout: int = 15) -> tuple[int, str]:
    full = ["ssh", "-p", POD_PORT, *SSH_OPTS, f"{POD_USER}@{POD_IP}", cmd]
    try:
        r = subprocess.run(full, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        return r.returncode, r.stdout
    except subprocess.TimeoutExpired:
        return 124, ""


def pulse() -> dict:
    out: dict = {}
    rc, _ = _ssh("echo alive", timeout=8)
    out["pod_alive"] = (rc == 0)
    if not out["pod_alive"]:
        return out

    # Disk
    rc, df_root = _ssh("df --output=avail,size -BG /root | tail -1")
    rc, df_ws   = _ssh("df --output=avail,size -BG /workspace | tail -1")
    out["disk_root"]      = df_root.strip()
    out["disk_workspace"] = df_ws.strip()

    # GPU
    rc, gpu = _ssh("nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu "
                   "--format=csv,noheader,nounits")
    out["gpu"] = gpu.strip()

    # Running pipelines: extract game_id from `--game-id <id>` arg
    rc, ps = _ssh(
        "ps -eo pid,etime,pcpu,rss,cmd --no-headers "
        "| grep 'scripts.run_clip\\|scripts/run_clip' "
        "| grep -v grep | grep -v timeout"
    )
    pipes = []
    for line in ps.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        pid, etime, pcpu, rss, cmd = parts
        gid = ""
        if "--game-id" in cmd:
            tokens = cmd.split()
            try:
                gid = tokens[tokens.index("--game-id") + 1]
            except (ValueError, IndexError):
                pass
        # Get frame progress
        frame, n_rows = None, None
        if gid:
            rc2, last = _ssh(
                f"tail -1 {POD_REPO}/data/tracking/{gid}/tracking_data.csv "
                f"2>/dev/null | cut -d',' -f1"
            )
            try:
                frame = int(last.strip())
            except (ValueError, AttributeError):
                pass
            rc3, wc = _ssh(
                f"wc -l < {POD_REPO}/data/tracking/{gid}/tracking_data.csv "
                f"2>/dev/null"
            )
            try:
                n_rows = int(wc.strip())
            except (ValueError, AttributeError):
                pass
        pipes.append({
            "pid": pid, "elapsed": etime, "cpu_pct": pcpu, "rss_kb": rss,
            "game_id": gid, "last_frame": frame, "tracking_rows": n_rows,
        })
    out["pipelines"] = pipes

    # Recent ingest log
    log_tail = []
    if INGEST_LOG.exists():
        try:
            with open(INGEST_LOG, newline="") as f:
                rows = list(csv.DictReader(f))
            log_tail = rows[-5:]
        except Exception:
            pass
    out["ingest_log_tail"] = log_tail

    # Local backup state
    if LOCAL_TRACKING.exists():
        dirs = [p for p in LOCAL_TRACKING.iterdir() if p.is_dir()]
        out["local_backup_games"] = len(dirs)
        # Total size
        total = 0
        small = []
        for d in dirs:
            for f in d.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
            td = d / "tracking_data.csv"
            if td.exists() and td.stat().st_size > 0:
                # Quick row estimate from bytes (~80B per row average)
                if td.stat().st_size < 80_000:
                    small.append((d.name, td.stat().st_size))
        out["local_backup_bytes"] = total
        out["local_backup_mb"]    = round(total / 1024 / 1024, 1)
        out["small_tracking_csvs"] = small
    return out


def fmt(p: dict) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append(f" INGEST PULSE  |  pod_alive={p.get('pod_alive')}")
    lines.append("=" * 60)
    if not p.get("pod_alive"):
        return "\n".join(lines)
    lines.append(f"  disk /root      = {p['disk_root']}")
    lines.append(f"  disk /workspace = {p['disk_workspace']}")
    lines.append(f"  gpu             = {p['gpu']}")
    lines.append("")
    pipes = p["pipelines"]
    lines.append(f"  Running pipelines: {len(pipes)}")
    for pp in pipes:
        gid = pp.get("game_id", "?")
        frame = pp.get("last_frame")
        et = pp.get("elapsed")
        cpu = pp.get("cpu_pct")
        rss_mb = int(pp.get("rss_kb") or 0) // 1024
        lines.append(f"    {gid}  elapsed={et}  cpu={cpu}%  rss={rss_mb}MB  "
                     f"frame={frame}")
    lines.append("")
    lines.append(f"  Local backup: {p.get('local_backup_games', 0)} games, "
                 f"{p.get('local_backup_mb', 0)} MB")
    small = p.get("small_tracking_csvs", [])
    if small:
        lines.append(f"  SMALL tracking CSVs (< 80KB):")
        for n, b in small:
            lines.append(f"    {n}: {b}B")
    lines.append("")
    lines.append(f"  Last {len(p['ingest_log_tail'])} ingest_log row(s):")
    for r in p["ingest_log_tail"]:
        lines.append(f"    {r.get('timestamp', '')[-8:]}  "
                     f"{r.get('game_id', ''):11}  "
                     f"{r.get('status', ''):4}  "
                     f"{r.get('wall_seconds', '0'):>7}s  "
                     f"{r.get('message', '')[:50]}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    p = pulse()
    if args.json:
        print(json.dumps(p, indent=2))
    else:
        print(fmt(p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
