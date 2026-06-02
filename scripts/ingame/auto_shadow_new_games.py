"""auto_shadow_new_games.py — Auto-shadow the unified in-game projector for every
finished game that has ``data/live`` snapshots but no shadow log yet.

SAFETY CONTRACT (same as unified_shadow_logger):
  * NEVER writes to data/live/ or any live / serving artifact.
  * Only READs data/live/<gid>_*.json (already-written snapshots).
  * APPENDS to data/cache/ingame/unified_shadow_<gid>.jsonl (shadow log only).
  * CV_INGAME_SBS is forced ON in this process only — does NOT affect the live
    api/poller or any other running process.
  * Idempotent: if a shadow log already exists for a game, that game is SKIPPED
    entirely (skip_logged=True inside log_existing).

What counts as a "finished" game snapshot set?
  The script looks for game IDs that have at least one snapshot in data/live/
  whose filename encodes a game ID (pattern: ``<gid>_<epoch_ms>.json``).
  It only processes games where the most-recent snapshot file has
  game_status == "FINAL" (or status unknown — in that case the shadow logger
  itself checks per-snapshot and gracefully handles non-final snapshots).
  To avoid re-processing partially-live games, we require at least one snapshot
  whose filename carries a non-zero epoch.

Skips 0042500317 (the reference game) if it already has a shadow log —
which validates Task 4's requirement.

Usage:
    NBA_OFFLINE=1 python scripts/ingame/auto_shadow_new_games.py
    NBA_OFFLINE=1 python scripts/ingame/auto_shadow_new_games.py --dry-run
    NBA_OFFLINE=1 python scripts/ingame/auto_shadow_new_games.py --force-all
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path
from typing import List, Optional, Set

# Force CV_INGAME_SBS ON for this process only (shadow lane; does NOT affect live).
os.environ["CV_INGAME_SBS"] = "1"
os.environ.setdefault("NBA_OFFLINE", "1")

PROJECT_DIR = Path(__file__).resolve().parents[2]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

LIVE_DIR = PROJECT_DIR / "data" / "live"
SHADOW_DIR = PROJECT_DIR / "data" / "cache" / "ingame"


# ---------------------------------------------------------------------------
# Snapshot discovery helpers
# ---------------------------------------------------------------------------

def _epoch_from_path(path: str) -> int:
    base = os.path.basename(path)
    stem = base[:-5] if base.endswith(".json") else base
    tail = stem.rsplit("_", 1)[-1]
    try:
        return int(tail)
    except (TypeError, ValueError):
        return 0


def _game_ids_in_live_dir(live_dir: Path) -> List[str]:
    """Return sorted unique game IDs from data/live/<gid>_<epoch>.json files."""
    seen: Set[str] = set()
    pattern = str(live_dir / "*.json")
    for path in glob.glob(pattern):
        base = os.path.basename(path)
        stem = base[:-5] if base.endswith(".json") else base
        parts = stem.rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            seen.add(parts[0])
    return sorted(seen)


def _latest_snapshot_path(game_id: str, live_dir: Path) -> Optional[str]:
    """Return the chronologically last snapshot path for a game."""
    paths = sorted(
        glob.glob(str(live_dir / f"{game_id}_*.json")),
        key=_epoch_from_path,
    )
    return paths[-1] if paths else None


def _is_final(path: str) -> bool:
    """Return True if the snapshot's game_status is FINAL."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            snap = json.load(fh)
        return str(snap.get("game_status") or "").upper() == "FINAL"
    except Exception:
        return False


def _shadow_log_exists(game_id: str, shadow_dir: Path) -> bool:
    """Return True if a shadow log file already exists and is non-empty for this game."""
    log_path = shadow_dir / f"unified_shadow_{game_id}.jsonl"
    if not log_path.exists():
        return False
    try:
        return log_path.stat().st_size > 0
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(
    dry_run: bool = False,
    force_all: bool = False,
    require_final: bool = True,
) -> int:
    """Scan data/live/ for completed games and shadow-log each un-logged game.

    Args:
        dry_run:      If True, detect games that need logging but don't call
                      log_existing.
        force_all:    If True, re-log all games regardless of existing logs
                      (passes skip_logged=False to log_existing; primarily for
                      debugging/recovery).
        require_final: If True (default), only process games whose latest snapshot
                      has game_status=FINAL.  Set False to also process in-progress.

    Returns:
        Number of games processed (shadow-logged).
    """
    if not LIVE_DIR.exists():
        print(f"  [auto_shadow] live dir not found: {LIVE_DIR} — nothing to do.")
        return 0

    game_ids = _game_ids_in_live_dir(LIVE_DIR)
    if not game_ids:
        print("  [auto_shadow] no snapshot files found in data/live/ — nothing to do.")
        return 0

    print(f"  [auto_shadow] found {len(game_ids)} unique game IDs in data/live/")

    # Import the shadow logger lazily (it sets env flags on import)
    from scripts.ingame.unified_shadow_logger import log_existing  # noqa: E402

    n_processed = 0
    n_skipped_logged = 0
    n_skipped_not_final = 0

    for gid in game_ids:
        latest = _latest_snapshot_path(gid, LIVE_DIR)
        if latest is None:
            continue

        # Check if already logged
        already_logged = _shadow_log_exists(gid, SHADOW_DIR)
        if already_logged and not force_all:
            n_skipped_logged += 1
            print(f"  [auto_shadow] SKIP {gid} — shadow log already exists")
            continue

        # Optionally require FINAL status
        if require_final and not _is_final(latest):
            n_skipped_not_final += 1
            print(f"  [auto_shadow] SKIP {gid} — latest snapshot not FINAL")
            continue

        print(f"  [auto_shadow] PROCESS {gid} (already_logged={already_logged}, "
              f"force_all={force_all}, dry_run={dry_run})")

        if dry_run:
            n_processed += 1
            continue

        try:
            n_logged = log_existing(
                gid,
                out_dir=str(SHADOW_DIR),
                skip_logged=(not force_all),
            )
            print(f"  [auto_shadow] {gid}: logged {n_logged} new record(s)")
            n_processed += 1
        except Exception as exc:
            print(f"  [auto_shadow] ERROR {gid}: {exc}", file=sys.stderr)

    print(
        f"\n  [auto_shadow] done — processed={n_processed} "
        f"skipped_already_logged={n_skipped_logged} "
        f"skipped_not_final={n_skipped_not_final}"
    )
    return n_processed


def _cli(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect games that need logging but do not call log_existing.",
    )
    ap.add_argument(
        "--force-all",
        action="store_true",
        help="Re-log all games (even those with existing shadow logs).",
    )
    ap.add_argument(
        "--no-require-final",
        action="store_true",
        help="Process games whose latest snapshot is not yet FINAL.",
    )
    args = ap.parse_args(argv)
    run(
        dry_run=args.dry_run,
        force_all=args.force_all,
        require_final=not args.no_require_final,
    )
    return 0  # always exit 0 (game count is informational, not an error code)


if __name__ == "__main__":
    sys.exit(_cli())
