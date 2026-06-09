"""Night-loop: audit the sim's TEAMMATE pts-pts correlation vs realized (the SGP teammate-stack signal).

The master canary is a single aggregate (sim teammate pts-pts rho -0.092 vs real ~-0.1). This audits it
per-pair, leak-free, on the SAME footing: ACROSS-GAME corr for both sim and realized over the pair's SHARED
games (so both include the common game-factor + the within-game shared-pie -- a fair comparison, unlike
mixing realized-across-game vs sim-within-game). For teammate pair (A,B): realized = corr over shared games
of (A_pts, B_pts); sim = mean over sim-index k of corr over shared games of (A_pts[k], B_pts[k]) (each k is
one coherent synthetic season; within a game A_pts[k]/B_pts[k] are the SAME simulated game so shared-pie is
captured). Reports per-pair-averaged realized vs sim, the gap, sign test, split-half. If realized and sim
agree, the teammate joint is calibrated (independence over-prices teammate stacks, as documented); a gap is
an SGP-pricing candidate. Self-contained, changes nothing, ascii-only.

  python scripts/team_system/nightloop/measure_teammates.py --stride 1 --ming 15
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from itertools import combinations

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "src"))
from build_player_rates import _pstat  # noqa: E402
from sim.basketball_sim import TeamModel  # noqa: E402
from sim.fast_sim import simulate_game_fast  # noqa: E402

TS = os.path.join(ROOT, "data", "cache", "team_system")
BOX = os.path.join(TS, "box")
MINE = {"NYK", "SAS"}


def _corr(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float)
    if len(x) < 4 or x.std() < 1e-9 or y.std() < 1e-9:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def _colcorr(A, B):
    """Vectorized per-column Pearson corr of two (G,K) matrices -> length-K array (across the G rows)."""
    am = A - A.mean(0); bm = B - B.mean(0)
    num = (am * bm).sum(0)
    den = np.sqrt((am ** 2).sum(0) * (bm ** 2).sum(0))
    out = np.full(A.shape[1], np.nan)
    ok = den > 1e-9
    out[ok] = num[ok] / den[ok]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--nsims", type=int, default=1500)
    ap.add_argument("--ming", type=int, default=15, help="min SHARED games for a teammate pair")
    ap.add_argument("--minmin", type=float, default=20.0)
    a = ap.parse_args()

    rates = pd.read_parquet(os.path.join(TS, "player_rates.parquet"))
    trates = json.load(open(os.path.join(TS, "team_rates.json")))
    games = sorted(json.load(open(os.path.join(TS, "nyk_sas_games.json"))), key=lambda g: g["date"])[::a.stride]
    models = {}

    def m(t):
        if t not in models:
            try:
                models[t] = TeamModel.from_cache(t, rates_df=rates, team_rates=trates)
            except Exception:
                models[t] = None
        return models[t]

    pdata = defaultdict(dict)    # pid -> {date: (actual_pts, sim_pts_array)}
    pteam = {}
    n = 0
    for gm in games:
        bf = os.path.join(BOX, f"{gm['gid']}.json")
        if not os.path.exists(bf):
            continue
        bg = json.load(open(bf))["game"]
        ht, at = bg["homeTeam"]["teamTricode"], bg["awayTeam"]["teamTricode"]
        if ht not in MINE and at not in MINE:
            continue
        hm, am = m(ht), m(at)
        if not hm or not am:
            continue
        try:
            res = simulate_game_fast(hm, am, n_sims=a.nsims, seed=2026, anchor=True, defense=True,
                                     context={"neutral_site": False})
        except Exception:
            continue
        n += 1
        d = str(gm["date"])
        for tri, side in ((ht, bg["homeTeam"]), (at, bg["awayTeam"])):
            if tri not in MINE:
                continue
            for p in side.get("players", []):
                st = _pstat(p); pid = int(p["personId"])
                if st["min"] < a.minmin or pid not in res.players:
                    continue
                pdata[pid][d] = (st["pts"], np.asarray(res.players[pid]["samples"]["pts"], float))
                pteam[pid] = tri

    by_team = defaultdict(list)
    for pid in pdata:
        by_team[pteam[pid]].append(pid)

    realized, simmean, sign, rh1, rh2, npair = [], [], [], [], [], 0
    rng = np.random.default_rng(7)
    for tri, pids in by_team.items():
        for A_id, B_id in combinations(sorted(pids), 2):
            shared = sorted(set(pdata[A_id]) & set(pdata[B_id]))
            if len(shared) < a.ming:
                continue
            aA = np.array([pdata[A_id][d][0] for d in shared], float)
            aB = np.array([pdata[B_id][d][0] for d in shared], float)
            rc = _corr(aA, aB)
            if np.isnan(rc):
                continue
            MA = np.stack([pdata[A_id][d][1] for d in shared])   # (G, nsims)
            MB = np.stack([pdata[B_id][d][1] for d in shared])
            ck = _colcorr(MA, MB)
            ck = ck[~np.isnan(ck)]
            if len(ck) < 20:
                continue
            npair += 1
            realized.append(rc)
            simmean.append(float(ck.mean()))
            sign.append(1.0 if rc > ck.mean() else 0.0)
            h1 = _corr(aA[0::2], aB[0::2]); h2 = _corr(aA[1::2], aB[1::2])
            if not np.isnan(h1):
                rh1.append(h1)
            if not np.isnan(h2):
                rh2.append(h2)

    realized = np.array(realized); simmean = np.array(simmean); sign = np.array(sign)
    rh1 = np.array(rh1); rh2 = np.array(rh2)
    print(f"=== measure_teammates ===  {n} games, {npair} teammate pairs (>= {a.ming} shared games, min>={a.minmin:.0f})")
    if npair == 0:
        print("VERDICT: no pairs"); return
    gap = float(realized.mean() - simmean.mean())
    print(f"  teammate pts-pts:  realized {realized.mean():+.3f}  sim {simmean.mean():+.3f}  gap {gap:+.3f}  "
          f"r>sim {sign.mean():.0%}  split-half {rh1.mean():+.2f}/{rh2.mean():+.2f}  (n={npair})")
    print(f"  realized range [{realized.min():+.2f},{realized.max():+.2f}]  sim range [{simmean.min():+.2f},{simmean.max():+.2f}]")
    if abs(gap) > 0.08 and sign.mean() >= 0.7 and (np.sign(rh1.mean()) == np.sign(rh2.mean())):
        direction = "MORE negative (over-prices teammate stacks even more)" if gap < 0 else "LESS negative / too positive (UNDER-prices the teammate anti-correlation)"
        print(f"VERDICT: CANDIDATE -- teammate pts-pts joint is off by {gap:+.3f}; realized is {direction}. "
              f"Affects SGP teammate-stack pricing via sgp_from_sim (verify vs real SGP prices before any change).")
    else:
        print(f"VERDICT: teammate pts-pts joint ~calibrated (gap {gap:+.3f} small / not robust) -- the sim's "
              f"shared-pie reproduces the realized teammate co-movement; matches the documented canary. No change.")


if __name__ == "__main__":
    main()
