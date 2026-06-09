"""Wave 2 folder: render scoring_profile signals into player vault notes.

Adds a "## Scoring Profile" section into existing
vault/Intelligence/Players/<pid>_*.md notes, wrapped in idempotent markers.
Only folds into notes that ALREADY EXIST (never creates stubs).

Run AFTER build_scoring_profile.py:
  python scripts/signals/fold_scoring_profile.py

Signals included (season-aggregate scouting; leak_rule = season-agg):
  - Court-zone shot distribution & FG% (rim / paint non-RA / mid-range /
    corner-3 / above-break-3)
  - Self-created vs assisted share (2P and 3P)
  - Catch-and-shoot vs drive PPP / volume
  - FT generation (FTA/36, FT%, pct pts from FT)
  - Transition vs halfcourt scoring share
  - Play-type PPP (spot-up, ISO, PnR ball-handler, post-up, transition)
    from Synergy (most recent season available)
"""
from __future__ import annotations

import glob
import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIG = os.path.join(ROOT, "data", "cache", "signals", "scoring_profile.parquet")
PLAYERS = os.path.join(ROOT, "vault", "Intelligence", "Players")
START = "<!-- SIGNALS:scoring_profile START -->"
END   = "<!-- SIGNALS:scoring_profile END -->"


# --- formatters -------------------------------------------------------------

def _pct_str(val, decimals=1) -> str:
    """Format a 0-1 fraction as a percentage string, or '–' if missing."""
    if val is None or (isinstance(val, float) and val != val):
        return "–"
    return f"{float(val)*100:.{decimals}f}%"


def _f(val, decimals=2, suffix="") -> str:
    """Format a float with given decimals, or '–' if missing."""
    if val is None or (isinstance(val, float) and val != val):
        return "–"
    return f"{float(val):.{decimals}f}{suffix}"


def _zone_line(r) -> str:
    """Render a concise zone shot distribution line."""
    parts = []
    zone_labels = [
        ("rim",         "Rim (RA)"),
        ("paint_nonra", "Paint non-RA"),
        ("midrange",    "Mid-range"),
        ("corner3",     "Corner 3"),
        ("above3",      "Above-break 3"),
    ]
    for key, label in zone_labels:
        fga = getattr(r, f"shotloc_{key}_fga", None)
        fg  = getattr(r, f"shotloc_{key}_fg_pct", None)
        shr = getattr(r, f"shotloc_{key}_shot_share", None)
        if fga is None or (isinstance(fga, float) and fga != fga) or fga == 0:
            continue
        fga_val = int(fga) if not (isinstance(fga, float) and fga != fga) else 0
        parts.append(
            f"**{label}**: {_pct_str(shr, 0)} of FGA ({fga_val} att, {_pct_str(fg, 0)} FG%)"
        )
    return "  ·  ".join(parts) if parts else "–"


def build_block(r) -> str:
    """Build the full markdown section for one player row."""
    lines = [START, "", "## Scoring Profile",
             "*Season-aggregate scouting signals (2025-26 primary, prior season "
             "for some sources). Leak rule: season-agg — safe for scouting and "
             "correlation consumers; not a direct point-model feed.*", ""]

    # --- Zone distribution --------------------------------------------------
    zone_str = _zone_line(r)
    if zone_str and zone_str != "–":
        lines.append("### Court-Zone Shot Distribution")
        lines.append(zone_str)
        c3_ratio = getattr(r, "shotloc_corner3_vs_above3_ratio", None)
        if c3_ratio is not None and not (isinstance(c3_ratio, float) and c3_ratio != c3_ratio):
            lines.append(
                f"Corner-3 share of all 3PA: **{_pct_str(c3_ratio, 0)}**"
            )
        lines.append("")

    # --- Self-created vs assisted -------------------------------------------
    u2 = getattr(r, "sc_unassisted_share_2pm", None)
    a2 = getattr(r, "sc_assisted_share_2pm", None)
    u3 = getattr(r, "sc_unassisted_share_3pm", None)
    a3 = getattr(r, "sc_assisted_share_3pm", None)
    # Also try breakdown source
    if u2 is None or (isinstance(u2, float) and u2 != u2):
        u2 = getattr(r, "bkdn_scoring_pct_uast_2pm", None)
        a2 = getattr(r, "bkdn_scoring_pct_ast_2pm", None)
        u3 = getattr(r, "bkdn_scoring_pct_uast_3pm", None)
        a3 = getattr(r, "bkdn_scoring_pct_ast_3pm", None)
    has_split = any(
        v is not None and not (isinstance(v, float) and v != v)
        for v in [u2, a2, u3, a3]
    )
    if has_split:
        lines.append("### Creation Split (Assisted vs Self-Created)")
        lines.append(
            f"2PM: **{_pct_str(u2, 0)} self-created** / {_pct_str(a2, 0)} assisted  ·  "
            f"3PM: **{_pct_str(u3, 0)} self-created** / {_pct_str(a3, 0)} assisted"
        )
        lines.append("")

    # --- Catch-and-shoot vs drive -------------------------------------------
    cs_fga = getattr(r, "trk_catch_shoot_fga", None)
    cs_fg  = getattr(r, "trk_catch_shoot_fg_pct", None)
    cs_efg = getattr(r, "trk_catch_shoot_efg_pct", None) or \
             getattr(r, "sc_catch_shoot_efg", None)
    cs_3pa = getattr(r, "trk_catch_shoot_fg3a", None)
    drv    = getattr(r, "trk_drives_per_g", None)
    drv_fg = getattr(r, "trk_drive_fg_pct", None)
    drv_pt = getattr(r, "trk_drive_pts_per_drive", None)
    has_cs  = cs_fga is not None and not (isinstance(cs_fga, float) and cs_fga != cs_fga)
    has_drv = drv is not None and not (isinstance(drv, float) and drv != drv)
    if has_cs or has_drv:
        lines.append("### Catch-and-Shoot vs Drive")
        if has_cs:
            lines.append(
                f"Catch-and-shoot: {_f(cs_fga, 0)} FGA  ·  {_pct_str(cs_fg, 0)} FG%  ·  "
                f"eFG% {_pct_str(cs_efg, 0)}  ·  3PA {_f(cs_3pa, 0)}"
            )
        if has_drv:
            lines.append(
                f"Drives: **{_f(drv, 1)}/game**  ·  {_pct_str(drv_fg, 0)} drive FG%  ·  "
                f"{_f(drv_pt, 2)} pts/drive"
            )
        lines.append("")

    # --- FT generation ------------------------------------------------------
    ft_pct  = getattr(r, "ft_pct", None)
    fta36   = getattr(r, "fta_per_36", None)
    fta_pg  = getattr(r, "fta_pg", None)
    pct_ft  = getattr(r, "pct_pts_from_ft", None)
    ft_l10  = getattr(r, "ft_pct_l10", None)
    has_ft  = any(
        v is not None and not (isinstance(v, float) and v != v)
        for v in [ft_pct, fta36, pct_ft]
    )
    # Also try breakdown source
    if not has_ft:
        pct_ft = getattr(r, "bkdn_scoring_pct_pts_ft", None)
        has_ft = pct_ft is not None and not (isinstance(pct_ft, float) and pct_ft != pct_ft)
    if has_ft:
        lines.append("### Free-Throw Generation")
        lines.append(
            f"FT%: **{_pct_str(ft_pct, 1)}** (L10: {_pct_str(ft_l10, 1)})  ·  "
            f"FTA/game: {_f(fta_pg, 1)}  ·  FTA/36: {_f(fta36, 1)}  ·  "
            f"% pts from FT: **{_pct_str(pct_ft, 0)}**"
        )
        lines.append("")

    # --- Transition vs halfcourt -------------------------------------------
    trans_sh  = getattr(r, "sc_transition_pts_share", None) or \
                getattr(r, "bkdn_scoring_pct_pts_fast_break", None)
    half_sh   = getattr(r, "sc_halfcourt_pts_share", None)
    trans_ppp = getattr(r, "syn_syn_transition_ppp", None) or \
                getattr(r, "syn_transition_ppp", None)
    trans_pg  = getattr(r, "sc_transition_poss_per_game", None)
    has_trans = any(
        v is not None and not (isinstance(v, float) and v != v)
        for v in [trans_sh, trans_ppp]
    )
    if has_trans:
        lines.append("### Transition vs Halfcourt")
        lines.append(
            f"Transition pts share: **{_pct_str(trans_sh, 0)}**  ·  "
            f"Halfcourt: {_pct_str(half_sh, 0)}  ·  "
            f"Transition PPP: {_f(trans_ppp, 3)}  ·  "
            f"Trans poss/game: {_f(trans_pg, 1)}"
        )
        lines.append("")

    # --- Synergy play-type PPP ---------------------------------------------
    syn_spotup = getattr(r, "syn_spotup_ppp", None) or \
                 getattr(r, "syn_syn_spotup_ppp", None)
    syn_iso    = getattr(r, "syn_iso_ppp", None) or \
                 getattr(r, "syn_syn_iso_ppp", None)
    syn_pnr    = getattr(r, "syn_pnr_bh_ppp", None) or \
                 getattr(r, "syn_syn_pnr_bh_ppp", None)
    syn_post   = getattr(r, "syn_postup_ppp", None) or \
                 getattr(r, "syn_syn_postup_ppp", None)
    syn_trans  = getattr(r, "syn_transition_ppp", None) or \
                 getattr(r, "syn_syn_transition_ppp", None)
    has_syn = any(
        v is not None and not (isinstance(v, float) and v != v)
        for v in [syn_spotup, syn_iso, syn_pnr, syn_post, syn_trans]
    )
    if has_syn:
        lines.append("### Synergy Play-Type PPP")
        lines.append(
            f"Spot-up: {_f(syn_spotup, 3)}  ·  ISO: {_f(syn_iso, 3)}  ·  "
            f"PnR ball-handler: {_f(syn_pnr, 3)}  ·  Post-up: {_f(syn_post, 3)}  ·  "
            f"Transition: {_f(syn_trans, 3)}"
        )
        lines.append(
            "*1.00 PPP ≈ league average; higher = more efficient in that play type.*"
        )
        lines.append("")

    # Close
    lines += [END, ""]
    return "\n".join(lines)


def upsert(note_path: str, block: str) -> None:
    """Idempotent insert/replace of the signal block in an existing note."""
    txt = open(note_path, encoding="utf-8").read()
    if START in txt and END in txt:
        # Remove old block (including trailing newline if any)
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
    folded = skipped_no_note = skipped_no_signal = 0

    for _, row in df.iterrows():
        pid = int(row["player_id"])
        cands = glob.glob(os.path.join(PLAYERS, f"{pid}_*.md"))
        if not cands:
            skipped_no_note += 1
            continue

        block = build_block(row)
        # Skip if the block would contain nothing useful
        if block.count("\n") < 6:
            skipped_no_signal += 1
            continue

        upsert(cands[0], block)
        folded += 1

    print(
        f"DONE: scoring_profile folded into {folded} player notes "
        f"({skipped_no_note} skipped — no note; "
        f"{skipped_no_signal} skipped — no usable signals)."
    )


if __name__ == "__main__":
    main()
