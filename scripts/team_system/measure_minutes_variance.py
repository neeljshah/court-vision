"""How much of a player's game-to-game POINTS variance is minutes vs scoring-rate?

The calibration residual (pts coverage 69% not 80%) and the team-total bias both point at minutes.
Before building a minutes/availability model, size the lever: decompose each NYK/SAS player's game
points variance into a minutes-driven part and a rate (pts-per-minute) part.

  pts = ppm * minutes.  Var(pts) ~ (E[ppm])^2 Var(min) + (E[min])^2 Var(ppm) + ... (Goodman).
We report, per player (>=20 games, min>=8): SD(pts), the SD if minutes were FIXED at the mean (pure
rate variance), and the SD if rate were FIXED (pure minutes variance). Their ratio to total SD says
which lever dominates -> whether a minutes model would close the coverage gap.

  python scripts/team_system/measure_minutes_variance.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_player_rates import _pstat  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
BOX_DIR = os.path.join(TS, "box")
MINE = {"NYK", "SAS"}


def main():
    games = json.load(open(os.path.join(TS, "nyk_sas_games.json")))
    P = defaultdict(lambda: {"pts": [], "min": [], "name": "", "team": ""})
    for gm in games:
        bf = os.path.join(BOX_DIR, f"{gm['gid']}.json")
        if not os.path.exists(bf):
            continue
        bg = json.load(open(bf))["game"]
        for tm in (bg["homeTeam"], bg["awayTeam"]):
            if tm["teamTricode"] not in MINE:
                continue
            for p in tm.get("players", []):
                st = _pstat(p)
                if st["min"] < 8:
                    continue
                pid = int(p["personId"])
                P[pid]["pts"].append(st["pts"]); P[pid]["min"].append(st["min"])
                P[pid]["name"] = p.get("name", ""); P[pid]["team"] = tm["teamTricode"]

    asc = lambda s: str(s).encode("ascii", "replace").decode()
    print("=== POINTS VARIANCE DECOMPOSITION: minutes vs rate (NYK/SAS, >=20 games, min>=8) ===\n")
    print(f"  {'player':20s} {'tm':3s} {'g':>3s} | {'SD(pts)':>7s} {'rate-only':>9s} {'min-only':>8s} | "
          f"{'min%var':>7s} {'rate%var':>8s}")
    minfrac, ratefrac = [], []
    for pid, d in sorted(P.items(), key=lambda x: -np.mean(x[1]["pts"]) if x[1]["pts"] else 0):
        if len(d["pts"]) < 20 or np.mean(d["pts"]) < 6:
            continue
        pts = np.array(d["pts"], float); mins = np.array(d["min"], float)
        ppm = pts / np.maximum(mins, 1.0)
        mbar, pbar = mins.mean(), ppm.mean()
        sd_tot = pts.std()
        sd_rate = mbar * ppm.std()          # minutes fixed at mean -> pure rate variance
        sd_min = pbar * mins.std()           # rate fixed at mean -> pure minutes variance
        # variance shares (Goodman first-order; normalize to total var)
        vmin = sd_min ** 2; vrate = sd_rate ** 2; vt = vmin + vrate or 1.0
        mf, rf = vmin / vt, vrate / vt
        minfrac.append(mf); ratefrac.append(rf)
        print(f"  {asc(d['name']):20s} {d['team']:3s} {len(pts):3d} | {sd_tot:7.2f} {sd_rate:9.2f} {sd_min:8.2f} | "
              f"{mf:6.0%} {rf:7.0%}")
    print(f"\n  MEAN variance share -> minutes {np.mean(minfrac):.0%}  |  rate {np.mean(ratefrac):.0%}  (n={len(minfrac)})")
    print("  if minutes dominate => build the minutes/availability model; if rate dominates => the")
    print("  dispersion shock already captures it and a minutes model won't move player coverage much.")


if __name__ == "__main__":
    main()
