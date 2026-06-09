"""Robust per-player intelligence memory — consolidates EVERYTHING into one dossier.

Pulls physical attributes + sim rates + adaptive home/road effects into a single
"## Player Intelligence" section per NYK/SAS player note, so each player's memory holds
the full picture the simulator reasons over: who they are physically, how they score,
their size identity (rim protector / gets-blocked risk), and their entity-specific,
confidence-weighted context effects. Idempotent marker upsert.

  python scripts/team_system/fold_player_intelligence.py
"""
from __future__ import annotations

import glob
import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
PLAYERS = os.path.join(ROOT, "vault", "Intelligence", "Players")
START, END = "<!-- SIGNALS:player-intel START -->", "<!-- SIGNALS:player-intel END -->"


def _hw(inch):
    return f"{int(inch // 12)}'{int(inch % 12)}\""


def _frame(a):
    sz = "towering" if a.size_z > 1.5 else "big" if a.size_z > 0.5 else "undersized" if a.size_z < -0.8 else "average-size"
    st = "strong" if a.strength_z > 0.7 else "slight" if a.strength_z < -0.7 else "solid"
    return f"{sz} for a {a.pos}, {st} frame"


def block(a, r, e):
    role = "primary option" if r.use_per_min > 0.6 else "secondary creator" if r.use_per_min > 0.45 else "role player"
    L = [START, "", "## Player Intelligence",
         "*Consolidated memory the simulator reasons over — physical identity, scoring profile, "
         "and entity-specific (confidence-weighted) context effects. Updates as data grows.*", "",
         f"**Physical:** {_hw(a.height_in)} / {a.weight_lb:.0f} lb · age {a.age} · {a.exp}y exp · "
         f"{a.pos} — {_frame(a)} · agility {a.agility_proxy:+.2f}"
         + (" · **rim protector**" if a.is_rim_protector else "") + (" · undersized scorer" if a.is_small else ""),
         f"**Role:** {role} ({r.use_per_min:.2f} usage/min, {r.pts_pg:.1f} ppg, {r.mpg:.0f} mpg)",
         f"**Shot diet:** rim {r.z_rim:.0%} / paint {r.z_paint:.0%} / mid {r.z_mid:.0%} / three {r.z_3:.0%}"
         f"  ·  3PA rate {r.fg3_rate:.0%} @ {r.fg3_pct:.0%}  ·  FT {r.ft_pct:.0%}"]
    fgr = [f"rim {r.fg_rim:.0%}" if pd.notna(r.fg_rim) else "", f"paint {r.fg_paint:.0%}" if pd.notna(r.fg_paint) else "",
           f"mid {r.fg_mid:.0%}" if pd.notna(r.fg_mid) else ""]
    L.append(f"**Finishing:** " + " · ".join(x for x in fgr if x))
    L.append(f"**Other per-min:** ast {r.ast_per_min:.2f} · oreb {r.oreb_per_min:.2f} · dreb {r.dreb_per_min:.2f} "
             f"· stl {r.stl_per_min:.2f} · blk {r.blk_per_min:.2f}")
    # size identity (matchup physics)
    if a.is_rim_protector:
        L.append(f"**Size identity:** at {_hw(a.height_in)} he suppresses opponent rim shots & blocks (interior anchor).")
    elif a.is_small:
        L.append(f"**Size identity:** undersized — rim attempts get contested harder vs tall protectors.")
    # adaptive context effects
    if e is not None:
        side = "AWAY" if e.plays_better_away else "HOME"
        L.append(f"**Adaptive home/road:** plays better **{side}** "
                 f"(home eFG {e.home_efg:.3f} → x{e.home_xfg:.3f}, road {e.road_efg:.3f} → x{e.road_xfg:.3f}; "
                 f"confidence {e.conf_home:.2f}, sharpens with more games).")
    L.append(f"**Fatigue:** B2B decline weight {a.age_fatigue_w} (age {a.age}; older → more rest-sensitive).")
    L += ["", END, ""]
    return "\n".join(L)


def upsert(fp, blk):
    txt = open(fp, encoding="utf-8").read()
    if START in txt and END in txt:
        txt = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", "", txt, flags=re.S)
    open(fp, "w", encoding="utf-8").write(txt.rstrip() + "\n\n" + blk)


def main():
    attr = pd.read_parquet(os.path.join(TS, "player_attributes.parquet")).set_index("pid")
    rates = pd.read_parquet(os.path.join(TS, "player_rates.parquet"))
    eff = pd.read_parquet(os.path.join(TS, "player_effects.parquet")).set_index("pid")
    rates = rates[(rates.team.isin(["NYK", "SAS"])) & (rates.mpg >= 8)]
    folded = skipped = 0
    for r in rates.itertuples(index=False):
        pid = int(r.pid)
        if pid not in attr.index:
            skipped += 1; continue
        cands = glob.glob(os.path.join(PLAYERS, f"{pid}_*.md"))
        if not cands:
            skipped += 1; continue
        a = attr.loc[pid]
        e = eff.loc[pid] if pid in eff.index else None
        upsert(cands[0], block(a, r, e))
        folded += 1
    print(f"DONE: folded consolidated player intelligence into {folded} NYK/SAS notes ({skipped} skipped).")


if __name__ == "__main__":
    main()
