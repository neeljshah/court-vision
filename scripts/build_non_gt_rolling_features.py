"""build_non_gt_rolling_features.py — INT-126: GT-Excluded Rolling Form Features.

Computes rolling form features using ONLY non-garbage-time stats.
Unlike INT-64 (which DOWN-WEIGHTED GT games), this approach SUBTRACTS GT stats
so that form features reflect true competitive minutes only.

For each (player, game):
  non_gt_{stat} = raw_{stat} - {stat}_in_gt   (clipped >= 0)
  non_gt_min    = raw_min    - minutes_in_gt   (clipped >= 0)

Rolling windows: L5 and L10, weighted by non_gt_min.
14 features: non_gt_{pts,reb,ast,fg3m,stl,blk,tov}_l{5,10}

SHIFT(1) DISCIPLINE: each row's features come from PRIOR games only.
See: feedback_no_season_final_features.md

Output schema keyed on (player_id, game_date, game_id):
  non_gt_{stat}_l5, non_gt_{stat}_l10  for 7 stats
  pct_minutes_in_gt_mean_l5 (rolling GT exposure for context)
  n_prior_games_l5, n_prior_games_l10
  build_date
"""
from __future__ import annotations

import json
import os
import sys
from collections import deque
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent  # script-relative, works on RunPod

_NBA_CACHE = ROOT / "data" / "nba"
_GT_PARQUET = ROOT / "data" / "intelligence" / "garbage_time_player_aggregates.parquet"
_OUT_PARQUET = ROOT / "data" / "intelligence" / "non_gt_forms_sidecar.parquet"

_GAMELOG_FULL_MIN_PLAYED = 1.0  # mirror prop_pergame.py:2973

# 7 prediction stats + minutes
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
GT_STAT_MAP = {
    "pts": "points_in_gt",
    "reb": "reb_in_gt",
    "ast": "ast_in_gt",
    "fg3m": "fg3m_in_gt",
    "stl": "stl_in_gt",
    "blk": "blk_in_gt",
    "tov": "tov_in_gt",
}
WINDOWS = [5, 10]


def _parse_date(s: str) -> Optional[date]:
    """Parse NBA gamelog date formats."""
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s[:10]).date()
    except (ValueError, IndexError):
        return None


def _safe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        return None if (f != f) else f
    except (TypeError, ValueError):
        return None


def _weighted_mean(vals_weights: list) -> Optional[float]:
    """Weighted mean over (value, weight) pairs; None values are skipped."""
    items = [(v, w) for v, w in vals_weights if v is not None]
    if not items:
        return None
    total_w = sum(w for _, w in items)
    if total_w <= 0:
        # all-zero weight → fall back to unweighted mean
        vals = [v for v, _ in items]
        return float(np.mean(vals))
    return sum(v * w for v, w in items) / total_w


def load_gt_lookup() -> Dict[Tuple[int, str], dict]:
    """Load GT parquet → dict keyed (player_id int, game_id str) → stat row dict.

    Includes minutes_in_gt and all {stat}_in_gt columns.
    Only rows with player_id > 0 are used.
    """
    df = pd.read_parquet(_GT_PARQUET)
    valid = df[df["player_id"] > 0].copy()
    valid["player_id"] = valid["player_id"].astype(int)

    lookup: Dict[Tuple[int, str], dict] = {}
    gt_cols = ["minutes_in_gt", "pct_minutes_in_gt"] + list(GT_STAT_MAP.values())
    for _, row in valid.iterrows():
        key = (int(row["player_id"]), str(row["game_id"]))
        lookup[key] = {c: float(row[c]) for c in gt_cols}

    print(f"  GT lookup: {len(lookup):,} entries from {valid['player_id'].nunique()} players")
    return lookup


def build_non_gt_rolling_features(gamelog_dir: Optional[str] = None) -> pd.DataFrame:
    """Main build function. Returns DataFrame with non-GT rolling features."""
    gdir = str(gamelog_dir or _NBA_CACHE)

    print("Loading GT parquet lookup...")
    gt_lookup = load_gt_lookup()

    print("Walking gamelog_full_*.json files...")
    by_pid: Dict[int, List[Tuple[date, str, str, dict]]] = {}

    files_read = 0
    games_skipped = 0
    for fname in os.listdir(gdir):
        if not fname.startswith("gamelog_full_") or not fname.endswith(".json"):
            continue
        fpath = os.path.join(gdir, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                games = json.load(f)
        except Exception:
            continue
        if not isinstance(games, list):
            continue
        files_read += 1
        for g in games:
            try:
                pid = int(g.get("player_id", 0) or 0)
                gdate_str = str(g.get("game_date", "") or "").strip()
                game_id = str(g.get("game_id", "") or "").strip()
            except Exception:
                continue
            if not pid or not gdate_str:
                continue
            try:
                minutes = float(g.get("min", 0.0) or 0.0)
            except (TypeError, ValueError):
                minutes = 0.0
            if minutes < _GAMELOG_FULL_MIN_PLAYED:
                games_skipped += 1
                continue
            d = _parse_date(gdate_str)
            if d is None:
                continue
            by_pid.setdefault(pid, []).append((d, gdate_str, game_id, g))

    print(f"  Files read: {files_read}, games skipped (<{_GAMELOG_FULL_MIN_PLAYED}min): {games_skipped:,}")
    print(f"  Unique players: {len(by_pid):,}")

    output_rows: List[dict] = []
    today_str = date.today().isoformat()
    gt_affected_count = 0

    for pid, entries in by_pid.items():
        entries.sort(key=lambda x: x[0])

        # Rolling buffers per window: deque of (non_gt_stat_dict, non_gt_min)
        bufs: Dict[int, deque] = {w: deque(maxlen=w) for w in WINDOWS}
        prior_gt_pct: deque = deque(maxlen=5)

        for gdate_dt, gdate_str, game_id, g in entries:
            gdate_iso = gdate_dt.isoformat()

            # === SHIFT(1): emit features from PRIOR games ===
            n5 = len(bufs[5])
            n10 = len(bufs[10])

            row: dict = {
                "player_id": pid,
                "game_date": gdate_iso,
                "game_id": game_id,
                "n_prior_games_l5": n5,
                "n_prior_games_l10": n10,
                "pct_minutes_in_gt_mean_l5": float(np.mean(list(prior_gt_pct))) if prior_gt_pct else 0.0,
                "build_date": today_str,
            }

            for w in WINDOWS:
                suffix = f"_l{w}"
                buf = bufs[w]
                if len(buf) < 2:
                    for stat in STATS:
                        row[f"non_gt_{stat}{suffix}"] = float("nan")
                else:
                    for stat in STATS:
                        pairs = [(slot.get(stat), slot.get("non_gt_min", 0.0)) for slot in buf]
                        wm = _weighted_mean(pairs)
                        row[f"non_gt_{stat}{suffix}"] = wm if wm is not None else float("nan")

            output_rows.append(row)

            # === BUILD stat slot for this game (appended AFTER emit) ===
            gt_key = (pid, game_id)
            gt_data = gt_lookup.get(gt_key)

            raw_min = _safe_float(g.get("min")) or 0.0
            if gt_data is not None:
                gt_min = max(0.0, float(gt_data.get("minutes_in_gt", 0.0)))
                pct_gt = float(gt_data.get("pct_minutes_in_gt", 0.0))
                gt_affected_count += 1
            else:
                gt_min = 0.0
                pct_gt = 0.0

            non_gt_min = max(0.0, raw_min - gt_min)

            slot: dict = {"non_gt_min": non_gt_min}
            for stat in STATS:
                raw_val = _safe_float(g.get(stat)) or 0.0
                if gt_data is not None:
                    gt_col = GT_STAT_MAP[stat]
                    gt_val = max(0.0, float(gt_data.get(gt_col, 0.0)))
                else:
                    gt_val = 0.0
                slot[stat] = max(0.0, raw_val - gt_val)

            for w in WINDOWS:
                bufs[w].append(slot)
            prior_gt_pct.append(pct_gt)

    print(f"  Total output rows: {len(output_rows):,}")
    print(f"  GT-affected game slots: {gt_affected_count:,}")

    df_out = pd.DataFrame(output_rows)

    # Column ordering
    base_cols = ["player_id", "game_date", "game_id",
                 "n_prior_games_l5", "n_prior_games_l10",
                 "pct_minutes_in_gt_mean_l5", "build_date"]
    feat_cols = []
    for w in WINDOWS:
        for stat in STATS:
            feat_cols.append(f"non_gt_{stat}_l{w}")
    df_out = df_out[base_cols + feat_cols]

    return df_out


def main():
    print("=== INT-126: Building GT-Excluded Rolling Form Features ===")
    out_dir = ROOT / "data" / "intelligence"
    out_dir.mkdir(parents=True, exist_ok=True)

    df = build_non_gt_rolling_features()

    print(f"\nWriting {_OUT_PARQUET} ...")
    df.to_parquet(_OUT_PARQUET, index=False)
    print(f"Done. Shape: {df.shape}")

    # Coverage stats
    n_total = len(df)
    n_with_l5 = (~df["non_gt_pts_l5"].isna()).sum()
    n_with_l10 = (~df["non_gt_pts_l10"].isna()).sum()
    print(f"\nCoverage stats:")
    print(f"  Total rows: {n_total:,}")
    print(f"  Rows with L5 features (>=2 prior): {n_with_l5:,} ({100*n_with_l5/n_total:.1f}%)")
    print(f"  Rows with L10 features (>=2 prior): {n_with_l10:,} ({100*n_with_l10/n_total:.1f}%)")

    # Fold-4 proxy: last 25% of rows by game_date
    df_sorted = df.sort_values("game_date")
    fold4_start = int(0.75 * n_total)
    fold4 = df_sorted.iloc[fold4_start:]
    print(f"\nFold-4 coverage (last 25% rows, n={len(fold4):,}):")
    for col in ["non_gt_pts_l5", "non_gt_pts_l10"]:
        nn = fold4[col].notna().sum()
        print(f"  {col}: {nn:,} non-null ({100*nn/len(fold4):.1f}%)")

    # GT-exposed subset
    gt_exposed = df[df["pct_minutes_in_gt_mean_l5"] > 0.05]
    print(f"\nGT-exposed subset (pct_gt_l5 > 5%): {len(gt_exposed):,} rows ({100*len(gt_exposed)/n_total:.1f}%)")

    print(f"\nSample output (first row with L5 features):")
    sample = df[~df["non_gt_pts_l5"].isna()]
    if len(sample) > 0:
        print(sample.head(3)[["player_id", "game_date", "non_gt_pts_l5", "non_gt_pts_l10",
                                "non_gt_reb_l5", "non_gt_ast_l5", "n_prior_games_l5"]].to_string())


if __name__ == "__main__":
    main()
