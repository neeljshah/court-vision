"""Rebounding Profile folder: render rebounding signals into player notes.

Adds a "## Rebounding Profile" section into the canonical
vault/Intelligence/Players/<pid>_*.md notes, wrapped in idempotent markers.
Only folds into notes that already exist — does NOT create stubs.

Signals folded (from data/cache/signals/rebounding.parquet):
  Season-aggregate (scouting, season-agg leak_rule): oreb/dreb/reb pct and percentile
    ranks, box-outs/game, 2nd-chance points, team rebounding context.
  L10 rolling (shift(1) prior-games-only): last-10-game oreb/dreb/reb averages.

Run after build_rebounding.py:
  python scripts/signals/fold_rebounding.py
"""
from __future__ import annotations

import glob
import os
import re
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIG = os.path.join(ROOT, "data", "cache", "signals", "rebounding.parquet")
PLAYERS = os.path.join(ROOT, "vault", "Intelligence", "Players")
START = "<!-- SIGNALS:rebounding START -->"
END = "<!-- SIGNALS:rebounding END -->"

# Minimum games to render a season row (below this it's too noisy to show)
MIN_GAMES_SEASON = 15


def _fmt(val, fmt_str: str, suffix: str = "") -> str:
    """Format a possibly-NaN value; return em-dash on missing."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "–"
    return format(val, fmt_str) + suffix


def _season_line(r) -> str:
    """One bullet line per season.

    2022-25 rows have possession-based *_pct_s (rendered as X.X%).
    2025-26 rows have per-minute *_pm_s (rendered as REB/min X.XX) to avoid
    unit mixing — the two values are not comparable and must not share a label.
    Percentile rank (reb_pct_rank_s) is the cross-season comparable headline.
    """
    reb_rank = _fmt(r.reb_pct_rank_s, ".0f", "th")
    oreb_rank = _fmt(r.oreb_pct_rank_s, ".0f")
    dreb_rank = _fmt(r.dreb_pct_rank_s, ".0f")
    bo = _fmt(r.box_outs_pg, ".2f")
    sc2 = _fmt(r.pts_2nd_chance_pg, ".1f")
    t_oreb = _fmt(r.team_oreb_pct, ".1%")
    t_dreb = _fmt(r.team_dreb_pct, ".1%")

    parts = [f"**{r.season}** ({int(r.n_games)}g)"]
    # Choose rate label/format by which column is populated
    if pd.notna(r.reb_pct_s):
        # 2022-25: possession-based percentage
        reb = _fmt(r.reb_pct_s, ".1%")
        oreb = _fmt(r.oreb_pct_s, ".1%")
        dreb = _fmt(r.dreb_pct_s, ".1%")
        parts.append(f"REB% **{reb}** ({reb_rank} pctile) "
                     f"· OREB% {oreb} (rk {oreb_rank}) "
                     f"· DREB% {dreb} (rk {dreb_rank})")
    else:
        # 2025-26: per-minute proxy (possession data unavailable)
        reb = _fmt(r.reb_pm_s, ".3f")
        oreb = _fmt(r.oreb_pm_s, ".3f")
        dreb = _fmt(r.dreb_pm_s, ".3f")
        parts.append(f"REB/min **{reb}** ({reb_rank} pctile) "
                     f"· OREB/min {oreb} (rk {oreb_rank}) "
                     f"· DREB/min {dreb} (rk {dreb_rank})")
    if bo != "–":
        parts.append(f"· box-outs/g {bo}")
    if sc2 != "–":
        parts.append(f"· 2nd-chance pts/g {sc2}")
    if t_oreb != "–":
        parts.append(f"· team OREB% {t_oreb} / DREB% {t_dreb}")
    return "- " + " ".join(parts)


def _l10_block(r) -> str:
    """Inline L10 stats for the most-recent season row."""
    oreb = _fmt(r.oreb_l10, ".1f")
    dreb = _fmt(r.dreb_l10, ".1f")
    reb = _fmt(r.reb_l10, ".1f")
    mins = _fmt(r.min_l10, ".1f")
    oshare = _fmt(r.oreb_share_l10, ".1%")
    if all(v == "–" for v in [oreb, dreb, reb]):
        return ""
    return (
        f"**L10 (prior-games-only):** REB {reb}/g "
        f"· OREB {oreb}/g · DREB {dreb}/g "
        f"· OREB share {oshare} · min {mins}/g"
    )


def build_block(g: pd.DataFrame) -> str:
    """Build the full markdown section for one player."""
    g = g[g.n_games >= MIN_GAMES_SEASON].sort_values("season", ascending=False)
    if g.empty:
        return ""

    L = [
        START,
        "",
        "## Rebounding Profile",
        (
            "*Season-aggregate scouting signal (season-agg, no overfit risk). "
            "REB%/OREB%/DREB% from official NBA per-game advanced stats (2022-25) "
            "or per-minute proxy (2025-26). L10 uses shift(1) prior-games-only — "
            "safe for pregame use. Percentile ranks within season.*"
        ),
        "",
    ]

    # Season lines
    for r in g.itertuples(index=False):
        L.append(_season_line(r))

    L.append("")

    # L10 from most recent season with l10 data
    l10_rows = g.dropna(subset=["reb_l10"])
    if not l10_rows.empty:
        top = l10_rows.iloc[0]
        l10_str = _l10_block(top)
        if l10_str:
            L.append(l10_str)
            L.append("")

    L += [END, ""]
    return "\n".join(L)


def upsert(note_path: str, block: str) -> None:
    """Idempotent insert/replace of the rebounding block."""
    txt = open(note_path, encoding="utf-8").read()
    if START in txt and END in txt:
        txt = re.sub(
            re.escape(START) + r".*?" + re.escape(END) + r"\n?",
            "",
            txt,
            flags=re.S,
        )
    txt = txt.rstrip() + "\n\n" + block
    open(note_path, "w", encoding="utf-8").write(txt)


def main():
    df = pd.read_parquet(SIG)
    folded = skipped = 0
    for pid, g in df.groupby("player_id"):
        cands = glob.glob(os.path.join(PLAYERS, f"{int(pid)}_*.md"))
        if not cands:
            skipped += 1
            continue
        block = build_block(g.copy())
        if not block:
            skipped += 1
            continue
        upsert(cands[0], block)
        folded += 1
    print(
        f"DONE: folded rebounding profile into {folded} player notes "
        f"({skipped} skipped: no note or below {MIN_GAMES_SEASON}-game floor)."
    )


if __name__ == "__main__":
    main()
