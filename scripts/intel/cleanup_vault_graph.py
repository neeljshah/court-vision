"""Declutter the Obsidian graph: fold matchup intelligence into the canonical
player + team notes, then delete the hundreds of standalone matchup nodes.

Run ORDER (after the scouting fan-out completes):
  1. python scripts/intel/consolidate_into_player_notes.py   (intel -> Players/)
  2. python scripts/intel/cleanup_vault_graph.py             (this: fold teams, delete clutter)

After this: ONE node per player (Players/), ONE per team (Matchups/<TEAM>.md with a
folded scouting section), the 7 Schemes/ notes, and a couple of league reference
notes. The 660 Matchups/Players/ nodes + 30 __scouting nodes are gone.
"""
from __future__ import annotations

import os
import re
import shutil
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MATCHUPS = os.path.join(ROOT, "vault", "Intelligence", "Matchups")
PLAYERS_SUB = os.path.join(MATCHUPS, "Players")

START = "<!-- TEAM-SCOUTING-START -->"
END = "<!-- TEAM-SCOUTING-END -->"


def fold_team_scouting():
    folded = 0
    for sc in glob.glob(os.path.join(MATCHUPS, "*__scouting.md")):
        team = os.path.basename(sc).replace("__scouting.md", "")
        body = open(sc, encoding="utf-8").read().strip()
        target = os.path.join(MATCHUPS, f"{team}.md")
        block = f"{START}\n\n{body}\n\n{END}\n"
        if os.path.exists(target):
            txt = open(target, encoding="utf-8").read()
            if START in txt and END in txt:
                txt = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", "", txt, flags=re.S)
            txt = txt.rstrip() + "\n\n" + block
        else:
            txt = block
        open(target, "w", encoding="utf-8").write(txt)
        os.remove(sc)
        folded += 1
    print(f"folded {folded} team scouting reports into Matchups/<TEAM>.md (and removed __scouting files)")


def delete_player_matchup_nodes():
    if os.path.isdir(PLAYERS_SUB):
        n = len(glob.glob(os.path.join(PLAYERS_SUB, "*.md")))
        shutil.rmtree(PLAYERS_SUB)
        print(f"deleted Matchups/Players/ ({n} standalone player-matchup nodes) — intel now lives in Players/")
    else:
        print("Matchups/Players/ already gone")


def drop_redundant_index():
    # _Scouting_Index linked the now-folded __scouting files; the master README supersedes it.
    idx = os.path.join(MATCHUPS, "_Scouting_Index.md")
    if os.path.exists(idx):
        os.remove(idx)
        print("removed redundant _Scouting_Index.md (superseded by _GAME_INTELLIGENCE_README.md)")


if __name__ == "__main__":
    fold_team_scouting()
    delete_player_matchup_nodes()
    drop_redundant_index()
    print("graph decluttered: one node per player (Players/), team scouting folded into team notes.")
