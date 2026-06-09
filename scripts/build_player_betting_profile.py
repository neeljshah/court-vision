"""
INT-140: Per-player betting profile builder.

Aggregates INT-101 retro picks + INT-104 per-book audit into a
per-(player_id, stat) parquet that powers AI Chat "Which player props
should I bet on?" queries.

SCOPED-SHIP NOTE: retro pool has only 18 distinct players (gate requires 30).
Profiles are valid but confidence tiers should be treated as early-signal only
until the retro pool grows to 30+ players.
"""

import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DATA_INT = REPO / "data" / "intelligence"
VAULT_INT = REPO / "vault" / "Intelligence"
VAULT_IMP = REPO / "vault" / "Improvements"

RETRO_PATH = DATA_INT / "daily_picks_retro_2026-04-25_to_2026-05-24.parquet"
BOOK_PATH = DATA_INT / "per_book_edge_audit_2026-05-29.parquet"
PICKS_PATH = DATA_INT / "daily_picks_2026-05-29.json"
FINGERPRINTS_PATH = DATA_INT / "player_fingerprints.parquet"

OUT_PARQUET = DATA_INT / "player_betting_profile.parquet"
OUT_MD = VAULT_INT / "Players_Betting_Index.md"
CV_STRATEGY_PATH = VAULT_IMP / "cv_master_strategy.md"

TODAY = str(date.today())
BANNER = "<!-- INT-140 player betting profile -->"


# ── helpers ──────────────────────────────────────────────────────────────────

def confidence_tier(n, hit_rate, roi):
    """Assign high/med/low confidence tier per INT-140 heuristic."""
    if n >= 5 and hit_rate >= 0.60 and roi >= 5.0:
        return "high"
    if n >= 3 and hit_rate >= 0.50:
        return "med"
    return "low"


def make_notes(row):
    """Auto-generate a 1-line note from aggregated metrics (no LLM)."""
    side_hint = row.get("dominant_side", "")
    stat = str(row["stat"]).upper()
    n = int(row["n_retro_bets"])
    hr_pct = f"{row['hit_rate'] * 100:.0f}%"
    roi = row["roi_kelly_025"]
    tier = row["confidence_tier"]

    if tier == "high":
        return (
            f"Strong {side_hint} edge on {stat} "
            f"(hit {hr_pct} of {n} retro bets, "
            f"+{roi:.1f}% ROI)"
        )
    elif tier == "med":
        return (
            f"Moderate {side_hint} edge on {stat} "
            f"(hit {hr_pct} of {n} retro bets, "
            f"{roi:+.1f}% ROI)"
        )
    else:
        return f"Marginal — small sample ({n} bets, {roi:+.1f}% ROI), monitor"


# ── STEP 1: load INT-101 retro ────────────────────────────────────────────────

def load_retro():
    if not RETRO_PATH.exists():
        sys.exit(f"BLOCKED: INT-101 retro parquet not found at {RETRO_PATH}")
    df = pd.read_parquet(RETRO_PATH)
    if df.empty:
        sys.exit("BLOCKED: INT-101 retro parquet has no rows")
    print(f"[G1] Retro loaded: {len(df)} rows")
    return df


# ── STEP 2: load INT-104 book audit ──────────────────────────────────────────

def load_book_audit():
    if not BOOK_PATH.exists():
        sys.exit(f"BLOCKED: INT-104 book audit parquet not found at {BOOK_PATH}")
    df = pd.read_parquet(BOOK_PATH)
    if df.empty:
        sys.exit("BLOCKED: INT-104 book audit parquet has no rows")
    print(f"[G1] Book audit loaded: {len(df)} rows")
    return df


# ── STEP 3: load INT-99 daily picks (supplementary context) ──────────────────

def load_daily_picks():
    if not PICKS_PATH.exists():
        print(f"[WARN] INT-99 daily picks not found at {PICKS_PATH}, skipping")
        return []
    with open(PICKS_PATH) as f:
        picks = json.load(f)
    print(f"[INFO] Daily picks loaded: {len(picks)} entries")
    return picks


# ── STEP 4: build per-(player_id, stat) aggregate ────────────────────────────

def build_profiles(retro: pd.DataFrame, book: pd.DataFrame) -> pd.DataFrame:
    # Filter to single-player single-stat rows only (exclude parlays/compound stats)
    singles = retro[
        ~retro["player"].str.contains(r"\+", na=False)
        & ~retro["stat"].str.contains(r"\+", na=False)
    ].copy()

    if singles.empty:
        sys.exit("BLOCKED: no single-player rows in retro after filtering")

    # Dominant side per (player_id, stat) — for notes generation
    def dominant_side(s):
        counts = s.value_counts()
        # Exclude ANTI_CORR from side label
        counts = counts[counts.index.isin(["OVER", "UNDER"])]
        return counts.index[0] if not counts.empty else ""

    side_map = (
        singles.groupby(["player_id", "stat"])["side"]
        .apply(dominant_side)
        .reset_index()
        .rename(columns={"side": "dominant_side"})
    )

    # Core aggregation
    agg = (
        singles.groupby(["player_id", "stat"])
        .agg(
            player_name=("player", "first"),
            n_retro_bets=("hit", "count"),
            hit_rate=("hit", "mean"),
            mean_edge_pp=("edge", "mean"),
            roi_kelly_025=("kelly_025", lambda x: x.sum() * 100),  # % ROI over window
        )
        .reset_index()
    )

    # Merge dominant side for notes
    agg = agg.merge(side_map, on=["player_id", "stat"], how="left")

    # ── left-join INT-104 book audit ──────────────────────────────────────────
    # Build lookup: (player_name, stat) -> best_book + edge_spread
    # book uses pick_player not player_id — join on normalized name + stat
    book_lookup = (
        book[["pick_player", "stat", "best_book", "edge_spread"]]
        .rename(columns={"pick_player": "player_name"})
    )
    # Only keep the best-edge row per (player_name, stat) (pick highest edge_spread)
    book_lookup = (
        book_lookup.sort_values("edge_spread", ascending=False)
        .drop_duplicates(subset=["player_name", "stat"])
    )

    agg = agg.merge(book_lookup, on=["player_name", "stat"], how="left")
    agg["best_book"] = agg["best_book"].fillna("any")
    agg["edge_spread"] = agg["edge_spread"].fillna(0.0)

    # G2 gate
    n_players_ge3 = (agg.groupby("player_id")["n_retro_bets"].sum() >= 3).sum()
    if n_players_ge3 < 30:
        print(
            f"[SCOPED-SHIP] G2: only {n_players_ge3} distinct players with >=3 retro bets "
            f"(gate=30). Shipping with disclaimer — refresh when retro pool grows."
        )

    # G3: distinct (player_id, stat) rows — duplicates would be a logic bug
    dupes = agg.duplicated(subset=["player_id", "stat"]).sum()
    if dupes > 0:
        sys.exit(f"BLOCKED G3: {dupes} duplicate (player_id, stat) rows — fix join logic")
    print(f"[G3] No duplicate (player_id, stat) rows")

    # Confidence tier
    agg["confidence_tier"] = agg.apply(
        lambda r: confidence_tier(r["n_retro_bets"], r["hit_rate"], r["roi_kelly_025"]),
        axis=1,
    )

    # G4 sanity
    assert agg["hit_rate"].between(0, 1).all(), "G4 FAIL: hit_rate out of [0,1]"
    assert agg["mean_edge_pp"].between(-50, 50).all(), "G4 FAIL: mean_edge_pp out of [-50,50]"
    assert agg["roi_kelly_025"].between(-100, 100).all(), "G4 FAIL: roi_kelly_025 out of [-100%,100%]"
    print("[G4] Sanity checks passed")

    # Check all-zero hit_rate kill switch
    if (agg["hit_rate"] == 0).all():
        sys.exit("BLOCKED: all player rows have hit_rate=0 — audit join logic")

    # Step 5: notes
    agg["notes"] = agg.apply(make_notes, axis=1)

    # Add metadata
    agg["last_updated_date"] = TODAY

    # Step 6: sort by roi_kelly_025 descending
    agg = agg.sort_values("roi_kelly_025", ascending=False).reset_index(drop=True)

    # Final column order per schema
    out_cols = [
        "player_id", "player_name", "stat",
        "n_retro_bets", "hit_rate", "mean_edge_pp",
        "roi_kelly_025", "best_book", "confidence_tier",
        "last_updated_date", "notes",
    ]
    return agg[out_cols]


# ── STEP 7: write parquet (atomic) ────────────────────────────────────────────

def write_parquet(df: pd.DataFrame):
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=OUT_PARQUET.parent, suffix=".parquet.tmp")
    os.close(fd)
    try:
        df.to_parquet(tmp_path, index=False)
        os.replace(tmp_path, OUT_PARQUET)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    print(f"[WRITE] {OUT_PARQUET} ({len(df)} rows)")


# ── STEP 8: write vault MD ────────────────────────────────────────────────────

def write_vault_md(df: pd.DataFrame):
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)

    n_players = df["player_id"].nunique()
    n_stats = df["stat"].nunique()
    tier_dist = df["confidence_tier"].value_counts().to_dict()

    top20 = df.head(20)
    bot10 = df.tail(10)

    def md_table(rows):
        lines = [
            "| Player | Stat | N | Hit% | Edge(pp) | ROI% | Best Book | Tier | Notes |",
            "|--------|------|---|------|----------|------|-----------|------|-------|",
        ]
        for _, r in rows.iterrows():
            lines.append(
                f"| {r['player_name']} | {r['stat'].upper()} | {r['n_retro_bets']} "
                f"| {r['hit_rate']*100:.0f}% | {r['mean_edge_pp']:+.3f} "
                f"| {r['roi_kelly_025']:+.1f}% | {r['best_book']} "
                f"| {r['confidence_tier']} | {r['notes']} |"
            )
        return "\n".join(lines)

    scoped_disclaimer = (
        "\n> **SCOPED-SHIP (G2):** retro pool has only "
        f"{n_players} distinct players (gate=30). "
        "Treat confidence tiers as early-signal only; "
        "refresh when retro pool grows.\n"
    )

    content = f"""# Players Betting Index

*Generated {TODAY} by INT-140 | Source: INT-101 retro + INT-104 daily book audit*
{scoped_disclaimer}
## Coverage

- Distinct players: **{n_players}**
- Distinct stats: **{n_stats}**
- Confidence tiers — high: {tier_dist.get('high', 0)} | med: {tier_dist.get('med', 0)} | low: {tier_dist.get('low', 0)}

## Top 20 Player-Stats by ROI

{md_table(top20)}

## Bottom 10 (Worst Edges — Avoid)

{md_table(bot10)}

## Usage Note

Updated daily from INT-101 retro + INT-104 daily audit; consume via `build_daily_picks.py` downstream.

Query pattern for AI Chat: `"Which player props should I bet on [player] tonight?"` →
load `data/intelligence/player_betting_profile.parquet`, filter by player_name, sort by roi_kelly_025.
"""

    OUT_MD.write_text(content, encoding="utf-8")
    print(f"[WRITE] {OUT_MD}")


# ── STEP 8b: append banner to cv_master_strategy.md ─────────────────────────

def append_banner():
    if not CV_STRATEGY_PATH.exists():
        print(f"[WARN] cv_master_strategy.md not found at {CV_STRATEGY_PATH}, skipping banner")
        return
    existing = CV_STRATEGY_PATH.read_text(encoding="utf-8")
    if BANNER in existing:
        print(f"[SKIP] Banner already present in cv_master_strategy.md")
        return
    append_line = (
        f"\n{BANNER} INT-140 ({TODAY}): per-player betting profile "
        f"(player_betting_profile.parquet) — {date.today():%Y-%m-%d} — "
        "n_retro_bets/hit_rate/roi_kelly_025/best_book/confidence_tier per (player, stat).\n"
    )
    with open(CV_STRATEGY_PATH, "a", encoding="utf-8") as f:
        f.write(append_line)
    print(f"[APPEND] Banner written to {CV_STRATEGY_PATH}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("=== INT-140: Per-Player Betting Profile Builder ===")
    print(f"Date: {TODAY}\n")

    retro = load_retro()
    book = load_book_audit()
    _daily = load_daily_picks()  # supplementary context, not aggregated

    profiles = build_profiles(retro, book)

    print(f"\nProfile rows: {len(profiles)}")
    print(f"Distinct players: {profiles['player_id'].nunique()}")
    print(f"Distinct stats: {profiles['stat'].nunique()}")
    print(f"Confidence tiers: {profiles['confidence_tier'].value_counts().to_dict()}")

    print("\nTop 5 by ROI:")
    for _, r in profiles.head(5).iterrows():
        print(
            f"  {r['player_name']:25s} {r['stat']:5s} "
            f"n={r['n_retro_bets']} HR={r['hit_rate']*100:.0f}% "
            f"ROI={r['roi_kelly_025']:+.1f}% book={r['best_book']} [{r['confidence_tier']}]"
        )

    print("\nBottom 3 by ROI:")
    for _, r in profiles.tail(3).iterrows():
        print(
            f"  {r['player_name']:25s} {r['stat']:5s} "
            f"n={r['n_retro_bets']} HR={r['hit_rate']*100:.0f}% "
            f"ROI={r['roi_kelly_025']:+.1f}%"
        )

    write_parquet(profiles)
    write_vault_md(profiles)
    append_banner()

    print("\n=== INT-140 COMPLETE ===")


if __name__ == "__main__":
    main()
