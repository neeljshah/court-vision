"""probe_player_tracking_pergame.py — cycle 78b (loop 5) research probe.

Pulls boxscoreplayertrackv3 (per-game) for ~12 recent games and prints
per-game tracking rows for LeBron, Jokic, and Curry. Goal: confirm the v3
endpoint returns true per-game data (not season aggregates), measure
game-to-game variance, and decide whether wiring last-N tracking trends
into prop_pergame is worth a real cycle.

NO production code is modified. Pure read-only research.

Notes:
- boxscoreplayertrackv2 returns empty payload from stats.nba.com (same
  failure mode as boxscoreadvancedv2, documented in
  scripts/fetch_advanced_boxscores.py). v3 works.
- Cache writes to data/nba/playertrackv3_<game_id>.json (perpetual: per-game
  historical data is immutable).
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from typing import Dict, List

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data import nba_api_headers_patch  # noqa: F401, E402

_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "nba")
_OUT_DIR = os.path.join(PROJECT_DIR, "scripts", "_results")

# Stars to track across games (personId from nba_api).
_TARGETS = {
    2544: "LeBron James",
    203999: "Nikola Jokic",
    201939: "Stephen Curry",
}

# Wider slate of 2024-25 regular-season games — ensures each star plays in
# several of them. Chosen by sweeping every 50 games across the season.
# Step through every 4th game to hit ~25 different team matchups — wider net
# guarantees several games per star.
_GAME_IDS = [f"00224000{n:02d}" for n in range(1, 100, 4)] + \
            [f"00224001{n:02d}" for n in range(1, 100, 4)] + \
            [f"00224002{n:02d}" for n in range(1, 100, 4)]


def fetch_game(game_id: str) -> List[Dict]:
    """Return list of per-player tracking rows for one game."""
    cache_path = os.path.join(_CACHE_DIR, f"playertrackv3_{game_id}.json")
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)
    from nba_api.stats.endpoints import boxscoreplayertrackv3
    last_err = None
    for attempt in range(3):
        try:
            resp = boxscoreplayertrackv3.BoxScorePlayerTrackV3(
                game_id=game_id, timeout=60,
            )
            df = resp.get_data_frames()[0]
            rows = [
                {k: v for k, v in r.items()} for r in df.to_dict("records")
            ]
            with open(cache_path, "w") as f:
                json.dump(rows, f, default=str)
            return rows
        except Exception as e:
            last_err = e
            time.sleep(1 + attempt)
    print(f"  [warn] {game_id} failed after retries: {last_err}")
    return []


def main() -> None:
    os.makedirs(_OUT_DIR, exist_ok=True)
    print(f"[probe] fetching {len(_GAME_IDS)} games via boxscoreplayertrackv3 ...")
    all_rows: List[Dict] = []
    star_rows: Dict[int, List[Dict]] = {pid: [] for pid in _TARGETS}
    for gid in _GAME_IDS:
        time.sleep(0.6)
        rows = fetch_game(gid)
        print(f"  {gid}: {len(rows)} player rows")
        for r in rows:
            pid = int(r.get("personId") or 0)
            r["_game_id"] = gid
            all_rows.append(r)
            if pid in star_rows:
                star_rows[pid].append(r)

    if not all_rows:
        print("[fail] no rows fetched")
        return

    # Schema dump (first row).
    print("\n[schema] columns from one row:")
    for k, v in all_rows[0].items():
        print(f"  {k!s:<36} = {v!r}")

    # Per-game star tables.
    cols = (
        "minutes", "speed", "distance", "touches", "passes", "assists",
        "secondaryAssists", "freeThrowAssists",
        "contestedFieldGoalsAttempted", "uncontestedFieldGoalsAttempted",
        "reboundChancesTotal", "defendedAtRimFieldGoalsAttempted",
    )
    print("\n[per-game star rows]")
    for pid, name in _TARGETS.items():
        rs = star_rows[pid]
        if not rs:
            print(f"  {name} (id {pid}): NO ROWS FOUND in this slate")
            continue
        print(f"\n  -- {name} (id {pid}) -- {len(rs)} games --")
        hdr = "  game_id     " + "  ".join(
            f"{c[:6]:>7s}" for c in cols
        )
        print(hdr)
        for r in rs:
            vals: List[str] = []
            for c in cols:
                v = r.get(c)
                if isinstance(v, (int, float)):
                    vals.append(f"{float(v):>7.2f}")
                elif isinstance(v, str):
                    vals.append(f"{v:>7s}")
                else:
                    vals.append(f"{'NaN':>7s}")
            print(f"  {r['_game_id']}  " + "  ".join(vals))

    # Variance: coefficient of variation for game-to-game noise sense.
    print("\n[variance] coefficient of variation (stdev/mean) across games per star:")
    metric_cols = (
        "speed", "distance", "touches", "passes",
        "contestedFieldGoalsAttempted", "reboundChancesTotal",
    )
    for pid, name in _TARGETS.items():
        rs = star_rows[pid]
        if len(rs) < 2:
            continue
        print(f"\n  {name}:")
        for c in metric_cols:
            vals = [float(r.get(c) or 0.0) for r in rs]
            mean = statistics.mean(vals)
            stdev = statistics.stdev(vals) if len(vals) > 1 else 0.0
            cov = (stdev / mean) if mean else float("nan")
            print(f"    {c:<32} n={len(vals)}  mean={mean:7.2f}  stdev={stdev:6.2f}  CoV={cov:.3f}")


if __name__ == "__main__":
    main()
