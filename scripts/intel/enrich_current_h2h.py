"""APPEND-ONLY current-season (2025-26) head-to-head enrichment for player notes.

The base notes (build_matchup_intelligence.py) used coverage_faced_matrix = 2024-25.
This adds the CURRENT season's H2H from coverage_faced_allseasons.parquet (built
from raw per-game files, 2025-26 = 147k pairs) — the most bet-relevant matchup
detail. APPEND-ONLY + idempotent (skips a note already carrying the marker), so it
never clobbers the agent-written "Scouting Read" sections.

Run AFTER the scouting fan-out completes:
  python scripts/intel/enrich_current_h2h.py
"""
from __future__ import annotations

import glob
import os
import re
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MATRIX = os.path.join(ROOT, "data", "cache", "coverage_faced_allseasons.parquet")
NOTES = os.path.join(ROOT, "vault", "Intelligence", "Matchups", "Players")
SEASON = "2025-26"
MARKER = "## Current-Season H2H (2025-26)"
MIN_POSS = 18.0


def main():
    df = pd.read_parquet(MATRIX)
    df = df[df.season == SEASON].copy()
    # per-offensive-player baseline pts/poss this season
    ob = df.groupby("off_player_id").agg(p=("pts", "sum"), q=("poss", "sum")).reset_index()
    ob["base"] = ob.p / ob.q.replace(0, 1)
    base = dict(zip(ob.off_player_id, ob.base))

    notes = glob.glob(os.path.join(NOTES, "*.md"))
    enriched = 0
    for fp in notes:
        m = re.match(r"(\d+)_", os.path.basename(fp))
        if not m:
            continue
        pid = int(m.group(1))
        txt = open(fp, encoding="utf-8").read()
        if MARKER in txt:
            continue  # idempotent
        # as offense: who guarded him this season
        off = df[(df.off_player_id == pid) & (df.poss >= MIN_POSS)].sort_values("poss", ascending=False).head(12)
        # as defender
        dfn = df[(df.def_player_id == pid) & (df.poss >= MIN_POSS)].sort_values("poss", ascending=False).head(10)
        if off.empty and dfn.empty:
            continue
        b = base.get(pid, 0.0)
        L = ["", MARKER, "*From raw 2025-26 defender-matchup files. PPP = pts/matchup-possession; "
             "vs-self = PPP ÷ his season matchup baseline (<0.85 tough, >1.15 feasts).*", ""]
        if not off.empty:
            L.append(f"**Guarded by (≥{MIN_POSS:.0f} poss, season baseline {b:.2f} pts/poss):**")
            L.append("| Defender | G | Poss | Pts | AST | TOV | FG% | PPP | vs self |")
            L.append("|---|--|--|--|--|--|--|--|--|")
            for r in off.itertuples(index=False):
                ppp = r.pts / r.poss if r.poss else 0
                rel = ppp / b if b else 0
                read = "tough" if rel < 0.85 else "feasts" if rel > 1.15 else "neutral"
                L.append(f"| {r.def_player_name} | {r.n_games} | {r.poss:.0f} | {int(r.pts)} | {int(r.ast)} | "
                         f"{int(r.tov)} | {'' if r.fg_pct is None else int(r.fg_pct*100)} | {ppp:.2f} | "
                         f"{rel:.2f} ({read}) |")
            L.append("")
        if not dfn.empty:
            L.append("**As a defender — who he guarded (≥{:.0f} poss):**".format(MIN_POSS))
            L.append("| Assignment | G | Poss | Pts allowed | FG% allowed |")
            L.append("|---|--|--|--|--|")
            for r in dfn.itertuples(index=False):
                L.append(f"| {r.off_player_name} | {r.n_games} | {r.poss:.0f} | {int(r.pts)} | "
                         f"{'' if r.fg_pct is None else int(r.fg_pct*100)} |")
            L.append("")
        with open(fp, "a", encoding="utf-8") as fh:
            fh.write("\n".join(L))
        enriched += 1
    print(f"DONE: appended 2025-26 H2H to {enriched} player notes")


if __name__ == "__main__":
    main()
