"""refresh_playtypes_2025-26.py — per-PLAYER synergy play-type freqs for 2025-26.

Mirrors fetch_player_synergy.py exactly (same endpoint, same column mapping)
but pins Season='2025-26' and writes data/playtypes_2025-26.parquet with the
EXACT schema of data/playtypes.parquet:
    player_id, season, play_type, freq_pct, ppp
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
OUT_PATH = os.path.join(PROJECT_DIR, "data", "playtypes_2025-26.parquet")

# Full list per task. fetch_player_synergy.py used 9; task asks for these 11.
_PLAY_TYPES = ["Isolation", "Transition", "PRBallHandler", "PRRollMan",
               "Postup", "Spotup", "Handoff", "Cut", "OffScreen",
               "OffRebound", "Misc"]


def fetch(play_type: str) -> list:
    from nba_api.stats.endpoints import synergyplaytypes
    last_err = None
    for attempt in range(2):
        try:
            df = synergyplaytypes.SynergyPlayTypes(
                season=SEASON, season_type_all_star="Regular Season",
                play_type_nullable=play_type, type_grouping_nullable="offensive",
                player_or_team_abbreviation="P",
                per_mode_simple="PerGame",
                timeout=60,
            ).get_data_frames()[0]
            time.sleep(0.6)
            rows = []
            for _, r in df.iterrows():
                d = {k.lower(): v for k, v in r.to_dict().items()}
                d["play_type"] = play_type
                d["season"] = SEASON
                rows.append(d)
            print(f"  {play_type}: {len(rows)} rows", flush=True)
            return rows
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"  [retry {attempt}] {play_type}: {e}", flush=True)
            time.sleep(5 + attempt * 3)
    print(f"  [FAIL] {play_type}: {last_err}", flush=True)
    return []


def main() -> None:
    all_rows: list = []
    failed: list = []
    for pt in _PLAY_TYPES:
        rows = fetch(pt)
        if not rows:
            failed.append(pt)
        all_rows.extend(rows)
        time.sleep(0.6)

    out_rows = []
    for r in all_rows:
        pid = r.get("player_id")
        freq = r.get("poss_pct") or r.get("freq_pct") or r.get("freq")
        if pid is None or freq is None:
            continue
        ppp_val = r.get("ppp")
        out_rows.append({
            "player_id": int(pid),
            "season": str(r["season"]),
            "play_type": str(r["play_type"]),
            "freq_pct": float(freq),
            "ppp": float(ppp_val) if ppp_val is not None else 0.0,
        })

    df = pd.DataFrame(out_rows, columns=["player_id", "season", "play_type",
                                         "freq_pct", "ppp"])
    df.to_parquet(OUT_PATH, index=False)
    print(f"\n[done] {len(df)} rows -> {OUT_PATH}", flush=True)
    print(f"distinct players= {df['player_id'].nunique()}")
    if failed:
        print(f"FAILED play types: {failed}")
    sga = df[df["player_id"] == 1628983]
    if len(sga):
        top = sga.sort_values("freq_pct", ascending=False).iloc[0]
        print(f"sanity SGA(1628983): {len(sga)} play_types; "
              f"top={top['play_type']} freq_pct={top['freq_pct']} ppp={top['ppp']}")
    else:
        print("sanity SGA(1628983): NOT in playtypes table")
    print(f"final cols: {list(df.columns)}")


if __name__ == "__main__":
    main()
