"""As-of rebuild of the form_trajectory signal at STRICTLY-PRIOR per-game grain.

The original build_form_trajectory.py emits one row per (player_id, season) --
season-aggregate grain, no game_id/game_date, so it cannot be joined into a
leak-free per-game feature bundle. This rebuild keys each row to
(player_id, season, game_id, game_date) and computes every feature using ONLY
games strictly BEFORE game_date (shift(1) before any rolling/expanding op).

Source: data/nba/gamelog_full_{player_id}_{season}.json only (the slim
gamelog_{player_id}_{season}.json fallback used by the original builder has no
game_id -- can't key an as-of row to it, so it is out of scope here).

Leak rule: every feature column is computed on a series shifted by 1 game
BEFORE any rolling/expanding call, so game i's row never sees game i's own
line. A game's own tampering can only ever affect LATER games' rows, never
its own. First game of a (player, season) has no prior games -> NaN features
(never a faked zero).

  python scripts/signals/build_form_trajectory_asof.py
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
OUT = os.path.join(OUT_DIR, "form_trajectory_asof.parquet")

WINDOWS = (5, 10)
SLOPE_WINDOW = 10
FULL_RX = re.compile(r"gamelog_full_(\d+)_(.+)[.]json$")

FEATURE_COLS = [
    "n_prior_games", "l5_pts", "l10_pts", "l5_min", "l10_min",
    "l5_ts_pct", "l10_ts_pct", "trend_pts_slope10", "baseline_pts",
    "dev_pts_vs_baseline",
]
KEY_COLS = ["player_id", "season", "game_id", "game_date"]


def discover_files(gamelog_dir: str) -> dict:
    """Map (player_id, season) -> path for every gamelog_full_*.json file."""
    index: dict = {}
    for path in glob.glob(os.path.join(gamelog_dir, "gamelog_full_*.json")):
        m = FULL_RX.match(os.path.basename(path))
        if m:
            index[(int(m.group(1)), m.group(2))] = path
    return index


def load_one(path: str, player_id: int, season: str) -> pd.DataFrame:
    """Load one gamelog_full JSON -> chronologically-sorted per-game DataFrame."""
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    needed = {"game_id", "game_date", "pts", "min", "fga", "fta"}
    if not needed.issubset(df.columns):
        return pd.DataFrame()
    df["game_date"] = pd.to_datetime(df["game_date"], format="%b %d, %Y", errors="coerce")
    df = df.dropna(subset=["game_date", "game_id"])
    for c in ("pts", "min", "fga", "fta"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    denom = 2.0 * (df["fga"] + 0.44 * df["fta"])
    df["ts_pct"] = np.where(denom > 0, df["pts"] / denom, np.nan)
    df["player_id"] = player_id
    df["season"] = season
    # chronological, stable, tie-broken by game_id for determinism
    df = df.sort_values(["game_date", "game_id"], kind="mergesort").reset_index(drop=True)
    return df[["player_id", "season", "game_id", "game_date", "pts", "min", "ts_pct"]]


def _window_slope(arr: np.ndarray) -> float:
    """Linear slope of the non-NaN values in a rolling window (chronological order preserved)."""
    y = arr[~np.isnan(arr)]
    if len(y) < 2:
        return np.nan
    x = np.arange(len(y), dtype=float)
    return float(np.polyfit(x, y, 1)[0])


def build_player_season_asof(df: pd.DataFrame) -> pd.DataFrame:
    """Given one chronologically-sorted (player, season) gamelog, emit one as-of row per game."""
    n = len(df)
    out = df[KEY_COLS].copy()
    out["n_prior_games"] = np.arange(n)

    pts_shift = df["pts"].shift(1)
    min_shift = df["min"].shift(1)
    ts_shift = df["ts_pct"].shift(1)

    for w in WINDOWS:
        out[f"l{w}_pts"] = pts_shift.rolling(w, min_periods=1).mean()
        out[f"l{w}_min"] = min_shift.rolling(w, min_periods=1).mean()
        out[f"l{w}_ts_pct"] = ts_shift.rolling(w, min_periods=1).mean()

    out["trend_pts_slope10"] = pts_shift.rolling(SLOPE_WINDOW, min_periods=1).apply(
        _window_slope, raw=True
    )
    out["baseline_pts"] = pts_shift.expanding(min_periods=1).mean()
    out["dev_pts_vs_baseline"] = out["l5_pts"] - out["baseline_pts"]

    return out[KEY_COLS + FEATURE_COLS]


def build(gamelog_dir: str = GAMELOG_DIR) -> pd.DataFrame:
    """Discover all gamelog_full files, compute as-of signals, return per-game rows."""
    index = discover_files(gamelog_dir)
    frames = []
    errors = 0
    for (pid, season), path in sorted(index.items()):
        try:
            df = load_one(path, pid, season)
            if df.empty:
                continue
            frames.append(build_player_season_asof(df))
        except Exception as exc:  # noqa: BLE001
            errors += 1
            if errors <= 5:
                print(f"  WARN pid={pid} season={season}: {exc}")
    if errors:
        print(f"  {errors} errors during build.")
    if not frames:
        return pd.DataFrame(columns=KEY_COLS + FEATURE_COLS)

    out = pd.concat(frames, ignore_index=True)
    out = out.sort_values(
        ["player_id", "season", "game_date", "game_id"], kind="mergesort"
    ).reset_index(drop=True)
    return out


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    print("Building form_trajectory_asof signals ...")
    out = build()

    assert out.duplicated(subset=["player_id", "season", "game_id"]).sum() == 0, \
        "Duplicate (player_id, season, game_id) rows -- join bug!"

    out.to_parquet(OUT, index=False)
    print(f"\nDONE: form_trajectory_asof signals -> {OUT}")
    print(f"  total rows={len(out)}  distinct players={out.player_id.nunique()}")

    print("\n  Rows per season:")
    print(out.groupby("season").size().to_string())

    if len(out):
        sample = out.sort_values(["player_id", "season", "game_date"]).iloc[[-1]]
        print("\n  Sample row (most recent game in the corpus):")
        print(sample.to_string(index=False))


if __name__ == "__main__":
    main()
