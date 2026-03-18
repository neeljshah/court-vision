"""
benchmark.py — NBA AI Tracking System Benchmark

Downloads real NBA highlight clips, runs tracking on each, evaluates metrics,
and produces a benchmark report. Optionally cross-validates against NBA Stats
shot chart data.

Usage
-----
    conda activate basketball_ai
    cd C:/Users/neelj/nba-ai-system

    # Run on all curated clips (downloads + tracks + evaluates)
    python benchmark.py

    # Run on specific clips only
    python benchmark.py --clips gsw_vs_bos_2022 nba_top10

    # Run on an existing local video (skip download)
    python benchmark.py --local resources/Short4Mosaicing.mp4

    # Full run with NBA Stats API cross-validation
    python benchmark.py --validate --team GSW --game-id 0022301234

    # Quick mode: only 150 frames per clip
    python benchmark.py --frames 150

Output
------
    data/benchmarks/report_<timestamp>.json   — full machine-readable results
    Printed summary table to stdout
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

from src.data.video_fetcher import (
    download_clip, download_curated, calibrate_from_video,
    list_downloaded, CURATED_CLIPS, _VIDEOS_DIR,
)

# Heavy tracking stack (torch / Detectron2) — imported lazily inside functions
def _load_tracking():
    from src.tracking.evaluate import (
        track_video, evaluate_tracking,
        fill_track_gaps, auto_correct_tracking,
    )
    return track_video, evaluate_tracking, fill_track_gaps, auto_correct_tracking

_BENCH_DIR   = os.path.join(PROJECT_DIR, "data", "benchmarks")
_RESOURCE_DIR = os.path.join(PROJECT_DIR, "resources")


# ─────────────────────────────────────────────────────────────────────────────
# Per-video benchmark
# ─────────────────────────────────────────────────────────────────────────────

def benchmark_video(
    video_path: str,
    label: str,
    max_frames: Optional[int] = None,
    yolo_weight_path: Optional[str] = None,
    resources_dir: Optional[str] = None,
) -> dict:
    """
    Run full tracking + evaluation pipeline on one video.

    Returns a result dict with raw + corrected metrics and timing.
    """
    print(f"\n{'─'*60}")
    print(f"  Video:  {label}")
    print(f"  Path:   {video_path}")

    # ── Calibration ───────────────────────────────────────────────────────
    if resources_dir is None:
        resources_dir = _RESOURCE_DIR  # use default if it has a pano

    pano_exists = (
        os.path.exists(os.path.join(resources_dir, "pano_enhanced.png")) or
        os.path.exists(os.path.join(resources_dir, "pano.png"))
    )

    if not pano_exists:
        print("  > Calibrating court from video frames...")
        cal = calibrate_from_video(video_path, resources_dir=resources_dir)
        if not cal["success"]:
            return {
                "label": label, "video": video_path,
                "error": f"Calibration failed: {cal['error']}",
                "skipped": True,
            }
        # Patch pipeline to use this resources_dir
        _patch_resources(resources_dir)

    # ── Track ─────────────────────────────────────────────────────────────
    track_video, evaluate_tracking, fill_track_gaps, auto_correct_tracking = _load_tracking()

    print("  > Tracking...")
    t0 = time.perf_counter()
    try:
        results = track_video(
            video_path,
            yolo_weight_path=yolo_weight_path,
            max_frames=max_frames,
            show=False,
        )
    except Exception as e:
        return {"label": label, "video": video_path, "error": str(e), "skipped": True}
    elapsed = time.perf_counter() - t0

    predictions = results["predictions"]
    n_frames    = results["total_frames"]
    fps_proc    = round(n_frames / max(1e-3, elapsed), 1)

    print(f"     {n_frames} frames in {elapsed:.1f}s ({fps_proc} fps)")

    # ── Evaluate raw ──────────────────────────────────────────────────────
    raw = evaluate_tracking(predictions)

    # ── Fill gaps + auto-correct ──────────────────────────────────────────
    gap_res  = fill_track_gaps(predictions)
    corr_res = auto_correct_tracking(gap_res["predictions"])
    fixed    = evaluate_tracking(corr_res["predictions"])

    # ── Per-player stats ──────────────────────────────────────────────────
    player_stats = _compute_player_stats(predictions)

    return {
        "label":            label,
        "video":            video_path,
        "frames_processed": n_frames,
        "processing_fps":   fps_proc,
        "elapsed_secs":     round(elapsed, 1),
        "raw_metrics":      raw,
        "corrected_metrics": fixed,
        "gaps_filled":      gap_res["gaps_filled"],
        "jumps_fixed":      corr_res["jumps_fixed"],
        "duplicates_removed": corr_res["duplicates_removed"],
        "player_stats":     player_stats,
        "error":            None,
        "skipped":          False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Multi-video benchmark runner
# ─────────────────────────────────────────────────────────────────────────────

def run_benchmark(
    video_paths: list,            # [(label, path), ...]
    max_frames: Optional[int] = None,
    yolo_weight_path: Optional[str] = None,
    validate_game_id: Optional[str] = None,
    validate_team: Optional[str] = None,
) -> dict:
    """
    Run benchmark across multiple videos and produce a consolidated report.
    """
    os.makedirs(_BENCH_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"\n{'='*60}")
    print(f"  NBA AI Tracking Benchmark")
    print(f"  Clips: {len(video_paths)}   Max frames: {max_frames or 'full'}")
    print(f"{'='*60}")

    results = []
    for label, path in video_paths:
        r = benchmark_video(path, label, max_frames=max_frames,
                            yolo_weight_path=yolo_weight_path)
        results.append(r)

    # ── NBA Stats cross-validation (optional) ─────────────────────────────
    validation = None
    if validate_game_id and results:
        print("\n> NBA Stats cross-validation...")
        validation = _cross_validate(
            results[0],   # validate against first clip
            validate_game_id,
            validate_team,
        )

    # ── Aggregate summary ─────────────────────────────────────────────────
    summary = _aggregate(results)
    report = {
        "timestamp":    timestamp,
        "clips":        len(video_paths),
        "summary":      summary,
        "results":      results,
        "validation":   validation,
    }

    # Save report
    report_path = os.path.join(_BENCH_DIR, f"report_{timestamp}.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    # Print summary table
    _print_report(results, summary, validation, report_path)
    return report


# ─────────────────────────────────────────────────────────────────────────────
# Cross-validation with NBA Stats
# ─────────────────────────────────────────────────────────────────────────────

def _cross_validate(result: dict, game_id: str, team: Optional[str]) -> dict:
    try:
        from src.data.nba_stats import fetch_shot_chart, fetch_team_info, validate_tracking_vs_shots

        team_id = None
        if team:
            info    = fetch_team_info(team)
            team_id = info.get("id")

        print(f"  Fetching shot chart for game {game_id}...")
        shots = fetch_shot_chart(game_id, team_id)
        print(f"  {len(shots)} shots found")

        if not shots:
            return {"error": "No shot chart data returned"}

        # We don't have per-frame tracking predictions here — reload from CSV
        predictions = _load_predictions_from_csv()
        if not predictions:
            return {"error": "No CSV tracking data found — run with --eval first"}

        val = validate_tracking_vs_shots(predictions, shots)
        print(f"  Shot detection rate: {val['detection_rate']:.1%}")
        return val

    except Exception as e:
        return {"error": str(e)}


def _load_predictions_from_csv() -> list:
    """Re-build a minimal predictions list from tracking_data.csv if available."""
    import csv
    csv_path = os.path.join(PROJECT_DIR, "data", "tracking_data.csv")
    if not os.path.exists(csv_path):
        return []

    frames: dict = {}
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            fr = int(row["frame"])
            if fr not in frames:
                frames[fr] = []
            frames[fr].append({
                "player_id":  int(row["player_id"]),
                "team":       row["team"],
                "x2d":        int(float(row["x_position"])),
                "y2d":        int(float(row["y_position"])),
                "has_ball":   row["ball_possession"] == "1",
                "confidence": float(row["confidence"]),
            })
    return [{"frame": fr, "tracks": t} for fr, t in sorted(frames.items())]


# ─────────────────────────────────────────────────────────────────────────────
# Per-player stats extraction
# ─────────────────────────────────────────────────────────────────────────────

def _compute_player_stats(predictions: list) -> list:
    """
    From raw predictions, compute per-player summary:
    frames detected, mean confidence, possession frames, estimated distance.
    """
    import math
    player_data: dict = {}

    for fd in predictions:
        for t in fd["tracks"]:
            key = f"{t['team']}_{t['player_id']}"
            if key not in player_data:
                player_data[key] = {
                    "player_id":       t["player_id"],
                    "team":            t["team"],
                    "frames_detected": 0,
                    "possession_frames": 0,
                    "conf_sum":        0.0,
                    "prev_pos":        None,
                    "total_distance":  0.0,
                }
            d = player_data[key]
            d["frames_detected"] += 1
            d["conf_sum"]        += t.get("confidence", 1.0)
            if t.get("has_ball") or t.get("ball_possession"):
                d["possession_frames"] += 1
            pos = (t.get("x2d", 0), t.get("y2d", 0))
            if d["prev_pos"] is not None:
                d["total_distance"] += math.hypot(
                    pos[0] - d["prev_pos"][0],
                    pos[1] - d["prev_pos"][1],
                )
            d["prev_pos"] = pos

    stats = []
    for key, d in player_data.items():
        n = max(1, d["frames_detected"])
        stats.append({
            "key":              key,
            "team":             d["team"],
            "player_id":        d["player_id"],
            "frames_detected":  d["frames_detected"],
            "mean_confidence":  round(d["conf_sum"] / n, 3),
            "possession_frames": d["possession_frames"],
            "estimated_dist_px": round(d["total_distance"], 1),
        })
    stats.sort(key=lambda s: (s["team"], s["player_id"]))
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation + reporting
# ─────────────────────────────────────────────────────────────────────────────

def _aggregate(results: list) -> dict:
    valid = [r for r in results if not r.get("skipped")]
    if not valid:
        return {"error": "No valid results"}

    def mean(key, sub="raw_metrics"):
        vals = [r[sub].get(key, 0) for r in valid if sub in r]
        return round(sum(vals) / max(1, len(vals)), 4) if vals else 0

    return {
        "clips_run":             len(valid),
        "clips_skipped":         len(results) - len(valid),
        "mean_fps":              round(sum(r["processing_fps"] for r in valid) / len(valid), 1),
        "mean_players_per_frame": mean("avg_players_per_frame"),
        "mean_id_switches":      mean("id_switches_estimated"),
        "mean_track_stability":  mean("track_stability"),
        "mean_confidence":       mean("mean_confidence"),
        "mean_oob_detections":   mean("oob_detections"),
        "mean_id_switches_corrected": mean("id_switches_estimated", "corrected_metrics"),
        "mean_stability_corrected":   mean("track_stability", "corrected_metrics"),
        "total_gaps_filled":     sum(r.get("gaps_filled", 0) for r in valid),
        "total_jumps_fixed":     sum(r.get("jumps_fixed", 0) for r in valid),
    }


def _print_report(results: list, summary: dict, validation, report_path: str):
    print(f"\n{'='*60}")
    print(f"  Benchmark Results")
    print(f"{'='*60}")

    # Per-clip table
    header = f"  {'Clip':<22} {'Frames':>6} {'Fps':>5} {'Stab':>6} {'IDsw':>5} {'OOB':>5} {'Conf':>6}"
    print(f"\n{header}")
    print(f"  {'-'*60}")
    for r in results:
        if r.get("skipped"):
            print(f"  {r['label']:<22}  SKIPPED — {r.get('error','')[:30]}")
            continue
        rm = r.get("raw_metrics", {})
        print(
            f"  {r['label']:<22} "
            f"{r['frames_processed']:>6} "
            f"{r['processing_fps']:>5.1f} "
            f"{rm.get('track_stability', 0):>6.3f} "
            f"{rm.get('id_switches_estimated', 0):>5} "
            f"{rm.get('oob_detections', 0):>5} "
            f"{rm.get('mean_confidence', 0):>6.3f}"
        )

    # Summary
    print(f"\n  ── Aggregate ──")
    for k, v in summary.items():
        print(f"  {k:<35} {v}")

    # Auto-correction delta
    print(f"\n  ── Post-correction improvement ──")
    print(f"  {'Metric':<30} {'Raw':>8}  {'Fixed':>8}")
    for r in results:
        if r.get("skipped"):
            continue
        rm = r.get("raw_metrics", {})
        cm = r.get("corrected_metrics", {})
        for key in ("id_switches_estimated", "track_stability", "oob_detections"):
            rv = rm.get(key, 0)
            cv = cm.get(key, 0)
            arrow = " v" if cv < rv else (" ^" if cv > rv else " =")
            print(f"  {r['label'][:15]}.{key[:14]:<29} {rv!s:>8}  {cv!s:>8}{arrow}")
        break  # only print for first clip to keep it concise

    # Player stats
    if results and not results[0].get("skipped"):
        ps = results[0].get("player_stats", [])
        if ps:
            print(f"\n  ── Player tracking summary (clip 1) ──")
            print(f"  {'Key':<18} {'Frames':>6} {'Conf':>6} {'Poss':>5} {'Dist(px)':>9}")
            for p in ps:
                print(
                    f"  {p['key']:<18} "
                    f"{p['frames_detected']:>6} "
                    f"{p['mean_confidence']:>6.3f} "
                    f"{p['possession_frames']:>5} "
                    f"{p['estimated_dist_px']:>9.0f}"
                )

    # Validation
    if validation and not validation.get("error"):
        print(f"\n  ── NBA Stats cross-validation ──")
        for k, v in validation.items():
            print(f"  {k:<35} {v}")

    print(f"\n  Report saved -> {report_path}")
    print(f"{'='*60}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline resource patching (for custom resources_dir)
# ─────────────────────────────────────────────────────────────────────────────

def _patch_resources(resources_dir: str):
    """
    Temporarily override the _RESOURCES constant in pipeline modules
    so calibrate_from_video outputs are picked up for this run.
    (Only needed when resources_dir != default resources/)
    """
    import src.pipeline.unified_pipeline as up
    import src.tracking.video_handler    as vh
    up._RESOURCES = resources_dir  # type: ignore[attr-defined]
    vh._RESOURCES_DIR = resources_dir  # type: ignore[attr-defined]


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="NBA AI Tracking Benchmark")
    ap.add_argument("--clips",    nargs="*", default=None,
                    help=f"Curated clip labels to download+test. Available: {list(CURATED_CLIPS)}")
    ap.add_argument("--local",    nargs="*", default=None,
                    help="Local video file(s) to benchmark (skip download)")
    ap.add_argument("--url",      default=None,
                    help="Single YouTube URL to download and benchmark")
    ap.add_argument("--frames",   type=int, default=300,
                    help="Max frames per clip (default: 300 for speed)")
    ap.add_argument("--full",     action="store_true",
                    help="Process full videos (overrides --frames)")
    ap.add_argument("--yolo",     default=None,
                    help="YOLO-NAS weights path")
    ap.add_argument("--validate", action="store_true",
                    help="Cross-validate with NBA Stats API")
    ap.add_argument("--game-id",  default=None,
                    help="NBA game ID for shot-chart validation")
    ap.add_argument("--team",     default=None,
                    help="Team abbreviation for NBA validation (e.g. GSW)")
    ap.add_argument("--list",     action="store_true",
                    help="List available curated clips and downloaded videos, then exit")
    args = ap.parse_args()

    if args.list:
        print("\nCurated clips:")
        for k, v in CURATED_CLIPS.items():
            print(f"  {k:<25}  {v}")
        print("\nDownloaded:")
        for d in list_downloaded():
            print(f"  {d['label']:<25}  {d['size_mb']} MB  {d['path']}")
        return

    # Build video list
    video_pairs = []

    if args.local:
        for path in args.local:
            if not os.path.exists(path):
                print(f"[!]  File not found: {path}")
                continue
            label = os.path.splitext(os.path.basename(path))[0]
            video_pairs.append((label, os.path.abspath(path)))

    if args.url:
        print(f"Downloading: {args.url}")
        try:
            path = download_clip(args.url)
            label = os.path.splitext(os.path.basename(path))[0]
            video_pairs.append((label, path))
        except RuntimeError as e:
            print(f"[!]  Download failed: {e}")

    if args.clips is not None or (not video_pairs and not args.url):
        # Default: download curated clips
        clip_keys = args.clips  # None -> all
        paths = download_curated(clip_keys)
        for p in paths:
            label = os.path.splitext(os.path.basename(p))[0]
            video_pairs.append((label, p))

    # Always include the default local video as baseline
    default_video = os.path.join(PROJECT_DIR, "resources", "Short4Mosaicing.mp4")
    if os.path.exists(default_video) and not any(p == default_video for _, p in video_pairs):
        video_pairs.insert(0, ("Short4Mosaicing_baseline", default_video))

    if not video_pairs:
        print("No videos to benchmark. Use --local, --url, or --clips.")
        return

    max_frames = None if args.full else args.frames

    run_benchmark(
        video_pairs,
        max_frames=max_frames,
        yolo_weight_path=args.yolo,
        validate_game_id=args.game_id if args.validate else None,
        validate_team=args.team,
    )


if __name__ == "__main__":
    main()
