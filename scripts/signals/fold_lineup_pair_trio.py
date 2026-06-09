"""Wave 2 folder: render lineup_pair_trio signals into per-team lineup notes.

Creates/updates vault/Intelligence/Lineups/<TRI>_lineups.md for all 30 teams,
summarising that team's best/worst 2-man and 3-man combos from the parquet.

Markers: <!-- SIGNALS:lineup_pair_trio START --> / <!-- SIGNALS:lineup_pair_trio END -->
Idempotent: re-running replaces the block in place.

Run after build_lineup_pair_trio.py:
  python scripts/signals/fold_lineup_pair_trio.py
"""
from __future__ import annotations

import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIG = os.path.join(ROOT, "data", "cache", "signals", "lineup_pair_trio.parquet")
LINEUPS_DIR = os.path.join(ROOT, "vault", "Intelligence", "Lineups")
START = "<!-- SIGNALS:lineup_pair_trio START -->"
END = "<!-- SIGNALS:lineup_pair_trio END -->"

# Show this many best + worst entries per type
N_SHOW = 5


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def _fmt_pair_row(r) -> str:
    stag = f" · stagger={r.stagger_score:.2f}" if not pd.isna(r.stagger_score) else ""
    handler = ""
    if not pd.isna(r.pnr_handler_share) and r.pnr_handler_share is not None:
        pct = int(round(r.pnr_handler_share * 100))
        handler = f" · PnR handler={pct}% {r.player_names.split(' / ')[0]}"
    avg_min = f" · avg_min={r.avg_player_min:.0f}" if not pd.isna(r.avg_player_min) else ""
    return (f"- **{r.player_names}** net={r.net:+.1f} pts/100 "
            f"({r.poss} poss · {r.floor_min:.0f} min · {r.n_lineups} lineups"
            f"{avg_min}{stag}{handler})")


def _fmt_trio_row(r) -> str:
    avg_min = f" · avg_min={r.avg_player_min:.0f}" if not pd.isna(r.avg_player_min) else ""
    return (f"- **{r.player_names}** net={r.net:+.1f} pts/100 "
            f"({r.poss} poss · {r.floor_min:.0f} min · {r.n_lineups} lineups{avg_min})")


# ---------------------------------------------------------------------------
# Block builder
# ---------------------------------------------------------------------------

def build_block(team: str, df_team: pd.DataFrame, season: str) -> str:
    pairs = df_team[df_team.combo_type == "pair"].sort_values("net", ascending=False)
    trios = df_team[df_team.combo_type == "trio"].sort_values("net", ascending=False)

    best_pairs = pairs.head(N_SHOW)
    worst_pairs = pairs.tail(N_SHOW).sort_values("net", ascending=True)
    best_trios = trios.head(N_SHOW)
    worst_trios = trios.tail(N_SHOW).sort_values("net", ascending=True)

    n_pairs = len(pairs)
    n_trios = len(trios)

    L = [
        START,
        "",
        "## 2-Man & 3-Man Combo Signals",
        f"*Season: {season} · Source: NBA Stats 5-man lineup box data (derived pair/trio net rating, "
        f"box-based, non-CV). Net = pts/100 poss while combo is on floor together (on-court, "
        f"not strict on/off). Stagger score = |min1-min2| / max(min1,min2); 0=full overlap, "
        f"~1=pure stagger. Season-aggregate scouting signal.*",
        "",
        f"**{n_pairs} qualifying pairs (≥150 poss) · {n_trios} qualifying trios (≥150 poss)**",
        "",
        "### Best 2-Man Combos",
    ]
    for r in best_pairs.itertuples(index=False):
        L.append(_fmt_pair_row(r))

    L += ["", "### Worst 2-Man Combos"]
    for r in worst_pairs.itertuples(index=False):
        L.append(_fmt_pair_row(r))

    L += ["", "### Best 3-Man Combos"]
    for r in best_trios.itertuples(index=False):
        L.append(_fmt_trio_row(r))

    L += ["", "### Worst 3-Man Combos"]
    for r in worst_trios.itertuples(index=False):
        L.append(_fmt_trio_row(r))

    L += ["", END, ""]
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Upsert helpers
# ---------------------------------------------------------------------------

def upsert(note_path: str, block: str) -> None:
    if os.path.exists(note_path):
        txt = open(note_path, encoding="utf-8").read()
        if START in txt and END in txt:
            txt = re.sub(
                re.escape(START) + r".*?" + re.escape(END) + r"\n?",
                "",
                txt,
                flags=re.S,
            )
        txt = txt.rstrip() + "\n\n" + block
    else:
        txt = block
    open(note_path, "w", encoding="utf-8").write(txt)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(LINEUPS_DIR, exist_ok=True)
    df = pd.read_parquet(SIG)
    season = df["season"].iloc[0] if not df.empty else "unknown"

    created = updated = 0
    for team, df_team in df.groupby("team"):
        note_path = os.path.join(LINEUPS_DIR, f"{team}_lineups.md")
        existed = os.path.exists(note_path)
        block = build_block(team, df_team, season)
        upsert(note_path, block)
        if existed:
            updated += 1
        else:
            created += 1

    print(f"DONE: lineup_pair_trio signals folded into {created} new + {updated} updated team lineup notes.")
    print(f"  Directory: {LINEUPS_DIR}")


if __name__ == "__main__":
    main()
