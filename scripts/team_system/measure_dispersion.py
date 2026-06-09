"""Measure the per-player scoring-dispersion gap: real game-to-game SD vs the sim's SD.

The calibration harness showed player point intervals are too tight (66% coverage) while team
totals are right (79%). This sizes the gap: for each NYK/SAS player, the real SD of his points
across his games (min>=12) vs the sim's SD for a representative matchup. The ratio is the
variance-inflation the per-player distribution needs (to be applied zero-sum so team total holds).

  python scripts/team_system/measure_dispersion.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
from build_player_rates import _pstat  # noqa: E402
from sim.basketball_sim import TeamModel  # noqa: E402
from sim.fast_sim import simulate_game_fast  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
BOX_DIR = os.path.join(TS, "box")
MINE = {"NYK", "SAS"}


def main():
    games = json.load(open(os.path.join(TS, "nyk_sas_games.json")))
    real = defaultdict(lambda: {"pts": [], "reb": [], "ast": [], "name": "", "team": ""})
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
                if st["min"] < 12:
                    continue
                pid = int(p["personId"])
                real[pid]["pts"].append(st["pts"]); real[pid]["reb"].append(st["oreb"] + st["dreb"])
                real[pid]["ast"].append(st["ast"]); real[pid]["name"] = p.get("name", "")
                real[pid]["team"] = tm["teamTricode"]

    # sim SD from a representative NYK vs SAS matchup (both rosters full)
    nyk, sas = TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS")
    res = simulate_game_fast(nyk, sas, n_sims=8000, seed=2026, anchor=True, defense=True,
                             context={"neutral_site": False})
    sim_sd = {pid: {"pts": float(np.std(d["samples"]["pts"])), "reb": float(np.std(d["samples"]["reb"])),
                    "ast": float(np.std(d["samples"]["ast"])), "ptsmean": float(d["mean"]["pts"])}
              for pid, d in res.players.items()}

    asc = lambda s: str(s).encode("ascii", "replace").decode()
    print("=== PER-PLAYER DISPERSION: real game SD vs sim SD (NYK/SAS, >=8 games min>=12) ===\n")
    print(f"  {'player':20s} {'tm':3s} {'g':>3s} | {'realPTSsd':>9s} {'simPTSsd':>8s} {'ratio':>6s} | "
          f"{'realREBsd':>9s} {'simREBsd':>8s} | {'realASTsd':>9s} {'simASTsd':>8s}")
    ratios = {"pts": [], "reb": [], "ast": []}
    for pid, r in sorted(real.items(), key=lambda x: -np.mean(x[1]["pts"]) if x[1]["pts"] else 0):
        if len(r["pts"]) < 8 or pid not in sim_sd:
            continue
        rp, rr, ra = np.std(r["pts"]), np.std(r["reb"]), np.std(r["ast"])
        sp = sim_sd[pid]["pts"]; sr = sim_sd[pid]["reb"]; sa = sim_sd[pid]["ast"]
        if np.mean(r["pts"]) < 6:
            continue
        for k, rv, sv in (("pts", rp, sp), ("reb", rr, sr), ("ast", ra, sa)):
            if sv > 0.3:
                ratios[k].append(rv / sv)
        rat = rp / sp if sp > 0 else 0
        print(f"  {asc(r['name']):20s} {r['team']:3s} {len(r['pts']):3d} | {rp:9.2f} {sp:8.2f} {rat:6.2f} | "
              f"{rr:9.2f} {sr:8.2f} | {ra:9.2f} {sa:8.2f}")
    print("\n  MEDIAN real/sim SD ratio (the inflation per-player dispersion needs):")
    for k in ("pts", "reb", "ast"):
        v = ratios[k]
        print(f"    {k}: {np.median(v):.2f}  (mean {np.mean(v):.2f}, n={len(v)})")
    print("\n  ratio > 1 => sim under-disperses; apply ~zero-sum across teammates so team total holds.")


if __name__ == "__main__":
    main()
