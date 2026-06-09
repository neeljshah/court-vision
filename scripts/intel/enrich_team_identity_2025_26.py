"""Append a 2025-26 TEAM IDENTITY block to each Matchups/<TEAM>.md note
(deterministic, current-season). Idempotent (marker-wrapped). Non-conflicting
with player-note waves.

Pulls: record + scoring from leaguegamelog_regular_season (2025-26), opponent
stat-allowed (final season-to-date) from pit/opp_allowed_asof_2025_26_reg, top
scorers from intel/season_2025_26.json.
"""
from __future__ import annotations
import os, re, json
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GL = os.path.join(ROOT, "data", "cache", "cv_fix", "leaguegamelog_regular_season.parquet")
OPP = os.path.join(ROOT, "data", "cache", "pit", "opp_allowed_asof_2025_26_reg.parquet")
SEASON = os.path.join(ROOT, "data", "cache", "intel", "season_2025_26.json")
MATCHUPS = os.path.join(ROOT, "vault", "Intelligence", "Matchups")
START, END = "<!-- TEAM-ID-2526-START -->", "<!-- TEAM-ID-2526-END -->"


def main():
    gl = pd.read_parquet(GL)
    gl["GAME_DATE"] = pd.to_datetime(gl["GAME_DATE"])
    # team-game totals
    tg = gl.groupby(["GAME_ID", "TEAM_ABBREVIATION"]).agg(
        pts=("PTS", "sum"), reb=("REB", "sum"), ast=("AST", "sum"),
        fg3m=("FG3M", "sum"), tov=("TOV", "sum"), fga=("FGA", "sum"),
        fta=("FTA", "sum"), oreb=("OREB", "sum"), wl=("WL", "first")).reset_index()
    # record + scoring
    teamstat = {}
    for team, sub in tg.groupby("TEAM_ABBREVIATION"):
        w = int((sub.wl == "W").sum()); l = int((sub.wl == "L").sum())
        poss = (sub.fga + 0.44 * sub.fta - sub.oreb + sub.tov)
        teamstat[team] = {
            "g": len(sub), "w": w, "l": l,
            "pts": round(float(sub.pts.mean()), 1), "ast": round(float(sub.ast.mean()), 1),
            "reb": round(float(sub.reb.mean()), 1), "fg3m": round(float(sub.fg3m.mean()), 1),
            "poss": round(float(poss.mean()), 1),
        }
    # opponent allowed (final season-to-date per team)
    oa = pd.read_parquet(OPP)
    oa = oa.sort_values("game_date").groupby("team").tail(1).set_index("team")
    # top scorers
    season = json.load(open(SEASON, encoding="utf-8")).get("reg", {})
    by_team = {}
    for pid, r in season.items():
        by_team.setdefault(r["team"], []).append((r["pts"], r["name"], r["reb"], r["ast"], r["min"]))
    for t in by_team:
        by_team[t].sort(reverse=True)

    written = 0
    for team, st in teamstat.items():
        target = os.path.join(MATCHUPS, f"{team}.md")
        L = [START, "", "## 2025-26 Team Identity",
             f"- **Record:** {st['w']}-{st['l']} ({st['g']}g) · **Pace (poss/g est):** {st['poss']}",
             f"- **Offense:** {st['pts']} pts · {st['ast']} ast · {st['reb']} reb · {st['fg3m']} 3pm per game"]
        if team in oa.index:
            r = oa.loc[team]
            def f(k):
                v = r.get(k)
                return round(float(v), 1) if v == v else "–"
            L.append(f"- **Defense allows (season-to-date):** {f('opp_pts_allowed_asof')} pts · "
                     f"{f('opp_ast_allowed_asof')} ast · {f('opp_reb_allowed_asof')} reb · "
                     f"{f('opp_fg3m_allowed_asof')} 3pm · forces {f('opp_tov_allowed_asof')} tov "
                     f"(allowed-to-opp; vs-league ast {f('opp_ast_allowed_vs_league')})")
        tops = by_team.get(team, [])[:4]
        if tops:
            L.append("- **Top scorers:** " + " · ".join(f"{nm} {p}p/{a}a" for p, nm, rb, a, mn in tops))
        L += ["", END, ""]
        block = "\n".join(L)
        if os.path.exists(target):
            txt = open(target, encoding="utf-8").read()
            if START in txt and END in txt:
                txt = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", "", txt, flags=re.S)
            # put identity near top: after first heading line
            lines = txt.split("\n")
            ins = 1 if lines and lines[0].startswith("#") else 0
            txt = "\n".join(lines[:ins] + ["", block] + lines[ins:])
        else:
            txt = f"# {team}\n\n{block}"
        open(target, "w", encoding="utf-8").write(txt)
        written += 1
    print(f"DONE: 2025-26 identity block on {written} team notes")


if __name__ == "__main__":
    main()
