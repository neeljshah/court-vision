"""refresh_hustle_2025-26.py — pull LeagueHustleStatsPlayer for 2025-26.

Writes data/cache/hustle_features_2025-26.parquet with the EXACT schema of
data/cache/hustle_features.parquet so a downstream merge is drop-in:
    player_id, player_name, season, hustle_games_played, hustle_deflections,
    hustle_contested_shots, hustle_screen_assists, hustle_box_outs,
    hustle_loose_balls, hustle_charges_drawn
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
OUT_PATH = os.path.join(PROJECT_DIR, "data", "cache", "hustle_features_2025-26.parquet")


def fetch() -> pd.DataFrame:
    from nba_api.stats.endpoints import leaguehustlestatsplayer
    last_err = None
    for attempt in range(2):
        try:
            resp = leaguehustlestatsplayer.LeagueHustleStatsPlayer(
                season=SEASON,
                season_type_all_star="Regular Season",
                per_mode_time="PerGame",
                timeout=60,
            )
            time.sleep(0.6)
            return resp.get_data_frames()[0]
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"  [retry {attempt}] {e}", flush=True)
            time.sleep(5 + attempt * 3)
    raise RuntimeError(f"hustle fetch failed after retries: {last_err}")


def main() -> None:
    df = fetch()
    print(f"[hustle] raw rows={len(df)} cols={list(df.columns)}", flush=True)
    if df.empty:
        raise RuntimeError("hustle returned empty frame for 2025-26")

    cols = {c.upper(): c for c in df.columns}

    def col(name: str):
        return df[cols[name]] if name in cols else 0.0

    out = pd.DataFrame({
        "player_id": col("PLAYER_ID").astype("int64"),
        "player_name": col("PLAYER_NAME").astype(str).str.strip(),
        "season": SEASON,
        "hustle_games_played": pd.to_numeric(col("G"), errors="coerce").astype("float64"),
        "hustle_deflections": pd.to_numeric(col("DEFLECTIONS"), errors="coerce"),
        "hustle_contested_shots": pd.to_numeric(col("CONTESTED_SHOTS"), errors="coerce"),
        "hustle_screen_assists": pd.to_numeric(col("SCREEN_ASSISTS"), errors="coerce"),
        "hustle_box_outs": pd.to_numeric(col("BOX_OUTS"), errors="coerce"),
        "hustle_loose_balls": pd.to_numeric(col("LOOSE_BALLS_RECOVERED"), errors="coerce"),
        "hustle_charges_drawn": pd.to_numeric(col("CHARGES_DRAWN"), errors="coerce"),
    })

    out = (out.sort_values("hustle_games_played", ascending=False)
              .drop_duplicates(subset=["player_id", "season"])
              .sort_values(["player_id", "season"])
              .reset_index(drop=True))

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    out.to_parquet(OUT_PATH, index=False)
    print(f"[hustle] wrote {len(out)} rows -> {OUT_PATH}", flush=True)
    print(f"distinct players= {out['player_id'].nunique()}")
    sga = out[out["player_id"] == 1628983]
    if len(sga):
        r = sga.iloc[0]
        print(f"sanity SGA(1628983): gp={r['hustle_games_played']} "
              f"deflections={r['hustle_deflections']} "
              f"contested={r['hustle_contested_shots']} "
              f"loose={r['hustle_loose_balls']}")
    else:
        print("sanity SGA(1628983): NOT in hustle table")
    print(f"final cols: {list(out.columns)}")


if __name__ == "__main__":
    main()
