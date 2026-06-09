"""Recency-weighted per-game rates -> captures the CURRENT regime (playoffs score below the season
rate) and current form. Walk-forward validated (walkforward_recency.py): flat season rates over-predict
playoff scoring +0.98/player; an exponentially recency-weighted rate cuts that to +0.11 and lowers
playoff MAE 4.18->4.05, while barely touching regular season at a moderate half-life.

For each NYK/SAS player, walks his games in chronological order and computes an exponentially weighted
per-game average (weight 0.5^(age_in_games/HALF_LIFE), most-recent age 0) of pts/reb/ast/min. Self-adapts:
when the recent games are playoffs, the rate reflects the playoff regime.

Output: data/cache/team_system/recency_rates.parquet (pid, pts_pg_rec, reb_pg_rec, ast_pg_rec, mpg_rec, gw)

  python scripts/team_system/build_recency_rates.py [--half_life 10]
"""
from __future__ import annotations

import argparse
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--half_life", type=float, default=10.0)
    a = ap.parse_args()
    games = sorted(json.load(open(os.path.join(TS, "nyk_sas_games.json"))), key=lambda g: (g["date"], g["gid"]))
    seq = defaultdict(list)   # pid -> [(pts,reb,ast,min)] chronological
    name, team = {}, {}
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
                if st["min"] <= 0:
                    continue
                pid = int(p["personId"])
                seq[pid].append((st["pts"], st["oreb"] + st["dreb"], st["ast"], st["min"]))
                name[pid] = p.get("name", str(pid)); team[pid] = tm["teamTricode"]

    rows = []
    for pid, g in seq.items():
        arr = np.array(g, dtype=float)              # cols: pts, reb, ast, min
        n = len(arr)
        ages = np.arange(n - 1, -1, -1.0)           # most recent = 0
        w = 0.5 ** (ages / a.half_life)
        wsum = w.sum()
        rows.append({
            "pid": pid, "player": name[pid], "team": team[pid], "g": n,
            "pts_pg_rec": round(float(np.sum(w * arr[:, 0]) / wsum), 2),
            "reb_pg_rec": round(float(np.sum(w * arr[:, 1]) / wsum), 2),
            "ast_pg_rec": round(float(np.sum(w * arr[:, 2]) / wsum), 2),
            "mpg_rec": round(float(np.sum(w * arr[:, 3]) / wsum), 1),
            "gw": round(float(wsum), 1),            # effective games of weight (recency-discounted)
        })
    df = pd.DataFrame(rows)
    df.to_parquet(os.path.join(TS, "recency_rates.parquet"), index=False)
    asc = lambda s: str(s).encode("ascii", "replace").decode()
    print(f"DONE: {len(df)} players, half_life={a.half_life} games -> recency_rates.parquet")
    # spot-check the Finals leaders: recency vs flat pts_pg
    flat = pd.read_parquet(os.path.join(TS, "player_rates.parquet")).set_index("pid")
    sub = df[df.team.isin(MINE)].sort_values("pts_pg_rec", ascending=False).head(8)
    print(f"  {'player':20s} {'flat ppg':>8s} {'rec ppg':>8s} {'flat mpg':>8s} {'rec mpg':>8s}")
    for r in sub.itertuples():
        fp = flat.loc[r.pid, "pts_pg"] if r.pid in flat.index else float("nan")
        fm = flat.loc[r.pid, "mpg"] if r.pid in flat.index else float("nan")
        print(f"  {asc(r.player):20s} {fp:8.1f} {r.pts_pg_rec:8.1f} {fm:8.1f} {r.mpg_rec:8.1f}")


if __name__ == "__main__":
    main()
