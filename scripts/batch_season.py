"""
batch_season.py -- Batch-process 2025-26 season games from select_season_games.py.

Reads data/season_2025-26_targets.json, then for each game:
  1. Download video via fetch_games.py logic (yt-dlp YouTube search)
  2. Run run_phase_g.py on the downloaded video
  3. Delete the .mp4 on success (disk space)
  4. Log result to data/season_batch_log.csv

Resume-safe: skips games that already have tracking_data.csv with >10K rows.
One game at a time (OOM guard).

Usage:
    conda activate basketball_ai
    python scripts/batch_season.py
    python scripts/batch_season.py --limit 5        # process at most 5 games
    python scripts/batch_season.py --frames 18000   # ~10 min at 30fps
    python scripts/batch_season.py --dry-run        # show plan, no downloads
"""

from __future__ import annotations

import argparse
import csv
import gc
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR    = PROJECT_DIR / "data"
GAMES_DIR   = DATA_DIR / "games"
TRACKING_DIR = DATA_DIR / "tracking"
VIDEOS_DIR  = DATA_DIR / "videos" / "full_games"
TARGETS_PATH = DATA_DIR / "season_2025-26_targets.json"
LOG_PATH     = DATA_DIR / "season_batch_log.csv"
LOG_FIELDS   = ["timestamp", "game_id", "matchup", "status", "rows",
                "shots", "poss", "duration_min",
                "quality_grade", "sentinel_pct", "possession_count",
                "median_poss_sec", "shot_count", "player_name_pct", "team_abbrev_pct",
                "error"]

PYTHON = sys.executable


def _load_targets() -> list:
    if not TARGETS_PATH.exists():
        print(f"ERROR: {TARGETS_PATH} not found. Run select_season_games.py first.")
        sys.exit(1)
    with open(TARGETS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    targets = data.get("targets", [])
    if not targets:
        err = data.get("error", "")
        print(f"No targets in {TARGETS_PATH}.")
        if err:
            print(f"  Note: {err}")
    return targets


def _already_done(game_id: str) -> Optional[int]:
    """Return row count if game has complete output (tracking + shots + possessions).
    Checks both data/tracking/ (run_phase_g output) and data/games/ (legacy)."""
    for parent in (TRACKING_DIR, GAMES_DIR):
        csv_path = parent / game_id / "tracking_data.csv"
        if not csv_path.exists():
            continue
        # Require all key output files, not just tracking_data
        required = ["tracking_data.csv", "possessions.csv", "shot_log.csv"]
        if not all((parent / game_id / f).exists() for f in required):
            continue
        try:
            with open(csv_path, encoding="utf-8", errors="replace") as f:
                rows = sum(1 for _ in f)
            if rows > 10_000:
                return rows
        except Exception:
            pass
    return None


def _read_metrics(game_id: str) -> dict:
    """Read shots/possessions from game output files.
    Checks data/tracking/ first (run_phase_g output), falls back to data/games/."""
    metrics = {"rows": 0, "shots": 0, "poss": 0, "duration_min": 0.0}
    # run_phase_g writes to data/tracking/; legacy pipeline uses data/games/
    game_dir = TRACKING_DIR / game_id
    if not game_dir.exists():
        game_dir = GAMES_DIR / game_id

    td = game_dir / "tracking_data.csv"
    if td.exists():
        try:
            with open(td, encoding="utf-8", errors="replace") as f:
                metrics["rows"] = max(0, sum(1 for _ in f) - 1)  # exclude header
        except Exception:
            pass

    sl = game_dir / "shot_log.csv"
    if sl.exists():
        try:
            with open(sl, encoding="utf-8", errors="replace") as f:
                metrics["shots"] = max(0, sum(1 for _ in f) - 1)
        except Exception:
            pass

    pv = game_dir / "possessions.csv"
    if pv.exists():
        try:
            with open(pv, encoding="utf-8", errors="replace") as f:
                metrics["poss"] = max(0, sum(1 for _ in f) - 1)
        except Exception:
            pass

    bt = game_dir / "ball_tracking.csv"
    if bt.exists():
        try:
            with open(bt, encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                rows_bt = list(reader)
            if rows_bt:
                ts_col = next((c for c in ("timestamp", "frame") if c in rows_bt[0]), None)
                if ts_col:
                    vals = [float(r[ts_col]) for r in rows_bt if r.get(ts_col)]
                    if vals:
                        metrics["duration_min"] = round((max(vals) - min(vals)) / 60.0, 1)
        except Exception:
            pass

    return metrics


def _append_log(row: dict) -> None:
    write_header = not LOG_PATH.exists()
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS, extrasaction="ignore")
        if write_header:
            w.writeheader()
        w.writerow(row)


def _download_video(game_id: str, matchup: str, game_date: str) -> Optional[Path]:
    """Download game video via fetch_games._search_and_download."""
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = VIDEOS_DIR / f"{game_id}.mp4"
    if out_path.exists() and out_path.stat().st_size > 1_000_000:
        print(f"  Video already on disk: {out_path}")
        return out_path

    # Import the proven search logic from fetch_games
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "fetch_games",
            str(PROJECT_DIR / "scripts" / "fetch_games.py")
        )
        fg = importlib.util.module_from_spec(spec)  # type: ignore
        spec.loader.exec_module(fg)  # type: ignore
    except Exception as e:
        print(f"  ERROR importing fetch_games: {e}")
        return None

    # Parse matchup "AWAY vs. HOME" or "AWAY @ HOME" -> team abbrevs
    import re
    m = re.match(r"(\w+)\s+(?:vs\.?|@)\s+(\w+)", matchup)
    if not m:
        print(f"  Could not parse matchup: {matchup}")
        return None
    away_abbr, home_abbr = m.group(1), m.group(2)

    game_info = {
        "id":   game_id,
        "away": away_abbr,
        "home": home_abbr,
        "date": game_date,
    }
    # segment_seconds=0 -> download full game (no clipping)
    print(f"  Searching YouTube for {game_id} ({matchup} {game_date})...")
    try:
        ok = fg._search_and_download(game_info, out_path, segment_seconds=0)
        if ok:
            return out_path
    except Exception as e:
        print(f"  _search_and_download error: {e}")
    return None


def _run_pipeline(game_id: str, video_path: Path, frames: int, gpu: int = 0) -> bool:
    """Run run_phase_g.py for a single game. Returns True on success."""
    cmd = [
        PYTHON, str(PROJECT_DIR / "scripts" / "run_phase_g.py"),
        "--game-ids", game_id,
    ]
    if frames > 0:
        cmd += ["--frames", str(frames)]
    else:
        cmd += ["--full"]
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(gpu)
    # GPU optimization: reduce CPU thread contention, let GPU do the work
    env["OMP_NUM_THREADS"] = "2"
    env["OPENBLAS_NUM_THREADS"] = "2"
    env["MKL_NUM_THREADS"] = "2"
    # cuDNN autotuner: benchmark conv algorithms, cache fastest
    env["TORCH_CUDNN_V8_API_ENABLED"] = "1"
    print(f"  Running pipeline (GPU {gpu}): {' '.join(cmd)}")
    try:
        # Full games can take 3-4 hours on GPU
        result = subprocess.run(cmd, timeout=14400, cwd=str(PROJECT_DIR), env=env)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("  Pipeline timeout (4h)")
        return False


def _verify_gpu(gpu_id: int = 0) -> None:
    """Print GPU status at startup. Warn loudly if CUDA unavailable."""
    try:
        import torch
        print(f"  PyTorch {torch.__version__}  CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            n = torch.cuda.device_count()
            for i in range(n):
                name = torch.cuda.get_device_name(i)
                mem = torch.cuda.get_device_properties(i).total_memory / 1e9
                print(f"    GPU {i}: {name} ({mem:.1f} GB)")
            # Pin this worker to its assigned GPU
            if gpu_id < n:
                torch.cuda.set_device(gpu_id)
            # Enable cuDNN autotuner for fixed-size inputs (broadcast frames)
            torch.backends.cudnn.benchmark = True
        else:
            print("  *** WARNING: CUDA NOT AVAILABLE -- running on CPU (very slow) ***")
            print("  Check: PyTorch CUDA version matches pod's nvcc/nvidia-smi")
    except ImportError:
        print("  *** WARNING: PyTorch not installed ***")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch-process 2025-26 season games")
    parser.add_argument("--frames", type=int, default=0,
                        help="Frames per game (0 = full video, default)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max games to process this run")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show plan without downloading or processing")
    parser.add_argument("--retry-failed", action="store_true",
                        help="Re-attempt games that previously failed (pipeline_failed or download_failed)")
    parser.add_argument("--gpu", type=int, default=0,
                        help="CUDA device index for this worker (default: 0)")
    parser.add_argument("--worker-id", type=int, default=0,
                        help="Worker index for multi-GPU runs (0-based)")
    parser.add_argument("--num-workers", type=int, default=1,
                        help="Total number of parallel workers (default: 1)")
    args = parser.parse_args()

    _verify_gpu(args.gpu)

    targets = _load_targets()
    if not targets:
        return

    # --retry-failed: re-queue games that previously failed
    if args.retry_failed and LOG_PATH.exists():
        _failed_ids = set()
        try:
            with open(LOG_PATH, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("status") in ("pipeline_failed", "download_failed"):
                        _failed_ids.add(row.get("game_id", ""))
            # Remove failed IDs from the "already done" check by filtering them
            # to the front of the targets list
            _failed_targets = [t for t in targets if t["game_id"] in _failed_ids]
            _other_targets = [t for t in targets if t["game_id"] not in _failed_ids]
            targets = _failed_targets + _other_targets
            if _failed_targets:
                print(f"  Retrying {len(_failed_targets)} previously failed games first")
        except Exception as e:
            print(f"  Warning: could not parse log for retry: {e}")

    # Multi-GPU: each worker takes every Nth game starting at offset worker-id
    if args.num_workers > 1:
        targets = [t for i, t in enumerate(targets) if i % args.num_workers == args.worker_id]
        print(f"=== Worker {args.worker_id}/{args.num_workers} on GPU {args.gpu} "
              f"-- {len(targets)} targets ===")
    else:
        print(f"=== batch_season.py -- {len(targets)} targets  GPU {args.gpu} ===")

    processed = 0
    skipped = 0

    for i, target in enumerate(targets):
        if args.limit and processed >= args.limit:
            print(f"\nLimit reached ({args.limit} games). Stopping.")
            break

        game_id  = target["game_id"]
        matchup  = target.get("matchup", "")
        gdate    = target.get("game_date", "")
        print(f"\n[{i+1}/{len(targets)}] {game_id}  {matchup}  {gdate}")

        # Resume check
        existing_rows = _already_done(game_id)
        if existing_rows:
            print(f"  SKIP -- already processed ({existing_rows:,} rows)")
            skipped += 1
            continue

        if args.dry_run:
            print(f"  [dry-run] Would download + process {game_id}")
            continue

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_row = {"timestamp": ts, "game_id": game_id, "matchup": matchup,
                   "status": "started", "rows": 0, "shots": 0, "poss": 0,
                   "duration_min": 0.0, "error": ""}

        # Step 1: Download
        video_path = _download_video(game_id, matchup, gdate)
        if video_path is None:
            log_row["status"] = "download_failed"
            log_row["error"] = "yt-dlp returned no video"
            _append_log(log_row)
            print(f"  FAILED download -- logged, continuing")
            continue

        # Step 2: Pipeline
        success = _run_pipeline(game_id, video_path, args.frames, gpu=args.gpu)

        # Step 3: Read metrics
        metrics = _read_metrics(game_id)
        log_row.update(metrics)

        # Quality gate -- reject games with too few tracking rows (bad video)
        MIN_ROWS = 10_000
        if success and metrics["rows"] < MIN_ROWS:
            success = False
            log_row["error"] = f"quality_gate: only {metrics['rows']} rows (min {MIN_ROWS})"
            print(f"  QUALITY FAIL -- only {metrics['rows']:,} rows (need {MIN_ROWS:,})")
            # Clean up garbage output so it doesn't block retries
            import shutil
            for parent in (TRACKING_DIR, GAMES_DIR):
                bad_dir = parent / game_id
                if bad_dir.exists():
                    shutil.rmtree(bad_dir, ignore_errors=True)
                    print(f"  Cleaned up {bad_dir}")

        # Step 3b: Clean + regenerate features + validate
        game_dir_path = TRACKING_DIR / game_id
        if not game_dir_path.exists():
            game_dir_path = GAMES_DIR / game_id
        if game_dir_path.exists():
            try:
                sys.path.insert(0, str(PROJECT_DIR))
                from src.data.tracking_cleaner import TrackingCleaner
                from src.data.quality_validator import QualityValidator
                TrackingCleaner(str(game_dir_path)).clean_all()

                # Regenerate features from cleaned tracking data
                td_path = game_dir_path / "tracking_data.csv"
                ft_path = game_dir_path / "features.csv"
                if td_path.exists():
                    from src.features.feature_engineering import run as run_features
                    run_features(
                        input_path=str(td_path),
                        output_path=str(ft_path),
                    )
                    # Re-clean features (sentinel removal on new rolling cols)
                    TrackingCleaner(str(game_dir_path)).clean_features()
                    print(f"  Features regenerated from cleaned tracking data")

                vr = QualityValidator(str(game_dir_path)).validate()
                grade = QualityValidator(str(game_dir_path)).grade()
                log_row["quality_grade"] = grade
                log_row["sentinel_pct"] = vr.get("sentinel_pct", {}).get("value", "")
                log_row["possession_count"] = vr.get("possession_count", {}).get("value", "")
                log_row["median_poss_sec"] = vr.get("median_poss_sec", {}).get("value", "")
                log_row["shot_count"] = vr.get("shot_count", {}).get("value", "")
                log_row["player_name_pct"] = vr.get("player_name_pct", {}).get("value", "")
                log_row["team_abbrev_pct"] = vr.get("team_abbrev_pct", {}).get("value", "")
                print(f"  Quality grade: {grade}")
            except Exception as e:
                print(f"  WARNING: cleaning/validation error: {e}")

        # Step 4: Delete video on success to save disk
        if success:
            try:
                video_path.unlink()
                print(f"  Deleted {video_path}")
            except Exception as e:
                print(f"  Warning: could not delete {video_path}: {e}")
            log_row["status"] = "success"
            processed += 1
            print(f"  SUCCESS -- rows={metrics['rows']:,}  shots={metrics['shots']}  "
                  f"poss={metrics['poss']}  dur={metrics['duration_min']}min")
        else:
            log_row["status"] = log_row.get("error", "") or "pipeline_failed"
            if not log_row.get("error"):
                log_row["error"] = "run_phase_g non-zero exit"
            print(f"  FAILED -- rows={metrics['rows']:,} -- logged, continuing")
            # Delete video on failure too (save disk -- can re-download)
            if video_path.exists():
                try:
                    video_path.unlink()
                    print(f"  Deleted failed video {video_path}")
                except Exception:
                    pass

        _append_log(log_row)
        # Free GPU + CPU memory between games to prevent VRAM fragmentation
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.reset_peak_memory_stats()
        except ImportError:
            pass
        time.sleep(2.0)  # brief pause for memory to settle (reduced 5->2s for throughput)

    print(f"\n=== Done. Processed: {processed}  Skipped: {skipped} ===")
    print(f"Log: {LOG_PATH}")


if __name__ == "__main__":
    main()
