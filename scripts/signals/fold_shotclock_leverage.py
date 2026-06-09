"""Wave 2 folder: render shotclock_leverage signals into existing player vault notes.

Adds a "## Shot-Clock & Leverage Scoring" section into
vault/Intelligence/Players/<pid>_*.md notes (idempotent via marker pair).
Only folds into notes that ALREADY exist — does not create stubs for unlisted players.

Signals rendered:
  Shot-clock: late-clock shots/pg, late-clock rate, TS%/eFG%
  Clutch:     clutch pts/36, plus-minus, FG%, FG3%, and-1s/pg
  Leverage:   pts/pg leading / tied / trailing, deltas vs tied
  Quarter:    Q1–Q4 pts shape, Q4-share, second-half minute share

Leak status (stated in the section header): SEASON-AGGREGATE — scouting only;
not suitable as a point-model feature without a shift-by-game-date as-of wrapper.

Run after build_shotclock_leverage.py:
  python scripts/signals/fold_shotclock_leverage.py
"""
from __future__ import annotations

import glob
import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIG = os.path.join(ROOT, "data", "cache", "signals", "shotclock_leverage.parquet")
PLAYERS = os.path.join(ROOT, "vault", "Intelligence", "Players")
START = "<!-- SIGNALS:shotclock_leverage START -->"
END   = "<!-- SIGNALS:shotclock_leverage END -->"

# Minimum thresholds for rendering a metric block
MIN_CLUTCH_GP   = 5    # clutch game appearances
MIN_LEVERAGE_GAMES = 5  # lead/trail/tied sample


def _fmt(v, fmt=".2f") -> str:
    """Format a value or return '—' if null."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return format(float(v), fmt)


def _pct(v) -> str:
    """Format a fraction as a percentage string."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{float(v)*100:.1f}%"


def _build_shot_clock_block(r) -> str:
    """One-liner shot-clock section."""
    shots  = _fmt(r.get("late_clock_shots_pg"), ".2f")
    rate   = _pct(r.get("late_clock_rate"))
    ts     = _pct(r.get("late_clock_ts_pct"))
    efg    = _pct(r.get("late_clock_efg_pct"))
    # If all null, skip
    if shots == "—" and rate == "—":
        return ""
    return (f"**Late clock (<7 s):** {shots} shot attempts/g · "
            f"{rate} of possessions end in late-clock shot · "
            f"TS% {ts} · eFG% {efg}")


def _build_clutch_block(r) -> str:
    """Clutch scoring summary."""
    gp  = r.get("clutch_gp")
    if gp is None or (isinstance(gp, float) and pd.isna(gp)) or float(gp) < MIN_CLUTCH_GP:
        return ""
    p36 = _fmt(r.get("clutch_pts_per36"), ".1f")
    pm  = _fmt(r.get("clutch_plus_minus"), ".1f")
    fg  = _pct(r.get("clutch_fg_pct"))
    fg3 = _pct(r.get("clutch_fg3_pct"))
    ft  = _pct(r.get("clutch_ft_pct"))
    and1 = _fmt(r.get("clutch_and1_pg"), ".2f")
    return (f"**Clutch** (last 5 min, ≤5 pts; {int(gp)} gp): "
            f"{p36} pts/36 · ±{pm} net/gm · "
            f"FG {fg} · FG3 {fg3} · FT {ft} · "
            f"and-1s/g {and1}")


def _build_leverage_block(r) -> str:
    """Leverage splits: leading / tied / trailing."""
    lead_n  = r.get("lead_n_games")
    tied_n  = r.get("tied_n_games")
    trail_n = r.get("trail_n_games")
    # Need at least one non-null split with sufficient sample
    has_any = any(
        (v is not None and not (isinstance(v, float) and pd.isna(v)) and float(v) >= MIN_LEVERAGE_GAMES)
        for v in [lead_n, tied_n, trail_n]
    )
    if not has_any:
        return ""
    lead_pts  = _fmt(r.get("lead_pts_pg"))
    tied_pts  = _fmt(r.get("tied_pts_pg"))
    trail_pts = _fmt(r.get("trail_pts_pg"))
    lead_efg  = _pct(r.get("lead_efg_pct"))
    tied_efg  = _pct(r.get("tied_efg_pct"))
    trail_efg = _pct(r.get("trail_efg_pct"))
    ltd = r.get("lead_vs_tied_pts_pm_delta")
    trd = r.get("trail_vs_tied_pts_pm_delta")
    ltd_str = ("▼" + _fmt(abs(ltd), ".3f") + " pts/min behind tied") if (ltd is not None and not pd.isna(ltd) and ltd < 0) else \
              ("▲+" + _fmt(ltd, ".3f") + " pts/min ahead of tied") if (ltd is not None and not pd.isna(ltd) and ltd > 0) else ""
    trd_str = ("▲+" + _fmt(trd, ".3f") + " pts/min vs tied") if (trd is not None and not pd.isna(trd) and trd > 0) else \
              ("▼" + _fmt(abs(trd), ".3f") + " pts/min vs tied") if (trd is not None and not pd.isna(trd) and trd < 0) else ""
    lines = ["**Game-script splits (pts/g · eFG%):**"]
    lead_ng = int(float(lead_n)) if (lead_n is not None and not pd.isna(lead_n)) else 0
    tied_ng = int(float(tied_n)) if (tied_n is not None and not pd.isna(tied_n)) else 0
    trail_ng = int(float(trail_n)) if (trail_n is not None and not pd.isna(trail_n)) else 0
    if lead_ng >= MIN_LEVERAGE_GAMES:
        lines.append(f"  - Leading (≥+5): {lead_pts} pts · eFG {lead_efg} ({lead_ng} gm) {ltd_str}")
    if tied_ng >= MIN_LEVERAGE_GAMES:
        lines.append(f"  - Tied (within 5): {tied_pts} pts · eFG {tied_efg} ({tied_ng} gm)")
    if trail_ng >= MIN_LEVERAGE_GAMES:
        lines.append(f"  - Trailing (≥−5): {trail_pts} pts · eFG {trail_efg} ({trail_ng} gm) {trd_str}")
    return "\n".join(lines)


def _build_quarter_block(r) -> str:
    """Q1–Q4 points and Q4 weight.

    2025-26 quarter_features has a median of ~4 games per player (early-season snapshot).
    Append a small-sample caveat whenever n < 15 so readers don't over-weight the shape.
    """
    n = r.get("qs_n_games")
    if n is None or (isinstance(n, float) and pd.isna(n)) or float(n) < 5:
        return ""
    n_int = int(float(n))
    q1 = _fmt(r.get("q1_pts_pg"), ".1f")
    q2 = _fmt(r.get("q2_pts_pg"), ".1f")
    q3 = _fmt(r.get("q3_pts_pg"), ".1f")
    q4 = _fmt(r.get("q4_pts_pg"), ".1f")
    q4sh = _pct(r.get("q4_share_pts"))
    q4tilt = _pct(r.get("q4_pts_tilt"))
    sample_note = f" *(small sample, ~{n_int} gp — early-season noise)*" if n_int < 15 else ""
    return (f"**Quarter shape** ({n_int} gm): "
            f"Q1 {q1} / Q2 {q2} / Q3 {q3} / Q4 {q4} pts/g · "
            f"Q4 share of pts {q4sh} · Q4 tilt {q4tilt}{sample_note}")


def build_block(r: dict) -> str:
    """Build the full marker-wrapped section for one player."""
    sc   = _build_shot_clock_block(r)
    cl   = _build_clutch_block(r)
    lev  = _build_leverage_block(r)
    qsh  = _build_quarter_block(r)

    bullets = [b for b in [sc, cl, lev, qsh] if b]
    if not bullets:
        return ""

    lines = [
        START, "",
        "## Shot-Clock & Leverage Scoring",
        ("*Season-aggregate scouting signals (2025-26 official + 2023-24 PBP). "
         "**Leak rule: season-agg** — describes the past season; use a shift-by-date wrapper "
         "before feeding the live prediction model.*"),
        "",
    ]
    for b in bullets:
        # Multi-line bullets (leverage split) get their own block; single-line → "- " prefix
        if "\n" in b:
            lines.append(b)
        else:
            lines.append("- " + b)
    lines += ["", END, ""]
    return "\n".join(lines)


def upsert(note_path: str, block: str) -> None:
    """Idempotent upsert: strip old block if present, append new block."""
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
    # Convert to dicts for fast row access
    records = {
        int(row.player_id): row.to_dict()
        for _, row in df.iterrows()
    }

    folded = skipped_no_note = skipped_no_data = 0
    for pid, r in records.items():
        cands = glob.glob(os.path.join(PLAYERS, f"{pid}_*.md"))
        if not cands:
            skipped_no_note += 1
            continue
        block = build_block(r)
        if not block:
            skipped_no_data += 1
            continue
        upsert(cands[0], block)
        folded += 1

    print(
        f"DONE: shotclock_leverage folded into {folded} player notes "
        f"({skipped_no_note} skipped: no vault note · "
        f"{skipped_no_data} skipped: below signal thresholds)."
    )


if __name__ == "__main__":
    main()
