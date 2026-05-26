"""probe_R25_R1_pregame_backfill.py — verify the 2025-26 backfill.

Reads the backfilled ``data/nba/season_games_2025-26.json`` and the
backup ``...bak_R25_R1``, then reports:
  * before/after row count
  * per-column non-null count (before vs after) for the 18 core team-
    rating features that R24_Q3 needed
  * 5 random rows spot-checked for plausibility (ortg ∈ [95, 130],
    pace ∈ [90, 110], elo ∈ [1200, 1800])
  * SHIP vs PARTIAL verdict

Persists machine-readable results to ``data/cache/probe_R25_R1_results.json``.
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_OUT = os.path.join(PROJECT_DIR, "data", "nba", "season_games_2025-26.json")
_BAK = _OUT + ".bak_R25_R1"
_RESULTS = os.path.join(PROJECT_DIR, "data", "cache",
                        "probe_R25_R1_results.json")

# 18 columns R24_Q3 needs to retrain m2_family on fresh 2025-26 data.
_CORE_COLS = [
    "home_off_rtg", "home_def_rtg", "home_pace", "home_net_rtg",
    "home_efg_pct", "home_tov_pct",
    "home_off_rtg_L10", "home_def_rtg_L10",
    "away_off_rtg", "away_def_rtg", "away_pace", "away_net_rtg",
    "away_efg_pct", "away_tov_pct",
    "away_off_rtg_L10", "away_def_rtg_L10",
    "elo_differential", "net_rtg_diff",
]


def _load(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
    except Exception:
        return []
    return p["rows"] if isinstance(p, dict) else (p if isinstance(p, list) else [])


def _count_populated(rows: list) -> dict:
    out = {}
    for c in _CORE_COLS:
        out[c] = sum(1 for r in rows if r.get(c) is not None)
    return out


def _spot_check(rows: list, n: int = 5, seed: int = 42) -> list:
    """Pick n random enriched rows from the mid/late season and check
    that the headline ratings sit in NBA-plausible ranges."""
    rng = random.Random(seed)
    mid = [r for r in rows
           if r.get("home_team") and r.get("home_off_rtg") is not None
           and r.get("game_date", "") >= "2025-12-01"]
    if len(mid) < n:
        return []
    picks = rng.sample(mid, n)
    out = []
    for r in picks:
        checks = {
            "ortg_ok":  95.0 <= float(r["home_off_rtg"]) <= 130.0,
            "drtg_ok":  95.0 <= float(r["home_def_rtg"]) <= 130.0,
            "pace_ok":  90.0 <= float(r["home_pace"]) <= 110.0,
            "elo_ok":   1200.0 <= float(r["home_elo"]) <= 1800.0,
            "efg_ok":   0.40 <= float(r["home_efg_pct"]) <= 0.65,
        }
        out.append({
            "game_id":  r["game_id"],
            "date":     r["game_date"],
            "matchup":  f"{r['away_team']}@{r['home_team']}",
            "home_off_rtg": r["home_off_rtg"],
            "home_def_rtg": r["home_def_rtg"],
            "home_pace":    r["home_pace"],
            "home_elo":     r["home_elo"],
            "home_efg_pct": r["home_efg_pct"],
            "checks":   checks,
            "all_pass": all(checks.values()),
        })
    return out


def main() -> int:
    print("=== R25_R1 probe: pregame feature backfill ===")
    before = _load(_BAK)
    after = _load(_OUT)
    print(f"  backup (before): {len(before)} rows from {_BAK}")
    print(f"  current (after): {len(after)} rows from {_OUT}")

    cnt_before = _count_populated(before)
    cnt_after = _count_populated(after)
    print()
    print(f"  {'column':<28} {'before':>8} {'after':>8} {'delta':>8}")
    for c in _CORE_COLS:
        b, a = cnt_before[c], cnt_after[c]
        print(f"  {c:<28} {b:>8} {a:>8} {a - b:>+8}")

    spot = _spot_check(after)
    print()
    print(f"  spot check (5 random mid-season rows):")
    for s in spot:
        flag = "OK" if s["all_pass"] else "FAIL"
        print(f"    [{flag}] {s['date']} {s['matchup']:<10}"
              f" ortg={s['home_off_rtg']:.1f} drtg={s['home_def_rtg']:.1f}"
              f" pace={s['home_pace']:.1f} elo={s['home_elo']:.0f}"
              f" efg={s['home_efg_pct']:.3f}")

    enriched_after = cnt_after.get("home_off_rtg", 0)
    spot_pass = sum(1 for s in spot if s["all_pass"])

    if enriched_after >= 1000 and spot_pass == len(spot) and len(spot) >= 5:
        status = "SHIP"
    elif enriched_after >= 500:
        status = "PARTIAL"
    else:
        status = "REJECT"

    results = {
        "status":             status,
        "timestamp":          datetime.utcnow().isoformat() + "Z",
        "rows_before":        len(before),
        "rows_after":         len(after),
        "populated_before":   cnt_before,
        "populated_after":    cnt_after,
        "core_cols":          _CORE_COLS,
        "spot_check":         spot,
        "rows_backfilled":    enriched_after,
        "rows_target":        1230,
        "summary":            (
            f"{enriched_after}/1230 rows have non-null home_off_rtg "
            f"(target ≥1000). Spot check: {spot_pass}/{len(spot)} rows "
            f"in plausible NBA ranges."
        ),
    }
    os.makedirs(os.path.dirname(_RESULTS), exist_ok=True)
    with open(_RESULTS, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print()
    print(f"  status: {status}")
    print(f"  results -> {_RESULTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
