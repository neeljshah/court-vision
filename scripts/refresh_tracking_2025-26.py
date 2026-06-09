"""refresh_tracking_2025-26.py — per-player season tracking for 2025-26.

Mirrors fetch_player_tracking.py exactly (LeagueDashPtStats, same Drives /
Passing / CatchShoot column mapping) but pins Season='2025-26' and writes
data/player_tracking_2025-26.parquet with the EXACT schema of
data/player_tracking.parquet:
    player_id, season, trk_drv_*, trk_pas_*, trk_cs_*
"""
from __future__ import annotations

import os
import sys
import time

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data import nba_api_headers_patch  # noqa: F401, E402

SEASON = "2025-26"
OUT_PATH = os.path.join(PROJECT_DIR, "data", "player_tracking_2025-26.parquet")
_MEASURES = ["Drives", "Passing", "CatchShoot"]

_COL_ORDER = [
    "player_id", "season",
    "trk_drv_count", "trk_drv_pts", "trk_drv_fg_pct", "trk_drv_passes",
    "trk_drv_ast", "trk_drv_tov_pct",
    "trk_pas_passes_made", "trk_pas_passes_received", "trk_pas_potential_ast",
    "trk_pas_ast_points_created", "trk_pas_secondary_ast", "trk_pas_ft_ast",
    "trk_cs_fga", "trk_cs_fg_pct", "trk_cs_efg_pct", "trk_cs_pts",
]


def fetch_one(measure: str) -> list:
    from nba_api.stats.endpoints import leaguedashptstats
    last_err = None
    for attempt in range(2):
        try:
            df = leaguedashptstats.LeagueDashPtStats(
                season=SEASON, season_type_all_star="Regular Season",
                pt_measure_type=measure, player_or_team="Player",
                per_mode_simple="PerGame",
                timeout=60,
            ).get_data_frames()[0]
            time.sleep(0.6)
            rows = []
            for _, r in df.iterrows():
                d = {k.lower(): v for k, v in r.to_dict().items()}
                rows.append(d)
            print(f"  {measure}: {len(rows)} rows", flush=True)
            return rows
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"  [retry {attempt}] {measure}: {e}", flush=True)
            time.sleep(5 + attempt * 3)
    print(f"  [FAIL] {measure}: {last_err}", flush=True)
    return []


def main() -> None:
    all_rows: dict = {}
    failed: list = []
    for measure in _MEASURES:
        rows = fetch_one(measure)
        if not rows:
            failed.append(measure)
        for r in rows:
            pid = r.get("player_id")
            if pid is None:
                continue
            key = int(pid)
            merged = all_rows.setdefault(key, {
                "player_id": int(pid), "season": SEASON,
            })
            if measure == "Drives":
                for c in ("drives", "drive_pts", "drive_fg_pct",
                          "drive_passes", "drive_ast", "drive_tov_pct"):
                    merged[f"trk_drv_{c.replace('drive_','').replace('drives','count')}"] = float(r.get(c, 0.0) or 0.0)
            elif measure == "Passing":
                for c in ("passes_made", "passes_received",
                          "potential_ast", "ast_points_created",
                          "secondary_ast", "ft_ast"):
                    merged[f"trk_pas_{c}"] = float(r.get(c, 0.0) or 0.0)
            elif measure == "CatchShoot":
                for c in ("catch_shoot_fga", "catch_shoot_fg_pct",
                          "catch_shoot_efg_pct", "catch_shoot_pts"):
                    merged[f"trk_cs_{c.replace('catch_shoot_','')}"] = float(r.get(c, 0.0) or 0.0)

    df = pd.DataFrame(list(all_rows.values()))
    if df.empty:
        print("[fail] no rows collected")
        if failed:
            print(f"FAILED measures: {failed}")
        return

    # Enforce exact column order/schema parity (fill any missing with 0.0).
    for c in _COL_ORDER:
        if c not in df.columns:
            df[c] = 0.0
    df = df[_COL_ORDER]

    df.to_parquet(OUT_PATH, index=False)
    print(f"\n[done] {len(df)} rows -> {OUT_PATH}", flush=True)
    print(f"distinct players= {df['player_id'].nunique()}")
    if failed:
        print(f"FAILED measures: {failed}")
    sga = df[df["player_id"] == 1628983]
    if len(sga):
        r = sga.iloc[0]
        print(f"sanity SGA(1628983): drives={r['trk_drv_count']} "
              f"drive_pts={r['trk_drv_pts']} passes_made={r['trk_pas_passes_made']} "
              f"cs_fga={r['trk_cs_fga']}")
    else:
        print("sanity SGA(1628983): NOT in tracking table")
    print(f"final cols: {list(df.columns)}")


if __name__ == "__main__":
    main()
