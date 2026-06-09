"""Wave 2 folder: render the playmaking signals into player notes.

Adds a "## Playmaking Profile" section into the canonical
vault/Intelligence/Players/<pid>_*.md notes, wrapped in idempotent markers.
Only folds into notes that ALREADY exist (does not create stubs).

Run after build_playmaking.py:
  python scripts/signals/fold_playmaking.py
"""
from __future__ import annotations

import glob
import os
import re
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIG = os.path.join(ROOT, "data", "cache", "signals", "playmaking.parquet")
PLAYERS = os.path.join(ROOT, "vault", "Intelligence", "Players")
START = "<!-- SIGNALS:playmaking START -->"
END = "<!-- SIGNALS:playmaking END -->"


def _fmt(val, digits: int = 1, suffix: str = "") -> str:
    """Format a numeric value, returning '–' if missing."""
    if val is None or (isinstance(val, float) and (val != val)):  # NaN check
        return "–"
    try:
        return f"{float(val):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return str(val)


def _pct(val) -> str:
    """Format as a percentage (multiply by 100)."""
    if val is None or (isinstance(val, float) and (val != val)):
        return "–"
    try:
        return f"{float(val) * 100:.1f}%"
    except (TypeError, ValueError):
        return str(val)


def build_block(r) -> str:
    """Build the full markdown block for one player row."""
    # --- Season-aggregate line ---
    ast_pts = _fmt(getattr(r, "ast_pts_created_pg", None))
    pot_ast = _fmt(getattr(r, "potential_ast_pg", None))
    sec_ast = _fmt(getattr(r, "secondary_ast_pg", None))
    passes = _fmt(getattr(r, "passes_made_pg", None))
    ast_pass = _fmt(getattr(r, "ast_per_pass", None), digits=3)
    ast_pct_tr = _pct(getattr(r, "ast_pct_tracking", None))
    _ast_pct_br_val = getattr(r, "ast_pct_bbref", None)
    ast_pct_br = "–" if _ast_pct_br_val is None or (isinstance(_ast_pct_br_val, float) and _ast_pct_br_val != _ast_pct_br_val) else f"{float(_ast_pct_br_val):.1f}%"
    _tov_pct_val = getattr(r, "tov_pct_bbref", None)
    tov_pct = "–" if _tov_pct_val is None or (isinstance(_tov_pct_val, float) and _tov_pct_val != _tov_pct_val) else f"{float(_tov_pct_val):.1f}%"

    ato_s = _fmt(getattr(r, "ato_season", None), digits=2)
    pnr_share = _pct(getattr(r, "pnr_bh_poss_share", None))
    drive_kick = _fmt(getattr(r, "drive_and_kick_pg", None))
    drive_kick_rate = _pct(getattr(r, "drive_kick_rate", None))
    drive_ast_drive = _pct(getattr(r, "drive_ast_per_drive", None))
    drive_tov_drive = _pct(getattr(r, "drive_tov_per_drive", None))
    screen_ast = _fmt(getattr(r, "screen_ast_pg", None))
    creation_conv = _fmt(getattr(r, "creation_conversion", None), digits=2)
    season = getattr(r, "season", None) or "–"

    # --- Rolling L10 line ---
    ast_l10 = _fmt(getattr(r, "ast_l10", None))
    tov_l10 = _fmt(getattr(r, "tov_l10", None))
    ato_l10 = _fmt(getattr(r, "ato_l10", None), digits=2)
    ast_vol = _fmt(getattr(r, "ast_vol_l10", None))
    as_of = getattr(r, "as_of_date", None) or ""
    n_games_gl = getattr(r, "n_games_gl", None)

    lines = [
        START,
        "",
        "## Playmaking Profile",
        (
            "*Assist points created, creation rate, drive-and-kick, A:TO, and PnR ball-handler share. "
            "Season-aggregate = scouting signal (season-agg, no overfit risk). "
            "Rolling L10 uses shift(1) prior-games-only = leak-free.*"
        ),
        "",
        f"**Season ({season}) — aggregate:**",
        (
            f"- AST pts created: **{ast_pts}**/g · Potential AST: {pot_ast}/g "
            f"· Secondary AST: {sec_ast}/g · Creation conversion: {creation_conv}"
        ),
        (
            f"- Passes/g: {passes} · AST/pass: {ast_pass} "
            f"· AST% (tracking): {ast_pct_tr} · AST% (BBRef): {ast_pct_br}"
        ),
        f"- A:TO (season): **{ato_s}** · TOV%: {tov_pct}",
        (
            f"- PnR ball-handler poss share: **{pnr_share}** "
            f"· Screen AST/g (screener proxy): {screen_ast}"
        ),
        (
            f"- Drive-and-kick: {drive_kick}/g ({drive_kick_rate} of drives) "
            f"· Drive→AST: {drive_ast_drive} · Drive→TOV: {drive_tov_drive}"
        ),
        "",
    ]

    # Rolling L10 line (only if we have data)
    has_rolling = ast_l10 != "–" or tov_l10 != "–"
    if has_rolling:
        as_of_str = f" as of {as_of}" if as_of else ""
        n_str = f" ({int(n_games_gl)}g)" if n_games_gl else ""
        lines.append(f"**Rolling L10{n_str}{as_of_str} — prior-games-only:**")
        lines.append(
            f"- AST L10: **{ast_l10}** · TOV L10: {tov_l10} "
            f"· A:TO L10: {ato_l10} · AST vol (std): {ast_vol}"
        )
        lines.append("")

    lines += [END, ""]
    return "\n".join(lines)


def upsert(note_path: str, block: str) -> None:
    """Idempotent upsert: remove old block (if any) and append new."""
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
    folded = skipped_no_note = skipped_no_data = 0

    for _, row in df.iterrows():
        pid = int(row["player_id"])
        cands = glob.glob(os.path.join(PLAYERS, f"{pid}_*.md"))
        if not cands:
            skipped_no_note += 1
            continue

        # Require at least one meaningful signal before folding
        has_season = pd.notna(row.get("ast_pts_created_pg"))
        has_rolling = pd.notna(row.get("ast_l10"))
        if not (has_season or has_rolling):
            skipped_no_data += 1
            continue

        block = build_block(row)
        upsert(cands[0], block)
        folded += 1

    print(
        f"DONE: folded playmaking profile into {folded} player notes "
        f"({skipped_no_note} skipped: no note, "
        f"{skipped_no_data} skipped: no signal data)."
    )


if __name__ == "__main__":
    main()
