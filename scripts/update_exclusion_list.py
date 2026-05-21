"""
update_exclusion_list.py — Compute 14-day rolling MAE per player and write
high-error players to config/exclusion_list.yaml.

Data sources (tried in order):
  1. data/predictions/scored/<date>_scored.json — produced by prediction_tracker
  2. data/output/slate_<YYYYMMDD>.json          — daily slate files with projections

Each scored file has the shape written by prediction_tracker.score_predictions():
  {
    "date": "YYYY-MM-DD",
    "clv_entries": [
        {"player_id": str, "player_name": str, "stat": str,
         "actual": float, "line": float, "edge_pct": float, ...},
        ...
    ]
  }

A player is excluded when their per-stat MAE (averaged over the rolling window)
exceeds ``mae_threshold`` for ANY stat.

Usage:
    python scripts/update_exclusion_list.py [--window 14] [--threshold 8.0] [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import yaml

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

log = logging.getLogger(__name__)

_SCORED_DIR = os.path.join(PROJECT_DIR, "data", "predictions", "scored")
_OUTPUT_DIR = os.path.join(PROJECT_DIR, "data", "output")
_CONFIG_DIR = os.path.join(PROJECT_DIR, "config")
_EXCLUSION_PATH = os.path.join(_CONFIG_DIR, "exclusion_list.yaml")

_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _date_in_window(date_str: str, cutoff: datetime.date) -> bool:
    """Return True when date_str (YYYY-MM-DD) is >= cutoff."""
    try:
        d = datetime.date.fromisoformat(date_str[:10])
        return d >= cutoff
    except ValueError:
        return False


def _load_scored_files(cutoff: datetime.date) -> List[dict]:
    """Load all scored JSON files within the rolling window."""
    if not os.path.isdir(_SCORED_DIR):
        return []
    entries = []
    for fname in os.listdir(_SCORED_DIR):
        if not fname.endswith("_scored.json"):
            continue
        date_part = fname.replace("_scored.json", "")
        if not _date_in_window(date_part, cutoff):
            continue
        fpath = os.path.join(_SCORED_DIR, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                entries.append(json.load(f))
        except Exception as exc:
            log.warning("Skipping %s: %s", fname, exc)
    return entries


def _load_slate_files(cutoff: datetime.date) -> List[dict]:
    """
    Load slate output files within the rolling window.

    Slate files don't carry actuals; they are used only if scored files
    are unavailable. Returns raw slate dicts for callers to handle.
    """
    if not os.path.isdir(_OUTPUT_DIR):
        return []
    slates = []
    for fname in os.listdir(_OUTPUT_DIR):
        if not fname.startswith("slate_") or not fname.endswith(".json"):
            continue
        # slate_YYYYMMDD.json
        compact = fname[len("slate_"):-len(".json")]
        if len(compact) == 8:
            date_str = f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"
        else:
            continue
        if not _date_in_window(date_str, cutoff):
            continue
        fpath = os.path.join(_OUTPUT_DIR, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                slates.append(json.load(f))
        except Exception as exc:
            log.warning("Skipping slate %s: %s", fname, exc)
    return slates


# ---------------------------------------------------------------------------
# MAE computation
# ---------------------------------------------------------------------------

PlayerStatErrors = Dict[str, Dict[str, List[float]]]
# shape: { player_id_str -> { stat -> [abs_errors] } }


def _collect_errors_from_scored(
    scored_files: List[dict],
) -> PlayerStatErrors:
    """Extract per-player per-stat absolute errors from scored files."""
    errors: PlayerStatErrors = defaultdict(lambda: defaultdict(list))
    for sf in scored_files:
        for entry in sf.get("clv_entries", []):
            raw_pid = entry.get("player_id")
            raw_stat = entry.get("stat")
            actual = entry.get("actual")
            line = entry.get("line")
            if raw_pid is None or raw_stat is None or actual is None or line is None:
                continue
            pid = str(raw_pid).strip()
            stat = str(raw_stat).strip()
            if not pid or not stat:
                continue
            try:
                errors[pid][stat].append(abs(float(actual) - float(line)))
            except (TypeError, ValueError):
                pass
    return errors


def compute_rolling_mae(
    window_days: int = 14,
) -> Dict[str, Dict[str, float]]:
    """
    Compute per-player per-stat MAE over the rolling window.

    Args:
        window_days: How many days back to look (default 14).

    Returns:
        Dict mapping player_id (str) -> {stat -> mae_float}.
        Only players/stats with at least one observation are included.
    """
    cutoff = datetime.date.today() - datetime.timedelta(days=window_days)
    scored_files = _load_scored_files(cutoff)
    log.info("Loaded %d scored files within %d-day window", len(scored_files), window_days)

    errors = _collect_errors_from_scored(scored_files)

    mae: Dict[str, Dict[str, float]] = {}
    for pid, stat_errors in errors.items():
        mae[pid] = {}
        for stat, abs_errs in stat_errors.items():
            if abs_errs:
                mae[pid][stat] = round(sum(abs_errs) / len(abs_errs), 4)
    return mae


# ---------------------------------------------------------------------------
# Exclusion list derivation
# ---------------------------------------------------------------------------

def _player_name_from_scored(scored_files: List[dict], player_id: str) -> str:
    """Best-effort lookup of a player's display name from scored files."""
    for sf in scored_files:
        for entry in sf.get("clv_entries", []):
            if str(entry.get("player_id", "")) == player_id:
                name = entry.get("player_name") or ""
                if name:
                    return str(name)
    return player_id


def build_exclusion_list(
    mae: Dict[str, Dict[str, float]],
    threshold: float,
    scored_files: List[dict],
) -> List[dict]:
    """
    Return players whose max per-stat MAE exceeds the threshold.

    Args:
        mae:          Output of compute_rolling_mae().
        threshold:    MAE cutoff (inclusive) for exclusion.
        scored_files: Source files used for player-name lookup.

    Returns:
        List of dicts: [{player_id, player_name, mae, stat}, ...],
        sorted descending by mae.
    """
    excluded = []
    for pid, stat_maes in mae.items():
        if not stat_maes:
            continue
        worst_stat = max(stat_maes, key=lambda s: stat_maes[s])
        worst_mae = stat_maes[worst_stat]
        if worst_mae >= threshold:
            excluded.append({
                "player_id": int(pid) if pid.lstrip("-").isdigit() else pid,
                "player_name": _player_name_from_scored(scored_files, pid),
                "mae": worst_mae,
                "stat": worst_stat,
            })
    excluded.sort(key=lambda r: r["mae"], reverse=True)
    return excluded


# ---------------------------------------------------------------------------
# YAML writer
# ---------------------------------------------------------------------------

def write_exclusion_yaml(
    excluded: List[dict],
    window_days: int,
    threshold: float,
    output_path: str = _EXCLUSION_PATH,
) -> None:
    """
    Write the exclusion list YAML file.

    Args:
        excluded:    List of exclusion dicts from build_exclusion_list().
        window_days: Rolling window used.
        threshold:   MAE threshold used.
        output_path: Destination file path.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    payload = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "window_days": window_days,
        "mae_threshold": threshold,
        "excluded_players": excluded,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, default_flow_style=False, sort_keys=False)
    log.info("Wrote %d excluded players -> %s", len(excluded), output_path)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def update_exclusion_list(
    window_days: int = 14,
    threshold: float = 8.0,
    dry_run: bool = False,
    output_path: str = _EXCLUSION_PATH,
) -> Tuple[List[dict], Dict[str, Dict[str, float]]]:
    """
    Compute rolling MAE and update config/exclusion_list.yaml.

    Args:
        window_days:  Rolling window in days (default 14).
        threshold:    Per-stat MAE cutoff for exclusion (default 8.0).
        dry_run:      If True, compute but do not write the YAML.
        output_path:  Destination YAML file path.

    Returns:
        (excluded_players, mae_by_player)
    """
    mae = compute_rolling_mae(window_days=window_days)

    cutoff = datetime.date.today() - datetime.timedelta(days=window_days)
    scored_files = _load_scored_files(cutoff)

    excluded = build_exclusion_list(mae, threshold, scored_files)

    if dry_run:
        log.info("dry-run: would exclude %d players", len(excluded))
    else:
        write_exclusion_yaml(excluded, window_days, threshold, output_path)

    return excluded, mae


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Compute 14-day rolling MAE per player and update exclusion list."
    )
    p.add_argument("--window", type=int, default=14,
                   help="Rolling window in days (default: 14)")
    p.add_argument("--threshold", type=float, default=8.0,
                   help="MAE threshold for exclusion (default: 8.0)")
    p.add_argument("--dry-run", action="store_true",
                   help="Compute but do not write config/exclusion_list.yaml")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Enable DEBUG logging")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    excluded, mae = update_exclusion_list(
        window_days=args.window,
        threshold=args.threshold,
        dry_run=args.dry_run,
    )
    print(f"Players evaluated: {len(mae)}")
    print(f"Players excluded (MAE >= {args.threshold}): {len(excluded)}")
    if excluded:
        print("\nExcluded players:")
        for row in excluded:
            print(f"  {row['player_name']:<30} stat={row['stat']:<6} "
                  f"mae={row['mae']:.2f}")


if __name__ == "__main__":
    main()
