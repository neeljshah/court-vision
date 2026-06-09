"""Does RECENT form beat flat season rates? (walk-forward, leak-free, reg-season vs playoffs)

The sim uses flat full-season scoring rates. But the playoffs are a different regime (tighter rotation,
current form). This tests, leak-free, whether an exponentially recency-weighted as-of scoring rate
predicts a player's points better than the flat cumulative rate. For each NYK/SAS player-game (>=60
prior min, actual min>=12) we predict pts = ppm * actual_min, where ppm is the as-of rate under several
half-lives (in games): inf = flat cumulative, then 30/15/8/4. Reported overall and split by the game's
kind (reg vs playoff) -- the question is whether recency helps, and whether it helps MORE in the playoffs.

  python scripts/team_system/walkforward_recency.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_player_rates import _pstat  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
BOX_DIR = os.path.join(TS, "box")
MINE = {"NYK", "SAS"}
HALFLIVES = [np.inf, 30.0, 15.0, 8.0, 4.0]
PRIOR_K = 36.0
M0 = 0.40
MIN_PRIOR_MIN = 60.0


def main():
    rates = pd.read_parquet(os.path.join(TS, "player_rates.parquet")).set_index("pid")
    games = sorted(json.load(open(os.path.join(TS, "nyk_sas_games.json"))), key=lambda g: (g["date"], g["gid"]))
    hist = defaultdict(list)   # pid -> list of (pts, min) in chronological order
    # err[hl][kind] = list of (pred-actual)
    err = {hl: {"all": [], "reg": [], "po": []} for hl in HALFLIVES}
    terr = {hl: {"reg": [], "po": []} for hl in HALFLIVES}   # team-total error by kind

    for gm in games:
        bf = os.path.join(BOX_DIR, f"{gm['gid']}.json")
        if not os.path.exists(bf):
            continue
        bg = json.load(open(bf))["game"]
        kind = "po" if gm.get("kind") == "po" or str(gm.get("kind", "")).startswith("p") else "reg"
        sides = {bg["homeTeam"]["teamTricode"]: bg["homeTeam"], bg["awayTeam"]["teamTricode"]: bg["awayTeam"]}
        # SCORE first (leak-free: only prior games in hist)
        for tri, tm in sides.items():
            if tri not in MINE:
                continue
            tpred = {hl: 0.0 for hl in HALFLIVES}; tact = 0.0
            for p in tm.get("players", []):
                st = _pstat(p); pid = int(p["personId"])
                h = hist[pid]
                tot_min = sum(m for _, m in h)
                if st["min"] < 12 or tot_min < MIN_PRIOR_MIN:
                    continue
                tact += st["pts"]
                n = len(h)
                for hl in HALFLIVES:
                    if hl == np.inf:
                        w = np.ones(n)
                    else:
                        ages = np.arange(n - 1, -1, -1.0)        # most recent = age 0
                        w = 0.5 ** (ages / hl)
                    pts = np.array([pp for pp, _ in h]); mins = np.array([mm for _, mm in h])
                    ppm = (np.sum(w * pts) + PRIOR_K * M0) / (np.sum(w * mins) + PRIOR_K)
                    pred = ppm * st["min"]
                    e = pred - st["pts"]
                    err[hl]["all"].append(e); err[hl][kind].append(e)
                    tpred[hl] += pred
            if tact > 0:
                for hl in HALFLIVES:
                    terr[hl][kind].append(tpred[hl] - tact)
        # THEN update history with this game
        for tri, tm in sides.items():
            if tri not in MINE:
                continue
            for p in tm.get("players", []):
                st = _pstat(p)
                if st["min"] > 0:
                    hist[int(p["personId"])].append((st["pts"], st["min"]))

    print("=== RECENCY vs FLAT (walk-forward, leak-free) ===\n")
    print(f"  half-life (games) | {'ALL MAE/bias':>16s} | {'REG MAE/bias':>16s} | {'PLAYOFF MAE/bias':>16s}")
    for hl in HALFLIVES:
        tag = "flat" if hl == np.inf else f"{hl:.0f}"
        def s(k):
            e = np.array(err[hl][k]); return f"{np.abs(e).mean():6.2f} {e.mean():+6.2f}" if len(e) else "   n/a"
        print(f"  {tag:>17s} | {s('all'):>16s} | {s('reg'):>16s} | {s('po'):>16s}")
    na = len(err[np.inf]['all']); npo = len(err[np.inf]['po'])
    print(f"\n  n={na} player-games ({npo} playoff). lower MAE under a finite half-life => recency helps.")
    print("\n  TEAM-TOTAL bias (sum of rotation preds - actual), by kind:")
    print(f"  {'half-life':>9s} | {'REG team bias':>14s} | {'PLAYOFF team bias':>17s}")
    for hl in HALFLIVES:
        tag = "flat" if hl == np.inf else f"{hl:.0f}"
        tr = np.array(terr[hl]["reg"]); tp = np.array(terr[hl]["po"])
        print(f"  {tag:>9s} | {tr.mean():+14.2f} | {tp.mean():+17.2f}")
    print("\n  caveat: leak-free as-of; pts=ppm*actual_min (minutes given). bias<0 => under-predicts.")


if __name__ == "__main__":
    main()
