"""Team-effect decomposition — how each player & lineup moves the TEAM.

Mission: "understand how each part affects the team." From the REAL 2025-26 5-man stints
(team_system/lineups.parquet) computes, per NYK/SAS player:
  - ON/OFF net rating (minute-weighted net of units WITH him vs WITHOUT him) = his lift
  - PACE tilt (possessions/min with him on vs off)
  - WHAT he adds (spacing / rim protection / creation / playmaking / rebounding) from his
    archetype + role propensities — the mechanism behind the number
  - his best 5-man unit
Folds `## Team Impact` into each player note and `## Lineup Impact` (on/off leaderboard +
top/bottom units) into the NYK/SAS team notes. Also writes team_effects.parquet.

  python scripts/team_system/build_team_effects.py
"""
from __future__ import annotations

import glob
import os
import re

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
VAULT = os.path.join(ROOT, "vault", "Intelligence")
PSTART, PEND = "<!-- SIGNALS:team-impact START -->", "<!-- SIGNALS:team-impact END -->"
TSTART, TEND = "<!-- SIGNALS:lineup-impact START -->", "<!-- SIGNALS:lineup-impact END -->"
ASC = lambda s: str(s).encode("ascii", "replace").decode()


def _adds(rl):
    """Narrative of what a player adds to the team, from his role propensities."""
    out = []
    if rl is None:
        return out
    if rl.spacing >= 0.62:
        out.append("floor spacing (3pt gravity)")
    if rl.rim_protect >= 0.72:
        out.append("rim protection")
    if rl.creation >= 0.72:
        out.append("shot creation")
    if rl.playmaking >= 0.70:
        out.append("playmaking hub")
    if rl.rebounding >= 0.72:
        out.append("rebounding")
    if rl.perimeter_d >= 0.72:
        out.append("perimeter defense")
    return out


def main():
    lu = pd.read_parquet(os.path.join(TS, "lineups.parquet"))
    ro = pd.read_parquet(os.path.join(TS, "player_roles.parquet")).set_index("pid")
    lu["ids"] = lu.ids.apply(lambda s: [int(x) for x in str(s).split(",")])
    lu["pace"] = np.where(lu["min"] > 0, lu.poss / lu["min"] * 24.0, np.nan)  # poss counts both teams -> per-team /2

    rows = []
    for team in ("NYK", "SAS"):
        tl = lu[lu.team == team]
        tot_min = tl["min"].sum()
        team_net = float((tl.net * tl["min"]).sum() / tot_min) if tot_min else 0.0
        players = sorted({pid for ids in tl.ids for pid in ids})
        for pid in players:
            on = tl[tl.ids.apply(lambda ids: pid in ids)]
            off = tl[tl.ids.apply(lambda ids: pid not in ids)]
            on_min, off_min = on["min"].sum(), off["min"].sum()
            if on_min < 30:
                continue
            on_net = float((on.net * on["min"]).sum() / on_min)
            off_net = float((off.net * off["min"]).sum() / off_min) if off_min else team_net
            on_pace = float((on.pace * on["min"]).sum() / on_min)
            off_pace = float((off.pace * off["min"]).sum() / off_min) if off_min else on_pace
            bpool = on[on["min"] >= 50]                  # avoid tiny-sample outlier "best" units
            bpool = bpool if len(bpool) else on
            best = bpool.loc[bpool.net.idxmax()] if len(bpool) else None
            rl = ro.loc[pid] if pid in ro.index else None
            rows.append({
                "pid": pid, "team": team, "name": ASC(rl.player) if rl is not None else str(pid),
                "on_net": round(on_net, 1), "off_net": round(off_net, 1),
                "on_off": round(on_net - off_net, 1), "on_min": round(on_min),
                "pace_tilt": round(on_pace - off_pace, 1), "on_pace": round(on_pace, 1),
                "adds": _adds(rl), "archetype": rl.archetype if rl is not None else "",
                "best_lineup": (best.lineup if best is not None else ""),
                "best_net": round(float(best.net), 1) if best is not None else 0.0,
                "best_min": round(float(best["min"])) if best is not None else 0,
            })
    df = pd.DataFrame(rows)
    df.to_parquet(os.path.join(TS, "team_effects.parquet"), index=False)
    nP = _fold_players(df, ro)
    nT = _fold_teams(df, lu)
    print(f"DONE: team-effect decomposition for {len(df)} players; folded {nP} player notes, {nT} team notes.")
    for team in ("NYK", "SAS"):
        print(f"\n{team} on/off net leaders (real 2025-26 5-man stints):")
        for r in df[df.team == team].sort_values("on_off", ascending=False).head(6).itertuples(index=False):
            print(f"  {r.name:22s} on/off {r.on_off:+5.1f} (on {r.on_net:+5.1f}/off {r.off_net:+5.1f}, {r.on_min}min) "
                  f"pace {r.pace_tilt:+.1f} | adds: {', '.join(r.adds) or '-'}")


def _fold_players(df, ro):
    folded = 0
    for r in df.itertuples(index=False):
        cands = glob.glob(os.path.join(VAULT, "Players", f"{int(r.pid)}_*.md"))
        if not cands:
            continue
        verdict = "elevates" if r.on_off >= 2 else ("drags" if r.on_off <= -2 else "roughly neutral on")
        pace = "faster" if r.pace_tilt >= 1 else ("slower" if r.pace_tilt <= -1 else "same pace")
        blk = (f"{PSTART}\n\n## Team Impact\n*How {r.team} plays with vs without him (real 2025-26 5-man stints).*\n\n"
               f"- **On/off net rating:** **{r.on_off:+.1f}** — on {r.on_net:+.1f} / off {r.off_net:+.1f} over {r.on_min} on-court min; "
               f"he **{verdict}** the team.\n"
               f"- **Pace:** {pace} with him on floor ({r.on_pace:.0f} poss/48, {r.pace_tilt:+.1f} vs off).\n"
               f"- **What he adds:** {', '.join(r.adds) if r.adds else 'connective / role minutes'}.\n"
               f"- **Best unit:** {ASC(r.best_lineup)} (net {r.best_net:+.1f} over {r.best_min} min).\n\n{PEND}\n")
        txt = open(cands[0], encoding="utf-8").read()
        if PSTART in txt:
            txt = re.sub(re.escape(PSTART) + r".*?" + re.escape(PEND) + r"\n?", "", txt, flags=re.S)
        open(cands[0], "w", encoding="utf-8").write(txt.rstrip() + "\n\n" + blk)
        folded += 1
    return folded


def _fold_teams(df, lu):
    folded = 0
    for team in ("NYK", "SAS"):
        cands = glob.glob(os.path.join(VAULT, "Teams", f"{team}.md"))
        if not cands:
            continue
        d = df[df.team == team].sort_values("on_off", ascending=False)
        tl = lu[(lu.team == team) & (lu["min"] >= 40)]
        top = tl.nlargest(3, "net"); bot = tl.nsmallest(2, "net")
        lines = ["| Player | On/Off | On | Off | Min | Pace | Adds |", "|---|---|---|---|---|---|---|"]
        for r in d.head(10).itertuples(index=False):
            lines.append(f"| {r.name} | **{r.on_off:+.1f}** | {r.on_net:+.1f} | {r.off_net:+.1f} | {r.on_min} | {r.pace_tilt:+.1f} | {', '.join(r.adds[:2])} |")
        units = ["", "**Top units:** " + " · ".join(f"{ASC(x.lineup)} (net {x.net:+.1f}, {round(getattr(x, 'min'))}m)" for x in top.itertuples(index=False))]
        units.append("**Struggled:** " + " · ".join(f"{ASC(x.lineup)} (net {x.net:+.1f}, {round(getattr(x, 'min'))}m)" for x in bot.itertuples(index=False)))
        blk = (f"{TSTART}\n\n## Lineup Impact\n*Per-player on/off net rating + best/worst 5-man units "
               f"(real 2025-26 stints).*\n\n" + "\n".join(lines) + "\n" + "\n".join(units) + f"\n\n{TEND}\n")
        txt = open(cands[0], encoding="utf-8").read()
        if TSTART in txt:
            txt = re.sub(re.escape(TSTART) + r".*?" + re.escape(TEND) + r"\n?", "", txt, flags=re.S)
        open(cands[0], "w", encoding="utf-8").write(txt.rstrip() + "\n\n" + blk)
        folded += 1
    return folded


if __name__ == "__main__":
    main()
