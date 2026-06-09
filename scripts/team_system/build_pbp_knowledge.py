"""Mine knowledge from EVERY NYK/SAS game's play-by-play.

Box scores give totals; the play-by-play gives the real structure of how points happen. Walking
all 196 cached games' actions, this extracts per player (NYK/SAS):
  - REAL assisted vs self-created make rate (assistPersonId present or not) — ground truth, not an estimate
  - the REAL assist network: who assists whom (passer -> shooter pair counts) -> feeds the sim
  - shot-type diet (dunk/layup/jumper/floater/hook) + zone from area
  - fast-break & 2nd-chance scoring share (qualifiers)
  - free-throw generation (fouls drawn) and clutch FG% (period 4, <5min, <=5 pts)
  - defensive events: steals, blocks

Outputs:
  data/cache/team_system/pbp_player_knowledge.parquet   (per-player real rates)
  data/cache/team_system/assist_network.parquet         (assister_pid, scorer_pid, n) per team
Folds `## PBP Knowledge` into NYK/SAS player notes.

  python scripts/team_system/build_pbp_knowledge.py
"""
from __future__ import annotations

import glob
import json
import os
import re
from collections import defaultdict

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
PLAYERS = os.path.join(ROOT, "vault", "Intelligence", "Players")
MINE = {"NYK", "SAS"}
START, END = "<!-- SIGNALS:pbp-knowledge START -->", "<!-- SIGNALS:pbp-knowledge END -->"
ASC = lambda s: str(s).encode("ascii", "replace").decode()
_CLK = re.compile(r"PT(?:(\d+)M)?([\d.]+)S")


def _secs(clock):
    m = _CLK.match(str(clock or ""))
    return (float(m.group(1) or 0) * 60 + float(m.group(2) or 0)) if m else 0.0


def _shot_type(sub):
    s = (sub or "").lower()
    for key in ("dunk", "layup", "hook", "floating", "pullup", "step back", "fadeaway", "jump shot"):
        if key in s:
            return {"floating": "floater", "step back": "stepback", "jump shot": "jumper"}.get(key, key)
    return "other"


def main():
    games = json.load(open(os.path.join(TS, "nyk_sas_games.json")))
    P = defaultdict(lambda: defaultdict(float))   # pid -> counters
    name, team = {}, {}
    net = defaultdict(int)                          # (team, assister, scorer) -> n
    n_games = 0
    for gm in games:
        fp = os.path.join(TS, "pbp", f"{gm['gid']}.json")
        if not os.path.exists(fp):
            continue
        d = json.load(open(fp))
        acts = d.get("game", {}).get("actions") or d.get("actions") or []
        if not acts:
            continue
        n_games += 1
        for a in acts:
            tri = a.get("teamTricode")
            at = a.get("actionType"); pid = a.get("personId")
            if at in ("2pt", "3pt") and tri in MINE and pid:
                pid = int(pid); name[pid] = a.get("playerNameI", str(pid)); team[pid] = tri
                made = a.get("shotResult") == "Made"
                three = at == "3pt"
                quals = a.get("qualifiers") or []
                P[pid]["fga"] += 1
                if three:
                    P[pid]["fg3a"] += 1
                if made:
                    P[pid]["fgm"] += 1
                    pts = 3 if three else 2
                    P[pid]["pts"] += pts
                    if a.get("assistPersonId"):
                        P[pid]["assisted"] += 1
                        ap = int(a["assistPersonId"]); net[(tri, ap, pid)] += 1
                        name.setdefault(ap, a.get("assistPlayerNameInitial", str(ap)))
                    else:
                        P[pid]["unassisted"] += 1
                    if "fastbreak" in quals:
                        P[pid]["fastbreak_pts"] += pts
                    if "2ndchance" in quals:
                        P[pid]["2nd_chance_pts"] += pts
                    P[pid][f"st_{_shot_type(a.get('subType'))}"] += 1
                # clutch
                if a.get("period", 0) >= 4 and _secs(a.get("clock")) <= 300 and \
                        abs(int(a.get("scoreHome") or 0) - int(a.get("scoreAway") or 0)) <= 5:
                    P[pid]["clutch_fga"] += 1
                    P[pid]["clutch_fgm"] += int(made)
            elif at == "freethrow" and tri in MINE and pid:
                pid = int(pid); P[pid]["fta"] += 1; P[pid]["ftm"] += int(a.get("shotResult") == "Made")
            elif at == "steal" and tri in MINE and pid:
                P[int(pid)]["steals"] += 1
            elif at == "block" and tri in MINE and pid:
                P[int(pid)]["blocks"] += 1
            elif at == "foul" and pid:               # fouls drawn: descriptor "(Name N FT)" on the foul
                m = re.search(r"\((\d+) FT\)", a.get("description", ""))
                if m and "FT" in a.get("description", ""):
                    pass                              # FT count tracked via freethrow events instead

    rows = []
    for pid, c in P.items():
        if team.get(pid) not in MINE or c["fgm"] < 20:
            continue
        makes = c["assisted"] + c["unassisted"]
        rows.append({
            "pid": pid, "player": name.get(pid, str(pid)), "team": team[pid],
            "fgm": int(c["fgm"]), "fga": int(c["fga"]),
            "self_create_rate": round(c["unassisted"] / makes, 3) if makes else 0.5,
            "assisted_rate": round(c["assisted"] / makes, 3) if makes else 0.5,
            "fastbreak_pts_pg": round(c["fastbreak_pts"] / n_games, 2),
            "second_chance_pts_pg": round(c["2nd_chance_pts"] / n_games, 2),
            "clutch_fg_pct": round(c["clutch_fgm"] / c["clutch_fga"], 3) if c["clutch_fga"] >= 5 else None,
            "clutch_fga": int(c["clutch_fga"]),
            "dunk_sh": round(c["st_dunk"] / c["fgm"], 2), "layup_sh": round(c["st_layup"] / c["fgm"], 2),
            "jumper_sh": round(c["st_jumper"] / c["fgm"], 2),
            "steals_pg": round(c["steals"] / n_games, 2), "blocks_pg": round(c["blocks"] / n_games, 2),
        })
    df = pd.DataFrame(rows)
    df.to_parquet(os.path.join(TS, "pbp_player_knowledge.parquet"), index=False)
    netdf = pd.DataFrame([{"team": t, "assister": ap, "scorer": sp, "n": n} for (t, ap, sp), n in net.items()])
    netdf.to_parquet(os.path.join(TS, "assist_network.parquet"), index=False)

    folded = _fold(df, netdf, name)
    print(f"DONE: mined {n_games} games' PBP -> {len(df)} players, {len(netdf)} assist pairs; folded {folded} notes.")
    print("\nNYK/SAS real self-creation (PBP, unassisted make share) + top assist connection:")
    for r in df.sort_values("fgm", ascending=False).head(14).itertuples(index=False):
        top = netdf[(netdf.scorer == r.pid)].sort_values("n", ascending=False).head(1)
        feeder = name.get(int(top.assister.iloc[0]), "?") if len(top) else "-"
        fn = int(top.n.iloc[0]) if len(top) else 0
        print(f"  {ASC(r.player):20s} {r.team}  self-create {r.self_create_rate:.0%}  "
              f"fastbreak {r.fastbreak_pts_pg:.1f}/g  clutch {('%.0f%%' % (100*r.clutch_fg_pct)) if r.clutch_fg_pct else 'n/a':>4s}  "
              f"fed most by {ASC(feeder)} ({fn})")


def _fold(df, netdf, name):
    folded = 0
    for r in df.itertuples(index=False):
        cands = glob.glob(os.path.join(PLAYERS, f"{int(r.pid)}_*.md"))
        if not cands:
            continue
        feeders = netdf[netdf.scorer == r.pid].sort_values("n", ascending=False).head(3)
        assistees = netdf[netdf.assister == r.pid].sort_values("n", ascending=False).head(3)
        fed = ", ".join(f"{ASC(name.get(int(x.assister), '?'))} ({int(x.n)})" for x in feeders.itertuples(index=False)) or "-"
        feeds = ", ".join(f"{ASC(name.get(int(x.scorer), '?'))} ({int(x.n)})" for x in assistees.itertuples(index=False)) or "-"
        clutch = f"{r.clutch_fg_pct:.0%} on {r.clutch_fga}" if r.clutch_fg_pct is not None else "n/a"
        blk = (f"{START}\n\n## PBP Knowledge\n*Mined from every game's play-by-play (ground truth, not box "
               f"estimates).*\n\n"
               f"- **Self-created scoring:** {r.self_create_rate:.0%} of his makes are unassisted "
               f"(assisted {r.assisted_rate:.0%}).\n"
               f"- **Shot diet (of makes):** dunk {r.dunk_sh:.0%} / layup {r.layup_sh:.0%} / jumper {r.jumper_sh:.0%}.\n"
               f"- **Fast break:** {r.fastbreak_pts_pg:.1f} pts/g · **2nd chance:** {r.second_chance_pts_pg:.1f} pts/g.\n"
               f"- **Clutch FG (Q4, <5min, <=5pts):** {clutch}.\n"
               f"- **Fed most by:** {fed}.\n- **Assists most to:** {feeds}.\n\n{END}\n")
        txt = open(cands[0], encoding="utf-8").read()
        if START in txt:
            txt = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", "", txt, flags=re.S)
        open(cands[0], "w", encoding="utf-8").write(txt.rstrip() + "\n\n" + blk)
        folded += 1
    return folded


if __name__ == "__main__":
    main()
