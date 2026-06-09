"""build_gt_weighted_forms.py — INT-64: GT-Weighted Form Features.

Replaces standard L5/EWMA form features with garbage-time-adjusted versions.
Games with high pct_minutes_in_gt are down-weighted so inflated stats from
garbage time don't pollute form estimates.

Weight formula: w_i = max(1.0 - pct_minutes_in_gt_i, 0.05)
  - Floor 0.05 preserves data point even for 100%-GT games.
  - Non-GT players (not in GT parquet): assume pct_gt=0 → w=1.0.

SHIFT(1) DISCIPLINE: each row's form features come from PRIOR games only.
The current game is NEVER included in its own form calculation.
See: feedback_no_season_final_features.md

Output schema (player_id, game_date, game_id, form cols, provenance):
  - pts_l5_no_gt, reb_l5_no_gt, ..., min_l5_no_gt   (L5 weighted mean)
  - pts_ewma_no_gt, ..., min_ewma_no_gt              (EWMA α=0.4 weighted)
  - pct_minutes_in_gt_l5                             (rolling mean of GT pct)
  - n_prior_games_used                               (int 0-5)
  - build_date

Coverage gate: rows with <2 prior games get NaN form cols (consumer fallback).
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
_OUT_PARQUET = ROOT / "data" / "intelligence" / "gt_weighted_forms.parquet"

# Mirror constants from src/prediction/prop_pergame.py (READ-ONLY reference)
_GAMELOG_FULL_MIN_PLAYED = 1.0   # line 2973 of prop_pergame.py
_EWMA_ALPHA = 0.40               # Opus spec: α=0.4 (NOTE: prop_pergame uses 0.30; Opus specified 0.40 here)

STATS_COLS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "min"]


def _parse_date(s: str) -> Optional[date]:
    """Parse various NBA gamelog date formats to date object."""
    if not s:
        return None
    s = str(s).strip()
    # ISO format: 2024-10-22
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        pass
    # NBA API format: "Apr 13, 2025"
    try:
        return datetime.strptime(s, "%b %d, %Y").date()
    except ValueError:
        pass
    # Try fromisoformat as fallback
    try:
        return datetime.fromisoformat(s[:10]).date()
    except (ValueError, IndexError):
        return None


def _safe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        return None if (f != f) else f  # NaN guard
    except (TypeError, ValueError):
        return None


def _weighted_mean_l5(vals_weights: deque) -> Optional[float]:
    """Weighted rolling mean over up to 5 (value, weight) pairs."""
    items = [(v, w) for v, w in vals_weights if v is not None]
    if not items:
        return None
    total_w = sum(w for _, w in items)
    if total_w <= 0:
        return None
    return sum(v * w for v, w in items) / total_w


def _weighted_ewma(vals_weights: deque, alpha: float = _EWMA_ALPHA) -> Optional[float]:
    """Weighted EWMA over up to 5 (value, weight) pairs.

    Combines recency decay (EWMA) with GT exposure inverse-weighting:
      decay_i = (1-alpha)^(k-i)  where k = position of most recent game (0-indexed from oldest)
      combined = w_i * decay_i
    Then normalise.

    EWMA + weight interaction note: when all recent games are 100%-GT,
    older non-GT games dominate via higher w_i. This is expected and documented
    behaviour — the feature degrades gracefully rather than silently using GT stats.
    """
    items = list(vals_weights)  # oldest first
    n = len(items)
    if n == 0:
        return None
    combined_w = []
    combined_v = []
    for i, (v, w) in enumerate(items):
        if v is None:
            continue
        decay = (1.0 - alpha) ** (n - 1 - i)
        combined_w.append(w * decay)
        combined_v.append(v)
    if not combined_w:
        return None
    total = sum(combined_w)
    if total <= 0:
        return None
    return sum(v * cw for v, cw in zip(combined_v, combined_w)) / total


def load_gt_lookup() -> Dict[Tuple[int, str], float]:
    """Load GT parquet → dict keyed (player_id, game_id) → pct_minutes_in_gt.

    Only rows with player_id > 0 are used (parser artefact in INT-56 build
    produced player_id=0 for multi-word suffixed names — skip those).
    """
    df = pd.read_parquet(_GT_PARQUET)
    valid = df[df["player_id"] > 0][["player_id", "game_id", "pct_minutes_in_gt"]].copy()
    valid["player_id"] = valid["player_id"].astype(int)
    lookup: Dict[Tuple[int, str], float] = {}
    for _, row in valid.iterrows():
        key = (int(row["player_id"]), str(row["game_id"]))
        lookup[key] = float(row["pct_minutes_in_gt"])
    print(f"  GT lookup: {len(lookup):,} entries from {valid['player_id'].nunique()} players")
    return lookup


def build_gt_weighted_forms(gamelog_dir: Optional[str] = None) -> pd.DataFrame:
    """Main build function. Returns DataFrame with GT-weighted form features."""
    gdir = str(gamelog_dir or _NBA_CACHE)

    # Step 1: Load GT lookup
    print("Loading GT parquet...")
    gt_lookup = load_gt_lookup()

    # Step 2: Walk all gamelog_full_*.json files (same pattern as build_gamelog_full_rolling)
    print("Walking gamelog_full_*.json files...")
    by_pid: Dict[int, List[Tuple[date, str, str, dict]]] = {}  # pid → [(date, gdate_str, game_id, g)]

    files_read = 0
    games_skipped_minutes = 0
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
            # Mirror _GAMELOG_FULL_MIN_PLAYED filter (prop_pergame.py:3038)
            if minutes < _GAMELOG_FULL_MIN_PLAYED:
                games_skipped_minutes += 1
                continue
            d = _parse_date(gdate_str)
            if d is None:
                continue
            by_pid.setdefault(pid, []).append((d, gdate_str, game_id, g))

    print(f"  Files read: {files_read}, games skipped (<{_GAMELOG_FULL_MIN_PLAYED}min): {games_skipped_minutes:,}")
    print(f"  Unique players: {len(by_pid):,}")

    # Step 3: Build rows
    output_rows: List[dict] = []
    players_with_coverage = 0
    today_str = date.today().isoformat()

    for pid, entries in by_pid.items():
        # Sort chronologically
        entries.sort(key=lambda x: x[0])

        # deque(maxlen=5) of (stat_value_dict, weight) from PRIOR games
        # Each slot: {'pts': float, 'reb': float, ...}
        prior_buf: deque = deque(maxlen=5)
        # Also track raw pct_gt values for pct_minutes_in_gt_l5
        prior_gt_pct: deque = deque(maxlen=5)

        for gdate_dt, gdate_str, game_id, g in entries:
            gdate_iso = gdate_dt.isoformat()

            # SHIFT(1): compute features from prior_buf BEFORE appending current game
            n_prior = len(prior_buf)

            if n_prior < 2:
                # Coverage gate: emit NaN form cols
                row = {
                    "player_id": pid,
                    "game_date": gdate_iso,
                    "game_id": game_id,
                    "n_prior_games_used": n_prior,
                    "pct_minutes_in_gt_l5": float(np.mean(list(prior_gt_pct))) if prior_gt_pct else 0.0,
                    "build_date": today_str,
                }
                for stat in STATS_COLS:
                    row[f"{stat}_l5_no_gt"] = float("nan")
                    row[f"{stat}_ewma_no_gt"] = float("nan")
                output_rows.append(row)
            else:
                players_with_coverage += 1
                # Build (value, weight) deques per stat
                row = {
                    "player_id": pid,
                    "game_date": gdate_iso,
                    "game_id": game_id,
                    "n_prior_games_used": n_prior,
                    "pct_minutes_in_gt_l5": float(np.mean(list(prior_gt_pct))),
                    "build_date": today_str,
                }
                for stat in STATS_COLS:
                    vals_weights = deque(
                        [(sv.get(stat), sw) for sv, sw in prior_buf],
                        maxlen=5
                    )
                    wm = _weighted_mean_l5(vals_weights)
                    we = _weighted_ewma(vals_weights)
                    row[f"{stat}_l5_no_gt"] = wm if wm is not None else float("nan")
                    row[f"{stat}_ewma_no_gt"] = we if we is not None else float("nan")
                output_rows.append(row)

            # Build stat dict and weight for this game (to append AFTER emitting)
            stat_dict = {}
            for stat in STATS_COLS:
                raw_col = "min" if stat == "min" else stat
                stat_dict[stat] = _safe_float(g.get(raw_col))

            # Look up GT weight for this game
            gt_key = (pid, game_id)
            pct_gt = gt_lookup.get(gt_key, 0.0)  # missing → assume non-GT
            weight = max(1.0 - pct_gt, 0.05)

            prior_buf.append((stat_dict, weight))
            prior_gt_pct.append(pct_gt)

    print(f"  Total output rows: {len(output_rows):,}")
    print(f"  Rows with >=2 prior games: {players_with_coverage:,}")

    df_out = pd.DataFrame(output_rows)

    # Ensure column order
    cols = ["player_id", "game_date", "game_id", "n_prior_games_used",
            "pct_minutes_in_gt_l5", "build_date"]
    for stat in STATS_COLS:
        cols += [f"{stat}_l5_no_gt", f"{stat}_ewma_no_gt"]
    df_out = df_out[cols]

    return df_out


def main():
    print("=== INT-64: Building GT-Weighted Forms ===")
    out_dir = ROOT / "data" / "intelligence"
    out_dir.mkdir(parents=True, exist_ok=True)

    df = build_gt_weighted_forms()

    print(f"\nWriting {_OUT_PARQUET} ...")
    df.to_parquet(_OUT_PARQUET, index=False)
    print(f"Done. Shape: {df.shape}")

    # Coverage stats
    n_with_feats = (~df["pts_l5_no_gt"].isna()).sum()
    n_total = len(df)
    print(f"\nCoverage stats:")
    print(f"  Total rows: {n_total:,}")
    print(f"  Rows with features (>=2 prior): {n_with_feats:,} ({100*n_with_feats/n_total:.1f}%)")
    print(f"  Rows NaN (coverage fallback): {n_total - n_with_feats:,}")
    print(f"\nGT exposure distribution (pct_minutes_in_gt_l5):")
    print(df[df["pct_minutes_in_gt_l5"] > 0]["pct_minutes_in_gt_l5"].describe())
    print(f"\nSample output:")
    print(df[~df["pts_l5_no_gt"].isna()].head(3).to_string())


if __name__ == "__main__":
    main()
