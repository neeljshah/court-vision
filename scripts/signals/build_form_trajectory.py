"""Wave 1 builder: per-player Form & Trajectory signal profile.

Reads per-player gamelog JSON files under data/nba/.  Prefers the richer
`gamelog_full_{pid}_{season}.json` (which includes game_id, oreb, dreb, fgm/fga,
fg3a, ftm/fta, plus_minus) and falls back to the slim `gamelog_{pid}_{season}.json`
(pts/reb/ast/fg3m/stl/blk/tov/min only).

Emits one wide row per (player_id, season) with:
  - L3/L5/L10/L20 rolling means per stat (shift(1) = prior games only, leak-safe)
  - EWMA (span=10) per stat on the shifted series
  - Hot/cold streak length per stat (signed: positive=hot, negative=cold)
  - Per-stat dispersion = season std-dev (season-aggregate, scouting only)
  - Month-over-month linear slope per stat (season-aggregate, scouting only)

Stats covered: pts, reb, ast, fg3m, stl, blk, tov
(oreb, dreb, plus_minus added when gamelog_full is available)

Leak rule:
  - Rolling windows (L3/L5/L10/L20) and EWMA: shift(1) = prior games only.
    Safe to feed into point model or in-game projector.
  - Dispersion (std) and slope: season-aggregate.  Label = "season-agg".
    Use for scouting / correlation model only; do NOT feed into D-consumer directly.

  python scripts/signals/build_form_trajectory.py
"""
from __future__ import annotations

import glob
import json
import os
import re

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GAMELOG_DIR = os.path.join(ROOT, "data", "nba")
OUT_DIR = os.path.join(ROOT, "data", "cache", "signals")
OUT = os.path.join(OUT_DIR, "form_trajectory.parquet")

CORE_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
EXTRA_STATS = ["oreb", "dreb", "plus_minus"]  # only in gamelog_full
WINDOWS = [3, 5, 10, 20]
EWMA_SPAN = 10
MIN_GAMES_STREAK = 5   # minimum prior games needed to assign a hot/cold streak

# Column mappings: JSON key → canonical lower name
SLIM_COL_MAP = {
    "GAME_DATE": "game_date", "PTS": "pts", "REB": "reb", "AST": "ast",
    "FG3M": "fg3m", "STL": "stl", "BLK": "blk", "TOV": "tov", "MIN": "min",
}
FULL_COL_MAP = {
    "game_date": "game_date",
    "pts": "pts", "reb": "reb", "ast": "ast", "fg3m": "fg3m",
    "stl": "stl", "blk": "blk", "tov": "tov", "min": "min",
    "oreb": "oreb", "dreb": "dreb", "plus_minus": "plus_minus",
    "fgm": "fgm", "fga": "fga", "fg3a": "fg3a",
}

ALL_STATS = CORE_STATS + EXTRA_STATS


def load_gamelog_full(path: str, player_id: int, season: str) -> pd.DataFrame:
    """Load a gamelog_full JSON — fields are already lowercase."""
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    rename = {k: v for k, v in FULL_COL_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)
    df["game_date"] = pd.to_datetime(df["game_date"], format="%b %d, %Y", errors="coerce")
    df = df.dropna(subset=["game_date"])
    for s in ALL_STATS:
        if s in df.columns:
            df[s] = pd.to_numeric(df[s], errors="coerce")
        else:
            df[s] = np.nan
    df = df.sort_values("game_date").reset_index(drop=True)
    df["player_id"] = player_id
    df["season"] = season
    return df


def load_gamelog_slim(path: str, player_id: int, season: str) -> pd.DataFrame:
    """Load a slim gamelog JSON — fields are uppercase."""
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    rename = {k: v for k, v in SLIM_COL_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)
    df["game_date"] = pd.to_datetime(df["game_date"], format="%b %d, %Y", errors="coerce")
    df = df.dropna(subset=["game_date"])
    for s in ALL_STATS:
        if s in df.columns:
            df[s] = pd.to_numeric(df[s], errors="coerce")
        else:
            df[s] = np.nan
    df = df.sort_values("game_date").reset_index(drop=True)
    df["player_id"] = player_id
    df["season"] = season
    return df


def _streak(vals: np.ndarray, means: np.ndarray) -> int:
    """Return signed consecutive streak at end of arrays.

    Positive = hot (at or above rolling prior mean), negative = cold.
    Returns 0 if insufficient data or all NaN.
    """
    if len(vals) < MIN_GAMES_STREAK:
        return 0
    # Find the last non-NaN index
    last = -1
    for i in range(len(vals) - 1, -1, -1):
        if not (np.isnan(vals[i]) or np.isnan(means[i])):
            last = i
            break
    if last < 0:
        return 0
    above = bool(vals[last] >= means[last])
    count = 0
    for i in range(last, -1, -1):
        if np.isnan(vals[i]) or np.isnan(means[i]):
            break
        if bool(vals[i] >= means[i]) == above:
            count += 1
        else:
            break
    return count if above else -count


def _month_slope(df: pd.DataFrame, stat: str) -> float | None:
    """Season-aggregate: linear slope of monthly stat averages (units: per month)."""
    if stat not in df.columns:
        return None
    tmp = df[["game_date", stat]].copy()
    tmp["month"] = tmp["game_date"].dt.to_period("M")
    monthly = tmp.groupby("month")[stat].mean().reset_index()
    monthly = monthly.dropna(subset=[stat])
    if len(monthly) < 2:
        return None
    x = np.arange(len(monthly), dtype=float)
    y = monthly[stat].values.astype(float)
    mask = ~np.isnan(y)
    if mask.sum() < 2:
        return None
    slope = float(np.polyfit(x[mask], y[mask], 1)[0])
    return round(slope, 4)


def build_player_season(df: pd.DataFrame, stats: list[str]) -> dict:
    """Compute all form signals for one (player_id, season) DataFrame (sorted oldest-first)."""
    pid = int(df["player_id"].iloc[0])
    season = df["season"].iloc[0]
    n_games = len(df)

    row: dict = {
        "player_id": pid,
        "season": season,
        "n_games": n_games,
    }

    for stat in stats:
        s = df[stat] if stat in df.columns else pd.Series(np.nan, index=df.index)

        # --- Leak-safe rolling windows: shift(1) so each game uses only prior games ---
        shifted = s.shift(1)
        for w in WINDOWS:
            val = shifted.rolling(w, min_periods=1).mean().iloc[-1] if n_games > 1 else np.nan
            row[f"l{w}_{stat}"] = float(val) if not pd.isna(val) else np.nan

        # --- EWMA (span=10) on prior games ---
        ewma_val = shifted.ewm(span=EWMA_SPAN, min_periods=1).mean().iloc[-1] if n_games > 1 else np.nan
        row[f"ewma_{stat}"] = float(ewma_val) if not pd.isna(ewma_val) else np.nan

        # --- Hot/cold streak (signed) ---
        if n_games > MIN_GAMES_STREAK:
            prior_mean = shifted.expanding(min_periods=1).mean()
            row[f"streak_{stat}"] = _streak(
                np.asarray(shifted, dtype=float),
                np.asarray(prior_mean, dtype=float),
            )
        else:
            row[f"streak_{stat}"] = 0

        # --- Season-aggregate dispersion (std-dev of actual game values) ---
        valid = s.dropna()
        row[f"std_{stat}"] = float(valid.std(ddof=1)) if len(valid) >= 3 else np.nan

        # --- Season-aggregate month-over-month slope ---
        row[f"slope_{stat}"] = _month_slope(df, stat)

    return row


def build() -> pd.DataFrame:
    """Discover all gamelog files, compute signals, return one-row-per-(player,season)."""
    # Index gamelog_full files (preferred)
    full_rx = re.compile(r"gamelog_full_(\d+)_(.+)[.]json$")
    full_index: dict[tuple[int, str], str] = {}
    for path in glob.glob(os.path.join(GAMELOG_DIR, "gamelog_full_*.json")):
        bn = os.path.basename(path)
        m = full_rx.match(bn)
        if m:
            pid = int(m.group(1))
            season = m.group(2)
            full_index[(pid, season)] = path

    # Index slim gamelog files (fallback)
    slim_rx = re.compile(r"gamelog_(\d+)_(.+)[.]json$")
    slim_index: dict[tuple[int, str], str] = {}
    for path in glob.glob(os.path.join(GAMELOG_DIR, "gamelog_*.json")):
        bn = os.path.basename(path)
        # Skip gamelog_full files (they'll match the pattern too)
        if bn.startswith("gamelog_full_"):
            continue
        m = slim_rx.match(bn)
        if m:
            pid = int(m.group(1))
            season = m.group(2)
            slim_index[(pid, season)] = path

    # Merge: full takes priority; fallback to slim for any (player, season) not in full
    all_keys = set(full_index.keys()) | set(slim_index.keys())
    print(f"  gamelog_full: {len(full_index)} player-seasons  |  "
          f"slim: {len(slim_index)} player-seasons  |  "
          f"total unique: {len(all_keys)}")

    rows = []
    errors = 0
    for key in sorted(all_keys):
        pid, season = key
        try:
            if key in full_index:
                df = load_gamelog_full(full_index[key], pid, season)
                stats = ALL_STATS
            else:
                df = load_gamelog_slim(slim_index[key], pid, season)
                stats = CORE_STATS

            if df.empty or len(df) < 2:
                continue

            rows.append(build_player_season(df, stats))
        except Exception as exc:
            errors += 1
            if errors <= 5:
                print(f"  WARN pid={pid} season={season}: {exc}")

    if errors > 5:
        print(f"  ... {errors} total errors (first 5 shown).")
    elif errors > 0:
        print(f"  {errors} errors.")

    return pd.DataFrame(rows)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("Building form_trajectory signals ...")
    out = build()

    # Sanity: no cartesian blowup — should be one row per (player, season)
    assert out.duplicated(subset=["player_id", "season"]).sum() == 0, \
        "Duplicate (player_id, season) rows — join bug!"
    # Should be well under 5000 rows (4 seasons × ~1100 players at most)
    assert len(out) <= 6000, f"Row count {len(out)} suspiciously large"

    out.to_parquet(OUT, index=False)
    print(f"\nDONE: form_trajectory signals -> {OUT}")
    print(f"  rows={len(out)}  distinct players={out.player_id.nunique()}"
          f"  seasons={sorted(out.season.unique())}")

    # Three sample rows
    print("\n  Sample rows (3):")
    sample = out.sample(3, random_state=42) if len(out) >= 3 else out
    disp = ["player_id", "season", "n_games",
            "l5_pts", "ewma_pts", "streak_pts", "std_pts", "slope_pts",
            "l5_ast", "ewma_ast", "streak_ast"]
    print(sample[[c for c in disp if c in sample.columns]].to_string(index=False))

    # Sanity ranking: top players by l10_pts in 2024-25 (stars should appear)
    s2425 = out[out.season == "2024-25"].copy()
    if not s2425.empty and "l10_pts" in s2425.columns:
        top = s2425.nlargest(10, "l10_pts")[
            ["player_id", "l10_pts", "ewma_pts", "streak_pts", "std_pts"]
        ]
        print("\n  Top 10 by l10_pts in 2024-25 (should see known high scorers):")
        print(top.to_string(index=False))

    # Most volatile scorers
    if not s2425.empty and "std_pts" in s2425.columns:
        vol = s2425.nlargest(8, "std_pts")[["player_id", "std_pts", "l10_pts", "slope_pts"]]
        print("\n  Most volatile scorers by std_pts in 2024-25:")
        print(vol.to_string(index=False))


if __name__ == "__main__":
    main()
