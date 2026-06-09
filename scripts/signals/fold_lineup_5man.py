"""Wave 2 folder: render lineup_5man signals into per-team lineup dossier notes.

Creates (or updates) one note per team at:
  vault/Intelligence/Lineups/<TRI>_lineups.md

Each note summarises the team's top 5-man lineups for the most recent qualifying
season (primary: 2024-25; fallback: most recent available), plus pair chemistry
from intel_outcome/lineup_combos_v2.json where present.

Run AFTER build_lineup_5man.py:
  python scripts/signals/fold_lineup_5man.py

Idempotent: re-running upserts the block between the markers, leaving any manually
written content outside the markers intact. Uses the same marker + regex upsert
pattern as fold_defense_matchup.py.
"""
from __future__ import annotations

import json
import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIG = os.path.join(ROOT, "data", "cache", "signals", "lineup_5man.parquet")
LINEUPS_DIR = os.path.join(ROOT, "vault", "Intelligence", "Lineups")
COMBOS_V2 = os.path.join(ROOT, "data", "cache", "intel_outcome", "lineup_combos_v2.json")

START = "<!-- SIGNALS:lineup_5man START -->"
END = "<!-- SIGNALS:lineup_5man END -->"

# Show at most this many lineups per team in the note
MAX_LINEUPS_SHOWN = 6
# Min minutes to show a lineup in the note
MIN_MINUTES_SHOW = 20.0
# Primary season preference
PRIMARY_SEASON = "2024-25"


def _safe(val, fmt="{:.1f}", fallback="—"):
    """Format a potentially-null value safely."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return fallback
    try:
        return fmt.format(float(val))
    except (TypeError, ValueError):
        return fallback


def _lineup_line(r) -> str:
    """Render one lineup row as a bullet."""
    net = _safe(r.net_rating, "{:+.1f}")
    off = _safe(r.off_rating, "{:.1f}")
    defr = _safe(r.def_rating, "{:.1f}")
    pace = _safe(r.pace, "{:.1f}")
    efg = _safe(r.efg_pct, "{:.1%}") if r.efg_pct is not None else "—"
    ast_to = _safe(r.ast_to, "{:.2f}")
    min_s = _safe(r.minutes, "{:.0f}")
    poss_s = _safe(r.poss, "{:.0f}") if r.poss is not None else "—"
    tier = r.net_rating_tier if hasattr(r, "net_rating_tier") else ""
    flag = " ★" if r.is_top_unit else ""
    return (
        f"- **#{r.lineup_rank}{flag}** {r.lineup_str}  "
        f"net **{net}** ({tier}) · off {off} / def {defr} · "
        f"pace {pace} · eFG {efg} · A/TO {ast_to} · "
        f"{min_s} min / {poss_s} poss"
    )


def _pair_line(pair: dict) -> str:
    names = " + ".join(pair.get("names", []))
    net = pair.get("net", 0.0)
    poss = pair.get("poss", 0)
    minutes = pair.get("min", 0)
    return f"- {names}  net **{net:+.1f}** ({poss} poss / {minutes:.0f} min)"


def _load_combos() -> dict:
    """Load best/worst pairs from lineup_combos_v2 by_team, keyed by tricode."""
    if not os.path.exists(COMBOS_V2):
        return {}
    with open(COMBOS_V2, encoding="utf-8") as f:
        d = json.load(f)
    return d.get("by_team", {})


def build_block(tri: str, g: pd.DataFrame, combos_by_team: dict) -> str:
    """Build the full SIGNALS block for one team."""
    # Select the best season of data available
    seasons_avail = g["season"].unique()
    if PRIMARY_SEASON in seasons_avail:
        season = PRIMARY_SEASON
    else:
        season = sorted(seasons_avail)[-1]

    season_df = g[g["season"] == season].copy()
    # Filter to min minutes and sort
    season_df = season_df[season_df["minutes"] >= MIN_MINUTES_SHOW].sort_values(
        "lineup_rank"
    )

    if season_df.empty:
        return ""

    coverage_note = ""
    if season != PRIMARY_SEASON:
        coverage_note = f"\n> *Note: {PRIMARY_SEASON} data not available for this team; showing {season}.*\n"

    lines = [START, "", "## 5-Man Lineup Dossier", ""]
    lines.append(
        f"*Season: **{season}** | Source: NBA Stats LeagueDashLineups (5-man box net rating) | "
        f"Leak rule: season-aggregate scouting signal.*"
    )
    if coverage_note:
        lines.append(coverage_note.strip())
    lines.append("")

    shown = 0
    for r in season_df.itertuples(index=False):
        if shown >= MAX_LINEUPS_SHOWN:
            break
        lines.append(_lineup_line(r))
        shown += 1

    remaining = len(season_df) - shown
    if remaining > 0:
        lines.append(f"  *…and {remaining} more qualifying lineups.*")

    # Pair chemistry from lineup_combos_v2
    team_combos = combos_by_team.get(tri, {})
    best_pairs = team_combos.get("best_pairs", [])[:3]
    worst_pairs = team_combos.get("worst_pairs", [])[:2]

    if best_pairs or worst_pairs:
        lines += ["", "### Pair Chemistry (2024-25 net, season-agg)"]
        if best_pairs:
            lines.append("")
            lines.append("**Best pairs on-court:**")
            for p in best_pairs:
                lines.append(_pair_line(p))
        if worst_pairs:
            lines.append("")
            lines.append("**Worst pairs on-court:**")
            for p in worst_pairs:
                lines.append(_pair_line(p))

    lines += ["", END, ""]
    return "\n".join(lines)


def upsert(note_path: str, block: str) -> None:
    """Idempotent upsert: replace the signal block if it exists, else append."""
    if os.path.exists(note_path):
        txt = open(note_path, encoding="utf-8").read()
    else:
        txt = ""

    if START in txt and END in txt:
        txt = re.sub(
            re.escape(START) + r".*?" + re.escape(END) + r"\n?",
            "",
            txt,
            flags=re.S,
        )
    txt = txt.rstrip() + ("\n\n" if txt.strip() else "") + block
    open(note_path, "w", encoding="utf-8").write(txt)


def main():
    df = pd.read_parquet(SIG)
    combos_by_team = _load_combos()

    os.makedirs(LINEUPS_DIR, exist_ok=True)

    created = updated = skipped = 0
    for tri, g in df.groupby("team_tricode"):
        block = build_block(tri, g, combos_by_team)
        if not block:
            skipped += 1
            continue
        note_path = os.path.join(LINEUPS_DIR, f"{tri}_lineups.md")
        existed = os.path.exists(note_path)
        upsert(note_path, block)
        if existed:
            updated += 1
        else:
            created += 1

    print(
        f"DONE: lineup_5man folded into {LINEUPS_DIR}  "
        f"(created={created}, updated={updated}, skipped={skipped})"
    )


if __name__ == "__main__":
    main()
