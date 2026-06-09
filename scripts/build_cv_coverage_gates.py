"""build_cv_coverage_gates.py — INT-53 E1 CV Coverage Gate parquet builder.

Computes per-(player, game) coverage gate scores capturing how many
quality-filtered prior games exist for a player in CV data, then
applies a sigmoid gate to shrink xFG toward a positional prior.

Output: data/intelligence/cv_coverage_gates.parquet

Schema:
  nba_player_id         int64
  game_date             date
  n_prior_cv_games      int32   — quality-filtered strict-before-asof count
  n_prior_cv_games_l30d int32   — same, last-30-day window
  coverage_gate         float32 — sigmoid(n - 5) / 2.5
  coverage_gate_l30d    float32 — sigmoid(n_l30d - 5) / 2.5
  xfg_baseline_prior    float32 — league-avg made_pct by position (frozen ≤ asof)
  xfg_player_raw        float32 — rolling player mean made_pct (strict-before)
  xfg_shrunk_by_coverage float32 — prior + gate × (raw - prior)

Quality filter (INT-39):
  Only games where quality_score > 0.4 AND phantom_slot_flag = False count
  toward n_prior_cv_games. 85% of cv_quality rows lack nba_player_id, so
  the filter is applied at game level when player-level data is unavailable:
  - If player-level quality row exists (game_id + nba_player_id): use it
  - Else: use game-level mean quality_score > 0.4 (no phantom at game level)
  See column mapping note at bottom for INT-39 column names.

Why E1 ≠ INT-39 (cv_quality_per_game) ≠ INT-16 (per_player_confidence):
  INT-39: game-level tracking quality (homography, jersey resolution, phantom)
  INT-16: per-stat coefficient of variation across ALL historical games
  INT-53: temporal coverage depth — how many quality games exist BEFORE today

Usage:
    python scripts/build_cv_coverage_gates.py
    python scripts/build_cv_coverage_gates.py --db data/nba_ai.db --dry-run
"""
from __future__ import annotations

import argparse
import bisect
import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import sqlite3

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DB_PATHS = ["data/nba_ai.db", "data/nba.db", "data/local.db"]
QUALITY_SCORE_THRESHOLD = 0.4  # INT-39 threshold
SIGMOID_MIDPOINT = 5.0         # n=5 → gate=0.50
SIGMOID_SCALE = 2.5            # sharpness
LOOKBACK_DAYS = 30             # recency window

# Column mapping from cv_quality_per_game (INT-39):
#   'quality_score'     — composite tracking quality
#   'phantom_slot_flag' — True = ghost slot (OSNet ghost pattern)
#   'nba_player_id'     — nullable Int64 (417 / 3560 rows have it)
INT39_QUALITY_COL = "quality_score"
INT39_PHANTOM_COL = "phantom_slot_flag"
INT39_PLAYER_COL = "nba_player_id"


def _sigmoid_gate(n: np.ndarray) -> np.ndarray:
    """sigmoid((n - midpoint) / scale). n=0→0.119, n=5→0.50, n=10→0.88."""
    return (1.0 / (1.0 + np.exp(-(n - SIGMOID_MIDPOINT) / SIGMOID_SCALE))).astype(np.float32)


def _load_db(db_path: str | None) -> sqlite3.Connection:
    if db_path and os.path.exists(db_path):
        return sqlite3.connect(db_path)
    for p in DB_PATHS:
        full = ROOT / p
        if full.exists():
            return sqlite3.connect(str(full))
    raise FileNotFoundError(f"No SQLite DB found in {DB_PATHS}")


def _build_game_date_map(cv_game_ids: list[str]) -> dict[str, pd.Timestamp]:
    """Return game_id -> Timestamp for all cv game_ids.

    Primary source: data/rest_travel.parquet (208/241 games).
    Fallback for remaining: linear interpolation from nearest known game_ids
    by numeric sort (NBA game numbering is sequential within a season).
    """
    rt_path = ROOT / "data" / "rest_travel.parquet"
    known: dict[int, pd.Timestamp] = {}
    if rt_path.exists():
        rt = pd.read_parquet(rt_path)
        rt["game_id"] = rt["game_id"].astype(str)
        rt_2526 = rt[rt["game_date"] >= "2025-10-01"]
        for _, row in rt_2526.groupby("game_id")["game_date"].min().items():
            known[int(_)] = pd.Timestamp(row)
        # Also include earlier seasons
        for gid, date in rt.groupby("game_id")["game_date"].min().items():
            k = int(gid)
            if k not in known:
                known[k] = pd.Timestamp(date)

    gid_to_date: dict[str, pd.Timestamp] = {}
    sorted_known = sorted(known.items())
    known_ints = [k for k, _ in sorted_known]
    known_dates = [v for _, v in sorted_known]

    for gid in cv_game_ids:
        gid_int = int(gid)
        if gid_int in known:
            gid_to_date[gid] = known[gid_int]
            continue
        # Interpolate between nearest neighbors
        idx = bisect.bisect_left(known_ints, gid_int)
        if idx == 0:
            gid_to_date[gid] = known_dates[0]
        elif idx >= len(known_ints):
            gid_to_date[gid] = known_dates[-1]
        else:
            lo_int, lo_date = known_ints[idx - 1], known_dates[idx - 1]
            hi_int, hi_date = known_ints[idx], known_dates[idx]
            frac = (gid_int - lo_int) / (hi_int - lo_int)
            delta = (hi_date - lo_date).days
            gid_to_date[gid] = lo_date + pd.Timedelta(days=int(frac * delta))

    return gid_to_date


def _load_quality_flags(cv_game_ids: list[str]) -> pd.DataFrame:
    """Load INT-39 quality data and return player-level and game-level masks.

    Returns DataFrame with columns:
      game_id, nba_player_id (nullable), passes_quality (bool)

    When nba_player_id is available: quality_score > threshold AND not phantom.
    When unavailable: game-level mean quality_score > threshold (phantom
    flag aggregated as game mean phantom_rate < 0.8, i.e. ≥20% valid slots).
    """
    qual_path = ROOT / "data" / "intelligence" / "cv_quality_per_game.parquet"
    if not qual_path.exists():
        # No quality data — treat all as passing
        return pd.DataFrame(columns=["game_id", "nba_player_id", "passes_quality"])

    qual = pd.read_parquet(qual_path)
    qual["game_id"] = qual["game_id"].astype(str)
    qual_in_cv = qual[qual["game_id"].isin(set(cv_game_ids))].copy()

    # Player-level rows (nba_player_id known)
    pl = qual_in_cv[qual_in_cv[INT39_PLAYER_COL].notna()].copy()
    pl["nba_player_id"] = pl[INT39_PLAYER_COL].astype("Int64")
    pl["passes_quality"] = (
        (pl[INT39_QUALITY_COL] > QUALITY_SCORE_THRESHOLD) &
        (~pl[INT39_PHANTOM_COL])
    )
    pl_out = pl[["game_id", "nba_player_id", "passes_quality"]].copy()

    # Game-level summary (used when no player-level row)
    game_qual = qual_in_cv.groupby("game_id").agg(
        mean_quality=(INT39_QUALITY_COL, "mean"),
        phantom_rate=(INT39_PHANTOM_COL, "mean"),
    ).reset_index()
    game_qual["game_passes"] = (
        (game_qual["mean_quality"] > QUALITY_SCORE_THRESHOLD) &
        (game_qual["phantom_rate"] < 0.8)
    )

    return pl_out, game_qual


def _load_position_map() -> dict[int, str]:
    """Return nba_player_id -> broad position (Guard/Forward/Center)."""
    pos_path = ROOT / "data" / "player_positions.parquet"
    if not pos_path.exists():
        return {}
    pp = pd.read_parquet(pos_path)
    pos_map: dict[int, str] = {}
    for _, row in pp.iterrows():
        raw = str(row.get("position", "")).split("-")[0].strip()
        if raw not in ("Guard", "Forward", "Center"):
            raw = "Guard"  # default
        pos_map[int(row["player_id"])] = raw
    return pos_map


def build_coverage_gates(db_path: str | None = None, dry_run: bool = False) -> pd.DataFrame:
    """Build the cv_coverage_gates parquet and return it."""

    # -- 1. Load cv_features from SQLite ---------------------------------
    conn = _load_db(db_path)
    print(f"Loading cv_features from {conn}...")
    cv_raw = pd.read_sql(
        "SELECT game_id, player_id, feature_name, feature_value FROM cv_features",
        conn,
    )
    conn.close()
    print(f"  cv_features rows: {len(cv_raw)}")

    # Pivot to wide
    cv_wide = cv_raw.pivot_table(
        index=["game_id", "player_id"],
        columns="feature_name",
        values="feature_value",
        aggfunc="first",
    ).reset_index()
    cv_wide.columns.name = None
    cv_wide = cv_wide.rename(columns={"player_id": "nba_player_id"})
    cv_wide["nba_player_id"] = cv_wide["nba_player_id"].astype("Int64")
    cv_wide["game_id"] = cv_wide["game_id"].astype(str)

    # xfg_player_raw source: made_pct (FG made / FG tracked per player-game)
    # This is the best available proxy for xFG given Bug 1/ISSUE-022 status.
    # cvb_contested_shot_pct has only 1 non-null row across 252 players.
    xfg_col = "made_pct"
    if xfg_col not in cv_wide.columns:
        # Fallback to contested_shot_rate
        xfg_col = "contested_shot_rate"
    if xfg_col not in cv_wide.columns:
        cv_wide["_xfg_src"] = np.nan
        xfg_col = "_xfg_src"
    print(f"  xfg_player_raw source: '{xfg_col}' "
          f"({cv_wide[xfg_col].notna().sum()} non-null / {len(cv_wide)} rows)")

    # -- 2. Game -> date mapping ------------------------------------------
    all_game_ids = cv_wide["game_id"].unique().tolist()
    print(f"  Building date map for {len(all_game_ids)} game_ids...")
    gid_to_date = _build_game_date_map(all_game_ids)
    cv_wide["game_date"] = cv_wide["game_id"].map(gid_to_date)
    cv_wide["game_date"] = pd.to_datetime(cv_wide["game_date"]).dt.normalize()
    n_missing_dates = cv_wide["game_date"].isna().sum()
    if n_missing_dates:
        print(f"  WARNING: {n_missing_dates} rows have no game_date (dropping)")
        cv_wide = cv_wide[cv_wide["game_date"].notna()].copy()

    # -- 3. Quality filter -----------------------------------------------
    print("  Loading INT-39 quality flags...")
    pl_quality, game_quality = _load_quality_flags(all_game_ids)

    # Build (game_id, nba_player_id) -> passes_quality dict
    player_qual_map: dict[tuple, bool] = {}
    for _, row in pl_quality.iterrows():
        player_qual_map[(row["game_id"], int(row["nba_player_id"]))] = bool(row["passes_quality"])

    # Game-level fallback map
    game_qual_map: dict[str, bool] = dict(
        zip(game_quality["game_id"], game_quality["game_passes"])
    )

    def _passes_quality(row) -> bool:
        gid = row["game_id"]
        pid = int(row["nba_player_id"]) if pd.notna(row["nba_player_id"]) else None
        if pid and (gid, pid) in player_qual_map:
            return player_qual_map[(gid, pid)]
        return game_qual_map.get(gid, True)  # default: pass if game not in quality table

    cv_wide["passes_quality"] = cv_wide.apply(_passes_quality, axis=1)
    print(f"  Quality filter: {cv_wide['passes_quality'].sum()}/{len(cv_wide)} rows pass")

    # -- 4. Sort by (player, date) for bisect prior-count computation ----
    cv_sorted = cv_wide.sort_values(["nba_player_id", "game_date"]).reset_index(drop=True)

    # Build per-player lookup structures for O(log n) bisect
    # For each player: sorted list of (game_date, passes_quality) tuples
    from collections import defaultdict
    player_game_dates: dict[int, list] = defaultdict(list)  # sorted dates (all games)
    player_qual_dates: dict[int, list] = defaultdict(list)  # sorted dates (quality-pass only)

    for _, row in cv_sorted.iterrows():
        pid = int(row["nba_player_id"]) if pd.notna(row["nba_player_id"]) else -1
        dt = row["game_date"]
        player_game_dates[pid].append(dt)
        if row["passes_quality"]:
            player_qual_dates[pid].append(dt)

    # Sort (should already be sorted but ensure)
    for pid in player_game_dates:
        player_game_dates[pid].sort()
    for pid in player_qual_dates:
        player_qual_dates[pid].sort()

    # -- 5. Compute n_prior_cv_games per row via bisect ------------------
    print("  Computing n_prior_cv_games via bisect...")
    n_prior = []
    n_prior_l30d = []
    for _, row in cv_sorted.iterrows():
        pid = int(row["nba_player_id"]) if pd.notna(row["nba_player_id"]) else -1
        dt = row["game_date"]
        qdates = player_qual_dates.get(pid, [])
        # Strict-before: bisect_left gives count < dt
        n = bisect.bisect_left(qdates, dt)
        n_prior.append(n)
        # 30-day window: count quality games in [dt - 30d, dt)
        lo = dt - pd.Timedelta(days=LOOKBACK_DAYS)
        n_lo = bisect.bisect_left(qdates, lo)
        n_hi = bisect.bisect_left(qdates, dt)
        n_prior_l30d.append(n_hi - n_lo)

    cv_sorted["n_prior_cv_games"] = np.array(n_prior, dtype=np.int32)
    cv_sorted["n_prior_cv_games_l30d"] = np.array(n_prior_l30d, dtype=np.int32)

    # -- 6. Gate sigmoid -------------------------------------------------
    cv_sorted["coverage_gate"] = _sigmoid_gate(cv_sorted["n_prior_cv_games"].values)
    cv_sorted["coverage_gate_l30d"] = _sigmoid_gate(cv_sorted["n_prior_cv_games_l30d"].values)

    # -- 7. xfg_baseline_prior (positional league average) ---------------
    pos_map = _load_position_map()

    # League-average made_pct from quality-pass games, frozen at each date
    # Use expanding mean over time (re-compute once per unique date)
    cv_quality_pass = cv_sorted[cv_sorted["passes_quality"]].copy()
    cv_quality_pass["position"] = cv_quality_pass["nba_player_id"].apply(
        lambda p: pos_map.get(int(p) if pd.notna(p) else -1, "Guard")
    )
    # Sort by date for expanding mean
    cv_quality_pass = cv_quality_pass.sort_values("game_date")
    cv_quality_pass[xfg_col] = pd.to_numeric(cv_quality_pass[xfg_col], errors="coerce")

    # Build cumulative position means: for each position, for each date,
    # what was the mean made_pct of all prior quality games?
    # Simple approach: per position, compute expanding mean over sorted dates
    pos_prior_by_date: dict[str, dict] = {}  # position -> {date -> prior_mean}
    for pos, grp in cv_quality_pass.groupby("position"):
        grp_s = grp.sort_values("game_date")
        vals = grp_s[xfg_col].values.astype(float)
        dates = grp_s["game_date"].values
        # Expanding mean (for each row i, mean of vals[:i], strictly before)
        cumsum = np.cumsum(np.where(np.isnan(vals), 0, vals))
        cumcount = np.cumsum(~np.isnan(vals))
        # prior at index i = cumsum[i-1] / cumcount[i-1]
        prior_mean = np.full(len(vals), np.nan)
        for i in range(1, len(vals)):
            if cumcount[i - 1] > 0:
                prior_mean[i] = cumsum[i - 1] / cumcount[i - 1]
        pos_grp_df = pd.DataFrame({"game_date": dates, "prior_mean": prior_mean})
        pos_prior_by_date[pos] = dict(zip(pos_grp_df["game_date"], pos_grp_df["prior_mean"]))

    # Global fallback prior (all positions)
    global_expanding = cv_quality_pass.sort_values("game_date")
    gv = pd.to_numeric(global_expanding[xfg_col], errors="coerce").values
    gc = np.cumsum(~np.isnan(gv))
    gs = np.cumsum(np.where(np.isnan(gv), 0, gv))
    global_prior_by_date: dict = {}
    for i, dt in enumerate(global_expanding["game_date"].values):
        if i > 0 and gc[i - 1] > 0:
            global_prior_by_date[dt] = gs[i - 1] / gc[i - 1]
        else:
            global_prior_by_date[dt] = np.nan

    def _xfg_prior(row) -> float:
        pid = int(row["nba_player_id"]) if pd.notna(row["nba_player_id"]) else -1
        pos = pos_map.get(pid, "Guard")
        dt = row["game_date"]
        # Look up closest prior date in position map
        prior = pos_prior_by_date.get(pos, {}).get(dt)
        if prior is None or np.isnan(prior):
            prior = global_prior_by_date.get(dt)
        if prior is None or (hasattr(prior, '__float__') and np.isnan(float(prior))):
            return 0.286  # empirical mean from full dataset
        return float(prior)

    print("  Computing xfg_baseline_prior (positional expanding mean)...")
    cv_sorted["position"] = cv_sorted["nba_player_id"].apply(
        lambda p: pos_map.get(int(p) if pd.notna(p) else -1, "Guard")
    )
    cv_sorted["xfg_baseline_prior"] = cv_sorted.apply(_xfg_prior, axis=1)

    # -- 8. xfg_player_raw (rolling player mean, strict-before) ----------
    print("  Computing xfg_player_raw (rolling player mean)...")
    cv_sorted_xfg = cv_sorted.copy()
    cv_sorted_xfg[xfg_col] = pd.to_numeric(cv_sorted_xfg[xfg_col], errors="coerce")

    # Per-player, per-row: mean of all prior quality-pass made_pct values
    player_xfg_vals: dict[int, list] = defaultdict(list)  # list of (date, value)
    xfg_player_raw_col = []

    for _, row in cv_sorted_xfg.iterrows():
        pid = int(row["nba_player_id"]) if pd.notna(row["nba_player_id"]) else -1
        dt = row["game_date"]
        hist = player_xfg_vals[pid]  # sorted by date (appended in order)
        if hist:
            prior_vals = [v for d, v in hist if d < dt]
            xfg_player_raw_col.append(np.nanmean(prior_vals) if prior_vals else np.nan)
        else:
            xfg_player_raw_col.append(np.nan)
        # Only append if this game passes quality
        if row["passes_quality"] and not np.isnan(float(row[xfg_col]) if pd.notna(row[xfg_col]) else np.nan):
            player_xfg_vals[pid].append((dt, float(row[xfg_col])))

    cv_sorted["xfg_player_raw"] = np.array(
        [float(x) if x is not None and not (isinstance(x, float) and np.isnan(x)) else np.nan
         for x in xfg_player_raw_col],
        dtype=np.float32
    )

    # -- 9. xfg_shrunk_by_coverage = prior + gate × (raw - prior) --------
    gate = cv_sorted["coverage_gate"].values.astype(float)
    raw = cv_sorted["xfg_player_raw"].values.astype(float)
    prior = cv_sorted["xfg_baseline_prior"].values.astype(float)
    # Where raw is NaN, use the prior alone (gate=0 fallback)
    raw_filled = np.where(np.isnan(raw), prior, raw)
    cv_sorted["xfg_shrunk_by_coverage"] = (prior + gate * (raw_filled - prior)).astype(np.float32)

    # -- 10. Assemble output schema --------------------------------------
    out_cols = [
        "nba_player_id", "game_date",
        "n_prior_cv_games", "n_prior_cv_games_l30d",
        "coverage_gate", "coverage_gate_l30d",
        "xfg_baseline_prior", "xfg_player_raw", "xfg_shrunk_by_coverage",
    ]
    out = cv_sorted[out_cols].copy()
    out["nba_player_id"] = out["nba_player_id"].astype("Int64")
    out["game_date"] = pd.to_datetime(out["game_date"]).dt.date
    out["n_prior_cv_games"] = out["n_prior_cv_games"].astype("int32")
    out["n_prior_cv_games_l30d"] = out["n_prior_cv_games_l30d"].astype("int32")
    out["coverage_gate"] = out["coverage_gate"].astype("float32")
    out["coverage_gate_l30d"] = out["coverage_gate_l30d"].astype("float32")
    out["xfg_baseline_prior"] = out["xfg_baseline_prior"].astype("float32")
    out["xfg_player_raw"] = out["xfg_player_raw"].astype("float32")
    out["xfg_shrunk_by_coverage"] = out["xfg_shrunk_by_coverage"].astype("float32")

    # -- 11. Print distribution summary ---------------------------------
    n_total = len(out)
    n_gt05 = (out["coverage_gate"] > 0.5).sum()
    n_gt07 = (out["coverage_gate"] > 0.7).sum()
    n_gt09 = (out["coverage_gate"] > 0.9).sum()
    print(f"\n=== Coverage Gate Distribution ===")
    print(f"  Total (player, game) rows : {n_total}")
    print(f"  gate > 0.5 (n_prior >= 5) : {n_gt05} ({100*n_gt05/n_total:.1f}%)")
    print(f"  gate > 0.7 (n_prior ~  7) : {n_gt07} ({100*n_gt07/n_total:.1f}%)")
    print(f"  gate > 0.9 (n_prior ~ 11): {n_gt09} ({100*n_gt09/n_total:.1f}%)")
    print(f"  n_prior_cv_games stats:")
    print(f"    {out['n_prior_cv_games'].describe().to_dict()}")
    print(f"  xfg_player_raw non-null  : {out['xfg_player_raw'].notna().sum()} ({100*out['xfg_player_raw'].notna().mean():.1f}%)")
    print(f"  xfg_baseline_prior range : [{out['xfg_baseline_prior'].min():.3f}, {out['xfg_baseline_prior'].max():.3f}]")

    # -- 12. Write output ------------------------------------------------
    out_path = ROOT / "data" / "intelligence" / "cv_coverage_gates.parquet"
    if not dry_run:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(out_path, index=False)
        print(f"\nWrote {out_path} ({len(out)} rows)")
    else:
        print(f"\nDRY RUN — would write {out_path} ({len(out)} rows)")

    return out


# ---------------------------------------------------------------------------
# INT-39 column name mapping documentation
# ---------------------------------------------------------------------------
# cv_quality_per_game (data/intelligence/cv_quality_per_game.parquet):
#   'quality_score'     → composite = mean(homography_valid_rate,
#                          jersey_resolution_rate, tracking_density)
#   'phantom_slot_flag' → True = ghost slot (OSNet tight-broadcast pattern)
#   'nba_player_id'     → nullable Int64; only 417/3560 rows resolved
#
# E1 applies:  quality_score > 0.4 AND phantom_slot_flag = False
# (quality_score > 0.4 filters nothing in practice — min=0.40 in INT-39;
#  phantom_slot_flag is the operative filter at game level when pid missing)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="SQLite DB path override")
    parser.add_argument("--dry-run", action="store_true", help="Skip writing parquet")
    args = parser.parse_args()
    build_coverage_gates(db_path=args.db, dry_run=args.dry_run)
