"""Wave 2 proof folder: render the defense_matchup signals into player notes.

Adds a "## Defensive Matchup Profile" section (opponent-adjusted defense) into the
canonical vault/Intelligence/Players/<pid>_*.md notes, wrapped in idempotent markers.
Only folds into notes that ALREADY exist (does not create stubs for obscure defenders).

Run after build_defense_matchup.py:
  python scripts/signals/fold_defense_matchup.py
"""
from __future__ import annotations

import glob
import os
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIG = os.path.join(ROOT, "data", "cache", "signals", "defense_matchup.parquet")
PLAYERS = os.path.join(ROOT, "vault", "Intelligence", "Players")
START = "<!-- SIGNALS:defense-matchup START -->"
END = "<!-- SIGNALS:defense-matchup END -->"
MIN_POSS_SEASON = 50.0   # don't render a season line below this (too noisy)


def _season_line(r) -> str:
    si = "–" if pd.isna(r.stops_index) else f"{r.stops_index:.2f}"
    pct = "" if pd.isna(r.stops_pctile) else f", {int(r.stops_pctile)}th pctile"
    fgs = "" if pd.isna(r.fg_suppression) else f" · FG supp {r.fg_suppression:.2f}"
    fg3 = "" if pd.isna(r.fg3_allowed) else f" · 3P allowed {int(r.fg3_allowed*100)}%"
    return (f"**{r.season}** ({r.poss_defended:.0f} poss · {r.n_assignments_any} players covered · "
            f"stops index **{si}**{pct} · allowed {r.ppp_allowed:.2f} vs exp "
            f"{r.expected_ppp:.2f} PPP/matchup{fgs}{fg3} · "
            f"{r.block_per100:.1f} blk / {r.foul_per100:.1f} fl per100)")


def build_block(g: pd.DataFrame) -> str:
    g = g[g.poss_defended >= MIN_POSS_SEASON].sort_values("season", ascending=False)
    if g.empty:
        return ""
    L = [START, "", "## Defensive Matchup Profile",
         "*Opponent-adjusted defense from tracked assignments. **Stops index** = points "
         "allowed per matchup-possession ÷ what those assignments score vs everyone else "
         "(1.00 = neutral; <1 suppresses). Season-aggregate scouting signal; single-pairing "
         "tails are small-sample.*", ""]
    for r in g.itertuples(index=False):
        L.append("- " + _season_line(r))
    L.append("")
    # named extremes from the most recent qualifying season
    top = g.iloc[0]
    if isinstance(top.top_shutdowns, str) and top.top_shutdowns:
        L.append(f"**Locks down ({top.season}):** {top.top_shutdowns}")
    if isinstance(top.got_cooked_by, str) and top.got_cooked_by:
        L.append(f"**Beaten by ({top.season}):** {top.got_cooked_by}")
    L += ["", END, ""]
    return "\n".join(L)


def upsert(note_path: str, block: str) -> None:
    import re
    txt = open(note_path, encoding="utf-8").read()
    if START in txt and END in txt:
        txt = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", "", txt, flags=re.S)
    txt = txt.rstrip() + "\n\n" + block
    open(note_path, "w", encoding="utf-8").write(txt)


def main():
    df = pd.read_parquet(SIG)
    folded = skipped = 0
    for did, g in df.groupby("def_player_id"):
        cands = glob.glob(os.path.join(PLAYERS, f"{int(did)}_*.md"))
        if not cands:
            skipped += 1
            continue
        block = build_block(g)
        if not block:
            skipped += 1
            continue
        upsert(cands[0], block)
        folded += 1
    print(f"DONE: folded defensive-matchup profile into {folded} player notes "
          f"({skipped} skipped: no note or below {MIN_POSS_SEASON:.0f}-poss floor).")


if __name__ == "__main__":
    main()
