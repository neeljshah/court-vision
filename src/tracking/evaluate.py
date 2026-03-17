"""
evaluate.py — Self-contained tracking evaluator and auto-corrector

Public API
----------
    track_video(video_path, **kwargs)           -> dict
    evaluate_tracking(predictions, gt=None)    -> dict
    fill_track_gaps(predictions, max_gap=5)    -> dict
    auto_correct_tracking(predictions)         -> dict
    run_self_test(video_path)                  -> None   (prints full report)

All functions operate on the canonical predictions format:
    [ {"frame": int, "tracks": [ {"player_id", "team", "bbox",
                                   "x2d", "y2d", "confidence", ...} ]} ]
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

# ── Tuning ────────────────────────────────────────────────────────────────────

JUMP_THRESH           = 350   # px — 2D court position jump treated as ID switch / error
                              # Calibrated for ~2800px-wide map (≈3.7m physical jump threshold)
DUPLICATE_DIST        = 130   # px — two same-team players closer than this = duplicate
                              # Scaled from 40px on 900px court → ~130px on 2800px court
SMOOTH_ALPHA          = 0.4   # EMA smoothing weight (0 = heavy smooth, 1 = raw)
MIN_PLAYERS_PER_FRAME = 3     # below this → frame flagged as low coverage
EXPECTED_TEAM_SIZE    = 5     # players per team
MAX_GAP_FRAMES        = 5     # fill track gaps up to this many consecutive missing frames
COURT_BOUNDS          = (0, 0, 3500, 1800)  # (x_min, y_min, x_max, y_max) in 2D court px
                               # pano_enhanced → map_2d is 3404×1711 at runtime; 3500 gives margin


# ─────────────────────────────────────────────────────────────────────────────
# 1. track_video
# ─────────────────────────────────────────────────────────────────────────────

def track_video(
    video_path: str,
    yolo_weight_path: Optional[str] = None,
    max_frames: Optional[int] = None,
    show: bool = False,
    output_video_path: Optional[str] = None,
) -> dict:
    """
    Run the full tracking pipeline on a video.

    Args:
        video_path:         Path to input .mp4.
        yolo_weight_path:   Optional YOLO-NAS weights for ball/event detection.
        max_frames:         Cap on frames to process (None = full video).
        show:               Display live visualisation window.
        output_video_path:  Write annotated debug video here if provided.

    Returns:
        Dict with keys:
            predictions   — per-frame tracking list
            stats         — per-player shot counts (YOLO mode only)
            id_switches   — estimated ID switch count
            stability     — track stability score [0, 1]
            total_frames  — frames processed
    """
    from src.pipeline.unified_pipeline import UnifiedPipeline

    pipeline = UnifiedPipeline(
        video_path=video_path,
        yolo_weight_path=yolo_weight_path,
        max_frames=max_frames,
        show=show,
        output_video_path=output_video_path,
    )
    return pipeline.run()


# ─────────────────────────────────────────────────────────────────────────────
# 2. evaluate_tracking  (extended — superset of advanced_tracker version)
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_tracking(
    predictions: List[dict],
    ground_truth: Optional[List[dict]] = None,
) -> dict:
    """
    Compute tracking quality metrics.

    When ground_truth is provided: MOTA, IDF1, mean IoU, position error.
    Always computed: ID switches, coverage, confidence, team balance, duplicates.

    Args:
        predictions:  List of {"frame": int, "tracks": [...]} dicts.
        ground_truth: Same format, or None for self-consistency metrics only.

    Returns:
        Flat dict of scalar metrics.
    """
    base = _self_metrics(predictions)

    if ground_truth is not None:
        base.update(_gt_metrics(predictions, ground_truth))

    return base


def _self_metrics(predictions: List[dict]) -> dict:
    """Self-consistency metrics that require no ground truth."""
    id_switches = position_jumps = duplicate_frames = total = 0
    low_coverage_frames = oob_detections = 0
    conf_sum = conf_n = 0
    team_imbalance_frames = 0
    xmin, ymin, xmax, ymax = COURT_BOUNDS

    prev_pos: Dict[str, Tuple[int, int]] = {}

    for fd in predictions:
        tracks = fd["tracks"]
        n = len(tracks)
        total += n

        if n < MIN_PLAYERS_PER_FRAME:
            low_coverage_frames += 1

        # Team balance — only flag when both team labels are present in the data.
        # When all players are unified to "green" (single-pool tracking mode),
        # "white" will always be 0, which is expected — not an imbalance.
        teams: Dict[str, int] = defaultdict(int)
        for t in tracks:
            teams[t["team"]] += 1
        both_teams_present = teams["green"] > 0 and teams["white"] > 0
        if both_teams_present:
            if min(teams["green"], teams["white"]) < 2:
                team_imbalance_frames += 1

        # Duplicate detection (same team, too close in 2D court space)
        by_team: Dict[str, list] = defaultdict(list)
        for t in tracks:
            by_team[t["team"]].append((t.get("x2d", 0), t.get("y2d", 0)))
        for positions in by_team.values():
            for i in range(len(positions)):
                for j in range(i + 1, len(positions)):
                    if _dist(positions[i], positions[j]) < DUPLICATE_DIST:
                        duplicate_frames += 1

        # Position jumps / ID switches / out-of-bounds
        # Interpolated gap-fill positions are synthetic — skip them for all quality metrics.
        for t in tracks:
            if t.get("interpolated", False):
                continue
            key = f"{t['team']}_{t['player_id']}"
            x, y = t.get("x2d", 0), t.get("y2d", 0)
            pos  = (x, y)
            conf_sum += t.get("confidence", 1.0)
            conf_n   += 1

            if not (xmin <= x <= xmax and ymin <= y <= ymax):
                oob_detections += 1

            if key in prev_pos:
                d = _dist(prev_pos[key], pos)
                if d > JUMP_THRESH:
                    position_jumps += 1
                    id_switches    += 1
            prev_pos[key] = pos

    n_frames = max(1, len(predictions))
    return {
        "self_evaluation":          True,
        "total_frames":             n_frames,
        "total_detections":         total,
        "avg_players_per_frame":    round(total / n_frames, 2),
        "id_switches_estimated":    id_switches,
        "position_jumps":           position_jumps,
        "track_stability":          round(1.0 - id_switches / max(1, total), 4),
        "mean_confidence":          round(conf_sum / max(1, conf_n), 4),
        "low_coverage_frames":      low_coverage_frames,
        "oob_detections":           oob_detections,
        "duplicate_detections":     duplicate_frames,
        "team_imbalance_frames":    team_imbalance_frames,
    }


def _gt_metrics(predictions: List[dict], ground_truth: List[dict]) -> dict:
    """MOTA / IDF1 / IoU / position error against ground truth."""
    from src.tracking.advanced_tracker import _iou, _assign

    gt_by_frame   = {f["frame"]: f["tracks"] for f in ground_truth}
    pred_by_frame = {f["frame"]: f["tracks"] for f in predictions}
    all_frames    = sorted(set(gt_by_frame) | set(pred_by_frame))

    tp = fp = fn = idsw = 0
    iou_sum = iou_n = pos_err_sum = pos_err_n = 0
    gt_id_map: Dict[str, str] = {}

    for fr in all_frames:
        gt_t   = gt_by_frame.get(fr, [])
        pred_t = pred_by_frame.get(fr, [])
        if not gt_t:
            fp += len(pred_t); continue
        if not pred_t:
            fn += len(gt_t);  continue

        cost = np.ones((len(gt_t), len(pred_t)), dtype=np.float32)
        for gi, g in enumerate(gt_t):
            for pi, p in enumerate(pred_t):
                if g.get("bbox") and p.get("bbox"):
                    cost[gi, pi] = 1.0 - _iou(g["bbox"], p["bbox"])

        matched_g: set = set()
        matched_p: set = set()
        for gi, pi in _assign(cost):
            if cost[gi, pi] < 0.5:
                tp += 1
                matched_g.add(gi); matched_p.add(pi)
                iou_sum += 1.0 - cost[gi, pi]; iou_n += 1
                gpos = (gt_t[gi].get("x2d", 0), gt_t[gi].get("y2d", 0))
                ppos = (pred_t[pi].get("x2d", 0), pred_t[pi].get("y2d", 0))
                pos_err_sum += _dist(gpos, ppos); pos_err_n += 1
                gk = f"{gt_t[gi]['team']}_{gt_t[gi]['player_id']}"
                pk = f"{pred_t[pi]['team']}_{pred_t[pi]['player_id']}"
                if gk in gt_id_map and gt_id_map[gk] != pk:
                    idsw += 1
                gt_id_map[gk] = pk
        fp += len(pred_t) - len(matched_p)
        fn += len(gt_t)   - len(matched_g)

    n_gt  = max(1, sum(len(f["tracks"]) for f in ground_truth))
    mota  = max(0.0, 1.0 - (fp + fn + idsw) / n_gt)
    id_p  = tp / max(1, tp + fp)
    id_r  = tp / max(1, tp + fn)
    idf1  = 2 * id_p * id_r / max(1e-9, id_p + id_r)

    return {
        "mota":           round(mota, 4),
        "idf1":           round(idf1, 4),
        "gt_id_switches": idsw,
        "mean_iou":       round(iou_sum / max(1, iou_n), 4),
        "position_error": round(pos_err_sum / max(1, pos_err_n), 2),
        "fp_per_frame":   round(fp / max(1, len(all_frames)), 3),
        "fn_per_frame":   round(fn / max(1, len(all_frames)), 3),
        "coverage":       round(tp / n_gt, 4),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. fill_track_gaps
# ─────────────────────────────────────────────────────────────────────────────

def fill_track_gaps(
    predictions: List[dict],
    max_gap: int = MAX_GAP_FRAMES,
) -> dict:
    """
    Interpolate missing track positions for short gaps (player briefly off-screen).

    For each player, if they disappear for ≤ max_gap consecutive frames and
    reappear afterwards, linearly interpolate their 2D court position for the
    missing frames. Interpolated entries are marked with confidence=0 and
    interpolated=True so downstream code can distinguish them from real detections.

    Args:
        predictions: Per-frame tracking list.
        max_gap:     Maximum consecutive missing frames to fill (default 5).

    Returns:
        {
          "predictions":      updated list (same structure, more tracks per frame),
          "gaps_filled":      int  (total interpolated player-frames inserted),
          "players_affected": int  (unique player tracks that had gaps filled),
        }
    """
    # Build per-player trajectory: {key: [(frame, x, y)]}
    traj: Dict[str, List[Tuple[int, int, int]]] = defaultdict(list)
    meta: Dict[str, dict] = {}  # key → sample track dict for team/id info

    for fd in predictions:
        for t in fd["tracks"]:
            key = f"{t['team']}_{t['player_id']}"
            traj[key].append((fd["frame"], t.get("x2d", 0), t.get("y2d", 0)))
            meta[key] = t

    # Collect interpolated positions: {frame: [(key, x, y)]}
    inserts: Dict[int, List[Tuple[str, int, int]]] = defaultdict(list)
    gaps_filled = 0
    players_affected: set = set()

    for key, pts in traj.items():
        for i in range(len(pts) - 1):
            f0, x0, y0 = pts[i]
            f1, x1, y1 = pts[i + 1]
            gap = f1 - f0 - 1
            if 0 < gap <= max_gap:
                for step in range(1, gap + 1):
                    t_frac = step / (gap + 1)
                    ix = int(round(x0 + (x1 - x0) * t_frac))
                    iy = int(round(y0 + (y1 - y0) * t_frac))
                    inserts[f0 + step].append((key, ix, iy))
                gaps_filled += gap
                players_affected.add(key)

    if not inserts:
        return {"predictions": predictions, "gaps_filled": 0, "players_affected": 0}

    # Merge interpolated points into predictions
    fd_by_frame = {fd["frame"]: fd for fd in predictions}
    all_frames  = sorted(set(fd_by_frame) | set(inserts))
    updated: List[dict] = []

    for frame in all_frames:
        tracks = list(fd_by_frame[frame]["tracks"]) if frame in fd_by_frame else []

        existing_keys = {f"{t['team']}_{t['player_id']}" for t in tracks}
        for key, ix, iy in inserts.get(frame, []):
            if key in existing_keys:
                continue  # real detection exists — don't overwrite
            src = meta[key]
            tracks.append({
                "player_id":    src["player_id"],
                "team":         src["team"],
                "bbox":         None,
                "x2d":          ix,
                "y2d":          iy,
                "confidence":   0.0,
                "interpolated": True,
            })

        updated.append({"frame": frame, "tracks": tracks})

    return {
        "predictions":      updated,
        "gaps_filled":      gaps_filled,
        "players_affected": len(players_affected),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. auto_correct_tracking
# ─────────────────────────────────────────────────────────────────────────────

def auto_correct_tracking(predictions: List[dict]) -> dict:
    """
    Post-process tracking output to fix common errors.

    Corrections applied (in order):
        1. Position-jump linear interpolation — replaces teleporting positions
           with a point linearly interpolated between the last stable position
           and the next detected position.
        2. EMA smoothing — applied AFTER jump correction so smooth values are
           based on already-corrected trajectories.
        3. Duplicate removal — if two same-team tracks are within DUPLICATE_DIST
           in the same frame, keep the higher-confidence one.

    Returns:
        {
          "predictions":        corrected predictions list,
          "jumps_fixed":        int,
          "smoothed":           int  (unique tracks smoothed),
          "duplicates_removed": int,
        }
    """
    import copy
    predictions = copy.deepcopy(predictions)

    # Build trajectory index: key → list of (frame, x, y) sorted by frame
    traj: Dict[str, List[Tuple[int, int, int]]] = defaultdict(list)
    for fd in predictions:
        for t in fd["tracks"]:
            key = f"{t['team']}_{t['player_id']}"
            traj[key].append((fd["frame"], t.get("x2d", 0), t.get("y2d", 0)))
    for pts in traj.values():
        pts.sort(key=lambda p: p[0])

    # ── 1. Linear interpolation for jumps ────────────────────────────────
    jump_map: Dict[Tuple[str, int], Tuple[int, int]] = {}
    jumps_fixed = 0

    for key, pts in traj.items():
        for i in range(1, len(pts)):
            fr, x, y   = pts[i]
            _, px, py  = pts[i - 1]
            if _dist((x, y), (px, py)) > JUMP_THRESH:
                if i + 1 < len(pts):
                    _, nx, ny = pts[i + 1]
                    # True midpoint of the non-jumping trajectory
                    ix = int(round((px + nx) / 2))
                    iy = int(round((py + ny) / 2))
                else:
                    # No future point — hold at last stable position
                    ix, iy = px, py
                jump_map[(key, fr)] = (ix, iy)
                jumps_fixed += 1
                # Update traj so next iteration sees the corrected value
                pts[i] = (fr, ix, iy)

    # ── 2. EMA smoothing (on jump-corrected positions) ────────────────────
    ema: Dict[str, Tuple[float, float]] = {}
    smooth_map: Dict[Tuple[str, int], Tuple[int, int]] = {}
    smoothed_keys: set = set()

    for key, pts in traj.items():
        for fr, x, y in pts:
            # Use jump-corrected value if available
            cx, cy = jump_map.get((key, fr), (x, y))
            if key in ema:
                ex = SMOOTH_ALPHA * cx + (1 - SMOOTH_ALPHA) * ema[key][0]
                ey = SMOOTH_ALPHA * cy + (1 - SMOOTH_ALPHA) * ema[key][1]
            else:
                ex, ey = float(cx), float(cy)
            ema[key] = (ex, ey)
            smooth_map[(key, fr)] = (int(round(ex)), int(round(ey)))
            smoothed_keys.add(key)

    # ── 3. Apply corrections + duplicate removal ──────────────────────────
    duplicates_removed = 0
    corrected: List[dict] = []

    for fd in predictions:
        frame  = fd["frame"]
        tracks = fd["tracks"]

        for t in tracks:
            key = f"{t['team']}_{t['player_id']}"
            if (key, frame) in smooth_map:
                t["x2d"], t["y2d"] = smooth_map[(key, frame)]

        # Remove duplicates — same team, too close in 2D court space
        kept: List[dict] = []
        by_team: Dict[str, List[dict]] = defaultdict(list)
        for t in tracks:
            by_team[t["team"]].append(t)

        for tm_tracks in by_team.values():
            to_remove: set = set()
            for i in range(len(tm_tracks)):
                for j in range(i + 1, len(tm_tracks)):
                    pi = (tm_tracks[i].get("x2d", 0), tm_tracks[i].get("y2d", 0))
                    pj = (tm_tracks[j].get("x2d", 0), tm_tracks[j].get("y2d", 0))
                    if _dist(pi, pj) < DUPLICATE_DIST:
                        ci = tm_tracks[i].get("confidence", 1.0)
                        cj = tm_tracks[j].get("confidence", 1.0)
                        to_remove.add(j if ci >= cj else i)
                        duplicates_removed += 1
            for idx, t in enumerate(tm_tracks):
                if idx not in to_remove:
                    kept.append(t)

        corrected.append({"frame": frame, "tracks": kept})

    return {
        "predictions":        corrected,
        "jumps_fixed":        jumps_fixed,
        "smoothed":           len(smoothed_keys),
        "duplicates_removed": duplicates_removed,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. run_self_test
# ─────────────────────────────────────────────────────────────────────────────

def run_self_test(
    video_path: str,
    max_frames: int = 200,
    yolo_weight_path: Optional[str] = None,
):
    """
    Full self-test: track → evaluate (raw) → auto-correct → evaluate (corrected).
    Prints a formatted report. No ground truth required.

    Args:
        video_path:       Video to test on.
        max_frames:       Frames to process (keep small for a quick test).
        yolo_weight_path: Optional YOLO weights.
    """
    print(f"\n{'='*60}")
    print(f"  NBA AI Tracking Self-Test")
    print(f"  Video:  {os.path.basename(video_path)}")
    print(f"  Frames: {max_frames}")
    print(f"{'='*60}\n")

    # ── Step 1: Track ──────────────────────────────────────────────────────
    print("► Running tracker...")
    results = track_video(
        video_path,
        yolo_weight_path=yolo_weight_path,
        max_frames=max_frames,
        show=False,
    )
    predictions = results["predictions"]
    print(f"  Frames processed: {results['total_frames']}")
    print()

    # ── Step 2: Evaluate raw output ────────────────────────────────────────
    print("► Evaluating raw tracking output...")
    raw_metrics = evaluate_tracking(predictions)
    _print_metrics("Raw Metrics", raw_metrics)

    # ── Step 3: Sanity checks ──────────────────────────────────────────────
    print("\n► Sanity checks:")
    _sanity_checks(predictions, raw_metrics)

    # ── Step 4: Fill track gaps ───────────────────────────────────────────
    print("\n► Filling track gaps (linear interpolation)...")
    gap_result = fill_track_gaps(predictions)
    print(f"  Player-frames filled:  {gap_result['gaps_filled']}")
    print(f"  Players affected:      {gap_result['players_affected']}")

    # ── Step 5: Auto-correct ───────────────────────────────────────────────
    print("\n► Auto-correcting tracking errors...")
    correction = auto_correct_tracking(gap_result["predictions"])
    print(f"  Jumps interpolated:    {correction['jumps_fixed']}")
    print(f"  Tracks smoothed:       {correction['smoothed']}")
    print(f"  Duplicates removed:    {correction['duplicates_removed']}")

    # ── Step 6: Re-evaluate corrected output ──────────────────────────────
    print()
    corrected_metrics = evaluate_tracking(correction["predictions"])
    _print_metrics("Corrected Metrics", corrected_metrics)

    # ── Step 7: Delta summary ──────────────────────────────────────────────
    print("\n► Improvement delta:")
    for key in ("id_switches_estimated", "position_jumps", "oob_detections",
                "duplicate_detections", "track_stability", "mean_confidence"):
        r = raw_metrics.get(key, 0)
        c = corrected_metrics.get(key, 0)
        arrow = "↓" if c < r else ("↑" if c > r else "=")
        print(f"  {key:<30} {r!s:>8}  →  {c!s:<8} {arrow}")

    print(f"\n{'='*60}")
    print("  Self-test complete.")
    print(f"{'='*60}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _dist(a: Tuple, b: Tuple) -> float:
    return float(np.hypot(a[0] - b[0], a[1] - b[1]))


def _print_metrics(title: str, metrics: dict):
    print(f"\n  ── {title} ──")
    skip = {"self_evaluation", "note"}
    for k, v in metrics.items():
        if k not in skip:
            print(f"  {k:<32} {v}")


def _sanity_checks(predictions: List[dict], metrics: dict):
    issues = []

    avg = metrics.get("avg_players_per_frame", 0)
    if avg < MIN_PLAYERS_PER_FRAME:
        issues.append(f"LOW COVERAGE: only {avg:.1f} players/frame on average "
                      f"(expected ≥ {MIN_PLAYERS_PER_FRAME})")

    id_sw = metrics.get("id_switches_estimated", 0)
    n_fr  = max(1, metrics.get("total_frames", 1))
    if id_sw / n_fr > 0.1:
        issues.append(f"HIGH ID SWITCH RATE: {id_sw} over {n_fr} frames "
                      f"({id_sw/n_fr:.2f}/frame)")

    if metrics.get("team_imbalance_frames", 0) > n_fr * 0.2:
        issues.append("TEAM IMBALANCE: >20% of frames have a team with 0 detections")

    if metrics.get("duplicate_detections", 0) > 0:
        issues.append(f"DUPLICATES: {metrics['duplicate_detections']} duplicate "
                      "detection pairs across frames")

    if not issues:
        print("  All sanity checks passed.")
    else:
        for issue in issues:
            print(f"  ⚠  {issue}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    _DEFAULT_VIDEO = os.path.join(PROJECT_DIR, "resources", "Short4Mosaicing.mp4")

    ap = argparse.ArgumentParser(description="NBA AI Tracking Evaluator")
    ap.add_argument("--video",  default=_DEFAULT_VIDEO, help="Input video path")
    ap.add_argument("--yolo",   default=None,           help="YOLO-NAS weights path")
    ap.add_argument("--frames", type=int, default=200,  help="Max frames to process")
    args = ap.parse_args()

    run_self_test(
        video_path=args.video,
        max_frames=args.frames,
        yolo_weight_path=args.yolo,
    )
