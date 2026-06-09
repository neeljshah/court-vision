"""
INT-88: Bookmaker Line Consistency Check — SCOPED v1 (DK vs FD only)
Honest two-book head-to-head sharpness.

Limitations documented:
- NO Pinnacle / MGM in data. "Pinnacle is sharp" hypothesis untestable.
- Snapshot proxy for closing line: max(scraped_at) per (game_id, player, prop, book).
  scraped_at is 1-6 hrs pre-tip, NOT true market close.
- benashkar covers Jan 29 – May 10 2026 (~3.5 months). No cross-season stability claim.
- Player-name join loss ~30-50% (name normalization mismatch).
- Two-book head-to-head is zero-sum by construction. "DK sharper" means only "less soft on that stat."
"""

from pathlib import Path
import glob
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent

BENASHKAR_GLOB = str(ROOT / "data/external/historical_lines/benashkar_nba_gambling/data__output__player_props_*.csv")
ITER35_PATH = ROOT / "data/external/historical_lines/_iter35_merged_2025_26.csv"
OUT_PARQUET = ROOT / "data/intelligence/bookmaker_consistency.parquet"
OUT_VAULT = ROOT / "vault/Intelligence/INT-88_Bookmaker_Consistency.md"

PROP_MAP = {
    "points": "pts",
    "rebounds": "reb",
    "assists": "ast",
    "threes": "fg3m",
    "threes_made": "fg3m",
    "steals": "stl",
    "blocks": "blk",
    "turnovers": "tov",
}

BOOK_MAP = {
    "draftkings": "DK",
    "fanduel": "FD",
}

MIN_N_FOR_RANKING = 200


# ---------------------------------------------------------------------------
# 1. Load + concat benashkar
# ---------------------------------------------------------------------------
print("Loading benashkar files...")
files = sorted(glob.glob(BENASHKAR_GLOB))
print(f"  Found {len(files)} CSV files")

raw_chunks = []
for f in files:
    raw_chunks.append(pd.read_csv(f, low_memory=False))
raw = pd.concat(raw_chunks, ignore_index=True)
print(f"  Total rows loaded: {len(raw):,}")

# ---------------------------------------------------------------------------
# 2. Filter: no alt lines, DK/FD only
# ---------------------------------------------------------------------------
raw = raw[raw["is_alt_line"] == False].copy()
print(f"  After is_alt_line==False filter: {len(raw):,}")

raw = raw[raw["sportsbook"].isin(BOOK_MAP)].copy()
print(f"  After DK/FD filter: {len(raw):,}")

# ---------------------------------------------------------------------------
# 3. Normalize prop_type and sportsbook
# ---------------------------------------------------------------------------
raw["stat"] = raw["prop_type"].map(PROP_MAP)
raw = raw[raw["stat"].notna()].copy()  # drop combos / unmapped
print(f"  After prop_type normalization (7 stats): {len(raw):,}")

raw["book"] = raw["sportsbook"].map(BOOK_MAP)

# ---------------------------------------------------------------------------
# 4. Parse scraped_at, snapshot collapse → keep max(scraped_at) per key
# ---------------------------------------------------------------------------
raw["scraped_at"] = pd.to_datetime(raw["scraped_at"], errors="coerce")

key_cols = ["game_id", "player_name", "stat", "book"]
raw_sorted = raw.sort_values("scraped_at")
snapshot = raw_sorted.groupby(key_cols).last().reset_index()
print(f"  After snapshot collapse (max scraped_at per key): {len(snapshot):,}")

# ---------------------------------------------------------------------------
# 5. Pivot wide: keep only rows with BOTH DK and FD lines
# ---------------------------------------------------------------------------
pivot = snapshot.pivot_table(
    index=["game_id", "player_name", "stat", "game_date"],
    columns="book",
    values="line",
    aggfunc="first",
).reset_index()
pivot.columns.name = None

# Only rows where both books present
pivot = pivot.dropna(subset=["DK", "FD"]).copy()
print(f"  Paired rows (both DK+FD present): {len(pivot):,}")

# Spread = DK line minus FD line
pivot["spread"] = pivot["DK"] - pivot["FD"]
pivot["abs_spread"] = pivot["spread"].abs()
pivot["disagree_ge_05"] = pivot["abs_spread"] >= 0.5
pivot["disagree_ge_10"] = pivot["abs_spread"] >= 1.0

# ---------------------------------------------------------------------------
# 6. Join iter35 actuals
# ---------------------------------------------------------------------------
print("Loading iter35 actuals...")
actuals = pd.read_csv(ITER35_PATH)
print(f"  iter35 rows: {len(actuals):,}")

# Normalize player names for join: lowercase, strip
def norm_name(s):
    return s.str.lower().str.strip()

pivot["_pname"] = norm_name(pivot["player_name"])
actuals["_pname"] = norm_name(actuals["player"])
actuals["_stat"] = actuals["stat"].str.lower().str.strip()
pivot["_stat"] = pivot["stat"].str.lower().str.strip()
actuals["_date"] = pd.to_datetime(actuals["date"]).dt.date.astype(str)
# game_date in benashkar is the game date (tip date)
pivot["_date"] = pd.to_datetime(pivot["game_date"]).dt.date.astype(str)

merged = pivot.merge(
    actuals[["_pname", "_stat", "_date", "actual_value"]],
    on=["_pname", "_stat", "_date"],
    how="left",
)
n_joined = merged["actual_value"].notna().sum()
join_rate = n_joined / len(merged)
print(f"  Join to actuals: {n_joined:,}/{len(merged):,} = {join_rate:.1%}")

# Drop temp cols
merged = merged.drop(columns=["_pname", "_stat", "_date"], errors="ignore")

# ---------------------------------------------------------------------------
# 7. Per-pair error metrics
# ---------------------------------------------------------------------------
has_actual = merged["actual_value"].notna()
merged_act = merged[has_actual].copy()

merged_act["dk_abs_error"] = (merged_act["actual_value"] - merged_act["DK"]).abs()
merged_act["fd_abs_error"] = (merged_act["actual_value"] - merged_act["FD"]).abs()
# DK wins if DK is closer to actual
merged_act["dk_wins"] = merged_act["dk_abs_error"] < merged_act["fd_abs_error"]
merged_act["fd_wins"] = merged_act["fd_abs_error"] < merged_act["dk_abs_error"]
# consensus (avg of two books) error
merged_act["consensus_line"] = (merged_act["DK"] + merged_act["FD"]) / 2
merged_act["consensus_abs_error"] = (merged_act["actual_value"] - merged_act["consensus_line"]).abs()

# ---------------------------------------------------------------------------
# 8. Per-stat aggregate (spread sanity + disagree rates)
# ---------------------------------------------------------------------------
print("\n--- Per-stat spread sanity ---")
spread_stats = []
for stat, grp in merged.groupby("stat"):
    n_total = len(grp)
    median_spread = grp["spread"].median()
    pct_ge05 = grp["disagree_ge_05"].mean() * 100
    pct_ge10 = grp["disagree_ge_10"].mean() * 100
    spread_stats.append({
        "stat": stat,
        "n_paired": n_total,
        "median_DK_minus_FD": round(median_spread, 3),
        "pct_disagree_ge_05": round(pct_ge05, 1),
        "pct_disagree_ge_10": round(pct_ge10, 1),
    })
    print(f"  {stat:5s}: n={n_total:5d}  median_spread={median_spread:+.3f}  "
          f"disagree>=0.5: {pct_ge05:.1f}%  >=1.0: {pct_ge10:.1f}%")

spread_df = pd.DataFrame(spread_stats)

# ---------------------------------------------------------------------------
# 9. Per-stat sharpness (head-to-head, requires actuals join)
# ---------------------------------------------------------------------------
print("\n--- Per-stat sharpness (actual required) ---")
sharpness_rows = []
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]

for stat in STATS:
    grp = merged_act[merged_act["stat"] == stat]
    n = len(grp)
    if n < MIN_N_FOR_RANKING:
        status = "INSUFFICIENT_N"
        dk_mae = fd_mae = cons_mae = dk_win_rate = fd_win_rate = float("nan")
        rank_dk = rank_fd = None
    else:
        status = "OK"
        dk_mae = grp["dk_abs_error"].mean()
        fd_mae = grp["fd_abs_error"].mean()
        cons_mae = grp["consensus_abs_error"].mean()
        dk_win_rate = grp["dk_wins"].mean()
        fd_win_rate = grp["fd_wins"].mean()
        if dk_mae < fd_mae:
            rank_dk, rank_fd = 1, 2
            verdict = "DK_SHARPER"
        elif fd_mae < dk_mae:
            rank_dk, rank_fd = 2, 1
            verdict = "FD_SHARPER"
        else:
            rank_dk = rank_fd = 1
            verdict = "TIED"
        # Check if difference is meaningful (>1% relative)
        if abs(dk_mae - fd_mae) / max(dk_mae, fd_mae) < 0.01:
            verdict = "TIED"

    sharpness_rows.append({
        "stat": stat,
        "n": n,
        "dk_mae": round(dk_mae, 4) if not np.isnan(dk_mae) else None,
        "fd_mae": round(fd_mae, 4) if not np.isnan(fd_mae) else None,
        "consensus_mae": round(cons_mae, 4) if not np.isnan(cons_mae) else None,
        "dk_win_rate": round(dk_win_rate, 4) if not np.isnan(dk_win_rate) else None,
        "fd_win_rate": round(fd_win_rate, 4) if not np.isnan(fd_win_rate) else None,
        "rank_dk": rank_dk,
        "rank_fd": rank_fd,
        "status": status,
        "verdict": verdict if status == "OK" else "INSUFFICIENT_N",
    })
    if status == "OK":
        print(f"  {stat:5s}: n={n:4d}  DK_MAE={dk_mae:.4f}  FD_MAE={fd_mae:.4f}  "
              f"DK_winrate={dk_win_rate:.3f}  verdict={verdict}")
    else:
        print(f"  {stat:5s}: n={n:4d}  STATUS=INSUFFICIENT_N")

sharp_df = pd.DataFrame(sharpness_rows)

# ---------------------------------------------------------------------------
# 10. Build output parquet (long format: book × stat)
# ---------------------------------------------------------------------------
out_rows = []
for _, row in sharp_df.iterrows():
    stat = row["stat"]
    # paired n (spread stats)
    spread_row = spread_df[spread_df["stat"] == stat]
    n_paired = int(spread_row["n_paired"].values[0]) if len(spread_row) else 0

    for book, mae_col, win_col, rank_col in [
        ("DK", "dk_mae", "dk_win_rate", "rank_dk"),
        ("FD", "fd_mae", "fd_win_rate", "rank_fd"),
    ]:
        out_rows.append({
            "book": book,
            "stat": stat,
            "n": row["n"],
            "mean_abs_error_vs_actual": row[mae_col],
            "win_rate_vs_other_book": row[win_col],
            "consensus_mae": row["consensus_mae"],
            "rank_within_stat": row[rank_col],
            "verdict": row["verdict"],
            "n_paired_lines": n_paired,
            "data_version": "benashkar_2026-01-29_to_2026-05-10",
            "snapshot_window": "max(scraped_at)_proxy_not_true_close",
            "n_unique_games": merged["game_id"].nunique(),
            "status": row["status"],
        })

out_df = pd.DataFrame(out_rows)
print(f"\nOutput parquet rows: {len(out_df)}")
out_df.to_parquet(OUT_PARQUET, index=False)
print(f"Written: {OUT_PARQUET}")

# ---------------------------------------------------------------------------
# 11. Build vault report
# ---------------------------------------------------------------------------
n_unique_games = merged["game_id"].nunique()
n_total_paired = len(merged)
n_with_actual = n_joined

insuf = [r["stat"] for r in sharpness_rows if r["status"] == "INSUFFICIENT_N"]

verdict_lines = []
for r in sharpness_rows:
    if r["status"] == "INSUFFICIENT_N":
        verdict_lines.append(f"| {r['stat']:5s} | {r['n']:5d} | N/A         | N/A         | N/A             | INSUFFICIENT_N |")
    else:
        verdict_lines.append(
            f"| {r['stat']:5s} | {r['n']:5d} | {r['dk_mae']:.4f}      | {r['fd_mae']:.4f}      | {r['dk_win_rate']:.3f}           | {r['verdict']:15s} |"
        )

spread_lines = []
for r in spread_stats:
    spread_lines.append(
        f"| {r['stat']:5s} | {r['n_paired']:5d} | {r['median_DK_minus_FD']:+.3f}              | {r['pct_disagree_ge_05']:5.1f}%              | {r['pct_disagree_ge_10']:5.1f}%               |"
    )

md = f"""# INT-88 Bookmaker Line Consistency Check — SCOPED v1

**Status:** SCOPED-SHIP
**Date:** 2026-05-29
**Scope:** DraftKings vs FanDuel only (Pinnacle/MGM NOT in available data)
**Data source:** benashkar_nba_gambling (Jan 29 – May 10 2026, {len(files)} snapshot files)
**Actuals source:** _iter35_merged_2025_26.csv

---

## Critical Limitations

- **NO Pinnacle / MGM.** The "Pinnacle is the sharp book" hypothesis is untestable with this data.
- **Snapshot proxy ≠ true closing line.** max(scraped_at) is 1–6 hrs pre-tip, not true market close.
- **3.5-month coverage only** (Jan–May 2026). No cross-season stability claim.
- **Two-book head-to-head is zero-sum.** "DK sharper" means only "less soft vs actual on that stat," not that DK is sharp in any absolute sense.
- **Player-name join loss:** {join_rate:.1%} join rate ({n_with_actual:,}/{n_total_paired:,} paired rows matched to actuals). Unmatched rows excluded from sharpness table.
- **Selection bias:** benashkar covers popular slate days. Thin games under-represented.

---

## Pre-flight Summary

| Metric | Value |
|--------|-------|
| Benashkar CSV files | {len(files)} |
| Raw rows (all books, all lines) | {sum(len(pd.read_csv(f, low_memory=False)) for f in files):,} |
| After is_alt_line==False + DK/FD filter | {len(raw):,} |
| After snapshot collapse | {len(snapshot):,} |
| Paired rows (both DK+FD present) | {n_total_paired:,} |
| Rows with actual_value (joined) | {n_with_actual:,} ({join_rate:.1%}) |
| Unique game_ids in paired set | {n_unique_games:,} |

---

## Spread Sanity Check (all paired rows)

Median DK−FD spread should be near 0 for most stats. If >0.3, snapshot-collapse logic is suspect.

| stat  | n_paired | median_DK_minus_FD | pct_disagree_>=0.5 | pct_disagree_>=1.0 |
|-------|----------|--------------------|--------------------|---------------------|
{chr(10).join(spread_lines)}

---

## DK vs FD Sharpness (rows with actuals only)

Minimum N for ranking: {MIN_N_FOR_RANKING}
Verdict threshold: MAE difference must be >1% relative to be non-TIED.

| stat  | n_act | DK_mean_AE | FD_mean_AE | DK_win_rate     | verdict         |
|-------|-------|------------|------------|-----------------|-----------------|
{chr(10).join(verdict_lines)}

**DK_win_rate** = fraction of head-to-head pairs where |actual − DK| < |actual − FD|.
Consensus MAE (average of both books) is logged in the parquet.

---

## INSUFFICIENT_N Stats

{"None — all 7 stats met the n≥200 threshold." if not insuf else ", ".join(insuf) + " — insufficient paired rows with actuals. Verdicts suppressed."}

---

## Verdict Summary

{"  ".join(f"**{r['stat']}**: {r['verdict']}" for r in sharpness_rows)}

---

## Files Written

- `data/intelligence/bookmaker_consistency.parquet` — long format (book × stat), {len(out_df)} rows
- `scripts/check_bookmaker_consistency.py` — this analysis script
- `vault/Intelligence/INT-88_Bookmaker_Consistency.md` — this report

---

## What This Does NOT Tell Us

1. Whether either book is sharp (no Pinnacle baseline)
2. True closing-line efficiency (snapshot proxy only)
3. Cross-season stability (3.5-month window)
4. Whether line differences represent information or simply different margin structures

The only actionable signal here: if one book consistently sets lines closer to actual outcomes on a specific stat, that stat's line from that book is a marginally better anchor when building consensus lines for prop modeling.
"""

OUT_VAULT.write_text(md, encoding="utf-8")
print(f"Written: {OUT_VAULT}")
print("\nDone. Status: SCOPED-SHIP")
