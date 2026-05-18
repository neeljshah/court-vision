"""
reprocess_failed_games.py — Re-run games with corrupted or failed outputs.

Covers four failure classes:

  1. Portrait-homography games (3): 0022400921, 0022400923, 0022401117
     map_2d was portrait (e.g. 168×2174) → all coordinates garbage.
     Portrait guard is now in unified_pipeline.py; re-running will produce
     correct landscape map_2d and valid coordinate data.

  2. Contaminated / NameError games (8): 0022401175-0022401198 batch + 0022400625
     These games all show identical shot/possession counts (14 shots,
     23 possessions, ~836K tracking rows) — a data-contamination artefact
     from the pre-fix shutil.copy2 race in run_phase_g.py.

  3. Empty shot-log games (2): 0022400852, 0022401123
     Tracking ran but Stage 2 never wrote shots (FileNotFoundError or
     empty pipeline output). shot_log.csv contains header only (0 data rows).

  4. Crash / zero-output games (1): 0022400710
     SIFT crash at startup — 0 rows, 0 frames produced (ISSUE-027).

  Additionally, 18 games were processed with the old over-detecting pipeline
  (5–15× too many shots, ~1000× too many possessions).  Pass --include-stale
  to reprocess those with the fixed detector.

Usage
-----
    conda activate basketball_ai

    # Re-run all known-bad games (13 games, ~4 hours)
    python scripts/reprocess_failed_games.py

    # Also reprocess 18 stale-detector games (~9 hours total)
    python scripts/reprocess_failed_games.py --include-stale

    # Dry-run: show what would be cleared and re-run without executing
    python scripts/reprocess_failed_games.py --dry-run

    # Re-run a custom subset
    python scripts/reprocess_failed_games.py --game-ids 0022400921 0022400923

    # Control frame budget (default: 18000 = 10 min @ 30fps)
    python scripts/reprocess_failed_games.py --frames 9000
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

DATA_DIR     = PROJECT_DIR / "data"
TRACKING_DIR = DATA_DIR / "tracking"
DONE_LOG     = DATA_DIR / "phase_g_processed.txt"
VIDEOS_DIR   = DATA_DIR / "videos" / "full_games"

# ── Known-bad game IDs ────────────────────────────────────────────────────────

_PORTRAIT_GAMES = [
    "0022400921",   # map_2d was 168×2174 (portrait)
    "0022400923",   # map_2d was 775×3647 (portrait)
    "0022401117",   # map_2d was 248×1053 (portrait)
]

_CONTAMINATED_GAMES = [
    "0022401175",   # identical outputs to other games in batch (14 shots/23 poss)
    "0022401183",
    "0022401185",
    "0022401190",
    "0022401194",
    "0022401196",
    "0022401198",
    "0022400625",   # pbp_coverage=12%: shots fall in Q2 but enrichment ran single-period;
                    # needs reprocess so _infer_period_count uses ball_tracking timestamps
                    # that correctly reflect Q2 footage (max_ts ~971s → 2-period mode)
]

# Games where tracking ran but Stage 2 never wrote shot_log rows (header only).
_EMPTY_SHOT_GAMES = [
    "0022400852",   # ISSUE-024: 393K frames tracked, tracking_data.csv never written
    "0022401123",   # shot_log.csv header-only, 0 data rows
]

# Games that crashed before producing any output (ISSUE-027).
_CRASH_GAMES = [
    "0022400710",   # SIFT crash at startup — 0 rows, 0 frames (tracking_results.json: ERROR)
]

# Games processed with the old over-detecting pipeline (5–15× shot inflation,
# ~1000× possession fragmentation).  Not failed — just stale quality.
# Reprocess with --include-stale to get clean data from the fixed detector.
_STALE_DETECTOR_GAMES = [
    "0022400015", "0022400021", "0022400042", "0022400058", "0022400067",
    "0022400072", "0022400078", "0022400083", "0022400112", "0022400242",
    "0022400316", "0022400396", "0022400402", "0022400408", "0022400430",
    "0022400537", "0022400686", "0022400909",
]

_DEFAULT_GAMES = _PORTRAIT_GAMES + _CONTAMINATED_GAMES + _EMPTY_SHOT_GAMES + _CRASH_GAMES


# ── Helpers ───────────────────────────────────────────────────────────────────

def _video_exists(game_id: str) -> bool:
    return (VIDEOS_DIR / f"{game_id}.mp4").exists()


def _clear_tracking_outputs(game_id: str, dry_run: bool) -> int:
    """Delete data/tracking/<game_id>/ and return number of files removed."""
    game_dir = TRACKING_DIR / game_id
    if not game_dir.exists():
        return 0
    files = list(game_dir.rglob("*"))
    n_files = sum(1 for f in files if f.is_file())
    if not dry_run:
        shutil.rmtree(game_dir)
    return n_files


def _remove_from_done_log(game_ids: list[str], dry_run: bool) -> list[str]:
    """Remove game_ids from phase_g_processed.txt; return lines removed."""
    if not DONE_LOG.exists():
        return []
    lines = DONE_LOG.read_text().splitlines()
    removed = [ln for ln in lines if ln.strip() in game_ids]
    kept    = [ln for ln in lines if ln.strip() not in game_ids]
    if not dry_run:
        DONE_LOG.write_text("\n".join(kept) + ("\n" if kept else ""))
    return removed


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game-ids", nargs="+", default=None,
                    help="Specific game IDs to reprocess (default: all known-bad games)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would happen without executing anything")
    ap.add_argument("--frames", type=int, default=18_000,
                    help="Max frames per game (default 18000 = 10 min @ 30fps)")
    ap.add_argument("--include-stale", action="store_true",
                    help="Also reprocess 18 stale-detector games (old shot/possession counts)")
    args = ap.parse_args()

    if args.game_ids:
        game_ids = args.game_ids
    elif args.include_stale:
        game_ids = _DEFAULT_GAMES + _STALE_DETECTOR_GAMES
    else:
        game_ids = _DEFAULT_GAMES
    tag = "[DRY-RUN] " if args.dry_run else ""

    _stale_note = " (+stale)" if args.include_stale else ""
    print(f"\n{'='*60}")
    print(f"  Reprocess Failed Games{_stale_note}{' — DRY RUN' if args.dry_run else ''}")
    print(f"  Games ({len(game_ids)}): {', '.join(game_ids)}")
    print(f"  Frames per game: {args.frames:,}")
    print(f"{'='*60}\n")

    # Categorise
    portrait  = [g for g in game_ids if g in _PORTRAIT_GAMES]
    contam    = [g for g in game_ids if g in _CONTAMINATED_GAMES]
    empty     = [g for g in game_ids if g in _EMPTY_SHOT_GAMES]
    crash     = [g for g in game_ids if g in _CRASH_GAMES]
    stale     = [g for g in game_ids if g in _STALE_DETECTOR_GAMES]
    _all_known = _PORTRAIT_GAMES + _CONTAMINATED_GAMES + _EMPTY_SHOT_GAMES + _CRASH_GAMES + _STALE_DETECTOR_GAMES
    other     = [g for g in game_ids if g not in _all_known]

    if portrait:
        print(f"{tag}Portrait-homography games ({len(portrait)}): {portrait}")
        print("  -> Portrait guard in unified_pipeline.py will force landscape map_2d\n")
    if contam:
        print(f"{tag}Contaminated-output games ({len(contam)}): {contam}")
        print("  -> stale per-game CSVs will be cleared before re-run\n")
    if empty:
        print(f"{tag}Empty shot-log games ({len(empty)}): {empty}")
        print("  -> shot_log.csv had header only (Stage 2 crash); full reprocess\n")
    if crash:
        print(f"{tag}Crash/zero-output games ({len(crash)}): {crash}")
        print("  -> 0 rows produced at last run (SIFT or startup crash)\n")
    if stale:
        print(f"{tag}Stale-detector games ({len(stale)}): {stale}")
        print("  -> processed with old over-detecting pipeline; clean reprocess\n")
    if other:
        print(f"{tag}Other games to reprocess ({len(other)}): {other}\n")

    # Check video availability
    missing = [g for g in game_ids if not _video_exists(g)]
    if missing:
        print(f"WARNING: no video file found for: {missing}")
        print(f"         Expected at: {VIDEOS_DIR}/<game_id>.mp4")
        print("         These games will be skipped by run_phase_g.py\n")

    # Step 1: Clear stale tracking outputs
    print("Step 1 — Clearing stale tracking outputs")
    total_cleared = 0
    for gid in game_ids:
        n = _clear_tracking_outputs(gid, dry_run=args.dry_run)
        if n > 0:
            print(f"  {tag}Removed {n} file(s) from data/tracking/{gid}/")
            total_cleared += n
        else:
            print(f"  (no tracking dir for {gid})")
    print(f"  Total files cleared: {total_cleared}\n")

    # Step 2: Remove from done log so run_phase_g.py will pick them up
    print("Step 2 — Removing from phase_g_processed.txt")
    removed_lines = _remove_from_done_log(game_ids, dry_run=args.dry_run)
    if removed_lines:
        print(f"  {tag}Removed {len(removed_lines)} entries: {removed_lines}")
    else:
        print("  (no matching entries found in done log)")
    print()

    # Step 3: Re-run with current pipeline
    print("Step 3 — Launching run_phase_g.py")
    cmd = [
        sys.executable,
        str(PROJECT_DIR / "scripts" / "run_phase_g.py"),
        "--game-ids", *game_ids,
        "--frames",   str(args.frames),
        "--reprocess",
    ]
    print(f"  Command: {' '.join(cmd)}\n")

    if args.dry_run:
        print("[DRY-RUN] Skipping actual execution.\n")
        print("Run without --dry-run to execute.")
        return

    result = subprocess.run(cmd, cwd=str(PROJECT_DIR))
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
