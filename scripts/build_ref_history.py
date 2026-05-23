"""
build_ref_history.py — Build per-referee tendency profiles from cached boxscores.

Walks data/nba/boxscore_*.json, fetches officials for each game via
BoxScoreSummaryV2 (with per-game caching), and saves aggregated profiles
to data/models/ref_history.json.

Usage:
    conda run -n basketball_ai python scripts/build_ref_history.py
    conda run -n basketball_ai python scripts/build_ref_history.py --limit 200
    conda run -n basketball_ai python scripts/build_ref_history.py --dry-run
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("build_ref_history")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build referee tendency history.")
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Max boxscore files to process (0 = all)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print stats without saving to disk",
    )
    args = parser.parse_args()

    from src.features.referee_features import (
        _NBA_CACHE, _OFFICIALS_DIR, _HISTORY_PATH,
        _extract_game_stats, get_referees,
    )
    import pandas as pd

    # ── scan boxscores ────────────────────────────────────────────────────────
    boxscore_files = sorted(glob.glob(os.path.join(_NBA_CACHE, "boxscore_*.json")))
    if args.limit:
        boxscore_files = boxscore_files[:args.limit]

    log.info("Scanning %d boxscore files...", len(boxscore_files))

    game_stats: dict = {}
    for fpath in boxscore_files:
        stats = _extract_game_stats(fpath)
        if stats:
            game_stats[stats["game_id"]] = stats

    log.info("%d games with valid score data", len(game_stats))

    # ── fetch officials ───────────────────────────────────────────────────────
    ref_games: dict = {}
    ref_names: dict = {}
    processed = skipped = api_calls = 0

    total = len(game_stats)
    for idx, (game_id, stats) in enumerate(game_stats.items()):
        # Progress heartbeat every 50 games
        if idx % 50 == 0:
            log.info("  Progress: %d/%d games (%.0f%%)  |  refs found: %d",
                     idx, total, 100 * idx / max(total, 1), len(ref_games))

        officials_cache = os.path.join(_OFFICIALS_DIR, f"{game_id}.json")
        if not os.path.exists(officials_cache):
            api_calls += 1

        refs = get_referees(game_id)
        if not refs:
            skipped += 1
            continue

        for ref in refs:
            rid  = int(ref.get("id", 0))
            name = str(ref.get("name", "")).strip()
            if rid == 0 and not name:
                continue
            if rid not in ref_games:
                ref_games[rid]  = []
                ref_names[rid]  = name
            ref_games[rid].append(stats)
        processed += 1

    log.info(
        "Done: %d games processed, %d skipped, %d NBA API calls made",
        processed, skipped, api_calls,
    )
    log.info("Unique referees found: %d", len(ref_games))

    if not ref_games:
        log.error("No referee data found — check officials cache or NBA API connectivity")
        sys.exit(1)

    # ── aggregate ─────────────────────────────────────────────────────────────
    rows = []
    for rid, g_list in ref_games.items():
        n = len(g_list)
        rows.append({
            "ref_id":            rid,
            "ref_name":          ref_names[rid],
            "games_officiated":  n,
            "avg_game_total":    sum(g["total_pts"] for g in g_list) / n,
            "avg_pace":          sum(g["pace_proxy"] for g in g_list) / n,
            "avg_fta_per_team":  sum(g["avg_fta"]   for g in g_list) / n,
            "avg_pf_per_team":   sum(g["avg_pf"]    for g in g_list) / n,
            "home_win_pct":      sum(g["home_win"]   for g in g_list) / n,
        })

    df = pd.DataFrame(rows).sort_values("games_officiated", ascending=False)

    # ── leaderboards ──────────────────────────────────────────────────────────
    min_games = 3  # Filter refs with meaningful sample

    qualified = df[df["games_officiated"] >= min_games].copy()

    print("\n" + "=" * 65)
    print(f"  REFEREE TENDENCY LEADERBOARDS  (min {min_games} games)")
    print("=" * 65)

    print(f"\n{'TOP 5 OVER-TOTAL REFS (highest avg game total)':}")
    top_total = qualified.nlargest(5, "avg_game_total")[
        ["ref_name", "games_officiated", "avg_game_total"]
    ]
    for _, r in top_total.iterrows():
        print(f"  {r['ref_name']:<28}  {int(r['games_officiated']):3d}g  "
              f"avg total={r['avg_game_total']:.1f}")

    print(f"\n{'TOP 5 HOME-WIN-PCT REFS':}")
    top_home = qualified.nlargest(5, "home_win_pct")[
        ["ref_name", "games_officiated", "home_win_pct"]
    ]
    for _, r in top_home.iterrows():
        print(f"  {r['ref_name']:<28}  {int(r['games_officiated']):3d}g  "
              f"home_win%={r['home_win_pct']:.3f}")

    print(f"\n{'TOP 5 LOW-FOUL REFS (lowest avg PF per team)':}")
    top_low_foul = qualified.nsmallest(5, "avg_pf_per_team")[
        ["ref_name", "games_officiated", "avg_pf_per_team", "avg_fta_per_team"]
    ]
    for _, r in top_low_foul.iterrows():
        print(f"  {r['ref_name']:<28}  {int(r['games_officiated']):3d}g  "
              f"avg_pf={r['avg_pf_per_team']:.1f}  avg_fta={r['avg_fta_per_team']:.1f}")

    print(f"\nTotal unique refs: {len(df)}  |  Games covered: {processed}")
    print("=" * 65 + "\n")

    # ── persist ───────────────────────────────────────────────────────────────
    if args.dry_run:
        log.info("--dry-run: skipping save")
    else:
        os.makedirs(os.path.dirname(_HISTORY_PATH), exist_ok=True)
        df.to_json(_HISTORY_PATH, orient="records", indent=2)
        log.info("Saved → %s", _HISTORY_PATH)


if __name__ == "__main__":
    main()
