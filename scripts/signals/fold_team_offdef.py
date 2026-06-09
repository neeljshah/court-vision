"""Wave 2 folder: render team_offdef signals into team vault notes.

Adds a "## Offense/Defense Granularity" section into the canonical
vault/Intelligence/Teams/<TRI>.md notes, wrapped in idempotent markers.
Only folds into notes that ALREADY exist (skips teams with no note).

Run after build_team_offdef.py:
  python scripts/signals/fold_team_offdef.py
"""
from __future__ import annotations

import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIG = os.path.join(ROOT, "data", "cache", "signals", "team_offdef.parquet")
TEAMS = os.path.join(ROOT, "vault", "Intelligence", "Teams")
START = "<!-- SIGNALS:team_offdef START -->"
END = "<!-- SIGNALS:team_offdef END -->"

# Display order / labels for play types
PLAY_TYPES_OFF = [
    ("pnrh", "PnR-Handler"),
    ("pnrr", "PnR-Roller"),
    ("iso", "Isolation"),
    ("post", "Post-Up"),
    ("spotup", "Spot-Up"),
    ("handoff", "Handoff"),
    ("cut", "Cut"),
    ("offscr", "Off-Screen"),
    ("trans", "Transition"),
    ("offreb", "Off-Rebound"),
]

PREFER_SEASON = "2025-26"
EFFICIENCY_COLS = ["off_rtg", "def_rtg", "pace", "tov_ratio", "efg_pct"]


def _fmt(val, decimals: int = 3, fallback: str = "—") -> str:
    """Format a numeric value or return fallback if NaN/None."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return fallback
    return f"{val:.{decimals}f}"


def _pct(val, fallback: str = "—") -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return fallback
    return f"{val:.1%}"


def _has_efficiency(row: pd.Series) -> bool:
    """Return True if the row has at least one non-null efficiency column."""
    return any(
        row.get(c) is not None and not pd.isna(row.get(c))
        for c in EFFICIENCY_COLS
    )


def build_block(g: pd.DataFrame) -> str:
    """Build the markdown block for a single team from its season rows.

    Play-type / shot-diet blocks use the most recent season available
    (preferring 2025-26).  The efficiency block is decoupled: it finds the
    most recent season that actually has non-null efficiency data (typically
    2024-25, because team_advanced_stats.parquet ends there) and labels
    itself with that season so readers know the data is not current-season.
    """
    season_order = [PREFER_SEASON, "2024-25", "2023-24", "2022-23"]

    # Primary row: used for play-type PPP/freq and shot-diet (2025-26 preferred)
    row = None
    season_used = None
    for s in season_order:
        candidates = g[g["season"] == s]
        if not candidates.empty:
            row = candidates.iloc[0]
            season_used = s
            break
    if row is None:
        return ""

    # Efficiency row: fall back to first season with non-null efficiency data
    eff_row = None
    eff_season = None
    for s in season_order:
        candidates = g[g["season"] == s]
        if not candidates.empty:
            candidate = candidates.iloc[0]
            if _has_efficiency(candidate):
                eff_row = candidate
                eff_season = s
                break

    tri = row["team_tricode"]
    L = [
        START,
        "",
        "## Offense/Defense Granularity",
        f"*Play-type/shot-diet: {season_used}. Season-aggregate scouting signal (consumer A). "
        "Sources: Synergy play-type data + shot-location zones + team advanced stats.*",
        "",
    ]

    # ── Team efficiency (decoupled season — may be older than play-type) ─────
    if eff_row is not None:
        pace_s = _fmt(eff_row.get("pace"), 1)
        off_rtg_s = _fmt(eff_row.get("off_rtg"), 1)
        def_rtg_s = _fmt(eff_row.get("def_rtg"), 1)
        tov_s = _fmt(eff_row.get("tov_ratio"), 1)
        efg_s = _fmt(eff_row.get("efg_pct"), 3)
        L += [
            f"### Team Efficiency ({eff_season})",
            f"- **Pace:** {pace_s}  |  **OffRtg:** {off_rtg_s}  |  **DefRtg:** {def_rtg_s}",
            f"- **eFG%:** {efg_s}  |  **TOV ratio:** {tov_s}%",
            "",
        ]

    # ── Play-type offense table ──────────────────────────────────────────────
    L += [
        f"### Offensive Play-Type Profile ({season_used})",
        "| Play Type | PPP | Freq | eFG% |",
        "|---|---|---|---|",
    ]
    for key, label in PLAY_TYPES_OFF:
        ppp = _fmt(row.get(f"off_{key}_ppp"))
        freq = _pct(row.get(f"off_{key}_freq"))
        efg = _fmt(row.get(f"off_{key}_efg"), 3)
        L.append(f"| {label} | {ppp} | {freq} | {efg} |")
    L.append("")

    # ── Play-type defense table ──────────────────────────────────────────────
    L += [
        f"### Defensive Play-Type Profile (PPP Allowed) ({season_used})",
        "| Play Type | PPP Allowed | Opp Freq | eFG% Allowed |",
        "|---|---|---|---|",
    ]
    for key, label in PLAY_TYPES_OFF:
        ppp = _fmt(row.get(f"def_{key}_ppp"))
        freq = _pct(row.get(f"def_{key}_freq"))
        efg = _fmt(row.get(f"def_{key}_efg"), 3)
        L.append(f"| {label} | {ppp} | {freq} | {efg} |")
    L.append("")

    # ── Shot diet ────────────────────────────────────────────────────────────
    shot_cols = ["shot_share_ra", "shot_share_paint_non_ra", "shot_share_midrange",
                 "shot_share_corner3", "shot_share_ab3", "shot_share_3pt", "shot_share_paint"]
    has_shot = any(not pd.isna(row.get(c, float("nan"))) for c in shot_cols)
    if has_shot:
        L += [
            f"### Shot Diet (Offensive Zone Share) ({season_used})",
            "| Zone | FGA Share | FG% |",
            "|---|---|---|",
            f"| Restricted Area | {_pct(row.get('shot_share_ra'))} | {_fmt(row.get('fg_pct_ra'), 3)} |",
            f"| Paint (non-RA) | {_pct(row.get('shot_share_paint_non_ra'))} | {_fmt(row.get('fg_pct_paint_non_ra'), 3)} |",
            f"| Mid-Range | {_pct(row.get('shot_share_midrange'))} | {_fmt(row.get('fg_pct_midrange'), 3)} |",
            f"| Corner 3 | {_pct(row.get('shot_share_corner3'))} | {_fmt(row.get('fg_pct_corner3'), 3)} |",
            f"| Above-Break 3 | {_pct(row.get('shot_share_ab3'))} | {_fmt(row.get('fg_pct_ab3'), 3)} |",
            f"| **3PT total** | **{_pct(row.get('shot_share_3pt'))}** | — |",
            f"| **Paint total** | **{_pct(row.get('shot_share_paint'))}** | — |",
            "",
        ]

    # ── Percentile callouts (sourced from efficiency row for rtg/pace columns)
    # Play-type percentiles come from primary row; efficiency percentiles from
    # eff_row so they match the season that actually has the data.
    pctile_notes = []
    platype_pctile_map = {
        "off_iso_ppp_pctile": "ISO OFF",
        "off_pnrh_ppp_pctile": "PnR-H OFF",
        "off_trans_ppp_pctile": "Transition OFF",
        "off_spotup_ppp_pctile": "Spot-Up OFF",
        "off_cut_ppp_pctile": "Cut OFF",
    }
    eff_pctile_map = {
        "pace_pctile": "Pace",
        "off_rtg_pctile": "OffRtg",
        "def_rtg_pctile": "DefRtg",
    }
    for col, label in platype_pctile_map.items():
        val = row.get(col)
        if val is not None and not pd.isna(val):
            pctile_notes.append(f"{label} {int(val)}th")
    src_for_eff = eff_row if eff_row is not None else row
    for col, label in eff_pctile_map.items():
        val = src_for_eff.get(col)
        if val is not None and not pd.isna(val):
            pctile_notes.append(f"{label} {int(val)}th")
    if pctile_notes:
        pctile_season = eff_season if eff_row is not None else season_used
        L += [
            f"### League Percentiles (play-type: {season_used} · efficiency: {pctile_season})",
            "- " + " · ".join(pctile_notes),
            "",
        ]

    L += [END, ""]
    return "\n".join(L)


def upsert(note_path: str, block: str) -> None:
    """Idempotent insert/replace of the block inside its markers."""
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
    for tri, g in df.groupby("team_tricode"):
        note_path = os.path.join(TEAMS, f"{tri}.md")
        if not os.path.exists(note_path):
            skipped += 1
            continue
        block = build_block(g)
        if not block:
            skipped += 1
            continue
        upsert(note_path, block)
        folded += 1
    print(
        f"DONE: folded team_offdef signals into {folded} team notes "
        f"({skipped} skipped: no vault note found)."
    )


if __name__ == "__main__":
    main()
