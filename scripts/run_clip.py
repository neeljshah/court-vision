"""
run_clip.py — Full data-extraction pipeline for a 5-minute basketball clip.

Runs every stage end-to-end and prints a summary of all output files.

Usage
-----
    conda activate basketball_ai

    # Basic — just tracking data
    python run_clip.py --video path/to/clip.mp4

    # With NBA enrichment (adds made/missed labels + possession outcomes)
    python run_clip.py --video clip.mp4 --game-id 0022301234 --period 2 --start 420

    # Headless (no preview window, faster)
    python run_clip.py --video clip.mp4 --no-show

    # Limit frames (useful for quick tests)
    python run_clip.py --video clip.mp4 --frames 500

Outputs (written to data/)
--------------------------
    tracking_data.csv       Per-frame rows for every tracked player (36 cols)
    ball_tracking.csv       Per-frame ball position + detection flag
    possessions.csv         One row per possession with aggregate stats
    shot_log.csv            One row per detected shot attempt
    player_clip_stats.csv   Per-player aggregate stats across the clip
    features.csv            ML-ready features (rolling windows, momentum, etc.)
    stats.json              Shot attempts + made baskets (YOLO mode only)

    If --game-id is provided, also writes:
    shot_log_enriched.csv       shot_log with made/missed from NBA API
    possessions_enriched.csv    possessions with result + score_diff from NBA API
"""

import argparse
import json
import os
import sys
import time
import uuid

import cv2

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Diagnostic: SIGUSR1 dumps all-thread Python stacks to stderr, even mid-C-call.
# Used to locate runaway native allocations (py-spy/gdb blocked in container).
if os.environ.get("FAULTHANDLER", "") == "1":
    import faulthandler as _fh
    import signal as _sig
    _fh.enable()
    try:
        _fh.register(_sig.SIGUSR1, all_threads=True, chain=False)
        print("[FAULTHANDLER] SIGUSR1 stack-dump armed", flush=True)
    except Exception:
        pass

from src.pipeline.unified_pipeline import UnifiedPipeline
from src.features.feature_engineering import run as run_features

try:
    from src.tracking.player_identity import (
        JerseyVotingBuffer,
        run_ocr_annotation_pass,
        SAMPLE_EVERY_N,
    )
    from src.data.player_identity import persist_identity_map, update_tracking_frames
    _HAS_IDENTITY = True
except ImportError:
    _HAS_IDENTITY = False


MIN_CLIP_SECONDS = 60  # clips under this are too short for meaningful analytics
_PREFLIGHT_FRAMES = 10   # number of evenly-spaced frames to sample
_PREFLIGHT_MIN_PERSONS = 3  # median person count below this → reject video


def _ensure_decodable_video(video_path: str) -> str:
    """Transcode AV1 videos to H.264 so opencv-python's bundled ffmpeg can read them.

    opencv-python ships its own libavcodec built without libdav1d → cap.read()
    returns False on every AV1 frame. System ffmpeg (apt install ffmpeg) has
    libdav1d + av1_cuvid + h264_nvenc, so we transcode once to a cache dir and
    return the cached path. Subsequent runs hit the cache.
    """
    import subprocess
    try:
        codec = subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1",
             video_path],
            text=True,
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        # ffprobe unavailable — fall back to cv2 read test
        cap = cv2.VideoCapture(video_path)
        ok, _ = cap.read()
        cap.release()
        if ok:
            return video_path
        # Can't read first frame — likely AV1 without hw decoder.
        # Try PyAV probe as last resort.
        try:
            import av
            c = av.open(video_path)
            codec = c.streams.video[0].codec_context.name
            c.close()
            if codec != "av1":
                return video_path
            # Fall through to transcode
        except Exception:
            print(f"[transcode] Cannot read video and cannot probe codec — skipping")
            return video_path
    if codec != "av1":
        return video_path

    cache_dir = os.path.join(PROJECT_DIR, "data", "videos", "full_games_h264")
    os.makedirs(cache_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(video_path))[0]
    out_path = os.path.join(cache_dir, f"{stem}.mp4")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1_000_000:
        print(f"[transcode] using cached H.264: {out_path}")
        return out_path

    print(f"[transcode] {codec} → h264 (CPU libdav1d/libx264): {video_path}")
    tmp_path = out_path + ".tmp.mp4"
    # RunPod containers typically do not expose NVDEC/NVENC (av1_cuvid + h264_nvenc
    # fail with "unsupported device") even though CUDA compute works. Use pure CPU.
    # ~2.5× realtime on this pod (~8–12 min per 20-min broadcast), multi-threaded.
    cpu_cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-c:v", "libdav1d",
        "-i", video_path,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-an", "-movflags", "+faststart",
        tmp_path,
    ]
    rc = subprocess.call(cpu_cmd)
    if rc != 0 or not os.path.exists(tmp_path):
        print(f"[transcode] FAILED rc={rc} — returning original path, pipeline will fail cleanly")
        return video_path
    os.rename(tmp_path, out_path)
    print(f"[transcode] done → {out_path} ({os.path.getsize(out_path)/1e6:.0f} MB)")
    return out_path


def _preflight_check(video_path: str, yolo_weight=None):
    """Sample 10 frames and run YOLO person detection.

    Returns (ok, median_person_count).
    ok=False means the video appears to be non-broadcast (app UI, no court footage).
    Exits with code 4 + prints a clear error when preflight fails.
    """
    try:
        from ultralytics import YOLO as _YOLO
        _model_path = yolo_weight or os.path.join(PROJECT_DIR, "yolov8n.pt")
        if not os.path.exists(_model_path):
            # Can't run preflight without model — skip and proceed
            print("[preflight] YOLO model not found — skipping preflight check")
            return True, 0.0
        _model = _YOLO(_model_path)
    except ImportError:
        print("[preflight] ultralytics not available — skipping preflight check")
        return True, 0.0

    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        cap.release()
        return True, 0.0  # can't read — let Stage 1 handle it

    # Quick decodability check: if first frame can't be read, video codec
    # is unsupported (e.g. AV1 without hw decoder). Fail fast.
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    _test_ok, _ = cap.read()
    if not _test_ok:
        cap.release()
        print("[preflight] FAIL — cannot decode first frame (likely AV1 without hw decoder)")
        return False, 0.0

    sample_indices = [int(total_frames * i / (_PREFLIGHT_FRAMES - 1))
                      for i in range(_PREFLIGHT_FRAMES)]
    counts = []
    for fi in sample_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
        ret, frame = cap.read()
        if not ret:
            continue
        results = _model(frame, classes=[0], verbose=False)  # class 0 = person
        n_persons = len(results[0].boxes) if results and results[0].boxes is not None else 0
        counts.append(n_persons)
    cap.release()

    if not counts:
        return False, 0.0

    import statistics
    median = statistics.median(counts)
    return median >= _PREFLIGHT_MIN_PERSONS, float(median)


def _fmt_rows(path: str) -> str:
    """Return '(N rows)' or '(not found)' for a CSV path."""
    if not os.path.exists(path):
        return "(not found)"
    with open(path) as f:
        n = sum(1 for _ in f) - 1  # subtract header
    return f"({max(0, n)} rows)"


def _fmt_size(path: str) -> str:
    if not os.path.exists(path):
        return "(not found)"
    kb = os.path.getsize(path) / 1024
    return f"({kb:.1f} KB)"


def main():
    ap = argparse.ArgumentParser(
        description="NBA AI — full data extraction pipeline for a single clip"
    )
    ap.add_argument("--video",    required=True,
                    help="Path to input video (.mp4)")
    ap.add_argument("--yolo",     default=None,
                    help="Path to YOLO-NAS weights (.pth). Optional.")
    ap.add_argument("--frames",      type=int, default=None,
                    help="Max frames to process (default: full video)")
    ap.add_argument("--start-frame", type=int, default=0,
                    help="Frame index to seek to before processing (default: 0)")
    ap.add_argument("--no-show",  action="store_true",
                    help="Disable live preview window")
    # NBA enrichment (optional)
    ap.add_argument("--game-id",  default=None,
                    help="NBA Stats game ID (e.g. 0022301234) for play-by-play enrichment")
    ap.add_argument("--period",   type=int, default=None,
                    help="Quarter the clip covers (1-4). Used with --game-id. "
                         "Defaults to auto-detect via ball_tracking.csv duration.")
    ap.add_argument("--periods",  default=None,
                    help="Comma-separated list of quarters to enrich (e.g. 1,2,3,4 for full game). "
                         "Overrides --period.")
    ap.add_argument("--start",    type=float, default=0.0,
                    help="Seconds elapsed in the period when the clip starts. "
                         "e.g. clip starts at 8:30 left in Q1 → --start 210")
    ap.add_argument("--data-dir", default=None,
                    help="Output directory for CSV files (default: data/). "
                         "run_phase_g.py passes data/tracking/<game_id>/ here.")
    ap.add_argument("--skip-tracking", action="store_true",
                    help="Skip Stage 1 (tracking) and jump straight to feature engineering "
                         "and enrichment.  Requires tracking_data.csv to already exist in "
                         "--data-dir.  Use for games where tracking crashed after Stage 1.")
    ap.add_argument("--skip-features", action="store_true",
                    help="Skip feature engineering (fast mode for jersey OCR only)")
    args = ap.parse_args()

    if not os.path.exists(args.video):
        print(f"Error: video not found at {args.video}")
        sys.exit(1)

    # AV1 → H.264 shim (transcodes once, caches under data/videos/full_games_h264/)
    args.video = _ensure_decodable_video(args.video)

    cap_check = cv2.VideoCapture(args.video)
    total_frames_check = int(cap_check.get(cv2.CAP_PROP_FRAME_COUNT))
    fps_check = cap_check.get(cv2.CAP_PROP_FPS) or 30.0
    cap_check.release()
    clip_duration_sec = total_frames_check / fps_check
    if clip_duration_sec < MIN_CLIP_SECONDS:
        print(
            f"\nWARNING: Clip is only {clip_duration_sec:.1f}s "
            f"(minimum recommended: {MIN_CLIP_SECONDS}s).\n"
            "Short clips produce unreliable shot/possession analytics.\n"
            "Pass --frames to process a subset, or use a longer broadcast clip.\n"
        )
        # Exit with non-zero so automated pipelines can detect short clips.
        sys.exit(2)

    # ── Preflight: verify broadcast content ───────────────────────────────────
    # Skip preflight in Phase G batch mode — videos are already quarantined by
    # bootstrap_pod.sh, and loading a separate YOLO model per worker wastes
    # ~500 MB GPU each during the simultaneous-init window.
    _skip_preflight = os.environ.get("COURTV_NO_OCR", "0") == "1"
    if _skip_preflight:
        print("[preflight] Skipped (batch mode — COURTV_NO_OCR=1)")
        _preflight_ok, _preflight_median = True, 10.0
    else:
        print("[preflight] Sampling 10 frames for person detection...")
        _preflight_ok, _preflight_median = _preflight_check(args.video, args.yolo)
    if not _preflight_ok:
        print(
            f"\n[PREFLIGHT FAIL] Median person count = {_preflight_median:.0f} "
            f"(threshold: {_PREFLIGHT_MIN_PERSONS})\n"
            "Video appears to be non-broadcast footage (app UI, overlays, no court).\n"
            "This is a YOLO detection check — if the video is a real broadcast,\n"
            "re-download from a different source and retry.\n"
        )
        sys.exit(4)
    print(f"[preflight] OK — median persons/frame = {_preflight_median:.1f}")

    data_dir = args.data_dir if args.data_dir else os.path.join(PROJECT_DIR, "data")
    os.makedirs(data_dir, exist_ok=True)
    t0 = time.time()

    # ── Stage 1: Tracking ─────────────────────────────────────────────────────
    if args.skip_tracking:
        print("\n" + "=" * 60)
        print(" Stage 1 / 3 — Tracking SKIPPED (--skip-tracking)")
        print("=" * 60)
        _td = os.path.join(data_dir, "tracking_data.csv")
        if not os.path.exists(_td):
            print(f"ERROR: --skip-tracking requires tracking_data.csv at {_td}")
            sys.exit(1)
        # Infer fps from the video for enrichment timestamp math
        _cap = cv2.VideoCapture(args.video)
        fps = _cap.get(cv2.CAP_PROP_FPS) or 30.0
        _cap.release()
        print(f" Using existing tracking_data.csv  fps={fps:.1f}")
    else:
        print("\n" + "=" * 60)
        print(" Stage 1 / 3 — Tracking")
        print("=" * 60)
        print(f" Video : {args.video}")

        pipeline = UnifiedPipeline(
            video_path=args.video,
            yolo_weight_path=args.yolo,
            max_frames=args.frames,
            start_frame=args.start_frame,
            show=not args.no_show,
            data_dir=data_dir,
            game_id=args.game_id,
        )
        results = pipeline.run()

        fps = getattr(getattr(pipeline, "stats_tracker", None), "fps", None) or 30.0

        print(f"\n Frames processed : {results['total_frames']}")
        print(f" Track stability  : {results['stability']:.3f}")
        print(f" Est. ID switches : {results['id_switches']}")

    # ── Free GPU memory after tracking — Stage 2+3 are CPU-only ─────────────
    try:
        del pipeline
        import gc; gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("  [mem] GPU memory released for post-processing")
    except Exception:
        pass

    # ── Stage 2: NBA enrichment (optional — runs BEFORE features) ──────────
    tracking_csv = os.path.join(data_dir, "tracking_data.csv")
    if not os.path.exists(tracking_csv):
        print("\n[WARN] tracking_data.csv not written — Stage 1 produced 0 rows.")
        print("       Possible causes: gameplay not detected, homography mismatch,")
        print("       or all frames filtered as dead-ball.  Skipping Stage 2.")
        sys.exit(3)  # exit 3 = empty tracking; run_phase_g treats 3 as soft failure

    # ── Stage 2: NBA enrichment (optional) ───────────────────────────────────
    enriched = {}
    if args.game_id:
        print("\n" + "=" * 60)
        print(" Stage 2 / 3 — NBA API Enrichment")
        print("=" * 60)
        try:
            from src.data.nba_enricher import enrich
            # Resolve period list: --periods overrides --period; default auto-detect.
            from src.data.nba_enricher import _infer_period_count
            if args.periods:
                enrich_periods = [int(p) for p in args.periods.split(",")]
            elif args.period is not None:
                enrich_periods = None  # single-period mode
            else:
                enrich_periods, _ = _infer_period_count(data_dir)
            enrich_kwargs = dict(
                game_id=args.game_id,
                clip_start_sec=args.start,
                fps=fps,
                data_dir=data_dir,
            )
            if enrich_periods is not None:
                enrich_kwargs["periods"] = enrich_periods
            else:
                enrich_kwargs["period"] = args.period or 1
            enriched = enrich(**enrich_kwargs)
        except Exception as e:
            print(f"  NBA enrichment failed: {e}")
            print("  (Tracking data is still complete — enrichment is optional)")
    else:
        print("\n Stage 2 / 3 — NBA Enrichment skipped (no --game-id)")
        print("  Run later: python -m src.data.nba_enricher "
              "--game-id <ID> --period <P> --start <secs>")

    # ── Team abbrev backfill (skip-tracking path) ──────────────────────────────
    # When --skip-tracking is used, pipeline.run() never fires _resolve_team_names
    # or _backfill_team_abbrev, leaving team_abbrev all NaN in tracking_data.csv.
    # Fix: resolve team names from NBA API and backfill here.
    if args.skip_tracking and args.game_id:
        try:
            import csv as _csv
            import json as _json
            _td_path = os.path.join(data_dir, "tracking_data.csv")
            # Check if team_abbrev is already filled
            _needs_backfill = True
            if os.path.exists(_td_path):
                import pandas as _pd
                _sample = _pd.read_csv(_td_path, nrows=100, encoding="utf-8")
                if "team_abbrev" in _sample.columns and _sample["team_abbrev"].notna().any():
                    _needs_backfill = False
            if _needs_backfill:
                # Try loading cached team map first
                _cache_path = os.path.join(
                    os.path.dirname(os.path.dirname(data_dir)), "nba",
                    f"team_map_{args.game_id}.json",
                )
                _color_map = {}
                if os.path.exists(_cache_path):
                    with open(_cache_path) as _f:
                        _color_map = _json.load(_f)
                if not _color_map:
                    # Resolve via NBA API
                    from nba_api.stats.static import teams as _teams_static
                    import time as _time
                    _time.sleep(0.6)
                    _id_to_abbr = {t["id"]: t["abbreviation"] for t in _teams_static.get_teams()}
                    try:
                        from nba_api.stats.endpoints import boxscoresummaryv3 as _bssv3
                        _bs = _bssv3.BoxScoreSummaryV3(game_id=args.game_id)
                        _df = _bs.get_data_frames()[0]
                        _home = _id_to_abbr.get(int(_df["homeTeamId"].iloc[0]), "UNK")
                        _away = _id_to_abbr.get(int(_df["awayTeamId"].iloc[0]), "UNK")
                    except Exception:
                        from nba_api.stats.endpoints import boxscoresummaryv2 as _bssv2
                        _bs = _bssv2.BoxScoreSummaryV2(game_id=args.game_id)
                        _df = _bs.get_data_frames()[0]
                        _home = _id_to_abbr.get(int(_df["HOME_TEAM_ID"].iloc[0]), "UNK")
                        _away = _id_to_abbr.get(int(_df["VISITOR_TEAM_ID"].iloc[0]), "UNK")
                    # Read color labels from tracking CSV
                    _full = _pd.read_csv(_td_path, usecols=["team"], encoding="utf-8")
                    _labels = sorted(_full["team"].dropna().unique().tolist())
                    _labels = [l for l in _labels if l and l != "referee"]
                    if len(_labels) >= 2:
                        _color_map = {_labels[0]: _home, _labels[1]: _away}
                    elif len(_labels) == 1:
                        _color_map = {_labels[0]: _home}
                    # Cache
                    os.makedirs(os.path.dirname(_cache_path), exist_ok=True)
                    with open(_cache_path, "w") as _f:
                        _json.dump(_color_map, _f)
                if _color_map:
                    # Backfill tracking_data.csv
                    with open(_td_path, newline="", encoding="utf-8") as _f:
                        _reader = _csv.DictReader(_f)
                        _fields = list(_reader.fieldnames or [])
                        _rows = list(_reader)
                    if "team_abbrev" not in _fields:
                        _fields.append("team_abbrev")
                    for _row in _rows:
                        _color = _row.get("team", "")
                        _row["team_abbrev"] = _color_map.get(_color, "")
                    with open(_td_path, "w", newline="", encoding="utf-8") as _f:
                        _w = _csv.DictWriter(_f, fieldnames=_fields, extrasaction="ignore")
                        _w.writeheader()
                        _w.writerows(_rows)
                    # Also write team_colors.json for feature_engineering fallback
                    _tc_path = os.path.join(data_dir, "team_colors.json")
                    with open(_tc_path, "w") as _f:
                        _json.dump(_color_map, _f, indent=2)
                    print(f"  [team_abbrev] backfill applied: {_color_map}")
                else:
                    print("  [team_abbrev] no color labels found — skipped")
        except Exception as _e:
            print(f"  [team_abbrev] backfill failed: {_e}")

    # ── OCR identity annotation pass ──────────────────────────────────────────
    if _HAS_IDENTITY and args.game_id:
        db_url = os.environ.get("DATABASE_URL")
        clip_id = str(uuid.uuid4())

        print("\n" + "=" * 60)
        print(" Stage 4 / 4 — OCR Identity Annotation")
        print("=" * 60)
        print("[run_clip] Running OCR annotation pass...")
        buf = JerseyVotingBuffer()

        # player_crops is a dict {slot: crop_bgr} saved during the tracking loop.
        # If the pipeline exposes crops, use them; otherwise pass an empty dict
        # and let run_ocr_annotation_pass skip gracefully (no crops = no OCR reads).
        player_crops: dict = getattr(results, "player_crops", {}) if not args.skip_tracking else {}

        # run_ocr_annotation_pass expects a frame and frame_index.
        # Since we are in post-processing mode (no live frame), pass a dummy frame
        # at frame_index=0 so SAMPLE_EVERY_N triggers (0 % N == 0).
        import numpy as np
        dummy_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        confirmed = run_ocr_annotation_pass(
            frame=dummy_frame,
            player_crops=player_crops,
            frame_index=0,
            buffer=buf,
        )

        if db_url and confirmed:
            print(f"[run_clip] Persisting {len(confirmed)} confirmed identities...")
            for slot, jersey_number in confirmed.items():
                persist_identity_map(
                    db_url=db_url,
                    game_id=args.game_id,
                    clip_id=clip_id,
                    slot=slot,
                    jersey_number=jersey_number,
                    player_id=None,   # player_id resolved from roster lookup downstream
                    confirmed_frame=0,
                    confidence=1.0,
                )
            rows_updated = update_tracking_frames(
                db_url=db_url,
                game_id=args.game_id,
                clip_id=clip_id,
            )
            print(f"[run_clip] Updated {rows_updated} tracking_frames rows with player_id")
        elif not db_url:
            print("[run_clip] DATABASE_URL not set — skipping identity persistence")
        else:
            print("[run_clip] No confirmed jersey identities in this clip")
    # ── end OCR annotation pass ───────────────────────────────────────────────

    # ── Stage 3: Feature engineering (AFTER enrichment so features include enrichment cols)
    if not args.skip_features:
        print("\n" + "=" * 60)
        print(" Stage 3 / 3 — Feature Engineering")
        print("=" * 60)
        features_df = run_features(
            input_path=tracking_csv,
            output_path=os.path.join(data_dir, "features.csv"),
        )
    else:
        print("\n[SKIP] Feature Engineering (--skip-features)")
        features_df = None

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print(" Output Summary")
    print("=" * 60)

    outputs = [
        ("tracking_data.csv",     "Per-frame player data (36 cols)"),
        ("ball_tracking.csv",     "Per-frame ball position"),
        ("possessions.csv",       "Per-possession aggregate stats"),
        ("shot_log.csv",          "Per-shot attempt log"),
        ("player_clip_stats.csv", "Per-player clip aggregates"),
        ("features.csv",          "ML-ready engineered features"),
    ]
    if not args.skip_tracking and results.get("stats"):
        outputs.append(("stats.json", "Shot attempts + made (YOLO mode)"))
    if enriched.get("shot_log_enriched"):
        outputs.append(("shot_log_enriched.csv",     "Shot log + made/missed (NBA API)"))
    if enriched.get("possessions_enriched"):
        outputs.append(("possessions_enriched.csv",  "Possessions + result + score_diff"))

    for fname, desc in outputs:
        path = os.path.join(data_dir, fname)
        if fname.endswith(".csv"):
            tag = _fmt_rows(path)
        else:
            tag = _fmt_size(path)
        exists = "✓" if os.path.exists(path) else "✗"
        print(f"  {exists}  {fname:<30}  {tag:<12}  {desc}")

    # ML readiness
    td_path = os.path.join(data_dir, "tracking_data.csv")
    fe_path = os.path.join(data_dir, "features.csv")
    n_frames = results["total_frames"] if not args.skip_tracking else 0
    n_cols   = len(features_df.columns) if features_df is not None else "?"

    print(f"\n ML Dataset")
    print(f"  features.csv : {_fmt_rows(fe_path)}  {n_cols} columns")
    print(f"  Frames        : {n_frames}  "
          f"({n_frames / max(1, fps):.0f}s @ {fps:.0f}fps)")
    if args.game_id:
        poss_path = os.path.join(data_dir, "possessions_enriched.csv")
        print(f"  possessions   : {_fmt_rows(poss_path)} labeled rows "
              f"(team / result / score_diff) — train your model here")
        shot_path = os.path.join(data_dir, "shot_log_enriched.csv")
        print(f"  shot_log      : {_fmt_rows(shot_path)} labeled rows "
              f"(zone / quality / made) — shot-quality model target")
    else:
        print("  Run with --game-id to add outcome labels for ML training.")

    print(f"\n Total time: {elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
