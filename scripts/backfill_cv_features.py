"""
backfill_cv_features.py — Register CV features from existing tracking game directories.

Reads all game directories under data/tracking/ and data/games/, extracts
per-player CV features via tracking_feature_extractor, resolves player_name
→ real NBA player_id using cached player_avgs, then writes to cv_features DB.

Usage:
    conda activate basketball_ai
    python scripts/backfill_cv_features.py
    python scripts/backfill_cv_features.py --dry-run
    python scripts/backfill_cv_features.py --game-id 0022500757

Only registers players whose slot names map to a known NBA player_id.
Skips games already registered (idempotent).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import unicodedata
from pathlib import Path
from typing import Dict, Optional

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

DATA_DIR    = PROJECT_DIR / "data"
TRACKING_DIR = DATA_DIR / "tracking"
GAMES_DIR   = DATA_DIR / "games"
NBA_CACHE   = DATA_DIR / "nba"

# Seasons to look up player → NBA ID mappings (newest first)
_LOOKUP_SEASONS = ["2025-26", "2024-25", "2023-24"]
# Cache file candidates per season (checked in order)
_CACHE_PATTERNS = ["player_full_{season}.json", "player_avgs_{season}.json"]


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()


def _build_name_to_id_map() -> Dict[str, int]:
    """Build player_name → NBA player_id from cached player stats files."""
    result: Dict[str, int] = {}
    for season in _LOOKUP_SEASONS:
        for pattern in _CACHE_PATTERNS:
            cache_path = NBA_CACHE / pattern.format(season=season)
            if not cache_path.exists():
                continue
            try:
                with open(cache_path) as f:
                    cache = json.load(f)
                if isinstance(cache, list):
                    # List format: [{PLAYER_NAME: ..., PLAYER_ID: ...}, ...]
                    for row in cache:
                        name = str(row.get("PLAYER_NAME") or row.get("player_name", ""))
                        pid = row.get("PLAYER_ID") or row.get("player_id")
                        if name and pid:
                            result[_norm(name)] = int(pid)
                elif isinstance(cache, dict):
                    # Dict format: {player_name: {player_id: ..., ...}}
                    for name, data in cache.items():
                        if isinstance(data, dict):
                            pid = data.get("player_id") or data.get("PLAYER_ID")
                        else:
                            pid = None
                        if pid:
                            result[_norm(name)] = int(pid)
            except Exception:
                pass
    return result


def _resolve_slot_via_jersey(
    game_dir: str,
    name_to_id: Dict[str, int],
) -> Dict[int, int]:
    """
    Return mapping: tracker_slot_id → real_nba_player_id using jersey number chain.

    Chain: slot_id → jersey_number (tracking_data.csv) → full_name (jersey_name_map.json) → NBA_id
    This handles last-name-only OCR in shot_log by using the jersey map which has full names.
    """
    # Load jersey_name_map.json (jersey_num → full_name)
    jnm_path = os.path.join(game_dir, "jersey_name_map.json")
    jersey_to_name: Dict[str, str] = {}
    try:
        with open(jnm_path, encoding="utf-8", errors="replace") as f:
            jnm = json.load(f)
        jersey_to_name = {str(k): str(v) for k, v in jnm.items() if v}
    except Exception:
        return {}

    if not jersey_to_name:
        return {}

    # Build slot → jersey_number from tracking_data.csv
    # jersey_number may be stored as float (e.g. "3.0") — normalize to int string ("3")
    tracking_path = os.path.join(game_dir, "tracking_data.csv")
    slot_to_jersey: Dict[int, str] = {}
    try:
        with open(tracking_path, newline="", encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                try:
                    slot = int(row.get("player_id", 0) or 0)
                    jersey_raw = str(row.get("jersey_number", "")).strip()
                    if not slot or not jersey_raw or jersey_raw in ("nan", ""):
                        continue
                    # Normalize float strings: "3.0" → "3", "00.0" handled via int
                    try:
                        jersey = str(int(float(jersey_raw)))
                    except (ValueError, TypeError):
                        jersey = jersey_raw
                    slot_to_jersey.setdefault(slot, jersey)
                except (ValueError, TypeError):
                    pass
    except Exception:
        return {}

    slot_to_nba: Dict[int, int] = {}
    for slot, jersey in slot_to_jersey.items():
        full_name = jersey_to_name.get(jersey)
        if not full_name:
            continue
        nba_id = name_to_id.get(_norm(full_name))
        if nba_id:
            slot_to_nba[slot] = nba_id
    return slot_to_nba


def _resolve_player_names_from_shot_log(
    shot_log_path: str,
    name_to_id: Dict[str, int],
) -> Dict[int, int]:
    """
    Return mapping: tracker_slot_id → real_nba_player_id.

    Reads player_name column from shot_log.csv and matches against the NBA
    player_id cache. Only slots with a clean name match are returned.
    """
    slot_to_name: Dict[int, str] = {}
    try:
        with open(shot_log_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    slot = int(row.get("player_id", 0) or 0)
                    name = str(row.get("player_name", "")).strip()
                    if slot and name and "?" not in name and "#" not in name and name:
                        slot_to_name.setdefault(slot, name)
                except (ValueError, TypeError):
                    pass
    except Exception:
        return {}

    slot_to_nba: Dict[int, int] = {}
    for slot, name in slot_to_name.items():
        nba_id = name_to_id.get(_norm(name))
        if nba_id:
            slot_to_nba[slot] = nba_id
    return slot_to_nba


def _already_registered(game_id: str) -> bool:
    """Return True if this game_id already has rows in cv_features."""
    try:
        from src.data.db import get_connection
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM cv_features WHERE game_id = ?",
                (game_id,),
            )
            count = cur.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def process_game(
    game_id: str,
    game_dir: str,
    name_to_id: Dict[str, int],
    dry_run: bool = False,
) -> int:
    """
    Extract and register CV features for one game.

    Returns the number of player records registered (0 on failure/skip).
    """
    from src.pipeline.tracking_feature_extractor import extract
    from src.pipeline.cv_feature_registry import register

    shot_log = os.path.join(game_dir, "shot_log.csv")
    if not os.path.exists(shot_log):
        return 0

    # Primary: slot → jersey_number (tracking_data) → full_name (jersey_name_map) → NBA_id
    slot_to_nba = _resolve_slot_via_jersey(game_dir, name_to_id)
    # Fallback: direct full-name match from shot_log player_name column
    if not slot_to_nba:
        slot_to_nba = _resolve_player_names_from_shot_log(shot_log, name_to_id)
    if not slot_to_nba:
        return 0

    # Extract CV features keyed by slot_id
    cv_by_slot = extract(game_id, data_root=str(os.path.dirname(game_dir)))
    if not cv_by_slot:
        # Try passing the game_dir parent explicitly
        cv_by_slot = extract(game_id)

    if not cv_by_slot:
        return 0

    registered = 0
    for slot_id, feats in cv_by_slot.items():
        nba_id = slot_to_nba.get(int(slot_id))
        if not nba_id:
            continue
        if not dry_run:
            register(player_id=nba_id, game_id=game_id, features=feats)
        registered += 1

    return registered


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print plan without writing")
    parser.add_argument("--game-id", help="Process only this game ID")
    args = parser.parse_args()

    name_to_id = _build_name_to_id_map()
    print(f"Player name→ID map: {len(name_to_id)} entries loaded")

    # Collect all game directories
    dirs_to_check: list[tuple[str, str]] = []  # (game_id, game_dir_path)
    for base_dir in (TRACKING_DIR, GAMES_DIR):
        if not base_dir.exists():
            continue
        for d in sorted(base_dir.iterdir()):
            if not d.is_dir() or d.name.startswith("_"):
                continue
            gid = d.name
            if args.game_id and gid != args.game_id:
                continue
            dirs_to_check.append((gid, str(d)))

    print(f"Found {len(dirs_to_check)} game directories to check")

    total_registered = 0
    skipped_already = 0
    skipped_no_names = 0

    for game_id, game_dir in dirs_to_check:
        if not args.dry_run and _already_registered(game_id):
            skipped_already += 1
            continue

        shot_log = os.path.join(game_dir, "shot_log.csv")
        if not os.path.exists(shot_log):
            continue

        n = process_game(game_id, game_dir, name_to_id, dry_run=args.dry_run)
        if n == 0:
            skipped_no_names += 1
            if args.dry_run:
                print(f"  {game_id}: no resolvable player names → skip")
        else:
            total_registered += n
            status = "[DRY RUN]" if args.dry_run else "registered"
            print(f"  {game_id}: {n} players {status}")

    print(f"\nDone: {total_registered} player-game records registered, "
          f"{skipped_already} already in DB, {skipped_no_names} skipped (no name match)")


if __name__ == "__main__":
    main()
