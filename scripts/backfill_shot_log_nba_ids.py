"""Backfill nba_player_id column into shot_log_enriched.csv (and shot_log.csv).

The CV pipeline writes shot_log_enriched.csv with player_id = tracker slot (1-10),
not NBA player_id. Downstream intelligence-layer signals (INT-115 shot types,
INT-121 shot range, INT-125 shot clock) need NBA player_id to join against
prop_pergame and player tables.

Uses the production 3-channel resolver from scripts/backfill_cv_features.py:
  Channel 1 (PBP):    shot_log player_name -> NBA id (most reliable for shots)
  Channel 2 (jersey): tracking_data mode jersey -> jersey_name_map -> NBA id
  Channel 3 (suffix): last-name suffix match (single candidate)

Plus the Bug 6 roster guard (rejects nba_ids not on the game's boxscore roster).

Usage:
  python scripts/backfill_shot_log_nba_ids.py            # all tracking dirs
  python scripts/backfill_shot_log_nba_ids.py --game-id 0022400909
  python scripts/backfill_shot_log_nba_ids.py --dry-run  # report only
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path
from typing import Dict, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.backfill_cv_features import (  # type: ignore
    _build_name_to_id_map,
    _build_slot_data_from_tracking,
    _build_slot_pbp_names,
    _build_suffix_index,
    _load_jersey_name_map,
    _resolve_slot_to_nba_id,
)

TRACKING_DIR = ROOT / "data" / "tracking"
GAMES_DIR = ROOT / "data" / "games"


def _build_slot_to_nba(
    game_dir: str,
    game_id: str,
    name_to_id: Dict[str, int],
    suffix_idx: Dict[str, list],
) -> Tuple[Dict[int, int], Dict[str, int]]:
    """Return (slot_to_nba, channel_counts).

    Iterates every slot present in either tracking_data.csv or shot_log.csv
    and applies the multi-channel resolver. Uses game-wide jersey counter
    (quarter=None) — appropriate for shot-level backfill since we want a
    single nba_id per slot per game.
    """
    shot_log = os.path.join(game_dir, "shot_log.csv")
    if not os.path.exists(shot_log):
        return {}, {}

    jersey_to_name = _load_jersey_name_map(game_dir)
    slot_data = _build_slot_data_from_tracking(game_dir)
    slot_pbp_names = _build_slot_pbp_names(shot_log)

    all_slots = set(slot_data.keys()) | set(slot_pbp_names.keys())
    if not all_slots:
        return {}, {}

    slot_to_nba: Dict[int, int] = {}
    channels: Dict[str, int] = {"pbp": 0, "jersey": 0, "suffix": 0}

    for slot_id in all_slots:
        nba_id, channel = _resolve_slot_to_nba_id(
            game_dir,
            name_to_id,
            slot_id,
            jersey_to_name,
            slot_data,
            slot_pbp_names,
            suffix_idx,
            game_id=game_id,
            quarter=None,
        )
        if nba_id:
            slot_to_nba[slot_id] = int(nba_id)
            channels[channel] = channels.get(channel, 0) + 1

    return slot_to_nba, channels


def _rewrite_shot_log(
    csv_path: str,
    slot_to_nba: Dict[int, int],
    dry_run: bool,
) -> Tuple[int, int]:
    """Add/overwrite nba_player_id column (and defender_nba_id when defender_slot_id
    is present). Returns (resolved, total) rows for the shooter resolution."""
    if not os.path.exists(csv_path):
        return 0, 0

    with open(csv_path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    if not rows:
        return 0, 0

    if "nba_player_id" not in fieldnames:
        try:
            idx = fieldnames.index("player_id") + 1
        except ValueError:
            idx = len(fieldnames)
        fieldnames.insert(idx, "nba_player_id")

    # P5 (2026-05-29): also resolve defender_slot_id -> defender_nba_id when present
    has_def_slot = "defender_slot_id" in fieldnames
    if has_def_slot and "defender_nba_id" not in fieldnames:
        fieldnames.insert(fieldnames.index("defender_slot_id") + 1, "defender_nba_id")

    resolved = 0
    total = 0
    for row in rows:
        total += 1
        slot_raw = row.get("player_id", "")
        try:
            slot = int(float(slot_raw)) if slot_raw not in ("", None) else 0
        except (ValueError, TypeError):
            slot = 0
        nba_id = slot_to_nba.get(slot)
        row["nba_player_id"] = str(nba_id) if nba_id else ""
        if nba_id:
            resolved += 1

        if has_def_slot:
            def_raw = row.get("defender_slot_id", "")
            if def_raw not in ("", None):
                try:
                    def_slot = int(float(def_raw))
                except (ValueError, TypeError):
                    def_slot = 0
                def_nba = slot_to_nba.get(def_slot)
                row["defender_nba_id"] = str(def_nba) if def_nba else ""
            else:
                row["defender_nba_id"] = ""

    if not dry_run:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    return resolved, total


def backfill_game(
    game_id: str,
    game_dir: str,
    name_to_id: Dict[str, int],
    suffix_idx: Dict[str, list],
    dry_run: bool,
) -> dict:
    slot_to_nba, channels = _build_slot_to_nba(game_dir, game_id, name_to_id, suffix_idx)
    enriched = os.path.join(game_dir, "shot_log_enriched.csv")
    base = os.path.join(game_dir, "shot_log.csv")

    e_res, e_tot = _rewrite_shot_log(enriched, slot_to_nba, dry_run)
    b_res, b_tot = _rewrite_shot_log(base, slot_to_nba, dry_run)

    return {
        "game_id": game_id,
        "slots_resolved": len(slot_to_nba),
        "channels": channels,
        "enriched_resolved": e_res,
        "enriched_total": e_tot,
        "base_resolved": b_res,
        "base_total": b_tot,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", default=None, help="Process only this game_id")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute resolution but don't rewrite CSVs",
    )
    parser.add_argument(
        "--min-shots",
        type=int,
        default=0,
        help="Skip games with fewer than N shot rows (default 0)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Stop after processing this many games (0 = no limit)",
    )
    args = parser.parse_args()

    print("Building name -> nba_player_id map from cached player stats...")
    name_to_id = _build_name_to_id_map()
    print(f"  loaded {len(name_to_id)} player names")
    if not name_to_id:
        print("ERROR: name->id map is empty. Need data/nba/player_full_<season>.json")
        return 1

    suffix_idx = _build_suffix_index(name_to_id)
    print(f"  suffix index: {len(suffix_idx)} surname buckets")

    targets = []
    if args.game_id:
        for base in (TRACKING_DIR, GAMES_DIR):
            d = base / args.game_id
            if d.is_dir():
                targets.append((args.game_id, str(d)))
    else:
        for base in (TRACKING_DIR, GAMES_DIR):
            if not base.is_dir():
                continue
            for d in sorted(base.iterdir()):
                if not d.is_dir() or d.name.startswith("_"):
                    continue
                targets.append((d.name, str(d)))

    if not targets:
        print("No tracking directories found.")
        return 1

    print(f"Processing {len(targets)} game directories (dry_run={args.dry_run})")

    games_touched = 0
    games_skipped = 0
    total_resolved = 0
    total_shots = 0
    per_game_rates = []
    channel_totals: Dict[str, int] = {"pbp": 0, "jersey": 0, "suffix": 0}

    for game_id, game_dir in targets:
        if args.limit and games_touched >= args.limit:
            break
        try:
            stats = backfill_game(game_id, game_dir, name_to_id, suffix_idx, args.dry_run)
        except Exception as exc:
            print(f"  {game_id}: ERROR {exc}")
            continue

        rep_res = stats["enriched_resolved"] or stats["base_resolved"]
        rep_tot = stats["enriched_total"] or stats["base_total"]

        if rep_tot < args.min_shots or rep_tot == 0:
            games_skipped += 1
            continue

        rate = rep_res / rep_tot if rep_tot else 0.0
        per_game_rates.append(rate)
        total_resolved += rep_res
        total_shots += rep_tot
        games_touched += 1
        for c, n in stats["channels"].items():
            channel_totals[c] = channel_totals.get(c, 0) + n

        if games_touched <= 20 or games_touched % 25 == 0:
            ch = stats["channels"]
            print(
                f"  {game_id}: {rep_res}/{rep_tot} shots ({rate*100:.0f}%) "
                f"slots={stats['slots_resolved']} "
                f"[pbp={ch.get('pbp',0)} jersey={ch.get('jersey',0)} suffix={ch.get('suffix',0)}]"
            )

    agg_rate = total_resolved / total_shots if total_shots else 0.0
    print()
    print("=" * 60)
    print(f"games processed : {games_touched}")
    print(f"games skipped   : {games_skipped} (no shots or under --min-shots)")
    print(f"total shots     : {total_shots}")
    print(f"shots resolved  : {total_resolved}")
    print(f"aggregate rate  : {agg_rate*100:.1f}%")
    if per_game_rates:
        per_game_rates.sort()
        median = per_game_rates[len(per_game_rates) // 2]
        p25 = per_game_rates[len(per_game_rates) // 4]
        p75 = per_game_rates[(3 * len(per_game_rates)) // 4]
        print(f"per-game rate   : p25={p25*100:.1f}% median={median*100:.1f}% p75={p75*100:.1f}%")
    print(
        f"channel mix     : pbp={channel_totals['pbp']} "
        f"jersey={channel_totals['jersey']} suffix={channel_totals['suffix']}"
    )
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
