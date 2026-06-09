#!/usr/bin/env python3
"""build_clutch_profiles.py -- 2025-26 player clutch profile dataset.

Pulls LeagueDashPlayerClutch (Last 5 Minutes, Ahead or Behind, +/-5 pt diff,
Base, PerGame) for the 2025-26 regular season and writes a clean per-player
parquet at data/cache/clutch_profiles_2025-26.parquet.

Usage:
    python scripts/build_clutch_profiles.py
"""
from __future__ import annotations

import os
import sys
import time

import pandas as pd

# Windows console chokes on non-ASCII player names (e.g. Jokic) when stdout is
# redirected; force UTF-8 so verification prints don't crash after the write.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data import nba_api_headers_patch  # noqa: F401, E402

OUT_PATH = os.path.join(PROJECT_DIR, "data", "cache", "clutch_profiles_2025-26.parquet")
SEASON = "2025-26"


def fetch_clutch() -> pd.DataFrame:
    from nba_api.stats.endpoints import leaguedashplayerclutch
    last_err = None
    for attempt in range(4):
        try:
            resp = leaguedashplayerclutch.LeagueDashPlayerClutch(
                clutch_time="Last 5 Minutes",
                ahead_behind="Ahead or Behind",
                point_diff=5,
                measure_type_detailed_defense="Base",
                per_mode_detailed="PerGame",
                season=SEASON,
                season_type_all_star="Regular Season",
                timeout=60,
            )
            time.sleep(0.6)
            return resp.get_data_frames()[0]
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"  [retry {attempt}] {e}", flush=True)
            time.sleep(2 + attempt)
    raise RuntimeError(f"clutch fetch failed after retries: {last_err}")


def main() -> None:
    df = fetch_clutch()
    print(f"[clutch] raw rows={len(df)} cols={list(df.columns)}", flush=True)

    colmap = {
        "PLAYER_ID": "player_id",
        "PLAYER_NAME": "player_name",
        "GP": "clutch_gp",
        "MIN": "clutch_min",
        "PTS": "clutch_pts",
        "FG_PCT": "clutch_fg_pct",
        "FG3_PCT": "clutch_fg3_pct",
        "FT_PCT": "clutch_ft_pct",
        "PLUS_MINUS": "clutch_plus_minus",
    }
    keep = {k: v for k, v in colmap.items() if k in df.columns}
    out = df[list(keep)].rename(columns=keep).copy()

    # USG if present (some MeasureType=Base payloads omit it)
    for usg_col in ("USG_PCT", "USG_PCT_RANK"):
        if usg_col in df.columns:
            out["clutch_usg"] = df[usg_col].values
            break

    # Normalizations (PerMode is already PerGame; MIN here is clutch min/game).
    # Per-36 points within the clutch context.
    if {"clutch_pts", "clutch_min"}.issubset(out.columns):
        import numpy as np
        m = out["clutch_min"].astype(float)
        per36 = np.where(m > 0, out["clutch_pts"].astype(float) * 36.0 / m, np.nan)
        out["clutch_pts_per36"] = np.round(per36, 3)

    out["season"] = SEASON
    out = out.reset_index(drop=True)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    out.to_parquet(OUT_PATH, index=False)
    print(f"[clutch] wrote {OUT_PATH}", flush=True)

    # ---- Verification ----
    print(f"\nrowcount        = {len(out)}")
    print(f"distinct players= {out['player_id'].nunique()}")
    top = out.sort_values("clutch_pts", ascending=False).head(10)
    print("\nTop-10 by clutch_pts:")
    print(top[["player_name", "clutch_pts", "clutch_fg_pct", "clutch_gp"]]
          .to_string(index=False))
    for pid, name in [(1628983, "SGA"), (1629029, "Doncic"), (1628369, "Tatum")]:
        row = out[out["player_id"] == pid]
        if len(row):
            r = row.iloc[0]
            print(f"\nsanity {name} ({pid}): gp={r['clutch_gp']} "
                  f"pts={r['clutch_pts']} fg_pct={r['clutch_fg_pct']} "
                  f"+/-={r.get('clutch_plus_minus')}")
        else:
            print(f"\nsanity {name} ({pid}): NOT in clutch table")


if __name__ == "__main__":
    main()
