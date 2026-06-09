"""Wave 2 folder: render situational_splits signals into player vault notes.

Adds a "## Situational Splits" section into existing
vault/Intelligence/Players/<pid>_*.md notes, wrapped in idempotent markers.
Only folds into notes that ALREADY EXIST — does not create stubs.

Signals folded (all season-aggregate scouting; leak_rule=season-agg):
  Quarter shape     : Q1-Q4 pts/reb/ast per game + Q4 fade direction.
  B2B fade          : pts, reb, ast delta on B2B second leg vs rested baseline.
  Rest-day response : eFG% and minutes across three rest-day buckets.
  Home / road split : stat delta (home minus road) for pts, reb, ast, fg3m.
  Game-script       : pts/eFG% while leading vs trailing vs tied.
  Foul-trouble proxy: PF/game, foul-out rate, early-trouble rate.
  Blowout behavior  : garbage-time exposure rate and per-game scoring in GT.

Run AFTER build_situational_splits.py:
  python scripts/signals/fold_situational_splits.py
"""
from __future__ import annotations

import glob
import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIG = os.path.join(ROOT, "data", "cache", "signals", "situational_splits.parquet")
PLAYERS = os.path.join(ROOT, "vault", "Intelligence", "Players")

START = "<!-- SIGNALS:situational_splits START -->"
END = "<!-- SIGNALS:situational_splits END -->"

# Minimum fill thresholds — skip a sub-section if the key signal is null
MIN_GAMES_Q = 10   # quarter-shape requires at least this many games in pqs


def _fmt(val, fmt: str = ".2f", na: str = "–") -> str:
    """Format a scalar value or return the na placeholder."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return na
    return format(float(val), fmt)


def _sign(val) -> str:
    """Return '+' for non-negative, '' for negative."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return "+" if float(val) >= 0 else ""


def _build_block(r) -> str:
    """Render one player row into the full Markdown section."""
    lines: list[str] = [START, "", "## Situational Splits",
                        "*Season-aggregate scouting signals. "
                        "Leak status: **season-agg** — computed over prior completed seasons; "
                        "safe for scouting (Consumer A) and pregame screening (Consumer D "
                        "with standard walk-forward gate). "
                        "Do NOT feed raw per-game values into the in-game model without shift(1).*",
                        ""]

    # --- Quarter scoring shape ---
    n_pqs = r.get("n_games_pqs")
    has_q = (n_pqs is not None and not pd.isna(n_pqs) and float(n_pqs) >= MIN_GAMES_Q
             and not pd.isna(r.get("q1_pts", float("nan"))))
    if has_q:
        q4_fade = r.get("q4_fade_pts_abs")
        fade_note = ""
        if q4_fade is not None and not pd.isna(q4_fade):
            if float(q4_fade) < -2.0:
                fade_note = " (**notable Q4 fade**)"
            elif float(q4_fade) > 1.5:
                fade_note = " (Q4 elevator)"
        lines.append("### Quarter Scoring Shape")
        lines.append(
            f"Pts/game: Q1 {_fmt(r.get('q1_pts'))} · Q2 {_fmt(r.get('q2_pts'))} "
            f"· Q3 {_fmt(r.get('q3_pts'))} · Q4 {_fmt(r.get('q4_pts'))}{fade_note}"
        )
        lines.append(
            f"Reb/game: Q1 {_fmt(r.get('q1_reb'))} · Q2 {_fmt(r.get('q2_reb'))} "
            f"· Q3 {_fmt(r.get('q3_reb'))} · Q4 {_fmt(r.get('q4_reb'))}"
        )
        lines.append(
            f"Ast/game: Q1 {_fmt(r.get('q1_ast'))} · Q2 {_fmt(r.get('q2_ast'))} "
            f"· Q3 {_fmt(r.get('q3_ast'))} · Q4 {_fmt(r.get('q4_ast'))}"
        )
        lines.append(
            f"Q4 fade (pts): {_sign(q4_fade)}{_fmt(q4_fade)} abs · "
            f"Q4/Q1 ratio {_fmt(r.get('q4_vs_q1_pts_ratio'), '.3f')} "
            f"(n={int(n_pqs)} games)"
        )
        lines.append("")

    # --- B2B fade ---
    # Prefer the richer per-stat delta from situational; fall back to qshape
    b2b_pts = r.get("b2b_pts_delta_vs_rested") or r.get("b2b_pts_delta")
    b2b_reb = r.get("b2b_reb_delta_vs_rested")
    b2b_ast = r.get("b2b_ast_delta_vs_rested")
    b2b_min = r.get("b2b_min_delta_vs_rested")
    b2b_efg = r.get("b2b_efg")
    two_plus_efg = r.get("two_plus_efg")
    has_b2b = b2b_pts is not None and not pd.isna(b2b_pts)
    if has_b2b:
        lines.append("### Back-to-Back Fade")
        lines.append(
            f"B2B 2nd-leg vs rested: pts {_sign(b2b_pts)}{_fmt(b2b_pts)} · "
            f"reb {_sign(b2b_reb)}{_fmt(b2b_reb)} · "
            f"ast {_sign(b2b_ast)}{_fmt(b2b_ast)} · "
            f"min {_sign(b2b_min)}{_fmt(b2b_min)}"
        )
        efg_diff = r.get("efg_b2b_minus_2plus")
        lines.append(
            f"eFG%: B2B {_fmt(b2b_efg, '.3f')} · 2+ rest {_fmt(two_plus_efg, '.3f')} "
            f"· Δ(B2B–2+rest) {_sign(efg_diff)}{_fmt(efg_diff, '.3f')}"
        )
        lines.append("")

    # --- Rest-day response ---
    one_efg = r.get("one_day_efg")
    has_rest = one_efg is not None and not pd.isna(one_efg)
    if has_rest:
        lines.append("### Rest-Day Response (eFG%)")
        lines.append(
            f"B2B: {_fmt(r.get('b2b_efg'), '.3f')} ({_fmt(r.get('b2b_min_pg'))} mpg) · "
            f"1-day rest: {_fmt(r.get('one_day_efg'), '.3f')} ({_fmt(r.get('one_day_min_pg'))} mpg) · "
            f"2+ days: {_fmt(r.get('two_plus_efg'), '.3f')} ({_fmt(r.get('two_plus_min_pg'))} mpg)"
        )
        lines.append("")

    # --- Home / road split ---
    pts_hr = r.get("pts_delta_home_minus_road")
    has_hr = pts_hr is not None and not pd.isna(pts_hr)
    if has_hr:
        lines.append("### Home / Road Split")
        lines.append(
            f"Home pts/game: {_fmt(r.get('home_pts_pg'))} · "
            f"Road pts/game: {_fmt(r.get('road_pts_pg'))} · "
            f"Δ(home−road): pts {_sign(pts_hr)}{_fmt(pts_hr)} · "
            f"reb {_sign(r.get('reb_delta_home_minus_road'))}{_fmt(r.get('reb_delta_home_minus_road'))} · "
            f"ast {_sign(r.get('ast_delta_home_minus_road'))}{_fmt(r.get('ast_delta_home_minus_road'))} · "
            f"fg3m {_sign(r.get('fg3m_delta_home_minus_road'))}{_fmt(r.get('fg3m_delta_home_minus_road'))} "
            f"(n≈{int(float(r['home_n_games'])) if r.get('home_n_games') and not pd.isna(r.get('home_n_games')) else '?'} home games)"
        )
        lines.append("")

    # --- Game-script: leading / trailing / tied ---
    lead_pts = r.get("lead_pts_pg")
    trail_pts = r.get("trail_pts_pg")
    has_margin = (lead_pts is not None and not pd.isna(lead_pts)
                  and trail_pts is not None and not pd.isna(trail_pts))
    if has_margin:
        lines.append("### Game-Script Splits (Leading / Trailing / Tied)")
        lines.append(
            f"Leading  : {_fmt(lead_pts)} pts · {_fmt(r.get('lead_reb_pg'))} reb · "
            f"{_fmt(r.get('lead_ast_pg'))} ast · eFG {_fmt(r.get('lead_efg'), '.3f')} "
            f"(n={int(float(r['lead_n_games'])) if r.get('lead_n_games') and not pd.isna(r.get('lead_n_games')) else '?'} games)"
        )
        lines.append(
            f"Trailing : {_fmt(trail_pts)} pts · {_fmt(r.get('trail_reb_pg'))} reb · "
            f"{_fmt(r.get('trail_ast_pg'))} ast · eFG {_fmt(r.get('trail_efg'), '.3f')} "
            f"(n={int(float(r['trail_n_games'])) if r.get('trail_n_games') and not pd.isna(r.get('trail_n_games')) else '?'} games)"
        )
        tied_pts = r.get("tied_pts_pg")
        if tied_pts is not None and not pd.isna(tied_pts):
            lines.append(
                f"Tied     : {_fmt(tied_pts)} pts · eFG {_fmt(r.get('tied_efg'), '.3f')} "
                f"(n={int(float(r['tied_n_games'])) if r.get('tied_n_games') and not pd.isna(r.get('tied_n_games')) else '?'} games)"
            )
        efg_delta = r.get("efg_trail_minus_lead")
        if efg_delta is not None and not pd.isna(efg_delta):
            lines.append(
                f"eFG Δ trailing−leading: {_sign(efg_delta)}{_fmt(efg_delta, '.3f')} "
                f"({'elevates' if float(efg_delta) > 0 else 'deflates'} when chasing)"
            )
        lines.append("")

    # --- Foul trouble proxy ---
    pf_pg = r.get("mean_pf_pg")
    has_foul = pf_pg is not None and not pd.isna(pf_pg)
    if has_foul:
        lines.append("### Foul-Trouble Proxy")
        lines.append(
            f"PF/game: {_fmt(pf_pg)} · "
            f"foul-out rate: {_fmt(r.get('foul_out_rate'), '.3f')} · "
            f"early-trouble rate (≥2 PF in Q1/Q2): {_fmt(r.get('early_foul_trouble_rate'), '.3f')} · "
            f"foul-trouble rate L10: {_fmt(r.get('foul_trouble_rate_l10'), '.3f')}"
        )
        lines.append(
            f"PF by quarter: Q1 {_fmt(r.get('q1_pf_pg'))} · "
            f"Q2 {_fmt(r.get('q2_pf_pg'))} · "
            f"Q3 {_fmt(r.get('q3_pf_pg'))} · "
            f"Q4 {_fmt(r.get('q4_pf_pg'))}"
        )
        lines.append("")

    # --- Blowout / garbage-time behavior ---
    gt_pct = r.get("pct_games_in_garbage_time")
    has_blowout = gt_pct is not None and not pd.isna(gt_pct)
    if has_blowout:
        lines.append("### Blowout / Garbage-Time Behavior")
        gt_note = ""
        if float(gt_pct) > 0.15:
            gt_note = " (**high GT exposure — inflates season stats**)"
        elif float(gt_pct) < 0.03:
            gt_note = " (minimal GT exposure)"
        lines.append(
            f"GT exposure: {float(gt_pct)*100:.1f}% of games{gt_note} · "
            f"avg pct of minutes in GT: {float(r['mean_pct_min_in_gt'])*100:.1f}% "
            if r.get("mean_pct_min_in_gt") is not None and not pd.isna(r.get("mean_pct_min_in_gt"))
            else f"GT exposure: {float(gt_pct)*100:.1f}% of games{gt_note} · "
        )
        lines.append(
            f"GT performance/game: {_fmt(r.get('gt_pts_pg'))} pts · "
            f"{_fmt(r.get('gt_reb_pg'))} reb · "
            f"{_fmt(r.get('gt_ast_pg'))} ast · "
            f"GT FG%: {_fmt(r.get('gt_fg_pct'), '.3f')} "
            f"(note: GT scoring often against bench / end-of-game opponents)"
        )
        lines.append("")

    # If no sections were written, skip this player
    content_written = len(lines) > 5  # more than just the header boilerplate
    if not content_written:
        return ""

    lines += [END, ""]
    return "\n".join(lines)


def _upsert(note_path: str, block: str) -> None:
    """Idempotent upsert: remove any existing marker block, append new one."""
    txt = open(note_path, encoding="utf-8", errors="replace").read()
    if START in txt and END in txt:
        txt = re.sub(
            re.escape(START) + r".*?" + re.escape(END) + r"\n?",
            "",
            txt,
            flags=re.S,
        )
    txt = txt.rstrip() + "\n\n" + block
    open(note_path, "w", encoding="utf-8").write(txt)


def main() -> None:
    df = pd.read_parquet(SIG)
    folded = skipped_no_note = skipped_no_data = 0

    for _, row in df.iterrows():
        pid = int(row["player_id"])
        cands = glob.glob(os.path.join(PLAYERS, f"{pid}_*.md"))
        if not cands:
            skipped_no_note += 1
            continue
        block = _build_block(row)
        if not block:
            skipped_no_data += 1
            continue
        _upsert(cands[0], block)
        folded += 1

    print(
        f"DONE: folded situational_splits into {folded} player notes "
        f"({skipped_no_note} skipped: no note, "
        f"{skipped_no_data} skipped: no data to render)."
    )


if __name__ == "__main__":
    main()
