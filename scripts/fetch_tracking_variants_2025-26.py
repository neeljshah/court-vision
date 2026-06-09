"""fetch_tracking_variants_2025-26.py — write the 2025-26 per-variant tracking
JSONs that build_player_tracking_features.py expects.

The Jun-2 refresh wrote a single combined parquet (player_tracking_2025-26.parquet)
which the features builder never reads. This emits the canonical per-variant
JSONs (Drives / Passing / CatchShoot) in the exact lowercase schema of the
2021-22..2024-25 files so a plain features rebuild picks up 2025-26.

    python scripts/fetch_tracking_variants_2025-26.py
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.data import nba_api_headers_patch  # noqa: F401,E402  (installs working headers)

SEASON = "2025-26"
DATA_NBA = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "nba"
)
MEASURES = ["Drives", "Passing", "CatchShoot"]


def fetch_one(measure: str) -> list[dict]:
    from nba_api.stats.endpoints import leaguedashptstats

    last_err = None
    for attempt in range(3):
        try:
            df = leaguedashptstats.LeagueDashPtStats(
                season=SEASON,
                season_type_all_star="Regular Season",
                pt_measure_type=measure,
                player_or_team="Player",
                per_mode_simple="PerGame",
                timeout=60,
            ).get_data_frames()[0]
            time.sleep(0.6)
            df.columns = [c.lower() for c in df.columns]
            rows = df.to_dict(orient="records")
            for r in rows:
                r["_season"] = SEASON
                r["_measure"] = measure
            print(f"  {measure}: {len(rows)} rows", flush=True)
            return rows
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"  [retry {attempt}] {measure}: {e}", flush=True)
            time.sleep(6 + attempt * 4)
    print(f"  [FAIL] {measure}: {last_err}", flush=True)
    return []


def main() -> None:
    for measure in MEASURES:
        rows = fetch_one(measure)
        if not rows:
            print(f"[skip-write] {measure} (no rows)")
            continue
        out = os.path.join(DATA_NBA, f"player_tracking_{measure}_{SEASON}.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(rows, fh)
        # sanity: Harper 1642844 + Castle 1642264
        for pid, nm in [(1642844, "Harper"), (1642264, "Castle")]:
            hit = next((r for r in rows if r.get("player_id") == pid), None)
            tag = "OK" if hit else "MISSING"
            print(f"    {measure} {nm}: {tag}")
        print(f"  -> {out}")


if __name__ == "__main__":
    main()
