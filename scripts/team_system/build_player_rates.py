"""Highest-fidelity basketball sim — Stage A: per-player & per-team RATE model.

Extracts the parameters a possession engine needs, straight from cached boxscores + PBP
(the most faithful, non-broadcast-CV source). For every player who appears in the cached
NYK/SAS games, aggregates season rates; for each team, the pace, assist/rebound/steal
structure, and the empirical 5-man lineup minute distribution (for shared-pie sampling).

Outputs:
  data/cache/team_system/player_rates.parquet  — one row per player
  data/cache/team_system/team_rates.json       — per-team aggregate rates + lineup weights

Usage rate among on-court teammates is the KEY to correct teammate correlation: exactly one
of the 5 on-court players uses each possession, so the scoring pie is shared (this is what
fixes the game_simulator teammate-rho 0.645 bug).

  python scripts/team_system/build_player_rates.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pbp_parse import parse_game, _shot_zone  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
PBP_DIR, BOX_DIR = os.path.join(TS, "pbp"), os.path.join(TS, "box")
ZONES = ["rim", "paint", "mid", "3"]


def _pstat(p):
    s = p.get("statistics", {})
    mins = s.get("minutesCalculated") or s.get("minutes") or "PT0M"
    # minutes like "PT34M12.00S" -> minutes float
    import re
    m = re.match(r"PT(?:(\d+)M)?(?:([\d.]+)S)?", str(mins))
    mn = (float(m.group(1) or 0) + float(m.group(2) or 0) / 60.0) if m else 0.0
    return dict(min=mn, pts=s.get("points", 0) or 0, fga=s.get("fieldGoalsAttempted", 0) or 0,
               fgm=s.get("fieldGoalsMade", 0) or 0, fg3a=s.get("threePointersAttempted", 0) or 0,
               fg3m=s.get("threePointersMade", 0) or 0, fta=s.get("freeThrowsAttempted", 0) or 0,
               ftm=s.get("freeThrowsMade", 0) or 0, oreb=s.get("reboundsOffensive", 0) or 0,
               dreb=s.get("reboundsDefensive", 0) or 0, ast=s.get("assists", 0) or 0,
               stl=s.get("steals", 0) or 0, blk=s.get("blocks", 0) or 0,
               tov=s.get("turnovers", 0) or 0, pf=s.get("foulsPersonal", 0) or 0)


def main():
    games = json.load(open(os.path.join(TS, "nyk_sas_games.json")))
    P = defaultdict(lambda: defaultdict(float))   # player_id -> stat sums
    pname, pteam = {}, {}
    zoneA = defaultdict(lambda: defaultdict(float)); zoneM = defaultdict(lambda: defaultdict(float))
    T = defaultdict(lambda: defaultdict(float))   # team -> sums (fga,fgm,fta,tov,ast,oreb,dreb,stl,blk,poss,pts,opp_dreb,mfg)
    lineups = defaultdict(lambda: defaultdict(float))  # team -> lineup(ids tuple) -> minutes
    ngames = defaultdict(int)

    for gm in games:
        gid = gm["gid"]
        bf, pf = os.path.join(BOX_DIR, f"{gid}.json"), os.path.join(PBP_DIR, f"{gid}.json")
        if not (os.path.exists(bf) and os.path.exists(pf)):
            continue
        box = json.load(open(bf)); g = parse_game(json.load(open(pf)), box)
        bg = box["game"]
        for tm in (bg["homeTeam"], bg["awayTeam"]):
            tri = tm["teamTricode"]
            for p in tm.get("players", []):
                pid = int(p["personId"]); st = _pstat(p)
                if st["min"] <= 0:
                    continue
                pname[pid] = p.get("name") or str(pid); pteam[pid] = tri
                for k, v in st.items():
                    P[pid][k] += v
                P[pid]["g"] += 1
        # team aggregates from parsed game (both NYK/SAS teams in the game)
        for tid in (g["home_id"], g["away_id"]):
            tri = g["home"] if tid == g["home_id"] else g["away"]
            oid = g["away_id"] if tid == g["home_id"] else g["home_id"]
            tt, ot = g["team_game"][tid], g["team_game"][oid]
            for k in ("fga", "fgm", "fg3a", "fg3m", "fta", "ftm", "oreb", "dreb", "tov", "ast", "pts", "poss"):
                T[tri][k] += tt[k]
            T[tri]["opp_dreb"] += ot["dreb"]
            T[tri]["opp_pts"] += ot["pts"]; T[tri]["opp_poss"] += ot["poss"]
            T[tri]["miss"] += tt["fga"] - tt["fgm"]
            ngames[tri] += 1
        # zones per player from PBP
        for act in json.load(open(pf)).get("game", {}).get("actions", []):
            if act.get("actionType") in ("2pt", "3pt") and act.get("personId"):
                pid = int(act["personId"]); z = _shot_zone(act)
                zoneA[pid][z] += 1
                if act.get("shotResult") == "Made":
                    zoneM[pid][z] += 1
        # lineup minute weights (size-5 stints) per team
        for s in g["stints"]:
            if len(s["h5"]) == 5:
                lineups[g["home"]][s["h5"]] += s["dur"] / 60.0
            if len(s["a5"]) == 5:
                lineups[g["away"]][s["a5"]] += s["dur"] / 60.0

    # ---- player rate rows ----
    rows = []
    for pid, d in P.items():
        mn = d["min"]
        if mn < 1:
            continue
        ft_trip = 0.44 * d["fta"]
        used = d["fga"] + ft_trip + d["tov"]
        za = {z: zoneA[pid].get(z, 0) for z in ZONES}; zt = sum(za.values()) or 1
        zfg = {z: (zoneM[pid].get(z, 0) / za[z]) if za[z] >= 5 else None for z in ZONES}
        rows.append({
            "pid": pid, "player": pname[pid], "team": pteam[pid], "g": int(d["g"]), "min": round(mn, 1),
            "mpg": round(mn / d["g"], 1) if d["g"] else 0,
            "use_per_min": round(used / mn, 4),                       # usage routing weight
            "shot_share": round(d["fga"] / used, 3) if used else 0,   # of a used poss
            "tov_share": round(d["tov"] / used, 3) if used else 0,
            "ft_share": round(ft_trip / used, 3) if used else 0,
            "fg3_rate": round(d["fg3a"] / d["fga"], 3) if d["fga"] else 0,
            "fg3_pct": round(d["fg3m"] / d["fg3a"], 3) if d["fg3a"] else 0.34,
            "ft_pct": round(d["ftm"] / d["fta"], 3) if d["fta"] >= 5 else 0.78,
            "ast_per_min": round(d["ast"] / mn, 4), "oreb_per_min": round(d["oreb"] / mn, 4),
            "dreb_per_min": round(d["dreb"] / mn, 4), "stl_per_min": round(d["stl"] / mn, 4),
            "blk_per_min": round(d["blk"] / mn, 4), "pf_per_min": round(d["pf"] / mn, 4),
            "z_rim": round(za["rim"] / zt, 3), "z_paint": round(za["paint"] / zt, 3),
            "z_mid": round(za["mid"] / zt, 3), "z_3": round(za["3"] / zt, 3),
            "fg_rim": zfg["rim"], "fg_paint": zfg["paint"], "fg_mid": zfg["mid"],
            "pts_pg": round(d["pts"] / d["g"], 1),
            # fraction of a player's points that come from FREE THROWS -> the anchor's FT-defense
            # matchup scales this portion by the opponent's foul-environment factor (ft_force).
            "ft_pts_share": round(d["ftm"] / d["pts"], 3) if d["pts"] else 0.0,
        })
    pr = pd.DataFrame(rows)
    pr.to_parquet(os.path.join(TS, "player_rates.parquet"), index=False)

    # ---- team rates + lineup weights ----
    tr = {}
    for tri, d in T.items():
        gp = ngames[tri]
        tr[tri] = {
            "pace": round(d["poss"] / gp, 1),
            "ast_rate_on_make": round(d["ast"] / d["fgm"], 3) if d["fgm"] else 0.6,   # P(made FG assisted)
            "oreb_per_miss": round(d["oreb"] / d["miss"], 3) if d["miss"] else 0.25,
            "fg3_rate": round(d["fg3a"] / d["fga"], 3) if d["fga"] else 0.4,
            "ortg": round(100 * d["pts"] / d["poss"], 1) if d["poss"] else 110,
            "def_rtg": round(100 * d["opp_pts"] / d["opp_poss"], 1) if d["opp_poss"] else 113.3,
            "lineups": [{"ids": list(k), "min": round(v, 1)} for k, v in
                        sorted(lineups[tri].items(), key=lambda x: -x[1]) if v >= 1.0],
        }
    json.dump(tr, open(os.path.join(TS, "team_rates.json"), "w"), indent=1)

    asc = lambda s: str(s).encode("ascii", "replace").decode()
    print(f"DONE: {len(pr)} player rate rows; teams {len(tr)}")
    for tri in ("NYK", "SAS"):
        nl = len(tr[tri]["lineups"])
        top = pr[(pr.team == tri) & (pr.mpg >= 12)].nlargest(3, "use_per_min")[["player", "use_per_min"]].values.tolist()
        print(f"  {tri}: pace {tr[tri]['pace']} ortg {tr[tri]['ortg']} astRate {tr[tri]['ast_rate_on_make']} "
              f"orebPerMiss {tr[tri]['oreb_per_miss']} | {nl} lineups | top-usage "
              f"{[(asc(p), u) for p, u in top]}")


if __name__ == "__main__":
    main()
