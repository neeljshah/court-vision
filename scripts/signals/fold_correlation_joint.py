"""Wave 2 folder: render correlation_joint signals into player notes.

Adds a "## Joint / Correlation Signals" section into existing vault player notes,
wrapped in idempotent markers. Only folds into notes that ALREADY exist (does not
create stubs). Each section explains the signal semantics and leak status so a
reader understands what the numbers mean without needing external docs.

Signals in this section (all SEASON-AGGREGATE, scouting / consumer-B only):
  - Own-stat pairwise rho (pts/reb/ast/fg3m/stl/blk/tov pairs)
  - Archetype-recalibrated rho for headline pairs (validated split-half; refined=True)
  - Per-stat volatility (std-dev of game outcomes — boom/bust profile)
  - Teammate on-off differential (net +/- swing when player on vs off court)

Leak rule: SEASON-AGGREGATE (all historical game outcomes used wholesale). Safe for
  correlation/SGP model (consumer B) and vault scouting (consumer A). NOT for the
  point-prediction model's feature vector (would require shift(1) / prior-season
  discipline to avoid label-leak).

Run after build_correlation_joint.py:
  python scripts/signals/fold_correlation_joint.py
"""
from __future__ import annotations

import glob
import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIG = os.path.join(ROOT, "data", "cache", "signals", "correlation_joint.parquet")
PLAYERS = os.path.join(ROOT, "vault", "Intelligence", "Players")
START = "<!-- SIGNALS:correlation_joint START -->"
END = "<!-- SIGNALS:correlation_joint END -->"

MIN_GAMES = 20   # don't render a section for a player with too few games


def _fmt(v, fmt=".3f", fallback="—") -> str:
    """Format a float value or return fallback for None/NaN."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return fallback
    try:
        return format(float(v), fmt)
    except Exception:
        return fallback


def _rho_label(rho: float | None) -> str:
    """Add a qualitative label to a rho value."""
    if rho is None or (isinstance(rho, float) and pd.isna(rho)):
        return "—"
    v = float(rho)
    label = (
        "strong" if abs(v) >= 0.5
        else "moderate" if abs(v) >= 0.30
        else "weak" if abs(v) >= 0.15
        else "negligible"
    )
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.3f} ({label})"


def build_block(r) -> str:
    """Build the markdown block for a single player row."""
    n = int(r.n_games_corr) if not pd.isna(r.n_games_corr) else 0
    if n < MIN_GAMES:
        return ""

    arch_sp = str(r.archetype_sameplayer) if r.archetype_sameplayer else "—"
    arch_tm = str(r.archetype_teammate) if r.archetype_teammate else "—"

    # Own-stat rho lines
    rho_lines = []
    for col, label in [
        ("rho_pts_ast", "PTS↔AST"),
        ("rho_pts_reb", "PTS↔REB"),
        ("rho_pts_fg3m", "PTS↔FG3M"),
        ("rho_reb_ast", "REB↔AST"),
        ("rho_ast_tov", "AST↔TOV"),
        ("rho_pts_stl", "PTS↔STL"),
        ("rho_pts_blk", "PTS↔BLK"),
    ]:
        val = getattr(r, col, None)
        rho_lines.append(f"  - {label}: {_rho_label(val)}")

    # Arch-refined rho lines (only if value available)
    arch_rho_lines = []
    for col, label in [
        ("arch_rho_pts_fg3m", "PTS↔FG3M (arch-refined)"),
        ("arch_rho_pts_ast", "PTS↔AST (arch-refined)"),
        ("arch_rho_pts_reb", "PTS↔REB (arch-refined)"),
        ("arch_rho_reb_ast", "REB↔AST (arch-refined)"),
    ]:
        val = getattr(r, col, None)
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            arch_rho_lines.append(f"  - {label}: {_rho_label(val)}")

    # Volatility line
    vol_parts = []
    for s in ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]:
        col = f"vol_{s}"
        v = getattr(r, col, None)
        if v is not None and not (isinstance(v, float) and pd.isna(v)):
            vol_parts.append(f"{s}={float(v):.2f}")
    vol_line = " · ".join(vol_parts) if vol_parts else "—"

    vol_pts_pctile = getattr(r, "vol_pts_pctile", None)
    pctile_str = (
        f" ({int(vol_pts_pctile)}th pctile)"
        if vol_pts_pctile is not None and not (isinstance(vol_pts_pctile, float) and pd.isna(vol_pts_pctile))
        else ""
    )

    # On-off line
    on_off_v = getattr(r, "on_off_diff", None)
    on_off_net = getattr(r, "on_off_net_rating_diff", None)
    on_off_line = "—"
    if on_off_v is not None and not (isinstance(on_off_v, float) and pd.isna(on_off_v)):
        on_off_line = f"+/-={_fmt(on_off_v, '+.1f')}"
        if on_off_net is not None and not (isinstance(on_off_net, float) and pd.isna(on_off_net)):
            on_off_line += f" · net_rating_diff={_fmt(on_off_net, '+.1f')}"

    lines = [
        START, "",
        "## Joint / Correlation Signals",
        ("*Season-aggregate pairwise correlations and per-stat volatility from historical "
         "game logs. **Leak rule: season-agg, scouting only** — safe for SGP/parlay "
         "correlation model (consumer B) and vault scouting (consumer A); NOT a point-model "
         f"feature. n={n} games. Archetype (sameplayer): {arch_sp} | (teammate): {arch_tm}.*"),
        "",
        "**Own-stat pairwise rho** (all historical games, Pearson r; |r|≥0.30 = material):",
        *rho_lines,
    ]

    if arch_rho_lines:
        lines += [
            "",
            "**Archetype-recalibrated rho** (split-half validated, refined=True cells; "
            "replaces naive flat assumption in SGP/parlay pricing):",
            *arch_rho_lines,
        ]

    lines += [
        "",
        f"**Per-stat volatility** (std-dev of game outcomes; higher = more boom/bust): {vol_line}",
        f"  - PTS volatility{pctile_str}; use for joint-distribution width in SGP sizing.",
        "",
        f"**Teammate on-off** (team net +/- swing this player on vs off): {on_off_line}",
        "  - Positive = team better with player on; drives vacated-load response for teammates.",
        "",
        END, "",
    ]
    return "\n".join(lines)


def upsert(note_path: str, block: str) -> None:
    """Idempotent upsert: remove old block (if any) then append new."""
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
    for _, row in df.iterrows():
        pid = int(row.player_id)
        cands = glob.glob(os.path.join(PLAYERS, f"{pid}_*.md"))
        if not cands:
            skipped += 1
            continue
        block = build_block(row)
        if not block:
            skipped += 1
            continue
        upsert(cands[0], block)
        folded += 1
    print(
        f"DONE: folded correlation_joint signals into {folded} player notes "
        f"({skipped} skipped: no note or below {MIN_GAMES}-game floor)."
    )


if __name__ == "__main__":
    main()
