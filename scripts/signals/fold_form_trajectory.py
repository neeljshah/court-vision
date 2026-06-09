"""Wave 2 folder: render Form & Trajectory signals into player vault notes.

Adds a "## Form & Trajectory" section into the canonical
vault/Intelligence/Players/<pid>_*.md notes, wrapped in idempotent markers.
Only folds into notes that ALREADY EXIST — does not create stubs.

Signals folded (all shift(1) leak-safe unless marked season-agg):
  L3/L5/L10/L20 rolling means, EWMA (span=10) per stat
  Hot/cold streak length per stat (prior-game expanding mean threshold)
  Per-stat dispersion = std-dev (season-agg, scouting)
  Month-over-month slope (season-agg, scouting)

Run after build_form_trajectory.py:
  python scripts/signals/fold_form_trajectory.py
"""
from __future__ import annotations

import glob
import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIG = os.path.join(ROOT, "data", "cache", "signals", "form_trajectory.parquet")
PLAYERS = os.path.join(ROOT, "vault", "Intelligence", "Players")
START = "<!-- SIGNALS:form_trajectory START -->"
END = "<!-- SIGNALS:form_trajectory END -->"

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
EXTRA_STATS = ["oreb", "dreb", "plus_minus"]
STAT_LABEL = {
    "pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "FG3M",
    "stl": "STL", "blk": "BLK", "tov": "TOV",
    "oreb": "OREB", "dreb": "DREB", "plus_minus": "+/-",
}

RECENT_SEASONS = ["2025-26", "2024-25"]  # show these seasons in note; skip older


def _fmt(val, decimals: int = 1) -> str:
    """Format a float or return '-' for NaN."""
    if pd.isna(val):
        return "-"
    return f"{val:.{decimals}f}"


def _streak_label(streak: int) -> str:
    if streak > 0:
        return f"HOT +{streak}g"
    elif streak < 0:
        return f"COLD -{abs(streak)}g"
    return "--"


def _season_block(r, available_stats: list[str]) -> list[str]:
    """Render one season's rolling + streak lines for all available stats."""
    lines: list[str] = []
    lines.append(f"\n**{r.season}** ({r.n_games} games)")
    lines.append("")
    lines.append("| Stat | L3 | L5 | L10 | L20 | EWMA | Streak | Std | Slope/mo |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for stat in available_stats:
        lbl = STAT_LABEL.get(stat, stat.upper())
        l3 = _fmt(getattr(r, f"l3_{stat}", float("nan")))
        l5 = _fmt(getattr(r, f"l5_{stat}", float("nan")))
        l10 = _fmt(getattr(r, f"l10_{stat}", float("nan")))
        l20 = _fmt(getattr(r, f"l20_{stat}", float("nan")))
        ewma = _fmt(getattr(r, f"ewma_{stat}", float("nan")))
        streak_val = getattr(r, f"streak_{stat}", 0)
        streak = _streak_label(int(streak_val) if not pd.isna(streak_val) else 0)
        std = _fmt(getattr(r, f"std_{stat}", float("nan")))
        slope = _fmt(getattr(r, f"slope_{stat}", float("nan")), decimals=2)
        lines.append(f"| {lbl} | {l3} | {l5} | {l10} | {l20} | {ewma} | {streak} | {std} | {slope} |")
    return lines


def build_block(g: pd.DataFrame) -> str:
    """Build the full markdown block for one player across their seasons."""
    # Filter to recent seasons and sort newest first
    g = g[g.season.isin(RECENT_SEASONS)].sort_values("season", ascending=False)
    if g.empty:
        return ""

    # Determine which stats are available (oreb/dreb/+/- only in gamelog_full players)
    sample_row = g.iloc[0]
    available = list(STATS)
    for s in EXTRA_STATS:
        col = f"l5_{s}"
        if hasattr(sample_row, col) and not pd.isna(getattr(sample_row, col, float("nan"))):
            available.append(s)

    L: list[str] = [
        START, "",
        "## Form & Trajectory",
        "*Rolling-window stats and trajectory from per-game logs. "
        "L3/L5/L10/L20 = prior-game rolling means (shift(1), leak-safe — safe for model use). "
        "EWMA = span-10 exponential moving avg on prior games. "
        "Streak = consecutive games above/below expanding prior mean (hot/cold). "
        "Std and Slope are season-aggregate (scouting only — do not feed into point model directly).*",
        "",
    ]

    for r in g.itertuples(index=False):
        L.extend(_season_block(r, available))

    L += ["", END, ""]
    return "\n".join(L)


def upsert(note_path: str, block: str) -> None:
    """Idempotent insert/replace of the signals block inside a note."""
    with open(note_path, encoding="utf-8") as fh:
        txt = fh.read()
    if START in txt and END in txt:
        txt = re.sub(
            re.escape(START) + r".*?" + re.escape(END) + r"\n?",
            "",
            txt,
            flags=re.S,
        )
    txt = txt.rstrip() + "\n\n" + block
    with open(note_path, "w", encoding="utf-8") as fh:
        fh.write(txt)


def main():
    df = pd.read_parquet(SIG)
    folded = skipped = 0

    for pid, g in df.groupby("player_id"):
        cands = glob.glob(os.path.join(PLAYERS, f"{int(pid)}_*.md"))
        if not cands:
            skipped += 1
            continue
        block = build_block(g)
        if not block:
            skipped += 1
            continue
        upsert(cands[0], block)
        folded += 1

    print(
        f"DONE: folded form_trajectory signals into {folded} player notes "
        f"({skipped} skipped: no vault note or no recent-season data)."
    )


if __name__ == "__main__":
    main()
