"""Night-loop: audit the sim's SAME-PLAYER cross-stat correlations (pts-reb, pts-ast) vs realized.

The JOINT structure is the documented open lane (the marginal ceiling does not bind it) and it is what
combo/PRA props price. measure_skew/sweeps covered marginals; this covers the joint. KEY mechanism check:
_apply_dispersion adds an INDEPENDENT mean-1 shock per stat-group (pts | oreb+dreb | ast are separate,
basketball_sim.py:286), which DILUTES same-player cross-stat correlation -- so if realized pts-reb / pts-ast
correlation EXCEEDS the sim's, the per-stat-independent shock is under-correlating combo stats (a real,
prop-relevant candidate); if it matches, the joint is calibrated.

Method (leak-free, observable -- same-player cross-stat IS observable across games, unlike teammate within-
game corr): for each NYK/SAS player with >=MIN_G games, realized corr = corr over his games of actual
(X,Y). Sim analog = for each sim-index k, take the k-th draw from each of his games to form one synthetic
season, corr over games; average over k -> the sim's EXPECTED across-game corr (the realized is one such
draw, so it should sit inside the sim's [5,95] band if the joint is calibrated). Reports per-pair mean
realized vs sim, the gap, and the fraction of players whose realized corr falls within the sim band.
Self-contained, changes nothing, ascii-only.

  python scripts/team_system/nightloop/measure_corr.py --stride 1 --ming 12
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--nsims", type=int, default=2000)
    ap.add_argument("--ming", type=int, default=12, help="min games per player to estimate a correlation")
    ap.add_argument("--minmin", type=float, default=18.0)
    ap.add_argument("--ksamp", type=int, default=400, help="sim-index resamples for the sim corr distribution")
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

    # per pid: list over games of (actual_triple, sim_pts[k], sim_reb[k], sim_ast[k])
    act = defaultdict(list)   # pid -> list of (pts,reb,ast) actual
    sim = defaultdict(list)   # pid -> list of (pts_arr, reb_arr, ast_arr) length-nsims each
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
        for tri, side in ((ht, bg["homeTeam"]), (at, bg["awayTeam"])):
            if tri not in MINE:
                continue
            for p in side.get("players", []):
                st = _pstat(p); pid = int(p["personId"])
                if st["min"] < a.minmin or pid not in res.players:
                    continue
                s = res.players[pid]["samples"]
                reb_arr = np.asarray(s["reb"] if "reb" in s else (np.asarray(s["oreb"], float) + np.asarray(s["dreb"], float)), float)
                act[pid].append((st["pts"], st["oreb"] + st["dreb"], st["ast"], max(st["min"], 1.0)))
                sim[pid].append((np.asarray(s["pts"], float), reb_arr, np.asarray(s["ast"], float)))

    pairs = {"pts_reb": (0, 1), "pts_ast": (0, 2), "reb_ast": (1, 2)}
    rng = np.random.default_rng(7)
    agg = {k: {"realized": [], "sim_mean": [], "sign": [], "rh1": [], "rh2": [], "rpm": []} for k in pairs}
    nplayers = 0
    for pid, ga in act.items():
        if len(ga) < a.ming:
            continue
        nplayers += 1
        A = np.array(ga, float)                       # (G,3) actual
        S = sim[pid]                                   # list of (pts_arr,reb_arr,ast_arr)
        G = len(ga)
        ks = rng.integers(0, a.nsims, size=a.ksamp)
        for name, (ix, iy) in pairs.items():
            rc = _corr(A[:, ix], A[:, iy])
            if np.isnan(rc):
                continue
            sc = []
            for k in ks:
                xs = np.array([S[g][ix][k] for g in range(G)])
                ys = np.array([S[g][iy][k] for g in range(G)])
                c = _corr(xs, ys)
                if not np.isnan(c):
                    sc.append(c)
            if len(sc) < 20:
                continue
            scm = float(np.mean(sc))
            h1 = _corr(A[0::2, ix], A[0::2, iy])       # split-half of the REALIZED corr (odd/even games)
            h2 = _corr(A[1::2, ix], A[1::2, iy])
            rpm = _corr(A[:, ix] / A[:, 3], A[:, iy] / A[:, 3])   # PER-MINUTE realized corr (strips the shared-minutes factor)
            agg[name]["realized"].append(rc)
            agg[name]["sim_mean"].append(scm)
            agg[name]["sign"].append(1.0 if rc > scm else 0.0)   # sign test: realized above sim?
            if not np.isnan(h1):
                agg[name]["rh1"].append(h1)
            if not np.isnan(h2):
                agg[name]["rh2"].append(h2)
            if not np.isnan(rpm):
                agg[name]["rpm"].append(rpm)

    print(f"=== measure_corr ===  {n} games, {nplayers} players (>= {a.ming} games, min>={a.minmin:.0f})")
    print(f"  {'pair':>9s} {'realized':>9s} {'permin':>7s} {'sim':>7s} {'gap(r-s)':>9s} {'r>sim':>7s}  (splithalf h1/h2, npl)")
    flags = []
    for name in pairs:
        r = np.array(agg[name]["realized"]); s = np.array(agg[name]["sim_mean"]); sg = np.array(agg[name]["sign"])
        h1 = np.array(agg[name]["rh1"]); h2 = np.array(agg[name]["rh2"]); rpm = np.array(agg[name]["rpm"])
        if len(r) == 0:
            print(f"  {name:>9s}: no data"); continue
        gap = float(r.mean() - s.mean())
        print(f"  {name:>9s} {r.mean():>+9.3f} {rpm.mean():>+7.3f} {s.mean():>+7.3f} {gap:>+9.3f} {sg.mean():>7.0%}  (h1 {h1.mean():+.2f}/h2 {h2.mean():+.2f}, {len(r)})")
        # candidate = consistent DIRECTIONAL gap (sign test) + the realized corr replicates across split-halves
        replic = (h1.mean() > 0.03 and h2.mean() > 0.03) if gap > 0 else (h1.mean() < -0.03 and h2.mean() < -0.03)
        if gap > 0.08 and sg.mean() >= 0.8 and replic:
            flags.append(f"{name}: realized {r.mean():+.2f} vs sim {s.mean():+.2f} (gap {gap:+.2f}), {sg.mean():.0%} of players realized>sim, split-half {h1.mean():+.2f}/{h2.mean():+.2f}")
    if flags:
        print("VERDICT: CANDIDATE (human review, split-half-confirmed) -- the sim UNDER-correlates same-player "
              "combo stats: " + "; ".join(flags) + ". Mechanism = _apply_dispersion's INDEPENDENT per-stat-group "
              "shock washes out possession-driven co-movement; prop-relevant for PRA/combo (sgp_from_sim). "
              "Fix idea (NOT applied): share a common minutes/usage component across a player's pts/reb/ast shocks.")
    else:
        print("VERDICT: same-player cross-stat joint ~calibrated or not robust (small gap / sign<80% / "
              "split-half unstable) -- no change.")


if __name__ == "__main__":
    main()
