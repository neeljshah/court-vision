"""
post_tracking_enrich.py — Post-tracking enrichment for Phase G games.

Runs after run_phase_g.py completes. For each processed game:
  1. Load tracking_data.csv
  2. Run feature engineering → features.csv
  3. Enrich with NBA PBP/possession outcomes
  4. Register CV spatial aggregates in cv_feature_bridge

Usage:
    python scripts/post_tracking_enrich.py [--dry-run] [--game-id GAME_ID]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.features.feature_engineering import run as run_features  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_DATA_DIR = os.path.join(PROJECT_DIR, "data")
_PROCESSED_LIST = os.path.join(_DATA_DIR, "phase_g_processed.txt")
_TRACKING_BASE = os.path.join(_DATA_DIR, "tracking")


# ── per-game enrichment ───────────────────────────────────────────────────────

def _enrich_with_nba(df: pd.DataFrame, game_id: str) -> pd.DataFrame:
    """
    Join per-game possessions.csv outcome columns onto the features DataFrame.

    Matches on possession_id. Adds: result, pbp_play_type, pbp_period,
    pbp_matched, score_diff. Skips silently if possessions.csv absent.
    """
    poss_path = os.path.join(_TRACKING_BASE, game_id, "possessions.csv")
    if not os.path.exists(poss_path):
        log.debug("%s: no possessions.csv, skipping NBA enrichment", game_id)
        return df

    try:
        poss = pd.read_csv(poss_path, low_memory=False)
    except Exception as exc:
        log.warning("%s: possessions.csv read error: %s", game_id, exc)
        return df

    outcome_cols = [c for c in (
        "possession_id", "result", "pbp_play_type", "pbp_period",
        "pbp_matched", "score_diff", "outcome_score",
    ) if c in poss.columns]

    if "possession_id" not in outcome_cols:
        return df
    if "possession_id" not in df.columns:
        return df

    poss_slim = poss[outcome_cols].drop_duplicates("possession_id")
    merged = df.merge(poss_slim, on="possession_id", how="left", suffixes=("", "_poss"))
    log.debug("%s: NBA enrichment joined %d poss rows", game_id, len(poss_slim))
    return merged


def _enrich_with_cv(df: pd.DataFrame, game_id: str, register: bool = True) -> pd.DataFrame:
    """
    Aggregate per-player spatial features and write to cv_registry/{game_id}.json.

    The cv_feature_bridge reads per-game features.csv (after the path fix in
    cv_feature_bridge.py). This step also writes a compact JSON summary for
    quick lookup without loading the full CSV.

    Args:
        register: When True, write cv_registry JSON and update flat features.csv
                  symlink used by the bridge's backward-compat fallback.
    """
    _CV_COLS = {
        "defender_dist_mean_90": "cvb_avg_defender_dist",
        "team_spacing":          "cvb_avg_spacing",
        "velocity":              "cvb_avg_velocity",
        "dist_traveled_90":      "cvb_fatigue_score",
        "paint_pressure_90":     "cvb_paint_time_pct",
        "off_ball_dist_mean_90": "cvb_off_ball_dist",
    }
    present = [c for c in _CV_COLS if c in df.columns]
    if not present or "player_name" not in df.columns:
        log.debug("%s: CV cols absent, skipping cv registration", game_id)
        return df

    registry: dict = {}
    for name, grp in df.groupby("player_name"):
        name_str = str(name).strip()
        if not name_str or name_str.lower() in ("nan", "none", ""):
            continue
        entry: dict = {}
        for csv_col, out_key in _CV_COLS.items():
            if csv_col not in grp.columns:
                continue
            vals = pd.to_numeric(grp[csv_col], errors="coerce").dropna()
            vals = vals[vals != 0.0]
            if len(vals):
                entry[out_key] = round(float(vals.mean()), 4)
        if entry:
            registry[name_str.lower()] = entry

    if register and registry:
        reg_dir = os.path.join(_DATA_DIR, "cv_registry")
        os.makedirs(reg_dir, exist_ok=True)
        reg_path = os.path.join(reg_dir, f"{game_id}.json")
        try:
            with open(reg_path, "w") as f:
                json.dump(registry, f, indent=2)
            log.debug("%s: cv_registry written (%d players)", game_id, len(registry))
        except Exception as exc:
            log.warning("%s: cv_registry write failed: %s", game_id, exc)

    return df


def _process_game(game_id: str, dry_run: bool = False) -> dict:
    """Run the 4-step enrichment pipeline for a single game. Returns status dict."""
    tracking_csv = os.path.join(_TRACKING_BASE, game_id, "tracking_data.csv")
    features_csv = os.path.join(_TRACKING_BASE, game_id, "features.csv")

    if not os.path.exists(tracking_csv):
        return {"game_id": game_id, "status": "skip", "reason": "no tracking_data.csv"}

    if dry_run:
        return {"game_id": game_id, "status": "dry-run", "rows": 0}

    try:
        # Step 1+2: load + feature engineering
        df = run_features(input_path=tracking_csv, output_path=features_csv)
        rows = len(df)

        # Step 3: NBA enrichment (join possession outcomes)
        df = _enrich_with_nba(df, game_id)

        # Step 4: CV registration
        df = _enrich_with_cv(df, game_id, register=True)

        # Overwrite features.csv with enriched version
        df.to_csv(features_csv, index=False)

        return {"game_id": game_id, "status": "ok", "rows": rows}

    except Exception as exc:
        log.exception("%s: enrichment failed: %s", game_id, exc)
        return {"game_id": game_id, "status": "error", "reason": str(exc)}


# ── main ──────────────────────────────────────────────────────────────────────

def _load_game_ids(single: Optional[str], all_missing: bool = False) -> list[str]:
    if single:
        return [single]
    if not os.path.exists(_PROCESSED_LIST):
        log.error("processed list not found: %s", _PROCESSED_LIST)
        return []
    with open(_PROCESSED_LIST) as f:
        ids = [ln.strip() for ln in f if ln.strip()]
    if all_missing:
        ids = [
            g for g in ids
            if not os.path.exists(os.path.join(_TRACKING_BASE, g, "features.csv"))
        ]
        log.info("--all-missing: %d games without features.csv", len(ids))
    return ids


def main() -> None:
    ap = argparse.ArgumentParser(description="Post-tracking enrichment for Phase G games")
    ap.add_argument("--dry-run", action="store_true", help="Check paths only, do not write")
    ap.add_argument("--game-id", metavar="ID", help="Process a single game instead of processed list")
    ap.add_argument("--all-missing", action="store_true", help="Only process games without features.csv")
    ap.add_argument("--workers", type=int, default=4, help="ThreadPoolExecutor workers (default 4)")
    args = ap.parse_args()

    game_ids = _load_game_ids(args.game_id, all_missing=args.all_missing)
    if not game_ids:
        log.error("No game IDs to process.")
        sys.exit(1)

    log.info("Enriching %d games with %d workers (dry_run=%s)", len(game_ids), args.workers, args.dry_run)

    results = {"ok": 0, "skip": 0, "error": 0, "dry-run": 0}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_process_game, gid, args.dry_run): gid for gid in game_ids}
        for fut in as_completed(futures):
            res = fut.result()
            status = res.get("status", "error")
            results[status] = results.get(status, 0) + 1
            if status == "ok":
                log.info("  ✓ %s  rows=%s", res["game_id"], res.get("rows", "?"))
            elif status == "error":
                log.warning("  ✗ %s  %s", res["game_id"], res.get("reason", ""))
            else:
                log.debug("  - %s  %s", res["game_id"], status)

    log.info("Done. ok=%d  skip=%d  error=%d", results["ok"], results["skip"], results["error"])
    if results["error"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
