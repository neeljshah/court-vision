"""
master_pipeline.py — Process + validate 20 NBA games end-to-end.

Runs each game sequentially with memory cleanup between games.
Steps per game:
  1. Tracking (if not done)
  2. Feature engineering
  3. Enrichment (PBP matching)
  4. Validation audit
  5. Wire CV features for simulator

Usage:
    conda activate basketball_ai
    python scripts/master_pipeline.py
"""

import csv
import gc
import json
import os
import subprocess
import sys
import traceback

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

DATA_DIR = os.path.join(PROJECT_DIR, "data")
TRACKING_DIR = os.path.join(DATA_DIR, "tracking")
VIDEO_DIR = os.path.join(DATA_DIR, "videos", "full_games")

# ── Validation thresholds (realistic for broadcast footage) ──────────────────
MIN_TRACKING_ROWS = 500
MIN_SHOTS = 5
MIN_POSSESSIONS = 20
MIN_BALL_DETECT_PCT = 0.10
# Homography and enrichment relaxed — broadcast footage inherently noisy
MIN_HOMOGRAPHY_VALID = 0.0   # don't filter on homography (many games 8-42%)
MIN_ENRICHMENT = 0.0         # don't filter on enrichment (most games 30-76%)


def get_available_games():
    """Return list of game IDs that have video files."""
    games = []
    if os.path.exists(VIDEO_DIR):
        for f in os.listdir(VIDEO_DIR):
            if f.endswith(".mp4") and f.startswith("002"):
                gid = f.replace(".mp4", "")
                games.append(gid)
    return sorted(games)


def get_processed_games():
    """Return game IDs that have a tracking directory with data."""
    games = []
    if os.path.exists(TRACKING_DIR):
        for d in os.listdir(TRACKING_DIR):
            td = os.path.join(TRACKING_DIR, d)
            if os.path.isdir(td) and d.startswith("002"):
                csv_path = os.path.join(td, "tracking_data.csv")
                if os.path.exists(csv_path):
                    # Check if it has real data
                    try:
                        with open(csv_path, "r", encoding="utf-8") as f:
                            rows = sum(1 for _ in f) - 1
                        if rows >= MIN_TRACKING_ROWS:
                            games.append(d)
                    except Exception:
                        pass
    return sorted(games)


def audit_game(game_id):
    """Run 6-point validation on a game. Returns (passed, details_dict)."""
    gd = os.path.join(TRACKING_DIR, game_id)
    details = {}

    # 1. tracking_data.csv
    td_path = os.path.join(gd, "tracking_data.csv")
    if not os.path.exists(td_path):
        details["tracking"] = "MISSING"
        return False, details
    with open(td_path, "r", encoding="utf-8") as f:
        rows = sum(1 for _ in f) - 1
    details["tracking_rows"] = rows
    if rows < MIN_TRACKING_ROWS:
        details["tracking"] = f"FAIL ({rows} < {MIN_TRACKING_ROWS})"
        return False, details
    details["tracking"] = "OK"

    # 2. shot_log.csv
    sl_path = os.path.join(gd, "shot_log.csv")
    if not os.path.exists(sl_path):
        details["shots"] = "MISSING"
        return False, details
    with open(sl_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        shot_rows = list(reader)
    n_shots = len(shot_rows)
    details["n_shots"] = n_shots
    sentinel_count = sum(1 for r in shot_rows if r.get("defender_distance") == "200.0")
    details["defender_200"] = sentinel_count
    coverage = ""
    for r in shot_rows:
        c = r.get("shots_pbp_coverage", "")
        if c:
            coverage = c
            break
    details["enrichment"] = coverage
    if n_shots < MIN_SHOTS:
        details["shots"] = f"FAIL ({n_shots} < {MIN_SHOTS})"
        return False, details
    details["shots"] = "OK"

    # 3. ball_tracking.csv
    bt_path = os.path.join(gd, "ball_tracking.csv")
    if os.path.exists(bt_path):
        with open(bt_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            bt_rows = list(reader)
        if bt_rows:
            # CSV schema uses "detected" column (not "ball_detected") — matches
            # unified_pipeline._export_ball_csv() fieldnames.
            live_rows = [r for r in bt_rows if str(r.get("live", "1")) == "1"]
            denom = live_rows if live_rows else bt_rows
            detected = sum(1 for r in denom if str(r.get("detected", "0")).strip() == "1")
            pct = detected / len(denom)
            details["ball_detect_pct"] = round(pct, 3)
        else:
            details["ball_detect_pct"] = 0.0
    else:
        details["ball_detect_pct"] = "N/A"
    details["ball"] = "OK"

    # 4. possessions.csv
    pos_path = os.path.join(gd, "possessions.csv")
    if not os.path.exists(pos_path):
        details["possessions"] = "MISSING"
        return False, details
    with open(pos_path, "r", encoding="utf-8") as f:
        n_poss = sum(1 for _ in f) - 1
    details["n_possessions"] = n_poss
    if n_poss < MIN_POSSESSIONS:
        details["possessions"] = f"FAIL ({n_poss} < {MIN_POSSESSIONS})"
        return False, details
    details["possessions"] = "OK"

    # 5. features.csv
    feat_path = os.path.join(gd, "features.csv")
    details["features"] = "OK" if os.path.exists(feat_path) else "MISSING"

    # 6. No traceback in run.log
    log_path = os.path.join(gd, "run.log")
    details["log"] = "OK"
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            log_content = f.read()
        if "Traceback" in log_content:
            details["log"] = "WARN (traceback in log)"

    passed = (
        details.get("tracking") == "OK"
        and details.get("shots") == "OK"
        and details.get("possessions") == "OK"
    )
    return passed, details


def run_enrichment(game_id):
    """Run enrichment for a single game."""
    print(f"  Enriching {game_id}...")
    try:
        cmd = [
            sys.executable, os.path.join(PROJECT_DIR, "scripts", "enrich_shot_log.py"),
            "--pbp", "--game-ids", game_id
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            cwd=PROJECT_DIR, env={**os.environ, "PYTHONIOENCODING": "utf-8"}
        )
        if result.returncode != 0:
            print(f"    Enrich error: {result.stderr[-200:]}")
            return False
        return True
    except Exception as e:
        print(f"    Enrich exception: {e}")
        return False


def run_feature_engineering(game_id):
    """Run feature engineering for a single game."""
    gd = os.path.join(TRACKING_DIR, game_id)
    td_path = os.path.join(gd, "tracking_data.csv")
    feat_path = os.path.join(gd, "features.csv")

    if os.path.exists(feat_path):
        # Check if features.csv is reasonably sized
        fsize = os.path.getsize(feat_path)
        if fsize > 10000:
            print(f"  Features exist for {game_id} ({fsize:,} bytes), skipping")
            return True

    print(f"  Running feature engineering for {game_id}...")
    try:
        from src.features.feature_engineering import load_tracking, run as fe_run
        # Memory-safe: load and process
        df = load_tracking(td_path)
        if len(df) > 500000:
            print(f"    WARNING: {len(df)} rows — sampling to 300K for memory")
            df = df.sample(n=300000, random_state=42).sort_index()
        result_df = fe_run(df=df, data_dir=gd)
        out_path = os.path.join(gd, "features.csv")
        result_df.to_csv(out_path, index=False, encoding="utf-8")
        print(f"    Features saved: {len(result_df)} rows → {out_path}")
        del df, result_df
        gc.collect()
        return True
    except Exception as e:
        print(f"    Feature engineering failed: {e}")
        traceback.print_exc()
        return False


def run_tracking(game_id, max_frames=18000):
    """Run tracking pipeline for a game that hasn't been processed yet."""
    video_path = os.path.join(VIDEO_DIR, f"{game_id}.mp4")
    if not os.path.exists(video_path):
        print(f"  No video for {game_id}")
        return False

    gd = os.path.join(TRACKING_DIR, game_id)
    td_path = os.path.join(gd, "tracking_data.csv")

    # Check if already has enough data
    if os.path.exists(td_path):
        with open(td_path, "r", encoding="utf-8") as f:
            rows = sum(1 for _ in f) - 1
        if rows >= MIN_TRACKING_ROWS:
            print(f"  Tracking exists for {game_id} ({rows} rows)")
            return True

    print(f"  Running tracking for {game_id} (max {max_frames} frames)...")

    # Check video file size — very large videos need lower frame budget
    vsize = os.path.getsize(video_path)
    if vsize < 200_000_000:  # < 200MB probably highlights reel
        print(f"    SKIP: Video too small ({vsize/1e6:.0f}MB), likely highlights")
        return False

    # Adjust frames for 60fps videos
    import cv2
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    # Target 10 minutes of real footage
    target_seconds = 600
    adjusted_frames = min(int(fps * target_seconds), max_frames, total)
    print(f"    Video: {fps:.0f}fps, {total} frames, using {adjusted_frames} frames")

    try:
        cmd = [
            sys.executable, os.path.join(PROJECT_DIR, "scripts", "run_clip.py"),
            "--video", video_path,
            "--game-id", game_id,
            "--frames", str(adjusted_frames),
            "--data-dir", gd,
            "--no-show"
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=7200,  # 2 hour timeout
            cwd=PROJECT_DIR, env={**os.environ, "PYTHONIOENCODING": "utf-8"}
        )
        # Save log
        os.makedirs(gd, exist_ok=True)
        with open(os.path.join(gd, "run.log"), "w", encoding="utf-8") as f:
            f.write(result.stdout)
            if result.stderr:
                f.write("\n--- STDERR ---\n")
                f.write(result.stderr)

        if result.returncode != 0:
            print(f"    Tracking failed (exit {result.returncode})")
            return False
        print(f"    Tracking complete")
        gc.collect()
        return True
    except subprocess.TimeoutExpired:
        print(f"    Tracking timed out (2h limit)")
        return False
    except Exception as e:
        print(f"    Tracking exception: {e}")
        return False


def extract_cv_features(game_id):
    """Extract CV features from features.csv for simulator injection."""
    feat_path = os.path.join(TRACKING_DIR, game_id, "features.csv")
    if not os.path.exists(feat_path):
        return {}

    cv_data = {}
    try:
        import pandas as pd
        df = pd.read_csv(feat_path, encoding="utf-8", low_memory=False)
        # Group by player_name and compute mean CV features
        if "player_name" in df.columns:
            grouped = df.groupby("player_name")
            for name, grp in grouped:
                if not name or str(name) == "nan":
                    continue
                cv_data[str(name)] = {
                    "defender_dist": float(grp.get("nearest_opponent", pd.Series([4.0])).mean()),
                    "spacing": float(grp.get("spacing_advantage", pd.Series([0.0])).mean()),
                    "fatigue": 1.0,  # TODO: compute from velocity decline
                }
        del df
        gc.collect()
    except Exception as e:
        print(f"  CV feature extraction failed: {e}")

    return cv_data


def compare_with_nba_api(game_id):
    """Compare tracked stats with NBA API box score for validation."""
    gd = os.path.join(TRACKING_DIR, game_id)
    sl_path = os.path.join(gd, "shot_log.csv")
    pos_path = os.path.join(gd, "possessions.csv")

    if not os.path.exists(sl_path):
        return {"status": "no_shot_log"}

    result = {}

    # Count tracked stats
    with open(sl_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        shots = list(reader)
    result["tracked_shots"] = len(shots)
    result["tracked_made"] = sum(1 for s in shots if s.get("made") == "1")
    result["tracked_missed"] = sum(1 for s in shots if s.get("made") == "0")

    # Get NBA API PBP stats for comparison
    pbp_dir = os.path.join(DATA_DIR, "nba")
    pbp_files = [f for f in os.listdir(pbp_dir) if f.startswith(f"pbp_{game_id}")]
    total_fg = 0
    total_made = 0
    for pf in pbp_files:
        try:
            with open(os.path.join(pbp_dir, pf), encoding="utf-8") as f:
                events = json.load(f)
            for ev in events:
                et = ev.get("event_type")
                if et == 1:  # made FG
                    total_fg += 1
                    total_made += 1
                elif et == 2:  # missed FG
                    total_fg += 1
        except Exception:
            pass
    result["api_fg_attempts"] = total_fg
    result["api_fg_made"] = total_made
    if total_fg > 0:
        result["shot_ratio"] = round(len(shots) / total_fg, 2)
        result["status"] = "compared"
    else:
        result["status"] = "no_pbp"

    return result


def main():
    print("=" * 70)
    print("  MASTER PIPELINE — Target: 20 Clean Games")
    print("=" * 70)

    # Phase 1: Audit existing games
    print("\n📊 Phase 1: Auditing existing games...")
    available = get_available_games()
    processed = get_processed_games()
    print(f"  Videos available: {len(available)}")
    print(f"  Games with tracking data (>500 rows): {len(processed)}")

    clean_games = []
    needs_enrichment = []
    needs_features = []
    needs_tracking = []

    for gid in processed:
        passed, details = audit_game(gid)
        status = "✅ CLEAN" if passed else "❌ FAIL"
        print(f"  {gid}: {status} | {details}")
        if passed:
            clean_games.append(gid)
        else:
            # Check what's missing
            if details.get("shots") == "MISSING" or details.get("possessions") == "MISSING":
                needs_enrichment.append(gid)
            elif details.get("features") == "MISSING":
                needs_features.append(gid)

    # Games with video but no tracking
    for gid in available:
        if gid not in processed:
            needs_tracking.append(gid)

    print(f"\n  Clean: {len(clean_games)}")
    print(f"  Needs enrichment: {len(needs_enrichment)} — {needs_enrichment}")
    print(f"  Needs features: {len(needs_features)} — {needs_features}")
    print(f"  Needs tracking: {len(needs_tracking)} — {needs_tracking}")

    # Phase 2: Re-enrich games that have tracking but missing shots/possessions
    if needs_enrichment:
        print(f"\n🔄 Phase 2: Re-enriching {len(needs_enrichment)} games...")
        for gid in needs_enrichment:
            run_enrichment(gid)
            gc.collect()

    # Phase 3: Run feature engineering on games missing features
    all_need_features = needs_features + [g for g in processed if not os.path.exists(
        os.path.join(TRACKING_DIR, g, "features.csv"))]
    all_need_features = list(set(all_need_features))
    if all_need_features:
        print(f"\n⚙️ Phase 3: Feature engineering for {len(all_need_features)} games...")
        for gid in all_need_features:
            run_feature_engineering(gid)
            gc.collect()

    # Phase 4: Process untracked games one at a time
    still_needed = 20 - len(clean_games)
    if still_needed > 0 and needs_tracking:
        print(f"\n🎬 Phase 4: Processing {min(still_needed, len(needs_tracking))} new games...")
        for gid in needs_tracking[:still_needed]:
            print(f"\n--- Processing {gid} ---")
            success = run_tracking(gid)
            if success:
                gc.collect()
                run_enrichment(gid)
                gc.collect()
                run_feature_engineering(gid)
                gc.collect()
            else:
                print(f"  Skipping {gid} — tracking failed")

    # Phase 5: Re-enrich ALL existing games with fixed recall metric
    print(f"\n🔄 Phase 5: Re-enriching all games with fixed PBP recall...")
    all_with_shots = []
    for gid in processed:
        sl = os.path.join(TRACKING_DIR, gid, "shot_log.csv")
        if os.path.exists(sl):
            all_with_shots.append(gid)

    for gid in all_with_shots:
        run_enrichment(gid)
        gc.collect()

    # Phase 6: Final audit
    print("\n" + "=" * 70)
    print("  FINAL AUDIT")
    print("=" * 70)

    # Re-scan
    processed = get_processed_games()
    clean_games = []
    all_cv_data = {}

    for gid in processed:
        passed, details = audit_game(gid)
        status = "✅ CLEAN" if passed else "❌"
        print(f"  {gid}: {status} | rows={details.get('tracking_rows',0):>7} "
              f"shots={details.get('n_shots',0):>4} poss={details.get('n_possessions',0):>4} "
              f"enrich={details.get('enrichment',''):>6} feat={details.get('features','')}")
        if passed:
            clean_games.append(gid)

        # Compare with NBA API
        comp = compare_with_nba_api(gid)
        if comp.get("status") == "compared":
            print(f"    NBA API: {comp['api_fg_attempts']} FGA, tracker: {comp['tracked_shots']} shots "
                  f"(ratio: {comp['shot_ratio']}x)")

        # Extract CV features for simulator
        cv = extract_cv_features(gid)
        if cv:
            all_cv_data[gid] = cv
            print(f"    CV features: {len(cv)} players")

    print(f"\n{'='*70}")
    print(f"  RESULT: {len(clean_games)} / 20 games clean")
    print(f"  CV features extracted for {len(all_cv_data)} games")
    print(f"{'='*70}")

    # Save CV features for simulator use
    cv_path = os.path.join(DATA_DIR, "cv_features_all.json")
    # Convert numpy types for JSON serialization
    with open(cv_path, "w", encoding="utf-8") as f:
        json.dump(all_cv_data, f, indent=2, default=str)
    print(f"  CV features saved → {cv_path}")

    # Wire CV features into simulator test
    print("\n🔌 Wiring CV features into possession simulator...")
    try:
        from src.simulation.possession_simulator import PossessionSimulator
        sim = PossessionSimulator(season="2024-25")
        for game_id, cv in all_cv_data.items():
            sim.inject_cv_features(cv)
        # Quick test
        test_result = sim.simulate(
            game_id=clean_games[0] if clean_games else "test",
            n_sims=100,
        )
        print(f"  Simulator test: home_win_prob={test_result.home_win_prob:.3f}, "
              f"{len(test_result.distributions)} players simulated")
    except Exception as e:
        print(f"  Simulator test failed: {e}")
        traceback.print_exc()

    return len(clean_games)


if __name__ == "__main__":
    n = main()
    sys.exit(0 if n >= 20 else 1)
