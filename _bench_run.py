"""
_bench_run.py — Automated benchmark + improvement loop for NBA AI tracker.

Usage
-----
    conda run -n basketball_ai python _bench_run.py
    conda run -n basketball_ai python _bench_run.py --video bos_mia_2025 --game-id 0022400307
    conda run -n basketball_ai python _bench_run.py --frames 150
"""

import argparse
import csv
import glob
import json
import os
import sys
import time
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

BENCH_DIR  = os.path.join(PROJECT_DIR, "data", "benchmarks")
VIDEOS_DIR = os.path.join(PROJECT_DIR, "data", "videos")

# Known clips with game_ids
CLIP_MAP = {
    "gsw_lakers_2025":    "0022401117",
    "bos_mia_2025":       "0022400307",
    "okc_dal_2025":       None,
    "mil_chi_2025":       None,
    "den_phx_2025":       None,
    "lal_sas_2025":       None,
    "atl_ind_2025":       None,
    "mem_nop_2025":       None,
    "mia_bkn_2025":       None,
    "phi_tor_2025":       None,
    "sac_por_2025":       None,
    "bos_mia_playoffs":   None,
    "den_gsw_playoffs":   None,
    "cavs_vs_celtics_2025": "0022400710",
    "cavs_broadcast_2025": None,
}

# ─────────────────────────────────────────────────────────────────────────────
# Clip rotation
# ─────────────────────────────────────────────────────────────────────────────

def pick_next_clip(forced: str = None):
    """Round-robin through available local clips."""
    if forced:
        label = forced
        return label, os.path.join(VIDEOS_DIR, f"{label}.mp4"), CLIP_MAP.get(label)

    state_file = os.path.join(BENCH_DIR, "clip_rotation.json")
    os.makedirs(BENCH_DIR, exist_ok=True)

    # Only use clips that exist locally
    available = [
        label for label in CLIP_MAP
        if os.path.exists(os.path.join(VIDEOS_DIR, f"{label}.mp4"))
    ]
    if not available:
        raise RuntimeError("No local clips found in data/videos/")

    state = {}
    if os.path.exists(state_file):
        with open(state_file) as f:
            state = json.load(f)

    last_idx = state.get("last_idx", -1)
    next_idx = (last_idx + 1) % len(available)
    label = available[next_idx]

    state["last_idx"] = next_idx
    state["last_clip"] = label
    with open(state_file, "w") as f:
        json.dump(state, f)

    return label, os.path.join(VIDEOS_DIR, f"{label}.mp4"), CLIP_MAP.get(label)


# ─────────────────────────────────────────────────────────────────────────────
# Run pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline(video_path: str, game_id: str, max_frames: int):
    """Run UnifiedPipeline + feature engineering. Returns (results, fps, error)."""
    from src.pipeline.unified_pipeline import UnifiedPipeline
    from src.features.feature_engineering import run as run_features

    data_dir = os.path.join(PROJECT_DIR, "data")
    t0 = time.perf_counter()

    try:
        pipeline = UnifiedPipeline(
            video_path=video_path,
            max_frames=max_frames,
            show=False,
        )
        results = pipeline.run()
    except Exception as e:
        return None, 0.0, str(e)

    elapsed = time.perf_counter() - t0
    fps = round(results["total_frames"] / max(0.001, elapsed), 1)

    # Feature engineering
    try:
        run_features(
            input_path=os.path.join(data_dir, "tracking_data.csv"),
            output_path=os.path.join(data_dir, "features.csv"),
        )
    except Exception:
        pass

    return results, fps, None


# ─────────────────────────────────────────────────────────────────────────────
# Evaluate CSV layers
# ─────────────────────────────────────────────────────────────────────────────

def _csv_rows(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def evaluate_layers(data_dir: str, results: dict, game_id: str):
    """Evaluate output CSV files into L1-L6 layer metrics."""
    layers = {}

    # ── L1: tracking_data.csv ────────────────────────────────────────────────
    rows = _csv_rows(os.path.join(data_dir, "tracking_data.csv"))
    if rows:
        events = [r.get("event", "none") for r in rows]
        confs  = [float(r.get("confidence", 0)) for r in rows if r.get("confidence")]
        team_a = sum(1 for r in rows if r.get("team") not in ("green", "red", "unknown", "referee", ""))
        team_b = sum(1 for r in rows if r.get("team") in ("green",))  # adjust per your labeling

        layers["L1_CV_Tracking"] = {
            "rows":             len(rows),
            "cols":             list(rows[0].keys()) if rows else [],
            "team_a_rows":      0,
            "team_b_rows":      0,
            "zero_position_pct": sum(1 for r in rows if float(r.get("x_position", 0)) == 0) / max(1, len(rows)),
            "nan_possession_pct": sum(1 for r in rows if not r.get("ball_possession")) / max(1, len(rows)),
            "shot_events":      events.count("shot"),
            "pass_events":      events.count("pass"),
            "dribble_events":   events.count("dribble"),
            "none_events":      events.count("none"),
            "mean_confidence":  round(sum(confs) / max(1, len(confs)), 3),
            "status":           "PASS" if rows else "FAIL",
        }
    else:
        layers["L1_CV_Tracking"] = {"status": "FAIL", "rows": 0}

    # ── L2: ball_tracking.csv ────────────────────────────────────────────────
    ball_rows = _csv_rows(os.path.join(data_dir, "ball_tracking.csv"))
    if ball_rows:
        # Support both column naming conventions
        valid = sum(
            1 for r in ball_rows
            if float(r.get("ball_x", r.get("ball_x2d", 0)) or 0) > 0
        )
        valid_pct = round(valid / max(1, len(ball_rows)), 3)
        layers["L2_Ball"] = {
            "status": "PASS" if valid_pct > 0.3 else "FAIL",
            "rows": len(ball_rows),
            "valid_ball_pct": valid_pct,
        }
    else:
        layers["L2_Ball"] = {"status": "FAIL", "rows": 0, "valid_ball_pct": 0.0}

    # Live/dead ball split (requires game_id for PBP mask)
    if game_id and ball_rows:
        try:
            from src.data.nba_enricher import build_live_mask
            live_mask = build_live_mask(game_id)
            if live_mask:
                live_valid = sum(
                    1 for i, r in enumerate(ball_rows)
                    if live_mask.get(i, "unknown") == "live"
                    and float(r.get("ball_x", r.get("ball_x2d", 0)) or 0) > 0
                )
                live_total = sum(
                    1 for i in range(len(ball_rows))
                    if live_mask.get(i, "unknown") == "live"
                )
                dead_valid = sum(
                    1 for i, r in enumerate(ball_rows)
                    if live_mask.get(i, "unknown") == "dead_ball"
                    and float(r.get("ball_x", r.get("ball_x2d", 0)) or 0) > 0
                )
                dead_total = sum(
                    1 for i in range(len(ball_rows))
                    if live_mask.get(i, "unknown") == "dead_ball"
                )
                layers["L2_Ball"]["ball_valid_live"] = round(live_valid / max(1, live_total), 3)
                layers["L2_Ball"]["ball_valid_dead"] = round(dead_valid / max(1, dead_total), 3)
                layers["L2_Ball"]["live_frames"]     = live_total
                layers["L2_Ball"]["dead_frames"]     = dead_total
        except Exception:
            pass  # non-fatal: live/dead split is diagnostic only

    # ── L3: possessions.csv ──────────────────────────────────────────────────
    poss_rows = _csv_rows(os.path.join(data_dir, "possessions.csv"))
    if poss_rows:
        nan_result = sum(1 for r in poss_rows if not r.get("result") or r.get("result") in ("", "nan")) / max(1, len(poss_rows))
        durs = [float(r["duration"]) for r in poss_rows if r.get("duration") and r["duration"] not in ("", "nan")]
        layers["L3_Possessions"] = {
            "status": "PASS" if nan_result < 0.5 else "WARN",
            "rows": len(poss_rows),
            "nan_result_pct": round(nan_result * 100, 1),
            "avg_duration_sec": round(sum(durs) / max(1, len(durs)), 1) if durs else 0,
        }
    else:
        layers["L3_Possessions"] = {"status": "WARN", "rows": 0}

    # ── L4: NBA enrichment ───────────────────────────────────────────────────
    shot_log = _csv_rows(os.path.join(data_dir, "shot_log.csv"))
    enriched = _csv_rows(os.path.join(data_dir, "shot_log_enriched.csv"))
    shots_det = layers.get("L1_CV_Tracking", {}).get("shot_events", len(shot_log))
    shots_enr = len([r for r in enriched if r.get("made") not in ("", None)]) if enriched else 0

    # Check NBA API reachable
    try:
        from src.data.nba_stats import fetch_team_info
        fetch_team_info("GSW")
        api_ok = True
    except Exception:
        api_ok = False

    layers["L4_NBA_Enrich"] = {
        "status": "PASS" if shots_enr > 0 else ("WARN" if game_id else "SKIP"),
        "shots_detected": shots_det,
        "shots_enriched": shots_enr,
        "game_id_found": bool(game_id),
    }

    # ── L5: features.csv ─────────────────────────────────────────────────────
    feat_rows = _csv_rows(os.path.join(data_dir, "features.csv"))
    if feat_rows:
        high_nan = []
        for col in feat_rows[0].keys():
            nan_count = sum(1 for r in feat_rows if not r.get(col) or r[col] in ("", "nan", "None"))
            if nan_count / len(feat_rows) > 0.5:
                high_nan.append(col)
        layers["L5_Features"] = {
            "status": "PASS" if not high_nan else "WARN",
            "rows": len(feat_rows),
            "cols": len(feat_rows[0].keys()),
            "high_nan_cols": high_nan[:5],
        }
    else:
        layers["L5_Features"] = {"status": "WARN", "rows": 0}

    # ── L6: Models ───────────────────────────────────────────────────────────
    model_status = {}
    try:
        from src.prediction.win_probability import WinProbModel
        m = WinProbModel()
        m.load()
        model_status["win_prob"] = "PASS"
    except Exception as e:
        model_status["win_prob"] = f"FAIL: {e}"

    try:
        from src.prediction.player_props import predict_props
        model_status["props"] = "PASS"
    except Exception as e:
        model_status["props"] = f"FAIL: {e}"

    try:
        from src.data.injury_monitor import InjuryMonitor
        im = InjuryMonitor()
        im.get_player_status("LeBron James")
        model_status["injury_monitor"] = "PASS"
    except Exception as e:
        model_status["injury_monitor"] = f"FAIL: {e}"

    any_pass = any(v == "PASS" for v in model_status.values())
    any_fail = any(v.startswith("FAIL") for v in model_status.values())
    layers["L6_Models"] = {
        **model_status,
        "status": "PASS" if not any_fail else ("WARN" if any_pass else "FAIL"),
    }

    # Identify weakest layer
    fail_layers = [k for k, v in layers.items() if isinstance(v, dict) and v.get("status") == "FAIL"]
    warn_layers = [k for k, v in layers.items() if isinstance(v, dict) and v.get("status") == "WARN"]
    weakest = fail_layers[0] if fail_layers else (warn_layers[0] if warn_layers else "none")

    return layers, weakest, api_ok


# ─────────────────────────────────────────────────────────────────────────────
# Build summary from layers + pipeline results
# ─────────────────────────────────────────────────────────────────────────────

def build_summary(results: dict, fps: float, layers: dict):
    l1 = layers.get("L1_CV_Tracking", {})
    l2 = layers.get("L2_Ball", {})
    l3 = layers.get("L3_Possessions", {})
    l4 = layers.get("L4_NBA_Enrich", {})

    total_frames = results.get("total_frames", 1) if results else 1
    jump_resets  = results.get("jump_resets", 0) if results else 0
    suspended    = results.get("suspended_frames", 0) if results else 0
    return {
        "mean_fps":             fps,
        "mean_track_stability": round(results.get("stability", 0.0), 3) if results else 0.0,
        "mean_id_switches":     results.get("id_switches", 0) if results else 0,
        "mean_confidence":      l1.get("mean_confidence", 0.0),
        "mean_oob_detections":  0,
        "tracking_rows":        l1.get("rows", 0),
        "ball_valid_pct":       l2.get("valid_ball_pct", 0.0),
        "possessions":          l3.get("rows", 0),
        "shots_detected":       l4.get("shots_detected", 0),
        "shots_enriched":       l4.get("shots_enriched", 0),
        # Ball tracking diagnostics
        "jump_resets":          jump_resets,
        "jump_resets_per_100f": round(jump_resets / max(1, total_frames) * 100, 1),
        "suspended_frames":     suspended,
        "suspended_pct":        round(suspended / max(1, total_frames), 3),
        # Live/dead split (populated when game_id is present)
        "ball_valid_live":      l2.get("ball_valid_live", None),
        "ball_valid_dead":      l2.get("ball_valid_dead", None),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Compare vs previous report
# ─────────────────────────────────────────────────────────────────────────────

def compare_vs_last(current_summary: dict):
    reports = sorted(glob.glob(os.path.join(BENCH_DIR, "report_*.json")))
    if len(reports) < 2:
        print("  (no prior report to compare against)")
        return

    with open(reports[-2]) as f:
        prev = json.load(f)
    ps = prev.get("summary", {})
    cs = current_summary

    metrics = [
        ("ball_valid_pct",       "Ball valid %",      True),
        ("jump_resets_per_100f", "Jump resets/100f",  False),
        ("suspended_pct",        "Suspended %",       True),
        ("mean_track_stability", "Stability",         True),
        ("mean_id_switches",     "ID switches",       False),
        ("mean_fps",             "FPS",               True),
        ("shots_detected",       "Shots det.",        True),
    ]

    print(f"\n{'Metric':<28} {'Prev':>8} {'Now':>8} {'Delta':>8}  Status")
    print("-" * 62)
    for key, label, higher_better in metrics:
        p = float(ps.get(key, 0) or 0)
        c = float(cs.get(key, 0) or 0)
        d = c - p
        if higher_better:
            st = "✅ up" if d > 0.005 else ("❌ down" if d < -0.005 else "= same")
        else:
            st = "✅ down" if d < -0.5 else ("❌ up" if d > 0.5 else "= same")
        print(f"  {label:<26} {p:>8.3f} {c:>8.3f} {d:>+8.3f}  {st}")


# ─────────────────────────────────────────────────────────────────────────────
# Identify and apply improvement
# ─────────────────────────────────────────────────────────────────────────────

def find_and_apply_fix(summary: dict, layers: dict):
    """
    Check metrics against priority thresholds and apply the highest-impact fix.
    Returns (fix_description, files_changed).
    """
    l1 = layers.get("L1_CV_Tracking", {})
    shots   = l1.get("shot_events", 0)
    dribbles = l1.get("dribble_events", 0)
    passes  = l1.get("pass_events", 0)
    tracking_rows = l1.get("rows", 0)
    stability = float(summary.get("mean_track_stability", 1.0))
    id_sw     = int(summary.get("mean_id_switches", 0))
    fps       = float(summary.get("mean_fps", 0))
    conf      = float(summary.get("mean_confidence", 0))

    # Priority 1: shot detection low (< 3 shots in 300 frames is suspicious)
    if shots < 3 and tracking_rows > 500:
        return _fix_shot_detection_threshold()

    # Priority 2: ID switches high
    if id_sw > 5:
        return _fix_id_switches()

    # Priority 3: stability low
    if stability < 0.75:
        return _fix_stability()

    # Priority 4: FPS too low
    if fps < 4.0:
        return _fix_fps()

    # Priority 5: confidence low
    if conf < 0.70:
        return _fix_confidence_threshold()

    # Priority 6: dribbles suspiciously low relative to passes
    if passes > 10 and dribbles < passes // 2:
        return _fix_dribble_sensitivity()

    return "no fix needed — all metrics within target range", []


def _fix_shot_detection_threshold():
    """Lower shot arc minimum positions to catch more shots."""
    import re
    path = os.path.join(PROJECT_DIR, "src", "tracking", "ball_detect_track.py")
    if not os.path.exists(path):
        return "SKIP: ball_detect_track.py not found", []

    with open(path) as f:
        src = f.read()

    # Look for polyfit minimum — raise catch rate by lowering from 8 to 6
    orig = "polyfit minimum positions raised 5→8"  # comment tag
    # Find the actual threshold line
    match = re.search(r'(_MIN_ARC_POSITIONS\s*=\s*)(\d+)', src)
    if match:
        cur = int(match.group(2))
        if cur > 5:
            new_val = max(5, cur - 1)
            new_src = src[:match.start(2)] + str(new_val) + src[match.end(2):]
            with open(path, "w") as f:
                f.write(new_src)
            desc = (f"Lowered _MIN_ARC_POSITIONS {cur}→{new_val} in ball_detect_track.py "
                    f"to improve shot detection recall (was missing short-arc shots)")
            return desc, ["src/tracking/ball_detect_track.py"]

    # Fallback: look for arc_positions or min_positions
    match2 = re.search(r'(min_arc_positions\s*=\s*)(\d+)', src)
    if match2:
        cur = int(match2.group(2))
        if cur > 5:
            new_val = max(5, cur - 1)
            new_src = src[:match2.start(2)] + str(new_val) + src[match2.end(2):]
            with open(path, "w") as f:
                f.write(new_src)
            desc = (f"Lowered min_arc_positions {cur}→{new_val} to improve shot recall")
            return desc, ["src/tracking/ball_detect_track.py"]

    return "no fix applied — shot count low but arc threshold not found to tune", []


def _fix_id_switches():
    """Tighten appearance threshold to reduce ID switches."""
    path = os.path.join(PROJECT_DIR, "src", "tracking", "tracker_config.py")
    if not os.path.exists(path):
        return "SKIP: tracker_config.py not found", []

    import re
    with open(path) as f:
        src = f.read()

    match = re.search(r'(APPEARANCE_THRESHOLD\s*=\s*)([0-9.]+)', src)
    if match:
        cur = float(match.group(2))
        if cur > 0.3:
            new_val = round(cur - 0.05, 2)
            new_src = src[:match.start(2)] + str(new_val) + src[match.end(2):]
            with open(path, "w") as f:
                f.write(new_src)
            return (f"Tightened APPEARANCE_THRESHOLD {cur}→{new_val} to reduce ID switches",
                    ["src/tracking/tracker_config.py"])

    return "no fix applied — ID switches high but APPEARANCE_THRESHOLD not found", []


def _fix_stability():
    """Increase Kalman process noise for more stable tracking."""
    path = os.path.join(PROJECT_DIR, "src", "tracking", "tracker_config.py")
    if not os.path.exists(path):
        return "SKIP: tracker_config.py not found", []

    import re
    with open(path) as f:
        src = f.read()

    match = re.search(r'(KALMAN_PROCESS_NOISE\s*=\s*)([0-9.e\-]+)', src)
    if match:
        cur = float(match.group(2))
        new_val = round(cur * 0.8, 6)
        new_src = src[:match.start(2)] + str(new_val) + src[match.end(2):]
        with open(path, "w") as f:
            f.write(new_src)
        return (f"Reduced KALMAN_PROCESS_NOISE {cur}→{new_val} to improve track stability",
                ["src/tracking/tracker_config.py"])

    return "no fix applied — stability low but KALMAN_PROCESS_NOISE not found", []


def _fix_fps():
    """Check if imgsz can be further reduced."""
    return ("FPS < 4 — check GPU utilization; imgsz=640 already set. "
            "Consider reducing YOLO confidence threshold to skip post-proc on low-conf frames."), []


def _fix_confidence_threshold():
    """Lower YOLO detection threshold."""
    path = os.path.join(PROJECT_DIR, "src", "tracking", "tracker_config.py")
    if not os.path.exists(path):
        return "SKIP: tracker_config.py not found", []

    import re
    with open(path) as f:
        src = f.read()

    match = re.search(r'(DETECTION_CONFIDENCE\s*=\s*)([0-9.]+)', src)
    if match:
        cur = float(match.group(2))
        if cur > 0.35:
            new_val = round(cur - 0.05, 2)
            new_src = src[:match.start(2)] + str(new_val) + src[match.end(2):]
            with open(path, "w") as f:
                f.write(new_src)
            return (f"Lowered DETECTION_CONFIDENCE {cur}→{new_val} to improve detection recall",
                    ["src/tracking/tracker_config.py"])

    return "no fix applied — confidence low but threshold not found", []


def _fix_dribble_sensitivity():
    """Lower dribble distance threshold in EventDetector."""
    path = os.path.join(PROJECT_DIR, "src", "tracking", "event_detector.py")
    if not os.path.exists(path):
        return "SKIP: event_detector.py not found", []

    import re
    with open(path) as f:
        src = f.read()

    # Look for DRIBBLE_DIST or dribble_threshold
    match = re.search(r'(_?DRIBBLE_(?:DIST|THRESHOLD|RADIUS)\s*=\s*)([0-9.]+)', src)
    if match:
        cur = float(match.group(2))
        if cur > 50:
            new_val = max(50, int(cur * 0.85))
            new_src = src[:match.start(2)] + str(new_val) + src[match.end(2):]
            with open(path, "w") as f:
                f.write(new_src)
            return (f"Lowered dribble distance threshold {cur}→{new_val}px to improve dribble recall",
                    ["src/tracking/event_detector.py"])

    return "no fix applied — dribble count low but threshold constant not found", []


# ─────────────────────────────────────────────────────────────────────────────
# Log to vault
# ─────────────────────────────────────────────────────────────────────────────

def log_to_vault(clip_label: str, summary: dict, fix_desc: str, ts: str):
    log_path = os.path.join(PROJECT_DIR, "vault", "Improvements", "Tracker Improvements Log.md")
    session_path = os.path.join(PROJECT_DIR, "vault", "Sessions",
                                f"Session-{datetime.now().strftime('%Y-%m-%d')}.md")

    stab = summary.get("mean_track_stability", 0)
    idsw = summary.get("mean_id_switches", 0)
    fps  = summary.get("mean_fps", 0)
    shots = summary.get("shots_detected", 0)
    dribs = 0  # pulled from layers upstream

    bench_tag = f"BENCH-{ts}"

    # Append to improvement log
    if os.path.exists(log_path):
        with open(log_path, "a") as f:
            f.write(f"\n### {bench_tag} — {clip_label} — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"Stab:{stab:.3f} IDsw:{idsw} FPS:{fps} Shots:{shots} | {fix_desc}\n")

    # Append to session note
    if os.path.exists(session_path):
        with open(session_path, "a") as f:
            f.write(f"\n| {bench_tag} | {clip_label} | FPS:{fps} Shots:{shots} Stab:{stab:.3f} | {fix_desc[:80]} |\n")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="NBA AI automated benchmark + improvement loop")
    ap.add_argument("--video",   default=None, help="Clip label (e.g. gsw_lakers_2025) or video path")
    ap.add_argument("--game-id", default=None, help="NBA game ID for enrichment (overrides auto)")
    ap.add_argument("--frames",  type=int, default=3600, help="Max frames to process (default: 3600)")
    args = ap.parse_args()

    os.makedirs(BENCH_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── Step 1: Pick clip ────────────────────────────────────────────────────
    label, video_path, game_id = pick_next_clip(args.video)
    if args.game_id:
        game_id = args.game_id

    print(f"\n{'='*60}")
    print(f"  NBA AI Benchmark Loop — {ts}")
    print(f"  Clip   : {label}")
    print(f"  Video  : {video_path}")
    print(f"  GameID : {game_id or 'none'}")
    print(f"  Frames : {args.frames}")
    print(f"{'='*60}\n")

    if not os.path.exists(video_path):
        print(f"[!] Video not found: {video_path}")
        sys.exit(1)

    # ── Step 2: Run pipeline ─────────────────────────────────────────────────
    print("Running pipeline...")
    results, fps, error = run_pipeline(video_path, game_id, args.frames)

    if error:
        print(f"[!] Pipeline error: {error}")
        report = {
            "timestamp": ts, "clip": label, "video": video_path, "game_id": game_id,
            "frames_requested": args.frames, "total_frames": 0, "fps_achieved": 0,
            "pipeline_error": error, "summary": {}, "layers": {}, "weakest_layer": "pipeline",
            "nba_api_reachable": False,
        }
        path = os.path.join(BENCH_DIR, f"report_{ts}.json")
        with open(path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Report saved: {path}")
        sys.exit(1)

    total_frames = results.get("total_frames", 0) if results else 0

    # ── Step 3: Evaluate layers ──────────────────────────────────────────────
    data_dir = os.path.join(PROJECT_DIR, "data")
    layers, weakest, api_ok = evaluate_layers(data_dir, results, game_id)
    summary = build_summary(results, fps, layers)

    # ── Step 4: Compare vs previous ──────────────────────────────────────────
    print("\n── Delta vs last benchmark ──────────────────────────────────")
    compare_vs_last(summary)

    # ── Step 5: Apply improvement ─────────────────────────────────────────────
    print("\n── Improvement check ────────────────────────────────────────")
    fix_desc, files_changed = find_and_apply_fix(summary, layers)
    print(f"  Fix: {fix_desc}")
    if files_changed:
        print(f"  Files: {', '.join(files_changed)}")

    # ── Step 6: Save report ───────────────────────────────────────────────────
    report = {
        "timestamp":        ts,
        "clip":             label,
        "video":            video_path,
        "game_id":          game_id,
        "frames_requested": args.frames,
        "total_frames":     total_frames,
        "fps_achieved":     fps,
        "pipeline_error":   None,
        "summary":          summary,
        "layers":           layers,
        "weakest_layer":    weakest,
        "nba_api_reachable": api_ok,
        "fix_applied":      fix_desc,
        "files_changed":    files_changed,
    }
    report_path = os.path.join(BENCH_DIR, f"report_{ts}.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    # ── Step 7: Log to vault ──────────────────────────────────────────────────
    log_to_vault(label, summary, fix_desc, ts)

    # ── Step 8: Output summary ───────────────────────────────────────────────
    l1 = layers.get("L1_CV_Tracking", {})
    l2 = layers.get("L2_Ball", {})

    print(f"\n{'='*60}")
    print(f"[Benchmark > Loop > {label}]")
    print(f"{'='*60}")
    print(f"Clip       : {label}")
    print(f"Frames     : {args.frames} (processed {total_frames} total)")
    print(f"FPS        : {fps}")
    print(f"\n{'Metric':<22} {'Value':>10}")
    print("-" * 35)
    print(f"  {'Dribbles detected':<22} {l1.get('dribble_events', 0):>10}")
    print(f"  {'Passes detected':<22} {l1.get('pass_events', 0):>10}")
    print(f"  {'Shots detected':<22} {l1.get('shot_events', 0):>10}")
    print(f"  {'Ball valid (2D)':<22} {l2.get('valid_ball_pct', 0)*100:>9.0f}%")
    live_pct = summary.get("ball_valid_live")
    dead_pct = summary.get("ball_valid_dead")
    if live_pct is not None:
        print(f"  {'Ball valid (live)':<22} {live_pct*100:>9.0f}%  ({layers.get('L2_Ball', {}).get('live_frames', 0)} frames)")
        print(f"  {'Ball valid (dead)':<22} {dead_pct*100:>9.0f}%  ({layers.get('L2_Ball', {}).get('dead_frames', 0)} frames)")
    print(f"  {'Jump resets (total)':<22} {summary.get('jump_resets', 0):>10}")
    print(f"  {'Jump resets/100f':<22} {summary.get('jump_resets_per_100f', 0):>9.1f}")
    print(f"  {'Suspended frames':<22} {summary.get('suspended_frames', 0):>10}  ({summary.get('suspended_pct', 0)*100:.0f}%)")
    print(f"  {'Track stability':<22} {summary['mean_track_stability']:>10.3f}")
    print(f"  {'Confidence':<22} {summary['mean_confidence']:>10.3f}")
    print(f"  {'FPS':<22} {fps:>10.1f}")
    print(f"\nNBA Stats API : {'reachable' if api_ok else 'unreachable'}")
    print(f"Shot events   : {l1.get('shot_events', 0)} detected")
    print(f"\nFix applied   : {fix_desc[:100]}")
    print(f"Weakest layer : {weakest}")
    print(f"Report saved  : {report_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
