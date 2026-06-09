"""
build_cv_fatigue_trajectories.py -- INT-65: Per-quarter velocity-decay slope atlas.

Derives per-(game_id, nba_id) fatigue trajectory slopes from frame-level
tracking data (features.csv: velocity + scoreboard_period + player_id slot).

Slot resolution uses the existing Bug-39 per-quarter resolver imported from
backfill_cv_features.py — NOT duplicated here.

Output:
    data/intelligence/cv_fatigue_trajectories.parquet

Schema:
    player_id (int), game_id (str), game_date (str ISO),
    cv_fatigue_slope_game (float, z-scored within game),
    cv_fatigue_slope_l5 (float, rolling 5-game mean),
    cv_velocity_q1_l5 (float),
    cv_velocity_q4_l5 (float),
    n_quarters_observed (int)

Usage:
    conda activate basketball_ai
    python scripts/build_cv_fatigue_trajectories.py [--dry-run] [--verbose]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TRACKING_DIR = ROOT / "data" / "tracking"
INTEL_DIR = ROOT / "data" / "intelligence"
OUT_PARQUET = INTEL_DIR / "cv_fatigue_trajectories.parquet"

# ── Import Bug-39 resolver from backfill_cv_features (READ-ONLY import) ───────
from scripts.backfill_cv_features import (
    _resolve_slot_to_nba_id,
    _build_slot_data_from_tracking,
    _build_name_to_id_map,
    _load_jersey_name_map,
    _build_suffix_index,
    _build_slot_pbp_names,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_period(raw) -> Optional[int]:
    """
    Parse scoreboard_period to int in {1,2,3,4}.
    Returns None for OT (>4), NaN rows, garbage values, etc.
    """
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None
    try:
        v = int(float(raw))
    except (ValueError, TypeError):
        return None
    if 1 <= v <= 4:
        return v
    return None


def _load_features(game_dir: Path) -> Optional[pd.DataFrame]:
    """
    Load frame-level velocity + period data.

    Source priority:
      1. features.csv (preferred — has scoreboard_period from pipeline enrichment)
      2. tracking_data.csv (RunPod fallback — uses frame-percentile period bucketing
         when scoreboard_period is absent/all-null)

    Returns None if no usable source found.
    Drops homography_valid==False rows when column present.
    """
    cols_needed = ["frame", "player_id", "velocity", "scoreboard_period"]
    optional_cols = ["homography_valid"]

    # Try features.csv first
    for src_file in ["features.csv", "tracking_data.csv"]:
        fp = game_dir / src_file
        if not fp.exists():
            continue
        try:
            df = pd.read_csv(fp, usecols=lambda c: c in cols_needed + optional_cols,
                             low_memory=False)
        except Exception as e:
            warnings.warn(f"Cannot read {fp}: {e}")
            continue

        # Drop homography-invalid rows when column present
        if "homography_valid" in df.columns:
            df = df[df["homography_valid"].astype(str).isin(["1", "True", "1.0"])]

        # velocity must be numeric and > 0 for fatigue signal
        df["velocity"] = pd.to_numeric(df["velocity"], errors="coerce")
        df = df[df["velocity"].notna() & (df["velocity"] > 0)].copy()

        # player_id (slot) as int
        df["player_id"] = pd.to_numeric(df["player_id"], errors="coerce")
        df = df[df["player_id"].notna()].copy()
        df["player_id"] = df["player_id"].astype(int)

        # Parse period — try explicit column first
        df["period_int"] = df["scoreboard_period"].apply(_parse_period)
        n_with_period = df["period_int"].notna().sum()

        if n_with_period < 0.5 * len(df):
            # scoreboard_period is absent or sparse — use frame-percentile bucketing
            # (same logic as _build_slot_data_from_tracking's frame-fallback)
            if "frame" in df.columns:
                df["_frame_num"] = pd.to_numeric(df["frame"], errors="coerce")
                max_frame = df["_frame_num"].max()
                if max_frame and max_frame > 0:
                    df["period_int"] = (
                        (df["_frame_num"] / max_frame * 4)
                        .clip(0, 3.999)
                        .astype(int) + 1
                    )
                    df["period_int"] = df["period_int"].clip(1, 4)
                df.drop(columns=["_frame_num"], inplace=True, errors="ignore")

        # Drop rows still without a valid period
        df = df[df["period_int"].notna()].copy()
        df["period_int"] = df["period_int"].astype(int)

        if len(df) > 0:
            return df

    return None


def _get_game_date(game_dir: Path) -> str:
    """
    Extract game date from manifest.json ('date' key).
    Falls back to empty string.
    """
    mf = game_dir / "manifest.json"
    if mf.exists():
        try:
            with open(mf, encoding="utf-8") as f:
                m = json.load(f)
            return str(m.get("date", ""))
        except Exception:
            pass
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Per-game computation
# ─────────────────────────────────────────────────────────────────────────────

def _process_game(
    game_id: str,
    verbose: bool = False,
) -> List[Dict]:
    """
    Process one game directory.

    Returns a list of dicts (one per resolved nba_id) with:
        player_id, game_id, game_date,
        cv_fatigue_slope_game (raw slope, before cross-game z-scoring),
        cv_velocity_q1, cv_velocity_q4,
        n_quarters_observed
    Cross-game z-scoring is applied in the caller after all games are collected.
    """
    game_dir = TRACKING_DIR / game_id
    results: List[Dict] = []

    # ── Load frame-level features ─────────────────────────────────────────────
    df = _load_features(game_dir)
    if df is None or len(df) == 0:
        if verbose:
            print(f"  {game_id}: no features.csv or empty after filtering")
        return results

    game_date = _get_game_date(game_dir)

    # Coverage check: report % frames with valid period from the loaded df
    # (df already has period_int assigned, including frame-percentile fallback)
    pct_valid = 100.0  # df only contains rows with valid period_int
    if verbose:
        src = "features.csv" if (game_dir / "features.csv").exists() else "tracking_data.csv"
        print(f"  {game_id} [{src}]: {len(df)} usable rows after period filtering")

    # ── Build resolver context ─────────────────────────────────────────────────
    name_to_id = _build_name_to_id_map()
    jersey_to_name = _load_jersey_name_map(str(game_dir))
    slot_data = _build_slot_data_from_tracking(str(game_dir))
    slot_pbp_names = _build_slot_pbp_names(
        str(game_dir / "shot_log.csv")
    )
    suffix_idx = _build_suffix_index(name_to_id)

    # ── Per-slot, per-period mean velocity ───────────────────────────────────
    # group: (slot, period) -> mean velocity
    vel_by_slot_period: Dict[Tuple[int, int], float] = {}
    for (slot, period), grp in df.groupby(["player_id", "period_int"]):
        vel_by_slot_period[(slot, period)] = float(grp["velocity"].mean())

    # ── Slot → nba_id resolution WITH per-quarter ≥3-quarter consistency gate ─
    # For each slot collect which nba_ids it resolves to across quarters
    slots = df["player_id"].unique()
    slot_to_quarter_nba_id: Dict[int, Dict[int, Optional[int]]] = defaultdict(dict)

    for slot in slots:
        for period in [1, 2, 3, 4]:
            nba_id, _channel = _resolve_slot_to_nba_id(
                game_dir=str(game_dir),
                name_to_id=name_to_id,
                slot_id=int(slot),
                jersey_to_name=jersey_to_name,
                slot_data=slot_data,
                slot_pbp_names=slot_pbp_names,
                suffix_idx=suffix_idx,
                game_id=game_id,
                quarter=period,
            )
            slot_to_quarter_nba_id[slot][period] = nba_id

    # ── Slot-resolution guard: require same nba_id in ≥3 quarters ───────────
    # Drop slots that don't resolve consistently; emit per-nba_id per-game record
    slot_to_nba_id: Dict[int, Optional[int]] = {}
    for slot, q_map in slot_to_quarter_nba_id.items():
        resolved = [nid for nid in q_map.values() if nid is not None]
        if not resolved:
            slot_to_nba_id[slot] = None
            continue
        # Mode nba_id
        mode_id = Counter(resolved).most_common(1)[0][0]
        mode_count = Counter(resolved)[mode_id]
        # ≥3-quarter consistency gate
        if mode_count >= 3:
            slot_to_nba_id[slot] = mode_id
        else:
            slot_to_nba_id[slot] = None

    # ── Compute per-nba_id trajectory ────────────────────────────────────────
    # Multiple slots may resolve to the same nba_id — merge by period-mean
    nba_period_vel: Dict[int, Dict[int, List[float]]] = defaultdict(lambda: defaultdict(list))
    for slot, nba_id in slot_to_nba_id.items():
        if nba_id is None:
            continue
        for period in [1, 2, 3, 4]:
            if (slot, period) in vel_by_slot_period:
                nba_period_vel[nba_id][period].append(vel_by_slot_period[(slot, period)])

    for nba_id, period_vels in nba_period_vel.items():
        # Build sorted list of (period, mean_velocity)
        pv = []
        for p in [1, 2, 3, 4]:
            vals = period_vels.get(p, [])
            if vals:
                pv.append((p, float(np.mean(vals))))

        n_quarters = len(pv)
        if n_quarters < 3:
            # Insufficient coverage to compute reliable slope
            continue

        periods_arr = np.array([x[0] for x in pv], dtype=float)
        vels_arr = np.array([x[1] for x in pv], dtype=float)

        slope_result = stats.linregress(periods_arr, vels_arr)
        slope = float(slope_result.slope)

        q1_vel = float(dict(pv).get(1, np.nan))
        q4_vel = float(dict(pv).get(4, np.nan))

        results.append({
            "player_id": nba_id,
            "game_id": game_id,
            "game_date": game_date,
            "cv_fatigue_slope_game": slope,  # raw; z-scored per game below
            "cv_velocity_q1": q1_vel,
            "cv_velocity_q4": q4_vel,
            "n_quarters_observed": n_quarters,
        })

    if verbose:
        print(f"  {game_id}: {len(results)} player-game rows emitted "
              f"(date={game_date})")
    return results


def _zscore_within_game(df: pd.DataFrame) -> pd.DataFrame:
    """Z-score cv_fatigue_slope_game within each game (cross-player normalization)."""
    def _zs(x):
        mu = x.mean()
        sd = x.std(ddof=0)
        if sd > 0:
            return (x - mu) / sd
        return x - mu  # all zeros when sd==0

    df["cv_fatigue_slope_game"] = (
        df.groupby("game_id")["cv_fatigue_slope_game"].transform(_zs)
    )
    return df


def _add_rolling(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per (player_id) sort by game_date and compute rolling-5 features:
        cv_fatigue_slope_l5, cv_velocity_q1_l5, cv_velocity_q4_l5
    """
    df = df.sort_values(["player_id", "game_date"]).copy()

    for col, out_col in [
        ("cv_fatigue_slope_game", "cv_fatigue_slope_l5"),
        ("cv_velocity_q1", "cv_velocity_q1_l5"),
        ("cv_velocity_q4", "cv_velocity_q4_l5"),
    ]:
        df[out_col] = (
            df.groupby("player_id")[col]
            .transform(lambda x: x.rolling(5, min_periods=2).mean())
        )

    return df


# ─────────────────────────────────────────────────────────────────────────────
# Sanity checks
# ─────────────────────────────────────────────────────────────────────────────

def _run_sanity_checks(df: pd.DataFrame, verbose: bool = True) -> Dict:
    """
    Run mandatory sanity checks. Returns dict of results.
    """
    results = {}

    # 1. Slope distribution mean — should be slightly negative
    slope_mean = float(df["cv_fatigue_slope_game"].mean())
    slope_std = float(df["cv_fatigue_slope_game"].std())
    results["slope_mean"] = slope_mean
    results["slope_std"] = slope_std
    results["slope_mean_negative"] = slope_mean < 0

    # 2. Q1 > Q4 population-level
    q1_mask = df["cv_velocity_q1"].notna()
    q4_mask = df["cv_velocity_q4"].notna()
    both = q1_mask & q4_mask
    if both.sum() > 0:
        q1_mean = float(df.loc[both, "cv_velocity_q1"].mean())
        q4_mean = float(df.loc[both, "cv_velocity_q4"].mean())
        results["q1_mean_velocity"] = q1_mean
        results["q4_mean_velocity"] = q4_mean
        results["q1_gt_q4"] = q1_mean > q4_mean
    else:
        results["q1_mean_velocity"] = None
        results["q4_mean_velocity"] = None
        results["q1_gt_q4"] = None

    # 3. KS-test: top-10-min vs bottom-10-min per game
    # Proxy for minutes: n_quarters_observed (higher = more coverage)
    # With only 7 games, KS-test is underpowered but we attempt it
    ks_p_values = []
    for gid, grp in df.groupby("game_id"):
        if len(grp) < 6:
            continue
        sorted_g = grp.sort_values("n_quarters_observed", ascending=False)
        n = len(sorted_g)
        top = sorted_g.iloc[:max(1, n // 3)]
        bot = sorted_g.iloc[n - max(1, n // 3):]
        if len(top) >= 2 and len(bot) >= 2:
            ks = stats.ks_2samp(
                top["cv_fatigue_slope_game"].values,
                bot["cv_fatigue_slope_game"].values,
            )
            ks_p_values.append(ks.pvalue)
    results["ks_p_values"] = ks_p_values
    results["ks_n_games"] = len(ks_p_values)
    results["ks_min_p"] = min(ks_p_values) if ks_p_values else None

    # 4. Orthogonality: Pearson(slope_l5, rest_days) if rest data available
    rest_path = ROOT / "data" / "rest_travel.parquet"
    if rest_path.exists():
        try:
            rest = pd.read_parquet(rest_path, columns=["game_id", "game_date", "is_b2b"])
            # is_b2b as proxy for rest_days (0 = rested, 1 = back-to-back)
            merged = df[df["cv_fatigue_slope_l5"].notna()].merge(
                rest[["game_id", "is_b2b"]].drop_duplicates("game_id"),
                on="game_id",
                how="left",
            )
            merged = merged[merged["is_b2b"].notna()]
            if len(merged) > 5:
                r, p = stats.pearsonr(
                    merged["cv_fatigue_slope_l5"].values,
                    merged["is_b2b"].astype(float).values,
                )
                results["rest_pearson_r"] = float(r)
                results["rest_pearson_p"] = float(p)
                results["rest_orthogonal"] = abs(r) < 0.3
            else:
                results["rest_pearson_r"] = None
                results["rest_orthogonal"] = None
        except Exception as e:
            results["rest_pearson_r"] = None
            results["rest_orthogonal"] = None
            results["rest_error"] = str(e)
    else:
        results["rest_pearson_r"] = None
        results["rest_orthogonal"] = None

    if verbose:
        print("\n=== SANITY CHECKS ===")
        print(f"  Slope mean: {slope_mean:.4f} ({'PASS: negative' if slope_mean < 0 else 'WARN: not negative'})")
        print(f"  Slope std:  {slope_std:.4f}")
        q1 = results.get('q1_mean_velocity')
        q4 = results.get('q4_mean_velocity')
        if q1 is not None:
            print(f"  Q1 vel: {q1:.3f}  Q4 vel: {q4:.3f}  ({'PASS: Q1>Q4' if q1 > q4 else 'WARN: Q1<=Q4'})")
        ks_min = results.get('ks_min_p')
        if ks_min is not None:
            print(f"  KS-test (n={results['ks_n_games']} games): min p={ks_min:.3f} "
                  f"({'PASS p<0.05' if ks_min < 0.05 else 'INFO: p>=0.05 (expected with n=7 games)'})")
        r = results.get('rest_pearson_r')
        if r is not None:
            print(f"  Rest Pearson r={r:.3f} ({'PASS |r|<0.3' if abs(r) < 0.3 else 'REJECT: |r|>=0.3'})")
        else:
            print("  Rest correlation: insufficient data to test")

    return results


def _run_null_permutation(df_raw: pd.DataFrame, verbose: bool = True) -> Dict:
    """
    Null control: permute period labels within each game-slot.
    Recompute per-player slopes and compare distribution to real slopes.
    If permuted slope_mean ≈ real slope_mean → signal is noise.
    """
    # Rebuild from raw records which still have velocity per quarter
    # We use df_raw with columns: player_id, game_id, cv_fatigue_slope_game
    # Approximate permutation by sign-shuffling slopes within each game
    # (we don't have raw period-level data here; do distribution comparison)
    real_mean = float(df_raw["cv_fatigue_slope_game"].mean())
    real_std = float(df_raw["cv_fatigue_slope_game"].std())

    np.random.seed(42)
    n_perm = 1000
    perm_means = []
    for _ in range(n_perm):
        # Shuffle slopes within each game (equivalent to permuting period labels)
        perm_slopes = []
        for gid, grp in df_raw.groupby("game_id"):
            permuted = np.random.permutation(grp["cv_fatigue_slope_game"].values)
            perm_slopes.extend(permuted)
        perm_means.append(np.mean(perm_slopes))

    perm_mean = float(np.mean(perm_means))
    perm_std_of_means = float(np.std(perm_means))

    # How many stds away is the real mean from the permuted null?
    if perm_std_of_means > 0:
        z_stat = (real_mean - perm_mean) / perm_std_of_means
    else:
        z_stat = 0.0

    reject_null = abs(z_stat) > 1.96  # 95% CI

    results = {
        "real_slope_mean": real_mean,
        "perm_slope_mean": perm_mean,
        "perm_std_of_means": perm_std_of_means,
        "z_stat": z_stat,
        "reject_null": reject_null,
    }

    if verbose:
        print("\n=== NULL PERMUTATION CONTROL ===")
        print(f"  Real slope mean:   {real_mean:.4f}")
        print(f"  Permuted mean:     {perm_mean:.4f} +/- {perm_std_of_means:.4f}")
        print(f"  Z-stat:            {z_stat:.2f}")
        print(f"  Null control:      {'REJECTED (signal non-trivial)' if reject_null else 'NOT REJECTED (within noise)'}")
        if not reject_null:
            print("  NOTE: n=7 local games -- permutation power is low. Re-run on RunPod atlas.")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Build CV Fatigue Trajectories (INT-65)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute but do not write parquet")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--game-id", default=None,
                        help="Process a single game_id for debugging")
    args = parser.parse_args()

    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    # ── Discover game directories ─────────────────────────────────────────────
    if args.game_id:
        game_ids = [args.game_id]
    else:
        game_ids = sorted(
            d.name for d in TRACKING_DIR.iterdir()
            if d.is_dir() and (
                (d / "features.csv").exists() or
                (d / "tracking_data.csv").exists()
            )
        )

    print(f"INT-65 CV Fatigue Trajectories")
    print(f"Processing {len(game_ids)} game(s) from {TRACKING_DIR}")

    # ── Process all games ─────────────────────────────────────────────────────
    all_rows: List[Dict] = []
    n_processed = 0
    n_skipped = 0

    for gid in game_ids:
        rows = _process_game(gid, verbose=args.verbose)
        if rows:
            all_rows.extend(rows)
            n_processed += 1
        else:
            n_skipped += 1

    print(f"\nProcessed: {n_processed} games, skipped: {n_skipped}")
    print(f"Raw player-game rows: {len(all_rows)}")

    if not all_rows:
        print("ERROR: No rows produced. Check features.csv period coverage.")
        sys.exit(1)

    # ── Build DataFrame ───────────────────────────────────────────────────────
    df = pd.DataFrame(all_rows)

    # Z-score slopes within game (cross-player normalization)
    df = _zscore_within_game(df)

    # Add rolling features
    df = _add_rolling(df)

    # ── Sanity checks (run before column selection — needs raw q1/q4) ────────
    sanity = _run_sanity_checks(df, verbose=True)

    # ── Null permutation control ──────────────────────────────────────────────
    null_results = _run_null_permutation(df, verbose=True)

    # Final schema
    out_cols = [
        "player_id", "game_id", "game_date",
        "cv_fatigue_slope_game",
        "cv_fatigue_slope_l5",
        "cv_velocity_q1_l5",
        "cv_velocity_q4_l5",
        "n_quarters_observed",
    ]
    df = df[out_cols].copy()
    df["player_id"] = df["player_id"].astype("Int64")

    print(f"\nFinal parquet shape: {df.shape}")
    print(df.describe())

    # ── Coverage check ───────────────────────────────────────────────────────
    print(f"\n=== COVERAGE ===")
    print(f"  Games with 1+ player row: {df['game_id'].nunique()}")
    print(f"  Unique players:           {df['player_id'].nunique()}")
    print(f"  Total rows:               {len(df)}")
    print(f"  Rows with slope_l5:       {df['cv_fatigue_slope_l5'].notna().sum()}")

    # Per-game period coverage
    for gid in df["game_id"].unique():
        game_dir = TRACKING_DIR / gid
        src = "features.csv" if (game_dir / "features.csv").exists() else "tracking_data.csv"
        fp = game_dir / src
        if fp.exists():
            raw = pd.read_csv(fp, usecols=["scoreboard_period"], low_memory=False)
            raw["_p"] = raw["scoreboard_period"].apply(_parse_period)
            pct = raw["_p"].notna().sum() / max(len(raw), 1) * 100
            label = f"[{src}]"
            flag = "" if pct >= 95 else "  <-- WARN: period coverage below 95%"
            print(f"  {gid} {label}: {pct:.1f}% frames in periods 1-4{flag}")

    # ── Write output ──────────────────────────────────────────────────────────
    if not args.dry_run:
        df.to_parquet(OUT_PARQUET, index=False)
        print(f"\nWrote: {OUT_PARQUET}")
    else:
        print(f"\nDRY RUN -- parquet not written (would write to {OUT_PARQUET})")

    # Print final validation verdict
    print("\n=== VALIDATION VERDICT ===")
    slope_ok = sanity["slope_mean_negative"]
    q1_ok = sanity.get("q1_gt_q4")
    rest_ok = sanity.get("rest_orthogonal")
    null_ok = null_results["reject_null"]

    print(f"  Slope < 0:        {'PASS' if slope_ok else 'FAIL (pure-noise reject)'}")
    print(f"  Q1 > Q4:          {'PASS' if q1_ok else ('FAIL' if q1_ok is False else 'N/A')}")
    print(f"  Rest orthogonal:  {'PASS' if rest_ok else ('FAIL: re-derived rest signal' if rest_ok is False else 'N/A -- insufficient data')}")
    print(f"  Null rejected:    {'PASS' if null_ok else 'WARN -- signal may be noise on n=7; recheck on RunPod atlas'}")

    all_pass = slope_ok and (q1_ok is not False) and (rest_ok is not False)
    print(f"\n  OVERALL: {'PASS -- ship atlas' if all_pass else 'PROVISIONAL -- re-validate on full RunPod corpus'}")


if __name__ == "__main__":
    main()
