"""
refresh_player_intelligence_cards.py — INT-141

Appends/replaces a "## Betting Surface (2026-05-29 refresh)" section to each
player intelligence card in vault/Intelligence/Players/*.md.

Sources used:
  - data/intelligence/teammate_correlation.parquet       (INT-86)
  - data/intelligence/parlay_scores_v2_demo.parquet      (INT-92)
  - data/intelligence/anti_correlation_parlay_candidates.parquet  (INT-98)
  - data/intelligence/daily_picks_retro_2026-04-25_to_2026-05-24.parquet (INT-101)
  - data/intelligence/per_book_edge_audit_2026-05-29.parquet       (INT-104)

Idempotent via banners:
  <!-- INT-141 betting surface start -->
  <!-- INT-141 betting surface end -->
"""

import re
import sys
import os
from pathlib import Path
from datetime import date

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
PLAYERS_DIR = REPO / "vault" / "Intelligence" / "Players"
DATA_DIR = REPO / "data" / "intelligence"

BANNER_START = "<!-- INT-141 betting surface start -->"
BANNER_END   = "<!-- INT-141 betting surface end -->"
REFRESH_DATE = "2026-05-29"

# ── Kill switches ─────────────────────────────────────────────────────────────
cards = sorted(PLAYERS_DIR.glob("*.md"))
if len(cards) < 50:
    print(f"BLOCKED: only {len(cards)} player cards found (expected ≥50).")
    sys.exit(1)

print(f"Found {len(cards)} player cards.")

# ── Load parquets ─────────────────────────────────────────────────────────────
def load_pq(name: str) -> pd.DataFrame:
    p = DATA_DIR / name
    if not p.exists():
        print(f"  WARNING: {name} not found — returning empty df")
        return pd.DataFrame()
    df = pd.read_parquet(p)
    print(f"  Loaded {name}: {len(df)} rows")
    return df

tc   = load_pq("teammate_correlation.parquet")
pv2  = load_pq("parlay_scores_v2_demo.parquet")
ac   = load_pq("anti_correlation_parlay_candidates.parquet")
retro= load_pq("daily_picks_retro_2026-04-25_to_2026-05-24.parquet")
book = load_pq("per_book_edge_audit_2026-05-29.parquet")

missing = sum([tc.empty, pv2.empty, ac.empty, retro.empty, book.empty])
if missing == 5:
    print("BLOCKED: all 5 input parquets missing.")
    sys.exit(1)

# ── Pre-process book_edge: build player_id lookup via player_fingerprints ──────
fp = load_pq("player_fingerprints.parquet")
# fp index is player_id; has player_name column
if not fp.empty and "player_name" in fp.columns:
    fp = fp.reset_index()[["player_id","player_name"]] if "player_id" in fp.reset_index().columns else fp[["player_name"]].reset_index().rename(columns={"index":"player_id"})
    name_to_id = {row["player_name"].lower(): row["player_id"] for _, row in fp.iterrows()}
else:
    name_to_id = {}

# book_edge uses pick_player (player name string)
# build a map from normalized name → rows
if not book.empty:
    book["_name_lower"] = book["pick_player"].str.lower()

# retro also uses player_name string + player_id
# Build retro hit-rate per (player_id, stat)
if not retro.empty:
    retro_summary = (
        retro.groupby(["player_id", "stat"])
        .agg(n_bets=("hit","count"), hit_rate=("hit","mean"), avg_edge=("edge","mean"))
        .reset_index()
    )
else:
    retro_summary = pd.DataFrame()

# parlay_v2: filter surfaced=True
if not pv2.empty and "surfaced" in pv2.columns:
    pv2_surf = pv2[pv2["surfaced"] == True].copy()
else:
    pv2_surf = pv2.copy() if not pv2.empty else pd.DataFrame()

# anti_corr: filter surfaceable=True
if not ac.empty and "surfaceable" in ac.columns:
    ac_surf = ac[ac["surfaceable"] == True].copy()
else:
    ac_surf = ac.copy() if not ac.empty else pd.DataFrame()

# ── Helpers ───────────────────────────────────────────────────────────────────
def _fmt_corr(row) -> str:
    """Format a teammate-correlation row as a one-liner."""
    partner = row["player_b_name"]
    sa, sb = row["stat_a"].upper(), row["stat_b"].upper()
    c = row["corr"]
    sign = "+" if c >= 0 else ""
    note = "usage steal" if c < -0.1 else ("stacks" if c > 0.1 else "neutral")
    return f"  - **{partner}** {sa}×{sb}: {sign}{c:.3f} ({note})"

def _build_section(player_id: int, player_name: str) -> str:
    lines = []
    lines.append(BANNER_START)
    lines.append("")
    lines.append(f"## Betting Surface ({REFRESH_DATE} refresh)")
    lines.append("")

    # ── 1. Teammate top-3 correlations (INT-86) ──────────────────────────────
    if not tc.empty:
        tc_p = tc[tc["player_id_a"] == player_id].copy()
        if tc_p.empty:
            # try as player_b
            tc_p = tc[tc["player_id_b"] == player_id].copy()
            if not tc_p.empty:
                tc_p = tc_p.rename(columns={
                    "player_id_a":"player_id_b","player_a_name":"player_b_name",
                    "player_id_b":"player_id_a","player_b_name":"player_a_name",
                    "stat_a":"stat_b","stat_b":"stat_a",
                })
        if not tc_p.empty:
            tc_p["abs_corr"] = tc_p["corr"].abs()
            top3 = tc_p.nlargest(3, "abs_corr")
            lines.append("### Teammate Correlations — Top 3 (INT-86)")
            for _, r in top3.iterrows():
                lines.append(_fmt_corr(r))
            lines.append("")
        else:
            lines.append("### Teammate Correlations — Top 3 (INT-86)")
            lines.append("  _No teammate-correlation data for this player._")
            lines.append("")
    else:
        lines.append("### Teammate Correlations — Top 3 (INT-86)")
        lines.append("  _Source parquet unavailable._")
        lines.append("")

    # ── 2. Today's parlay edges (INT-92 + INT-98) ────────────────────────────
    lines.append("### Today's Parlay Edges")
    has_edge = False

    # INT-92 multi-leg
    if not pv2_surf.empty and "player_id" in pv2_surf.columns:
        p92 = pv2_surf[pv2_surf["player_id"] == player_id]
        for _, r in p92.iterrows():
            edge_pct = r.get("edge_vs_book", 0) * 100
            stats_lbl = r.get("stats","?")
            line_lbl  = r.get("line","?")
            bet_type  = r.get("bet_type","?")
            lines.append(f"  - **INT-92** [{bet_type}] {stats_lbl} >{line_lbl}: **+{edge_pct:.1f}pp edge** vs book")
            has_edge = True

    # INT-98 anti-correlation (as player_a)
    if not ac_surf.empty:
        p98_a = ac_surf[ac_surf["player_id_a"] == player_id]
        for _, r in p98_a.iterrows():
            partner  = r.get("player_name_b","?")
            sa, da   = r.get("stat_a","?").upper(), r.get("dir_a","?")
            sb, db   = r.get("stat_b","?").upper(), r.get("dir_b","?")
            edge_pct = r.get("edge_vs_book", 0) * 100
            rho      = r.get("rho", 0)
            lines.append(f"  - **INT-98** {sa} {da} + {partner} {sb} {db}: **+{edge_pct:.1f}pp** (ρ={rho:.3f})")
            has_edge = True

        # as player_b
        p98_b = ac_surf[ac_surf["player_id_b"] == player_id]
        for _, r in p98_b.iterrows():
            partner  = r.get("player_name_a","?")
            sa, da   = r.get("stat_a","?").upper(), r.get("dir_a","?")
            sb, db   = r.get("stat_b","?").upper(), r.get("dir_b","?")
            edge_pct = r.get("edge_vs_book", 0) * 100
            rho      = r.get("rho", 0)
            lines.append(f"  - **INT-98** {partner} {sa} {da} + {sb} {db}: **+{edge_pct:.1f}pp** (ρ={rho:.3f})")
            has_edge = True

    if not has_edge:
        lines.append("  _No surfaced parlay edges today (INT-92/INT-98)._")
    lines.append("")

    # ── 3. Retro hit rate per stat (INT-101) ──────────────────────────────────
    lines.append("### Retro Hit Rate by Stat (INT-101)")
    if not retro_summary.empty:
        r_p = retro_summary[retro_summary["player_id"] == player_id]
        if not r_p.empty and len(r_p) >= 2:
            lines.append("| Stat | Bets | Hit% | Avg Edge |")
            lines.append("|------|------|------|----------|")
            for _, r in r_p.sort_values("stat").iterrows():
                lines.append(f"| {r['stat'].upper()} | {int(r['n_bets'])} | {r['hit_rate']*100:.0f}% | {r['avg_edge']*100:+.1f}pp |")
            lines.append("")
        elif not r_p.empty:
            r = r_p.iloc[0]
            lines.append(f"  - {r['stat'].upper()}: {int(r['n_bets'])} bet(s), {r['hit_rate']*100:.0f}% hit, {r['avg_edge']*100:+.1f}pp edge")
            lines.append("")
        else:
            lines.append("  _No retro bets for this player in the 2026-04-25→2026-05-24 window._")
            lines.append("")
    else:
        lines.append("  _Retro parquet unavailable._")
        lines.append("")

    # ── 4. Best book per stat (INT-104) ────────────────────────────────────────
    lines.append("### Best Book per Stat (INT-104)")
    if not book.empty:
        # Match by name (case-insensitive)
        b_p = book[book["_name_lower"] == player_name.lower()]
        if b_p.empty:
            # try partial match on last name
            last_name = player_name.split()[-1].lower() if player_name else ""
            b_p = book[book["_name_lower"].str.contains(last_name, na=False)] if last_name else b_p
        if not b_p.empty:
            lines.append("| Stat | Side | Best Book | Edge vs Model |")
            lines.append("|------|------|-----------|---------------|")
            for _, r in b_p.sort_values("stat").iterrows():
                stat  = r["stat"].upper()
                side  = r.get("side","?")
                bbook = r.get("best_book","?")
                bedge = r.get("best_edge", float("nan"))
                bedge_str = f"{bedge*100:+.1f}pp" if pd.notna(bedge) else "?"
                lines.append(f"| {stat} | {side} | {bbook} | {bedge_str} |")
            lines.append("")
        else:
            lines.append("  _No book-edge data for this player (not in today's slate)._")
            lines.append("")
    else:
        lines.append("  _Book-edge parquet unavailable._")
        lines.append("")

    # ── Footer ─────────────────────────────────────────────────────────────────
    lines.append(f"_Last refreshed by INT-141 on {REFRESH_DATE}_")
    lines.append("")
    lines.append(BANNER_END)

    return "\n".join(lines)

# ── Per-card update logic ─────────────────────────────────────────────────────
def extract_player_id_from_filename(fname: str) -> int | None:
    """Extract player_id from filename like 1628369_jayson_tatum.md"""
    parts = fname.split("_", 1)
    try:
        return int(parts[0])
    except ValueError:
        return None

def extract_player_name_from_filename(fname: str) -> str:
    """Extract readable player name from filename."""
    stem = Path(fname).stem
    parts = stem.split("_", 1)
    if len(parts) == 2:
        name = parts[1].replace("_", " ").title()
    else:
        name = stem
    return name

def update_card(card_path: Path) -> dict:
    """Read card, replace/append betting surface section. Return stats dict."""
    fname = card_path.name
    player_id = extract_player_id_from_filename(fname)
    player_name = extract_player_name_from_filename(fname)

    try:
        content = card_path.read_text(encoding="utf-8")
    except Exception as e:
        return {"file": fname, "status": "read_error", "error": str(e)}

    new_section = _build_section(player_id, player_name)

    # Idempotent replace
    if BANNER_START in content and BANNER_END in content:
        pattern = re.escape(BANNER_START) + r".*?" + re.escape(BANNER_END)
        new_content = re.sub(pattern, new_section, content, flags=re.DOTALL)
        action = "replaced"
    else:
        # Append after last non-empty line
        new_content = content.rstrip() + "\n\n" + new_section + "\n"
        action = "appended"

    try:
        card_path.write_text(new_content, encoding="utf-8")
    except Exception as e:
        return {"file": fname, "status": "write_error", "error": str(e)}

    # Gather match stats
    has_tc      = not tc.empty and (player_id in tc["player_id_a"].values or player_id in tc["player_id_b"].values)
    has_retro   = not retro_summary.empty and player_id in retro_summary["player_id"].values
    has_pv2     = not pv2_surf.empty and "player_id" in pv2_surf.columns and player_id in pv2_surf["player_id"].values
    has_ac      = not ac_surf.empty and (
        ("player_id_a" in ac_surf.columns and player_id in ac_surf["player_id_a"].values) or
        ("player_id_b" in ac_surf.columns and player_id in ac_surf["player_id_b"].values)
    )
    has_book    = not book.empty and player_name.lower() in book["_name_lower"].values

    # INT-92 edge for top-5 ranking
    pv2_edge = 0.0
    if not pv2_surf.empty and "player_id" in pv2_surf.columns:
        p92 = pv2_surf[pv2_surf["player_id"] == player_id]
        if not p92.empty:
            pv2_edge = float(p92["edge_vs_book"].max())
    ac_edge = 0.0
    if not ac_surf.empty:
        p98_a = ac_surf[ac_surf.get("player_id_a", pd.Series(dtype=int)) == player_id] if "player_id_a" in ac_surf.columns else pd.DataFrame()
        p98_b = ac_surf[ac_surf.get("player_id_b", pd.Series(dtype=int)) == player_id] if "player_id_b" in ac_surf.columns else pd.DataFrame()
        edges = []
        if not p98_a.empty: edges.extend(p98_a["edge_vs_book"].tolist())
        if not p98_b.empty: edges.extend(p98_b["edge_vs_book"].tolist())
        ac_edge = max(edges) if edges else 0.0

    return {
        "file": fname,
        "player_id": player_id,
        "player_name": player_name,
        "action": action,
        "status": "ok",
        "has_tc": has_tc,
        "has_retro": has_retro,
        "has_pv2": has_pv2,
        "has_ac": has_ac,
        "has_book": has_book,
        "max_edge": max(pv2_edge, ac_edge),
    }

# ── Main loop ─────────────────────────────────────────────────────────────────
results = []
for card in cards:
    r = update_card(card)
    results.append(r)
    if r["status"] != "ok":
        print(f"  {r['status'].upper()}: {r['file']} — {r.get('error','')}")

ok = [r for r in results if r["status"] == "ok"]
n_tc      = sum(r.get("has_tc", False) for r in ok)
n_retro   = sum(r.get("has_retro", False) for r in ok)
n_pv2     = sum(r.get("has_pv2", False) for r in ok)
n_ac      = sum(r.get("has_ac", False) for r in ok)
n_book    = sum(r.get("has_book", False) for r in ok)
n_cards   = len(ok)

print(f"\n=== INT-141 Summary ===")
print(f"Cards refreshed: {n_cards}/{len(cards)}")
print(f"Teammate corr match:   {n_tc} ({n_tc/n_cards*100:.0f}%)")
print(f"Retro hit-rate match:  {n_retro} ({n_retro/n_cards*100:.0f}%)")
print(f"INT-92 parlay match:   {n_pv2}")
print(f"INT-98 anti-corr match:{n_ac}")
print(f"Book-edge match:       {n_book}")

# Top-5 by edge
top5 = sorted(ok, key=lambda r: r.get("max_edge", 0), reverse=True)[:5]
print("\nTop 5 by today's edge (INT-92 + INT-98):")
for r in top5:
    print(f"  {r['player_name']} ({r['player_id']}): max_edge={r['max_edge']:.4f}")

# ── Write summary log ─────────────────────────────────────────────────────────
log_path = REPO / "vault" / "Intelligence" / "_Player_Betting_Refresh_Log.md"
top5_md = "\n".join(
    f"{i+1}. **{r['player_name']}** (ID:{r['player_id']}) — max edge {r['max_edge']*100:.2f}pp"
    for i, r in enumerate(top5)
)
log_content = f"""# Player Betting Surface Refresh Log — INT-141

**Date:** {REFRESH_DATE}
**Script:** `scripts/refresh_player_intelligence_cards.py`

## Summary

| Metric | Value |
|--------|-------|
| Total cards found | {len(cards)} |
| Cards refreshed (ok) | {n_cards} |
| With teammate correlation (INT-86) | {n_tc} ({n_tc/n_cards*100:.0f}%) |
| With retro hit-rate data (INT-101) | {n_retro} ({n_retro/n_cards*100:.0f}%) |
| With INT-92 parlay edge today | {n_pv2} |
| With INT-98 anti-corr edge today | {n_ac} |
| With book-edge data (INT-104) | {n_book} |

## Top 5 Players by Today's Edge (INT-92 + INT-98)

{top5_md}

## Notes
- Idempotent via `<!-- INT-141 betting surface start/end -->` banners
- Replace on re-run; won't accumulate duplicate sections
- Sources: teammate_correlation (INT-86), parlay_scores_v2_demo (INT-92),
  anti_correlation_parlay_candidates (INT-98),
  daily_picks_retro_2026-04-25_to_2026-05-24 (INT-101),
  per_book_edge_audit_2026-05-29 (INT-104)

_Generated by INT-141 refresh on {REFRESH_DATE}_
"""
log_path.write_text(log_content, encoding="utf-8")
print(f"\nWrote {log_path}")

# ── Append to cv_master_strategy.md ───────────────────────────────────────────
strat_path = REPO / "vault" / "Improvements" / "cv_master_strategy.md"
if strat_path.exists():
    existing = strat_path.read_text(encoding="utf-8")
    banner_line = f"\n<!-- INT-141 player cards refresh --> {REFRESH_DATE}: refreshed {n_cards} player intelligence cards with betting surface (INT-86/92/98/101/104). Teammate matches={n_tc}, retro={n_retro}, edges={n_pv2+n_ac}.\n"
    if "<!-- INT-141 player cards refresh -->" not in existing:
        strat_path.write_text(existing.rstrip() + banner_line, encoding="utf-8")
        print(f"Appended banner to {strat_path}")
    else:
        print(f"Banner already present in {strat_path} — skipping.")
else:
    print(f"WARNING: {strat_path} not found — skipping strategy append.")

print("\nINT-141 complete.")
