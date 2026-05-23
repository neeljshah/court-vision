"""
scripts/build_coach_history.py — Build and cache coach aggregate stats.

Fetches NBA API TeamGameLog for each team × season, maps to head coach,
aggregates pace/efficiency/style stats, and writes data/models/coach_history.json.

Usage:
    python scripts/build_coach_history.py [--seasons 2022-23 2023-24 2024-25]
    python scripts/build_coach_history.py --seasons 2024-25
"""

import argparse
import json
import logging
import os
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build coach history cache")
    parser.add_argument(
        "--seasons",
        nargs="+",
        default=["2022-23", "2023-24", "2024-25"],
        help="NBA season strings to process",
    )
    args = parser.parse_args()

    log.info("Building coach history for seasons: %s", args.seasons)

    from src.features.coach_features import build_coach_history

    df = build_coach_history(seasons=args.seasons)

    if df.empty:
        log.warning("No data returned — nba_api may be unavailable. "
                    "Hard-coded fallback map is active for get_coach_features().")
        return

    log.info("Built history for %d coach records", len(df))

    # ── Report top 5 by pace ────────────────────────────────────────────────
    if "coach_avg_pace" in df.columns and "coach" in df.columns:
        top_pace = df.nlargest(5, "coach_avg_pace")[["coach", "coach_avg_pace", "coach_games_coached"]]
        log.info("\nTop 5 Highest-Pace Coaches:\n%s", top_pace.to_string(index=False))
    else:
        log.info("coach_avg_pace column not available in returned df")

    # ── Report top 5 by 3PA rate ───────────────────────────────────────────
    if "coach_3pa_rate" in df.columns and "coach" in df.columns:
        top_3pa = df.nlargest(5, "coach_3pa_rate")[["coach", "coach_3pa_rate", "coach_games_coached"]]
        log.info("\nTop 5 Highest 3PA Rate Coaches:\n%s", top_3pa.to_string(index=False))

    # ── Verify cache file written ──────────────────────────────────────────
    cache_path = os.path.join(PROJECT_DIR, "data", "models", "coach_history.json")
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            cached = json.load(f)
        log.info("coach_history.json: %d coaches cached at %s", len(cached), cache_path)
    else:
        log.warning("Cache file not found at %s", cache_path)


if __name__ == "__main__":
    main()
