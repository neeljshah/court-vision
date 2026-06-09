"""Per-ENTITY adaptive effects — signals unique to each player, that strengthen with data.

The league-average modulators (signal_effects.json) are only the FLOOR/prior. Real basketball
is per-entity: Brunson may shoot better on the road; a team may play better at a specific venue.
This builds each PLAYER's OWN home/road shooting effect via partial pooling (empirical Bayes):

    player_effect = league_effect ^ (1-w)  *  player_raw_effect ^ w ,   w = n / (n + K)

w (confidence) grows with the player's sample, so the signal AUTO-STRENGTHENS toward the
player's own truth as data accumulates and stays near the league prior when data is thin.
This is the template for ALL signals (B2B, vs-opponent, lineup, clutch…): same shrinkage spine.

Output: data/cache/team_system/player_effects.parquet (per player: home_xfg, road_xfg, conf, raw).

  python scripts/team_system/build_entity_effects.py
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
BOX = os.path.join(TS, "box")
K_SHRINK = 18.0                 # games at which w=0.5 (own data == league prior)
LEAGUE_HOME_XFG = 1.010         # home eFG vs the player's own overall (from home_road effect)
LEAGUE_ROAD_XFG = 0.990


def _efg(s):
    return (s["fgm"] + 0.5 * s["fg3m"]) / s["fga"] if s["fga"] else None


def main():
    games = json.load(open(os.path.join(TS, "nyk_sas_games.json")))
    # per player: accumulate home/road/overall eFG numerator/denominator
    H = defaultdict(lambda: [0.0, 0.0, 0])   # [efg_pts, fga, n_games]  home
    R = defaultdict(lambda: [0.0, 0.0, 0])   # road
    name, team = {}, {}
    for gm in games:
        bf = os.path.join(BOX, f"{gm['gid']}.json")
        if not os.path.exists(bf):
            continue
        bg = json.load(open(bf))["game"]
        home_tri = bg["homeTeam"]["teamTricode"]
        for tm in (bg["homeTeam"], bg["awayTeam"]):
            is_home = tm["teamTricode"] == home_tri
            for p in tm.get("players", []):
                st = _pstat(p)
                if st["fga"] < 1:
                    continue
                pid = int(p["personId"]); name[pid] = p.get("name") or str(pid); team[pid] = tm["teamTricode"]
                bucket = H if is_home else R
                bucket[pid][0] += st["fgm"] + 0.5 * st["fg3m"]
                bucket[pid][1] += st["fga"]
                bucket[pid][2] += 1

    rows = []
    for pid in set(H) | set(R):
        hn, rn = H[pid][2], R[pid][2]
        h_efg = H[pid][0] / H[pid][1] if H[pid][1] else None
        r_efg = R[pid][0] / R[pid][1] if R[pid][1] else None
        ov = ((H[pid][0] + R[pid][0]) / (H[pid][1] + R[pid][1])) if (H[pid][1] + R[pid][1]) else None
        if not ov:
            continue
        # raw per-player multipliers vs own overall
        h_raw = (h_efg / ov) if h_efg else LEAGUE_HOME_XFG
        r_raw = (r_efg / ov) if r_efg else LEAGUE_ROAD_XFG
        wh = hn / (hn + K_SHRINK); wr = rn / (rn + K_SHRINK)
        # geometric shrink toward league prior
        h_mult = LEAGUE_HOME_XFG ** (1 - wh) * h_raw ** wh
        r_mult = LEAGUE_ROAD_XFG ** (1 - wr) * r_raw ** wr
        rows.append({
            "pid": pid, "player": name[pid], "team": team[pid],
            "n_home": hn, "n_road": rn,
            "home_efg": round(h_efg, 3) if h_efg else None, "road_efg": round(r_efg, 3) if r_efg else None,
            "overall_efg": round(ov, 3),
            "home_xfg_raw": round(h_raw, 3), "road_xfg_raw": round(r_raw, 3),
            "home_xfg": round(h_mult, 3), "road_xfg": round(r_mult, 3),
            "conf_home": round(wh, 2), "conf_road": round(wr, 2),
            "plays_better_away": bool(r_raw > h_raw),
        })
    df = pd.DataFrame(rows).sort_values(["team", "n_home"], ascending=[True, False])
    df.to_parquet(os.path.join(TS, "player_effects.parquet"), index=False)

    asc = lambda s: str(s).encode("ascii", "replace").decode()
    print(f"DONE: per-player home/road effects for {len(df)} players (K={K_SHRINK:.0f}, league prior {LEAGUE_HOME_XFG}/{LEAGUE_ROAD_XFG})")
    print("\nProof — NYK/SAS rotation (raw home/road eFG -> shrunk multipliers; conf grows with games):")
    sub = df[(df.team.isin(["NYK", "SAS"])) & (df.n_home + df.n_road >= 20)].nlargest(12, "n_home")
    print(f"  {'player':22s} {'gH/gR':>7s} {'eFG H/R':>11s} {'rawH/R':>11s} {'shrunkH/R':>11s} conf away?")
    for r in sub.itertuples(index=False):
        print(f"  {asc(r.player):22s} {r.n_home:3d}/{r.n_road:<3d} "
              f"{(r.home_efg or 0):.3f}/{(r.road_efg or 0):.3f} {r.home_xfg_raw:.3f}/{r.road_xfg_raw:.3f} "
              f"{r.home_xfg:.3f}/{r.road_xfg:.3f} {r.conf_home:.2f} {'AWAY' if r.plays_better_away else 'home'}")


if __name__ == "__main__":
    main()
