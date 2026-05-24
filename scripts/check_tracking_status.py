#!/usr/bin/env python3
"""Verify pod-side tracking data is being produced for every fetched game.

For each game that's been downloaded (status='downloaded'/'processed'/'verified'),
checks pod for:
  - tracking_data.csv exists and is non-trivial (>1MB)
  - run.log has terminal marker (success or known failure)
  - audit tier (CLEAN/USABLE/BAD or missing)
  - training_grade rows in pbp_shot_context.csv

Reports games that FELL THROUGH (downloaded but never tracked, or partial).

Usage:
    python scripts/check_tracking_status.py
    python scripts/check_tracking_status.py --missing-only   # just the broken ones
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys

POD_SSH_HOST = "root@213.192.2.86"
POD_SSH_PORT = "40045"


def ssh(cmd: str) -> str:
    full = ["ssh", "-p", POD_SSH_PORT, "-o", "StrictHostKeyChecking=no",
            POD_SSH_HOST, cmd]
    r = subprocess.run(full, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"ssh failed: {r.stderr.strip()}")
    return r.stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--missing-only", action="store_true")
    args = ap.parse_args()

    # 1. Pull queue.db game list (filter to real game IDs: 00*)
    py = (
        "import sqlite3; "
        "c=sqlite3.connect('/workspace/nba-ai-system/data/ingest/queue.db'); "
        "rows=c.execute(\"SELECT game_id, status FROM games WHERE status IN "
        "('downloaded','processed','verified','REJECT') "
        "AND game_id LIKE '00%' "
        "ORDER BY game_id\").fetchall(); "
        "[print(r[0]+'|'+r[1]) for r in rows]"
    )
    queue_out = ssh(f"python3 -c {shlex.quote(py)}")
    queue_pairs = [tuple(l.split("|", 1)) for l in queue_out.strip().splitlines() if "|" in l]

    # 2. For each game, gather tracking facts on pod via a heredoc probe script
    gids = [g for g, _ in queue_pairs]
    if not gids:
        print("(no games in queue with terminal status)")
        return 0

    # Write the probe as a proper multi-line script (heredoc bypasses ssh quoting limits)
    probe_script = f"""import os, csv, re
T = '/workspace/nba-ai-system/data/tracking'
gids = {gids!r}
for g in gids:
    d = f'{{T}}/{{g}}'
    td = f'{{d}}/tracking_data.csv'
    rl = f'{{d}}/run.log'
    pbp = f'{{d}}/pbp_shot_context.csv'
    td_sz = os.path.getsize(td)//1024 if os.path.exists(td) else -1
    rl_sz = os.path.getsize(rl) if os.path.exists(rl) else -1
    done = False
    if rl_sz > 0:
        with open(rl, errors='replace') as f:
            txt = f.read()
        done = bool(re.search(r'PREFLIGHT FAIL|Output Summary|Total time:', txt))
    tg = 0; total = 0
    if os.path.exists(pbp):
        with open(pbp, errors='replace') as f:
            for row in csv.DictReader(f):
                total += 1
                if row.get('training_grade') == '1':
                    tg += 1
    print(f'{{g}}|{{td_sz}}|{{rl_sz}}|{{int(done)}}|{{total}}|{{tg}}')
"""
    # Send script to pod via stdin
    full = ["ssh", "-p", POD_SSH_PORT, "-o", "StrictHostKeyChecking=no",
            POD_SSH_HOST, "python3 -"]
    r = subprocess.run(full, input=probe_script, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"probe failed: {r.stderr.strip()}")
    out = r.stdout

    # 3. Get audit tier for each
    audit_out = ssh(
        "cd /workspace/nba-ai-system && python3 scripts/audit_completed.py 2>&1"
    )
    tier = {}
    for line in audit_out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0].startswith("00"):
            tier[parts[0]] = parts[2]  # CLEAN / USABLE / BAD

    # 4. Render report
    status = dict(queue_pairs)
    print(f"{'gid':14} {'q_status':10} {'tier':6} {'td_KB':>8} {'log_B':>7} "
          f"{'done':>5} {'pbp_rows':>9} {'train_grade':>11}")
    print("-" * 92)
    missing = []
    for line in out.strip().splitlines():
        p = line.split("|")
        if len(p) < 6:
            continue
        g, td, rl, dn, tot, tg = p
        td_int = int(td)
        rl_int = int(rl)
        is_missing = td_int < 100 or int(dn) == 0
        if args.missing_only and not is_missing:
            continue
        flag = " <-- MISSING" if is_missing else ""
        print(f"{g:14} {status.get(g,'?'):10} {tier.get(g,'-'):6} "
              f"{td_int:>8} {rl_int:>7} {dn:>5} {tot:>9} {tg:>11}{flag}")
        if is_missing:
            missing.append(g)

    print()
    print(f"queued games: {len(queue_pairs)}")
    if missing:
        print(f"!!  GAMES MISSING TRACKING DATA: {len(missing)}")
        for g in missing[:10]:
            print(f"   {g}")
    else:
        print("OK: all queued games have tracking data")
    return 0


if __name__ == "__main__":
    sys.exit(main())
