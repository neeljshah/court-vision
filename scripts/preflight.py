"""
preflight.py — Pre-flight validation for NBA AI game processing.

Checks all dependencies, model files, resources, and environment variables
before running a full game through the pipeline.

Usage
-----
    conda activate basketball_ai
    python scripts/preflight.py
"""

from __future__ import annotations

import datetime
import os
import shutil
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_PASS = "[PASS]"
_FAIL = "[FAIL]"
_WARN = "[WARN]"

_MODEL_CUTOFF = datetime.date(2026, 3, 1)

checks_passed = 0
checks_total  = 0
checks_failed: list = []


def _check(label: str, ok: bool, note: str = "") -> bool:
    """Record and print one check result."""
    global checks_passed, checks_total
    checks_total += 1
    if ok:
        checks_passed += 1
        print(f"  {_PASS} {label}" + (f"  ({note})" if note else ""))
    else:
        checks_failed.append(label)
        print(f"  {_FAIL} {label}" + (f"  -- {note}" if note else ""))
    return ok


def _file_fresh(path: str) -> bool:
    """Return True if file exists and was modified after _MODEL_CUTOFF."""
    if not os.path.exists(path):
        return False
    mtime = datetime.date.fromtimestamp(os.path.getmtime(path))
    return mtime >= _MODEL_CUTOFF


# ── Section 1: Python environment ─────────────────────────────────────────────

def check_python_env() -> None:
    print("\n[Python environment]")
    for pkg, import_name in [
        ("ultralytics", "ultralytics"),
        ("opencv-python", "cv2"),
        ("torch", "torch"),
        ("paddleocr", "paddleocr"),
        ("decord", "decord"),
    ]:
        try:
            __import__(import_name)
            _check(pkg, True)
        except ImportError as e:
            _check(pkg, False, f"ImportError: {e}")


# ── Section 2: YOLO / pose / OSNet / ball models ──────────────────────────────

def check_model_weights() -> None:
    print("\n[CV model weights]")
    res = os.path.join(PROJECT_DIR, "resources")

    # YOLO person detection: prefer TensorRT engine, fall back to .pt
    yolo_engine = os.path.join(res, "yolov8n.engine")
    yolo_pt     = os.path.join(res, "yolov8n.pt")
    if os.path.exists(yolo_engine):
        _check("YOLO (person) model", True, "TensorRT engine")
    elif os.path.exists(yolo_pt):
        _check("YOLO (person) model", True, ".pt fallback (slower — export to TRT for speed)")
    else:
        _check("YOLO (person) model", False,
               "MISSING: run scripts/export_tensorrt.py on a machine with TensorRT")

    # Pose model
    pose_engine = os.path.join(res, "yolov8n-pose.engine")
    pose_pt     = os.path.join(res, "yolov8n-pose.pt")
    if os.path.exists(pose_engine):
        _check("Pose model", True, "TensorRT engine")
    elif os.path.exists(pose_pt):
        _check("Pose model", True, ".pt fallback")
    else:
        _check("Pose model", False,
               "MISSING: run scripts/export_tensorrt.py")

    # OSNet re-ID
    osnet_engine = os.path.join(res, "osnet_x025.engine")
    if os.path.exists(osnet_engine):
        _check("OSNet TRT (re-ID)", True)
    else:
        _check("OSNet TRT (re-ID)", False,
               "MISSING: run scripts/export_tensorrt.py")

    # Ball YOLO: TRT engine or custom weights (optional — Hough circles are the fallback)
    ball_engine = os.path.join(res, "yolov8n_ball.engine")
    ball_pt     = os.path.join(PROJECT_DIR, "models", "weights", "yolov8n_ball.pt")
    if os.path.exists(ball_engine):
        _check("Ball YOLO model", True, "TensorRT engine")
    elif os.path.exists(ball_pt):
        _check("Ball YOLO model", True, ".pt fallback")
    else:
        # Not a blocker — tracker falls back to Hough circles
        global checks_total, checks_passed
        checks_total += 1
        checks_passed += 1  # count as pass; it's a future improvement, not a blocker
        print(f"  {_WARN} Ball YOLO model  "
              "(not trained yet — Hough circles fallback active; "
              "train when ready: label_ball_yolo.py + train_ball_yolo.py)")

    # Homography matrix
    homo = os.path.join(res, "Rectify1.npy")
    _check("Homography (Rectify1.npy)", os.path.exists(homo),
           "" if os.path.exists(homo) else "MISSING: run the pipeline once on a reference clip")


# ── Section 3: ML models ──────────────────────────────────────────────────────

def check_ml_models() -> None:
    print("\n[ML model files]")
    models_dir = os.path.join(PROJECT_DIR, "data", "models")
    required = [
        ("win_probability.pkl",  "Win probability"),
        ("xfg_v1.pkl",           "xFG v1"),
        ("props_pts.json",       "Props — pts"),
        ("matchup_model.json",   "Matchup model"),
    ]
    for fname, label in required:
        path = os.path.join(models_dir, fname)
        fresh = _file_fresh(path)
        if not os.path.exists(path):
            _check(label, False, f"MISSING: {fname}")
        elif not fresh:
            mtime = datetime.date.fromtimestamp(os.path.getmtime(path))
            _check(label, False,
                   f"STALE (last modified {mtime}) — run python scripts/retrain_all.py")
        else:
            mtime = datetime.date.fromtimestamp(os.path.getmtime(path))
            _check(label, True, f"last trained {mtime}")


# ── Section 4: Environment variables ──────────────────────────────────────────

def check_env_vars() -> None:
    global checks_total, checks_passed
    print("\n[Environment variables]")
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url:
        _check("DATABASE_URL", True, db_url[:30] + "…" if len(db_url) > 30 else db_url)
    else:
        # Not a blocker for single-game runs — wire up when ready for full videos
        checks_total += 1
        checks_passed += 1
        print(f"  {_WARN} DATABASE_URL  "
              "(not set — tracking rows saved to CSV only; "
              "set before running full-game batch processing)")

    redis_url = os.environ.get("REDIS_URL", "")
    if redis_url:
        _check("REDIS_URL", True, redis_url[:30] + "…" if len(redis_url) > 30 else redis_url)
    else:
        # Not a blocker — only needed for Celery batch jobs, not single-game runs
        checks_total += 1
        checks_passed += 1
        print(f"  {_WARN} REDIS_URL  "
              "(not set — Celery batch jobs unavailable; "
              "set before running scripts/batch_process.py)")


# ── Section 5: Database migrations ────────────────────────────────────────────

def check_database() -> None:
    print("\n[Database]")
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print(f"  {_WARN} DATABASE_URL not set — migration check skipped (deferred until full-video runs)")
        return
    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur  = conn.cursor()
        cur.execute("SELECT 1 FROM tracking_frames LIMIT 1")
        cur.close()
        conn.close()
        _check("tracking_frames table", True)
    except Exception as e:
        err = str(e)
        if "does not exist" in err or "relation" in err.lower():
            _check("tracking_frames table", False,
                   "Run: psql $DATABASE_URL < database/migrations/001_tracking_nullable_game_id.sql")
        else:
            _check("tracking_frames table", False, f"DB connection error: {err[:80]}")


# ── Section 6: Phase A data files ─────────────────────────────────────────────

def check_phase_a_data() -> None:
    print("\n[Phase A data]")
    nba_dir = os.path.join(PROJECT_DIR, "data", "nba")
    checks = [
        (os.path.join(nba_dir, "synergy_offensive_all_2024-25.json"),
         "Synergy offensive 2024-25"),
        (os.path.join(nba_dir, "shot_dashboard_all_2024-25.json"),
         "Shot dashboard all 2024-25"),
        (os.path.join(nba_dir, "player_tracking_2024-25.json"),
         "Player tracking 2024-25"),
        (os.path.join(nba_dir, "hustle_stats_2024-25.json"),
         "Hustle stats 2024-25"),
        (os.path.join(nba_dir, "matchups_2024-25.json"),
         "Matchup data 2024-25"),
    ]
    for path, label in checks:
        exists = os.path.exists(path)
        note = ""
        if exists:
            size_kb = os.path.getsize(path) // 1024
            note = f"{size_kb} KB"
        else:
            note = "MISSING: run scripts/pull_missing_data.py"
        _check(label, exists, note)


# ── Section 7: Hardware resources ─────────────────────────────────────────────

def check_hardware() -> None:
    global checks_total, checks_passed
    print("\n[Hardware resources]")

    # VRAM: warn if GPU has < 23 GB total memory
    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            vram_gb = props.total_memory / (1024 ** 3)
            ok = vram_gb >= 23.0
            if ok:
                _check("VRAM >= 23GB", True, f"{vram_gb:.1f}GB on {props.name}")
            else:
                checks_total += 1
                checks_passed += 1  # warn only, not blocker
                print(f"  {_WARN} VRAM  {vram_gb:.1f}GB < 23GB on {props.name} — "
                      "parallel-4 may OOM; consider --parallel 2")
        else:
            checks_total += 1
            checks_passed += 1
            print(f"  {_WARN} CUDA not available — skipping VRAM check")
    except ImportError:
        checks_total += 1
        checks_passed += 1
        print(f"  {_WARN} torch not installed — skipping VRAM check")

    # Disk: fail if /workspace has < 100 GB free
    _disk_path = "/workspace" if os.path.exists("/workspace") else PROJECT_DIR
    try:
        free_gb = shutil.disk_usage(_disk_path).free / (1024 ** 3)
        _check(f"Disk free >= 100GB ({_disk_path})", free_gb >= 100.0,
               f"{free_gb:.1f}GB free" if free_gb < 100.0
               else f"{free_gb:.1f}GB free")
    except Exception as e:
        _check(f"Disk free >= 100GB ({_disk_path})", False, str(e))


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print(" NBA AI — Pre-flight Validation")
    print(f" Project: {PROJECT_DIR}")
    print("=" * 60)

    check_python_env()
    check_model_weights()
    check_ml_models()
    check_env_vars()
    check_database()
    check_phase_a_data()
    check_hardware()

    print()
    print("=" * 60)
    n_failed = checks_total - checks_passed
    if n_failed == 0:
        print(f" {checks_passed}/{checks_total} checks passed. Ready to run games.")
    else:
        print(f" {checks_passed}/{checks_total} checks passed. "
              f"Fix {n_failed} issue{'s' if n_failed != 1 else ''} before running games.")
        print()
        print(" Issues to fix:")
        for label in checks_failed:
            print(f"   - {label}")
    print("=" * 60)


if __name__ == "__main__":
    main()
