"""Wave 2 folder: render the ingame_rotation signals into player vault notes.

Adds a "## In-Game Rotation & Pace Profile" section into the canonical
vault/Intelligence/Players/<pid>_*.md notes, wrapped in idempotent markers.
Only folds into notes that ALREADY exist — does not create stubs.

Leak status of signals: season-aggregate (prior completed games; not per-game
shift). Safe for scouting / in-game projector context; not for point-model
features without a shift(1) gamelog variant.

Run after build_ingame_rotation.py:
  python scripts/signals/fold_ingame_rotation.py
"""
from __future__ import annotations

import glob
import os
import re
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIG = os.path.join(ROOT, "data", "cache", "signals", "ingame_rotation.parquet")
PLAYERS = os.path.join(ROOT, "vault", "Intelligence", "Players")
START = "<!-- SIGNALS:ingame_rotation START -->"
END = "<!-- SIGNALS:ingame_rotation END -->"
MIN_GAMES = 10  # don't fold a note if fewer than this games in sample


def _fmt_opt(val, fmt: str, suffix: str = "") -> str:
    """Format a possibly-NaN value; return '–' if missing."""
    if pd.isna(val):
        return "–"
    return format(val, fmt) + suffix


def _skew_label(skew: float) -> str:
    """Human label for min_curve_skew."""
    if pd.isna(skew):
        return "unknown"
    if skew > 0.15:
        return "Q4-heavy (closer role)"
    if skew < -0.15:
        return "Q1-heavy (starter rested late)"
    return "balanced"


def build_block(r) -> str:
    """Build the markdown section for one player row."""
    # per-quarter minutes line
    q1 = _fmt_opt(r.q1_min_avg, ".1f")
    q2 = _fmt_opt(getattr(r, "atlas_q2_min", float("nan")), ".1f")
    q3 = _fmt_opt(r.q3_starter_min_avg, ".1f")
    q4 = _fmt_opt(r.q4_min_avg, ".1f")

    # per-quarter pts line
    pts_line = (
        f"Q1 {_fmt_opt(r.q1_pts_pg, '.1f')} / "
        f"Q2 {_fmt_opt(r.q2_pts_pg, '.1f')} / "
        f"Q3 {_fmt_opt(r.q3_pts_pg, '.1f')} / "
        f"Q4 {_fmt_opt(r.q4_pts_pg, '.1f')} pts/game"
    )

    skew = getattr(r, "min_curve_skew", float("nan"))
    skew_str = _fmt_opt(skew, "+.3f") if not pd.isna(skew) else "–"
    role_label = _skew_label(skew)

    q4_share = _fmt_opt(r.q4_pts_share, ".1%")
    q4_fade = _fmt_opt(getattr(r, "q4_fade_pts", float("nan")), "+.1f", " pts vs Q1-3 avg")
    q4_ratio = _fmt_opt(getattr(r, "q4_vs_early_ratio", float("nan")), ".2f")

    foul_rate = _fmt_opt(getattr(r, "foul_trouble_rate", float("nan")), ".1%")
    pf36 = _fmt_opt(getattr(r, "pf_per36", float("nan")), ".2f")

    pace_pref = getattr(r, "pace_preference", None)
    pace_pref_str = str(pace_pref) if (pace_pref and not pd.isna(pace_pref)) else "–"
    pace_fit = _fmt_opt(getattr(r, "pace_fit_score", float("nan")), ".3f")
    usg_delta = _fmt_opt(getattr(r, "usage_pace_delta", float("nan")), "+.3f")

    b2b = _fmt_opt(getattr(r, "b2b_decay_ratio", float("nan")), ".2f")

    n = int(r.n_games)

    L = [
        START,
        "",
        "## In-Game Rotation & Pace Profile",
        (
            "*Season-aggregate rotation and pace signals for the in-game projector. "
            "**Leak status: season-agg** — safe for scouting and live context; "
            "not a point-model candidate without a per-game shift(1) variant.*"
        ),
        "",
        f"**Sample:** {n} games (2024-25 + 2025-26 corpus)",
        "",
        "**Minute curve (avg min per quarter):**",
        f"- Q1: {q1} min · Q2: {q2} min · Q3 (starter): {q3} min · Q4: {q4} min",
        f"- Curve skew: **{skew_str}** ({role_label})",
        f"  *(skew = (Q4−Q1) / (Q1+Q4); positive = plays more late; negative = typical resting starter)*",
        "",
        "**Quarter scoring shape:**",
        f"- {pts_line}",
        f"- Q4 share of total pts: **{q4_share}** · Q4 fade vs Q1–3 avg: **{q4_fade}**",
        f"- Q4 vs early ratio (atlas): {q4_ratio}  *(1.0 = same output, <1 = fades, >1 = elevates late)*",
        "",
        "**Foul-trouble profile:**",
        f"- Foul-trouble rate (4+ PF in first half): **{foul_rate}**",
        f"- PF per 36 min (rolling season): {pf36}",
        "",
        "**Pace context:**",
        f"- Pace preference: **{pace_pref_str}** · Pace-fit score: {pace_fit}",
        f"- Usage delta fast−slow games: {usg_delta}",
        f"  *(positive = higher usage in uptempo games; in-game projector can tilt when pace is live)*",
        "",
        "**Load / fatigue proxy:**",
        f"- Second-half minute share: {_fmt_opt(r.second_half_min_share, '.1%')}",
        f"- B2B decay ratio (atlas): {b2b}  *(1.0 = no decay; <1 = worse on 2nd night)*",
        "",
        END,
        "",
    ]
    return "\n".join(L)


def upsert(note_path: str, block: str) -> None:
    """Idempotent upsert: remove old block if present, append new one."""
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
    folded = skipped_no_note = skipped_low_n = 0

    for _, row in df.iterrows():
        pid = int(row["player_id"])
        if row["n_games"] < MIN_GAMES:
            skipped_low_n += 1
            continue
        cands = glob.glob(os.path.join(PLAYERS, f"{pid}_*.md"))
        if not cands:
            skipped_no_note += 1
            continue
        block = build_block(row)
        upsert(cands[0], block)
        folded += 1

    print(
        f"DONE: folded ingame_rotation profile into {folded} player notes "
        f"({skipped_no_note} skipped: no note; {skipped_low_n} skipped: <{MIN_GAMES} games)."
    )


if __name__ == "__main__":
    main()
