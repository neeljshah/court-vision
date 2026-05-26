"""refresh_predictions_cache.py — R30_W3 rebuild today's predictions cache.

Re-runs scripts/build_prediction_cache.py for today's date so the parquet
reflects current code (R28_U2 pace fix, R29_V3 residual drift fixes, R25_R1
pregame backfill, R20_M7 + R21_N5 m2_family wire/cache).

NOTE on scope:
  - The artifact ``data/cache/predictions_cache_<date>.parquet`` is the
    PLAYER-PROP cache (player_id x stat x q10/q50/q90), produced by
    ``scripts/build_prediction_cache.py``. It is NOT the m2_family game
    cache (m2_family writes JSON keyed by game_id with total_pts/spread).
  - R28_U2/R29_V3/R25_R1 patch GAME-LEVEL pregame features in
    data/nba/season_games_<season>.json. Those features feed m2_family
    (game-level). They do NOT feed prop_pergame (player-level), which
    reads only from gamelog_<pid>_<season>.json + opponent-defense /
    playtype / bbref / contract caches.
  - So this rebuild is a no-op-vs-stale check for the player-prop cache:
    if the cache was built post-fix it will reproduce; if not, the same
    code + same gamelog data still yields the same numbers (deterministic
    models, frozen artifacts). The value of the rebuild is verifying the
    cache is fresh-mtime, schema-valid, and that the artifact is usable
    by the serving helper.

Worktree note:
  The isolated worktree may lack data/nba/gamelog_*.json files. This
  script accepts a ``--nba-cache-dir`` override (defaulting to the parent
  repo ``C:\\Users\\neelj\\nba-ai-system\\data\\nba`` when present) so the
  rebuild can run end-to-end locally. Models are read from worktree's
  data/models/ — only data files are sourced from the parent.

Usage:
  python scripts/improve_loop/refresh_predictions_cache.py
  python scripts/improve_loop/refresh_predictions_cache.py --max 50
  python scripts/improve_loop/refresh_predictions_cache.py --no-backup
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from datetime import date as _date
from typing import Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_PARENT_REPO = r"C:\Users\neelj\nba-ai-system"
_BACKUP_SUFFIX = ".bak_R30_W3"


def _default_nba_cache_dir() -> str:
    """Prefer worktree's data/nba/ if it has gamelogs; else fall back to parent."""
    wt = os.path.join(PROJECT_DIR, "data", "nba")
    parent = os.path.join(_PARENT_REPO, "data", "nba")
    has_worktree_gamelogs = (
        os.path.isdir(wt)
        and any(f.startswith("gamelog_") for f in os.listdir(wt))
    )
    if has_worktree_gamelogs:
        return wt
    if os.path.isdir(parent) and any(
        f.startswith("gamelog_") for f in os.listdir(parent)
    ):
        return parent
    return wt  # caller will get 0 candidates and we report it


def _backup(out_path: str) -> Optional[str]:
    if not os.path.exists(out_path):
        return None
    bak = out_path + _BACKUP_SUFFIX
    # Don't clobber an existing backup (first-write wins — preserves the
    # truly-original pre-rebuild state across multiple invocations).
    if not os.path.exists(bak):
        shutil.copy2(out_path, bak)
    return bak


def refresh(
    *,
    season: Optional[str] = None,
    max_players: Optional[int] = None,
    nba_cache_dir: Optional[str] = None,
    backup: bool = True,
    out_path: Optional[str] = None,
    verbose: bool = True,
) -> Tuple[str, int, Optional[str]]:
    """Rebuild today's predictions_cache parquet. Returns (out_path, n_rows, bak_path)."""
    # Resolve gamelog source first — patch the prop_pergame module constant
    # BEFORE importing build_prediction_cache (which captures _NBA_CACHE_DIR).
    src_dir = nba_cache_dir or _default_nba_cache_dir()
    if verbose:
        print(f"[R30_W3] using gamelog dir: {src_dir}", flush=True)

    # Patch the module constant so _iter_active_players + build_prediction_row
    # both pick up the override consistently.
    import src.prediction.prop_pergame as _pp  # noqa: PLC0415
    _pp._NBA_CACHE = src_dir
    import scripts.build_prediction_cache as bpc  # noqa: PLC0415
    bpc._NBA_CACHE_DIR = src_dir

    today_iso = _date.today().isoformat()
    if out_path is None:
        out_path = os.path.join(
            PROJECT_DIR, "data", "cache", f"predictions_cache_{today_iso}.parquet"
        )

    bak_path = _backup(out_path) if backup else None
    if verbose and bak_path:
        print(f"[R30_W3] backup -> {bak_path}", flush=True)

    t0 = time.perf_counter()
    written_path, n_rows = bpc.build_cache(
        season=season,
        max_players=max_players,
        out_path=out_path,
        verbose=False,  # bpc prints unicode arrow that crashes on cp1252
    )
    elapsed = time.perf_counter() - t0
    if verbose:
        print(
            f"[R30_W3] rebuilt {n_rows} rows in {elapsed:.1f}s -> {written_path}",
            flush=True,
        )
    return written_path, n_rows, bak_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=None)
    ap.add_argument("--max", type=int, default=None,
                    help="Cap players (smoke test).")
    ap.add_argument("--nba-cache-dir", default=None,
                    help="Override gamelog source dir. Default: worktree "
                         "if populated, else parent repo.")
    ap.add_argument("--no-backup", action="store_true",
                    help="Skip the .bak_R30_W3 backup step.")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    refresh(
        season=args.season,
        max_players=args.max,
        nba_cache_dir=args.nba_cache_dir,
        backup=not args.no_backup,
        out_path=args.out,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
