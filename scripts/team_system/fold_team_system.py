"""NYK/SAS Team System — Stage 4: fold into the vault + Finals War Room.

Writes:
  - "## PBP System — Current Season" into vault/Intelligence/Teams/{NYK,SAS}.md
  - "## Real 2025-26 Lineups (PBP)" into vault/Intelligence/Lineups/{NYK,SAS}_lineups.md
  - vault/Intelligence/Previews/NYK_SAS_Finals_WarRoom.md  (the head-to-head crown doc)

All idempotent (marker upsert). Run after build_team_system.py.
  python scripts/team_system/fold_team_system.py
"""
from __future__ import annotations

import json
import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
VINT = os.path.join(ROOT, "vault", "Intelligence")
TEAMS_DIR = os.path.join(VINT, "Teams")
LINE_DIR = os.path.join(VINT, "Lineups")
PREV_DIR = os.path.join(VINT, "Previews")
PS, PE = "<!-- PBP-SYSTEM START -->", "<!-- PBP-SYSTEM END -->"
LS, LE = "<!-- PBP-LINEUPS START -->", "<!-- PBP-LINEUPS END -->"


def upsert(fp, start, end, block, create=False):
    if os.path.exists(fp):
        txt = open(fp, encoding="utf-8").read()
        if start in txt and end in txt:
            txt = re.sub(re.escape(start) + r".*?" + re.escape(end) + r"\n?", "", txt, flags=re.S)
        txt = txt.rstrip() + "\n\n" + block
    elif create:
        txt = block
    else:
        return False
    open(fp, "w", encoding="utf-8").write(txt)
    return True


def team_block(t, s, as_of):
    L = [PS, "", f"## PBP System — Current Season (live, PBP-derived)",
         f"*Built from every 2025-26 {t} game's play-by-play (cdn.nba.com). **As of {as_of}.** "
         f"Four factors, lineup net ratings, and rotation reconstructed from substitution events. "
         f"Refresh: `python scripts/team_system/update.py`.*", "",
         f"**Record {s['record']} · Net {s['net_rtg']:+.1f}** (Off {s['off_rtg']} / Def {s['def_rtg']}) · Pace {s['pace']}",
         f"- **Offense:** eFG {s['efg']:.3f} · TOV% {s['tov_pct']:.1%} · OREB% {s['oreb_pct']:.1%} · "
         f"FTr {s['ftr']:.3f} · 3PA-rate {s['fg3a_rate']:.1%}",
         f"- **Defense:** forces opp TOV% {s['tov_forced_pct']:.1%} (def rating {s['def_rtg']})",
         f"- **Quarter scoring (avg):** Q1 {s['q_for'][0]} · Q2 {s['q_for'][1]} · Q3 {s['q_for'][2]} · Q4 {s['q_for'][3]}",
         f"- **Last 10:** {s['last10_record']}, net {s['last10_net']:+.1f}"]
    if s.get("playoff"):
        po = s["playoff"]
        L.append(f"- **Playoffs:** {po['record']}, net {po['net_rtg']:+.1f} (off {po['off_rtg']} / def {po['def_rtg']})")
    L += ["", "**Top real 2025-26 lineups (PBP stints, ≥12 min):**"]
    for l in s["top_lineups"][:6]:
        L.append(f"- {l['min']:.0f}m · net **{l['net']:+.1f}** (off {l['off_rtg']} / def {l['def_rtg']}) — {l['lineup']}")
    rot = " · ".join(f"{r['player']} {r['mpg']}" for r in s["rotation"][:9])
    L += ["", f"**Rotation (mpg):** {rot}", "", PE, ""]
    return "\n".join(L)


def lineup_block(t, s):
    L = [LS, "", "## Real 2025-26 Lineups (PBP-derived)",
         "*Reconstructed from substitution events across every 2025-26 game (the current-season "
         "replacement for the stale 2024-25 LeagueDashLineups block above). Net = off−def rating per 100.*", ""]
    for l in s["top_lineups"]:
        L.append(f"- {l['min']:.0f}m · net **{l['net']:+.1f}** (off {l['off_rtg']} / def {l['def_rtg']}, "
                 f"{l['poss']:.0f} poss) — {l['lineup']}")
    L += ["", LE, ""]
    return "\n".join(L)


def _finals_scoring(gids):
    """Top scorers per team across the Finals games, from boxscores."""
    agg = {}
    for gid in gids:
        bf = os.path.join(TS, "box", f"{gid}.json")
        if not os.path.exists(bf):
            continue
        g = json.load(open(bf))["game"]
        for tm in (g["homeTeam"], g["awayTeam"]):
            tri = tm["teamTricode"]
            for p in tm.get("players", []):
                st = p.get("statistics", {})
                pts = st.get("points", 0) or 0
                d = agg.setdefault((tri, p.get("name")), [0, 0])
                d[0] += pts; d[1] += 1
    out = {}
    for (tri, name), (pts, gp) in agg.items():
        out.setdefault(tri, []).append((name, pts / gp if gp else 0, gp))
    for tri in out:
        out[tri] = sorted(out[tri], key=lambda x: -x[1])[:5]
    return out


def war_room(summary, finals_gids):
    h = summary["h2h"]; n, sa = summary["teams"]["NYK"], summary["teams"]["SAS"]
    nf, sf = h["nyk_ff_vs_sas"], h["sas_ff_vs_nyk"]
    lead = "NYK" if h["finals_series"].split("-")[0] > h["finals_series"].split("-")[1] else "SAS"
    scor = _finals_scoring(finals_gids)
    L = [f"# NYK vs SAS — Finals War Room",
         f"*Live PBP-derived head-to-head. **As of {summary['as_of']}.** "
         f"Refresh: `python scripts/team_system/update.py`. Links: [[Teams/NYK]] · [[Teams/SAS]] · "
         f"[[Lineups/NYK_lineups]] · [[Lineups/SAS_lineups]].*", "",
         f"## Series state — **NYK {h['finals_series']} SAS** ({lead} leads)", ""]
    for gm in h["finals_games"]:
        L.append(f"- {gm['date']}: NYK {gm['site']} SAS **{gm['nyk']}-{gm['sas']}** — "
                 f"{'NYK' if gm['nyk_win'] else 'SAS'} win")
    L += ["", f"Full-season meetings: {h['n_games']} games, NYK {h['nyk_wins']}-{h['sas_wins']}.", ""]
    for gm in h["games"]:
        if gm["kind"] == "reg":
            L.append(f"- (reg) {gm['date']}: NYK {gm['site']} SAS {gm['nyk']}-{gm['sas']} "
                     f"({'NYK' if gm['nyk_win'] else 'SAS'})")
    L += ["", "## Head-to-head four factors (in NYK–SAS games)", "",
          "| | Off Rtg | Def Rtg | eFG% | TOV% | OREB% | FTr | Pace |",
          "|---|--|--|--|--|--|--|--|",
          f"| **NYK** | {nf['off_rtg']} | {nf['def_rtg']} | {nf['efg']:.3f} | {nf['tov_pct']:.1%} | "
          f"{nf['oreb_pct']:.1%} | {nf['ftr']:.3f} | {nf['pace']} |",
          f"| **SAS** | {sf['off_rtg']} | {sf['def_rtg']} | {sf['efg']:.3f} | {sf['tov_pct']:.1%} | "
          f"{sf['oreb_pct']:.1%} | {sf['ftr']:.3f} | {sf['pace']} |", "",
          "**Edges:** " + _edges(nf, sf), ""]
    # Finals scoring leaders
    L += ["## Finals scoring leaders (per game, so far)", ""]
    for t in ("NYK", "SAS"):
        lead_s = " · ".join(f"{nm} {pp:.1f}" for nm, pp, gp in scor.get(t, []))
        L.append(f"- **{t}:** {lead_s}")
    L += ["", "## Top lineups this matchup brings"]
    for t, s in (("NYK", n), ("SAS", sa)):
        L.append(f"\n**{t}** (season net / minutes):")
        for l in s["top_lineups"][:4]:
            L.append(f"- {l['min']:.0f}m net **{l['net']:+.1f}** — {l['lineup']}")
    L += ["", "## Season form into the series", "",
          f"- **NYK:** {n['record']}, net {n['net_rtg']:+.1f} · last-10 {n['last10_record']} ({n['last10_net']:+.1f})"
          + (f" · playoffs {n['playoff']['record']} net {n['playoff']['net_rtg']:+.1f}" if n.get('playoff') else ""),
          f"- **SAS:** {sa['record']}, net {sa['net_rtg']:+.1f} · last-10 {sa['last10_record']} ({sa['last10_net']:+.1f})"
          + (f" · playoffs {sa['playoff']['record']} net {sa['playoff']['net_rtg']:+.1f}" if sa.get('playoff') else ""),
          "", "*Descriptive scouting from play-by-play — not a betting projection.*", ""]
    return "\n".join(L)


def _edges(nf, sf):
    e = []
    if nf["efg"] > sf["efg"]:
        e.append(f"NYK shooting better (eFG {nf['efg']:.3f} vs {sf['efg']:.3f})")
    if sf["tov_pct"] > nf["tov_pct"] + 0.02:
        e.append(f"SAS turning it over more ({sf['tov_pct']:.1%} vs {nf['tov_pct']:.1%}) — NYK feeds off it")
    if sf["ftr"] > nf["ftr"] + 0.05:
        e.append(f"SAS getting to the line more (FTr {sf['ftr']:.3f} vs {nf['ftr']:.3f})")
    if nf["oreb_pct"] > sf["oreb_pct"] + 0.02:
        e.append(f"NYK winning the offensive glass ({nf['oreb_pct']:.1%} vs {sf['oreb_pct']:.1%})")
    return "; ".join(e) if e else "even across the four factors so far."


def main():
    s = json.load(open(os.path.join(TS, "summary.json")))
    as_of = s["as_of"]
    tg = pd.read_parquet(os.path.join(TS, "team_game.parquet"))
    finals_gids = sorted(tg[(tg.team == "NYK") & (tg.opp == "SAS") & (tg.kind == "playoff")].gid.tolist())

    done = []
    for t in ("NYK", "SAS"):
        st = s["teams"][t]
        if upsert(os.path.join(TEAMS_DIR, f"{t}.md"), PS, PE, team_block(t, st, as_of)):
            done.append(f"{t} team note")
        if upsert(os.path.join(LINE_DIR, f"{t}_lineups.md"), LS, LE, lineup_block(t, st), create=True):
            done.append(f"{t} lineups")
    os.makedirs(PREV_DIR, exist_ok=True)
    wr = os.path.join(PREV_DIR, "NYK_SAS_Finals_WarRoom.md")
    open(wr, "w", encoding="utf-8").write(war_room(s, finals_gids))
    done.append("Finals War Room")
    print("DONE folded:", " | ".join(done))
    print("  War Room:", wr)


if __name__ == "__main__":
    main()
