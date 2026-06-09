"""Team physical / size identity -> Obsidian team notes.

Aggregates player attributes (minute-weighted) into a team's size profile: how big the
rotation is, the rim anchor, frontcourt vs backcourt size, and whether the team plays big
or small. Complements the rate-based ## PBP System with the physical dimension the user
flagged (size shapes rebounding, rim protection, matchups).

  python scripts/team_system/fold_team_size.py
"""
from __future__ import annotations

import os
import re

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
TEAMS = os.path.join(ROOT, "vault", "Intelligence", "Teams")
START, END = "<!-- SIGNALS:team-size START -->", "<!-- SIGNALS:team-size END -->"
LEAGUE_H = 78.4


def _hw(inch):
    return f"{int(inch // 12)}'{int(inch % 12)}\""


def block(tri, sub):
    sub = sub.sort_values("mpg", ascending=False)
    starters = sub.head(5)
    w = sub["mpg"].to_numpy()
    wavg_h = float(np.average(sub["height_in"], weights=w))
    start_h = float(starters["height_in"].mean())
    anchor = sub.loc[sub["height_in"].idxmax()]
    guards = sub[sub["pos"] == "G"]; bigs = sub[sub["pos"].isin(["BIG", "C"])]
    g_h = float(guards.head(3)["height_in"].mean()) if len(guards) else float("nan")
    b_h = float(bigs.head(2)["height_in"].mean()) if len(bigs) else float("nan")
    avg_age = float(np.average(sub["age"], weights=w))
    n_rim = int((sub["is_rim_protector"] == 1).sum())
    tag = ("big / long" if wavg_h > LEAGUE_H + 0.6 else "small / switchy" if wavg_h < LEAGUE_H - 0.6 else "average-size")
    L = [START, "", "## Team Size & Identity",
         "*Minute-weighted physical profile from player attributes — shapes rebounding, rim "
         "protection, and matchup size. (Pairs with the rate-based ## PBP System.)*", "",
         f"**Rotation size:** {_hw(wavg_h)} avg ({wavg_h - LEAGUE_H:+.1f}\" vs league) — **{tag}** · "
         f"starters {_hw(start_h)} · weighted age {avg_age:.1f}",
         f"**Rim anchor:** {anchor['player_name']} ({_hw(anchor['height_in'])}, {anchor['weight_lb']:.0f} lb)"
         f"{' — elite rim protector' if anchor['height_in'] >= 84 else ''} · {n_rim} rotation bigs ≥6'10\"",
         f"**Backcourt:** ~{_hw(g_h)} guards" + ("  ·  **undersized backcourt**" if g_h < 75.5 else "")
         if not np.isnan(g_h) else "",
         f"**Frontcourt:** ~{_hw(b_h)} bigs" if not np.isnan(b_h) else "",
         f"**Sim effect:** opponents' rim makes are scaled by this team's tallest on-court protector "
         f"({_hw(anchor['height_in'])} → rim suppression when they anchor the paint).",
         "", END, ""]
    return "\n".join(x for x in L if x is not None)


def upsert(fp, blk):
    if not os.path.exists(fp):
        return False
    txt = open(fp, encoding="utf-8").read()
    if START in txt and END in txt:
        txt = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", "", txt, flags=re.S)
    open(fp, "w", encoding="utf-8").write(txt.rstrip() + "\n\n" + blk)
    return True


def main():
    attr = pd.read_parquet(os.path.join(TS, "player_attributes.parquet"))
    rates = pd.read_parquet(os.path.join(TS, "player_rates.parquet"))[["pid", "team", "mpg"]]
    df = rates.merge(attr, on="pid", how="inner")
    df = df[df.mpg >= 8]
    done = []
    for tri in ("NYK", "SAS"):
        sub = df[df.team == tri]
        if sub.empty:
            continue
        if upsert(os.path.join(TEAMS, f"{tri}.md"), block(tri, sub)):
            done.append(tri)
            s = sub.sort_values("mpg", ascending=False)
            anchor = s.loc[s["height_in"].idxmax()]
            wavg = np.average(s["height_in"], weights=s["mpg"])
            print(f"  {tri}: rotation {_hw(wavg)} avg, anchor {anchor['player_name']} {_hw(anchor['height_in'])}")
    print(f"DONE: team size identity folded into {done}")


if __name__ == "__main__":
    main()
