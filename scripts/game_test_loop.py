"""
game_test_loop.py — 3-hour full-system test loop.

Processes every video in data/videos/, matches each to its NBA game ID,
runs the full 4-stage pipeline (track → features → enrich → retrain check),
records per-game metrics, and logs a quality report to vault/.

Usage
-----
    conda activate basketball_ai
    cd C:/Users/neelj/nba-ai-system
    python scripts/game_test_loop.py

Options
-------
    --hours N       Runtime cap in hours  (default: 3)
    --max-frames N  Frame cap per clip    (default: no cap — full game)
    --no-enrich     Skip NBA enrichment   (faster, no game_id required)
    --dry-run       Print plan, don't process

Output files
------------
    data/game_loop_results.json   — per-game metrics (updated after each game)
    vault/Sessions/game_loop_<date>.md — human-readable run report
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# ── Paths ──────────────────────────────────────────────────────────────────────

_VIDEOS_DIR   = os.path.join(PROJECT_DIR, "data", "videos")
_DATA_DIR     = os.path.join(PROJECT_DIR, "data")
_SCHEDULE_DIR = os.path.join(_DATA_DIR, "nba", "schedule")
_GAMES_DIR    = os.path.join(_DATA_DIR, "games")
_VAULT_DIR    = os.path.join(PROJECT_DIR, "vault", "Sessions")
_RESULTS_PATH = os.path.join(_DATA_DIR, "game_loop_results.json")

os.makedirs(_GAMES_DIR, exist_ok=True)
os.makedirs(_VAULT_DIR, exist_ok=True)

# ── Team abbreviation map (video filename prefix → NBA abbr pairs) ─────────────

_TEAM_MAP: Dict[str, Tuple[str, str]] = {
    "atl_ind": ("ATL", "IND"),
    "bos_mia": ("BOS", "MIA"),
    "cavs_vs_celtics": ("CLE", "BOS"),
    "cavs_broadcast": ("CLE", None),
    "gsw_lakers": ("GSW", "LAL"),
    "mil_chi": ("MIL", "CHI"),
    "den_phx": ("DEN", "PHX"),
    "lal_sas": ("LAL", "SAS"),
    "mem_nop": ("MEM", "NOP"),
    "phi_tor": ("PHI", "TOR"),
    "okc_dal": ("OKC", "DAL"),
    "sac_por": ("SAC", "POR"),
    "mia_bkn": ("MIA", "BKN"),
    "den_gsw": ("DEN", "GSW"),
    "nba_highlights_gsw": ("GSW", None),
    "bos_mia_playoffs": ("BOS", "MIA"),
}

# ── Schedule loader ────────────────────────────────────────────────────────────

_SCHEDULE_CACHE: Dict[str, List[dict]] = {}

def _load_schedule(team: str, season: str = "2024-25") -> List[dict]:
    """Load schedule for a team. Returns list of game dicts."""
    key = f"{team}_{season}"
    if key in _SCHEDULE_CACHE:
        return _SCHEDULE_CACHE[key]
    # Try v2 file first, then plain
    for suffix in [f"_v2.json", ".json"]:
        path = os.path.join(_SCHEDULE_DIR, f"schedule_{team}_{season}{suffix}")
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            games = data if isinstance(data, list) else data.get("games", [])
            _SCHEDULE_CACHE[key] = games
            return games
    return []


def find_game_id(team_a: str, team_b: Optional[str], season: str = "2024-25") -> Optional[str]:
    """
    Find the best matching game_id for a matchup in the 2024-25 schedule.

    Searches team_a's schedule for a game against team_b. Returns the first
    match (most recent season games are stored chronologically).
    """
    games = _load_schedule(team_a, season)
    if not games:
        return None

    for game in games:
        opp = game.get("opponent", "")
        game_id = game.get("game_id", "")
        if not game_id:
            continue
        if team_b is None or opp == team_b:
            return game_id

    # Fallback: try from team_b's perspective
    if team_b:
        games_b = _load_schedule(team_b, season)
        for game in games_b:
            opp = game.get("opponent", "")
            game_id = game.get("game_id", "")
            if not game_id:
                continue
            if opp == team_a:
                return game_id

    return None


def match_video_to_game_id(video_stem: str) -> Optional[str]:
    """
    Match a video filename stem to an NBA game_id from schedule data.

    Tries 2024-25 first, then 2023-24 for playoff clips.
    """
    # Normalize stem (remove trailing numbers, underscores)
    stem_lower = video_stem.lower().rstrip("_0123456789")

    for key, (team_a, team_b) in _TEAM_MAP.items():
        if stem_lower.startswith(key) or key in stem_lower:
            # Try 2024-25 first, then 2023-24 for playoff clips
            for season in ["2024-25", "2023-24"]:
                gid = find_game_id(team_a, team_b, season)
                if gid:
                    return gid

    return None


# ── Video discovery ────────────────────────────────────────────────────────────

def discover_videos() -> List[dict]:
    """
    Find all .mp4 files in data/videos/ and match to game IDs.

    Returns list of dicts: {path, stem, game_id, already_processed}
    """
    entries = []
    for fname in sorted(os.listdir(_VIDEOS_DIR)):
        if not fname.endswith(".mp4"):
            continue
        path = os.path.join(_VIDEOS_DIR, fname)
        stem = Path(fname).stem
        size_mb = os.path.getsize(path) / (1024 * 1024)

        game_id = match_video_to_game_id(stem)

        # Check if already processed (has game_tracking.csv)
        already_done = False
        if game_id:
            merged = os.path.join(_GAMES_DIR, game_id, "game_tracking.csv")
            already_done = os.path.exists(merged)

        entries.append({
            "path":              path,
            "stem":              stem,
            "size_mb":           round(size_mb, 1),
            "game_id":           game_id,
            "already_processed": already_done,
        })

    # Sort: largest files first (most likely full games), skip already-done last
    entries.sort(key=lambda x: (-x["size_mb"], x["already_processed"]))
    return entries


# ── Metrics helpers ────────────────────────────────────────────────────────────

def _count_csv_rows(path: str) -> int:
    if not os.path.exists(path):
        return 0
    try:
        import csv
        with open(path, newline="") as f:
            return sum(1 for _ in csv.DictReader(f))
    except Exception:
        return 0


def _read_json_safe(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


# ── Single game runner ─────────────────────────────────────────────────────────

def run_one_game(
    video: dict,
    max_frames: Optional[int],
    no_enrich: bool,
) -> dict:
    """
    Run the full 4-stage pipeline on one video.

    Returns a result dict with timing, quality metrics, and any errors.
    """
    t0 = time.time()
    game_id = video["game_id"] or f"noid_{video['stem']}"
    result = {
        "stem":          video["stem"],
        "path":          video["path"],
        "game_id":       game_id,
        "size_mb":       video["size_mb"],
        "started_at":    datetime.now().isoformat(),
        "duration_sec":  0,
        "success":       False,
        "error":         None,
        "traceback":     None,
        # tracking quality
        "total_frames":      0,
        "tracking_rows":     0,
        "stability":         0.0,
        "id_switches":       0,
        "ball_detected_pct": 0.0,
        # data volume
        "shots_detected":        0,
        "possessions_labeled":   0,
        "shots_enriched":        0,
        "possessions_enriched":  0,
        # pipeline perf
        "fps_estimate":    0.0,
        "stages_completed": [],
    }

    try:
        # ── Stage 1: Tracking ────────────────────────────────────────────────
        print(f"\n{'='*60}")
        print(f"  VIDEO : {video['stem']}  ({video['size_mb']} MB)")
        print(f"  GAME  : {game_id}")
        print(f"{'='*60}")
        print("  Stage 1/4 — Tracking...")
        t_stage = time.time()

        from src.pipeline.unified_pipeline import UnifiedPipeline
        import inspect

        up_sig = inspect.signature(UnifiedPipeline.__init__).parameters
        up_kwargs = dict(
            video_path=video["path"],
            yolo_weight_path=None,
            max_frames=max_frames,
            show=False,
            game_id=game_id if video["game_id"] else None,
        )
        if "frame_skip" in up_sig:
            up_kwargs["frame_skip"] = 1   # pipeline handles stride internally

        pipeline = UnifiedPipeline(**up_kwargs)
        tracking_result = pipeline.run()

        result["total_frames"]  = tracking_result.get("total_frames", 0)
        result["stability"]     = round(float(tracking_result.get("stability", 0)), 3)
        result["id_switches"]   = tracking_result.get("id_switches", 0)
        elapsed_track = time.time() - t_stage
        result["fps_estimate"]  = round(result["total_frames"] / max(elapsed_track, 1), 1)
        result["stages_completed"].append("tracking")
        print(f"  ✓ Tracking done — {result['total_frames']} frames @ {result['fps_estimate']} fps"
              f"  stability={result['stability']:.3f}")

        # Count ball detection rate from ball_tracking.csv
        bt_path = os.path.join(_DATA_DIR, "ball_tracking.csv")
        bt_rows = _count_csv_rows(bt_path)
        if bt_rows > 0:
            try:
                import csv
                detected = 0
                with open(bt_path, newline="") as f:
                    for row in csv.DictReader(f):
                        if row.get("detected", "0") == "1":
                            detected += 1
                result["ball_detected_pct"] = round(100.0 * detected / bt_rows, 1)
            except Exception:
                pass
        print(f"  Ball detection: {result['ball_detected_pct']}%")

        result["tracking_rows"]   = _count_csv_rows(os.path.join(_DATA_DIR, "tracking_data.csv"))
        result["shots_detected"]  = _count_csv_rows(os.path.join(_DATA_DIR, "shot_log.csv"))
        result["possessions_labeled"] = _count_csv_rows(os.path.join(_DATA_DIR, "possessions.csv"))

        # ── Stage 2: Feature engineering ────────────────────────────────────
        print("  Stage 2/4 — Feature engineering...")
        try:
            from src.features.feature_engineering import run as run_features
            run_features(
                input_path=os.path.join(_DATA_DIR, "tracking_data.csv"),
                output_path=os.path.join(_DATA_DIR, "features.csv"),
            )
            result["stages_completed"].append("features")
            feat_rows = _count_csv_rows(os.path.join(_DATA_DIR, "features.csv"))
            print(f"  ✓ Features done — {feat_rows} rows")
        except Exception as e:
            print(f"  ⚠ Feature engineering failed: {e}")

        # ── Stage 3: NBA enrichment ──────────────────────────────────────────
        if no_enrich or not video["game_id"]:
            print("  Stage 3/4 — NBA enrichment SKIPPED (no game_id or --no-enrich)")
        else:
            print("  Stage 3/4 — NBA enrichment...")
            try:
                import csv
                from src.data.nba_enricher import enrich
                fps_vid = result["fps_estimate"] or 30.0
                enrich_result = enrich(
                    game_id=game_id,
                    period=1,
                    clip_start_sec=0.0,
                    fps=fps_vid,
                    data_dir=_DATA_DIR,
                )
                result["stages_completed"].append("enrichment")
                # Count enriched rows
                for key, path_key in [
                    ("shots_enriched",       "shot_log_enriched"),
                    ("possessions_enriched", "possessions_enriched"),
                ]:
                    p = enrich_result.get(path_key, "")
                    if p and os.path.exists(p):
                        with open(p, newline="") as fh:
                            rows_e = list(csv.DictReader(fh))
                        if path_key == "shots_enriched":
                            result[key] = sum(1 for r in rows_e if r.get("made", "") != "")
                        else:
                            result[key] = sum(1 for r in rows_e if r.get("result", "") not in ("", "unknown"))
                print(f"  ✓ Enrichment done — {result['shots_enriched']} shots / "
                      f"{result['possessions_enriched']} possessions enriched")
            except Exception as e:
                print(f"  ⚠ Enrichment failed: {e}")

        # ── Stage 4: Snapshot to games/ dir ─────────────────────────────────
        print("  Stage 4/4 — Saving to games/ dir...")
        try:
            _snapshot_game(game_id, result)
            result["stages_completed"].append("snapshot")
            print(f"  ✓ Saved → data/games/{game_id}/")
        except Exception as e:
            print(f"  ⚠ Snapshot failed: {e}")

        result["success"] = True

    except KeyboardInterrupt:
        raise
    except Exception as e:
        result["error"]     = str(e)
        result["traceback"] = traceback.format_exc()
        print(f"\n  ✗ FAILED: {e}")
        print(result["traceback"])

    result["duration_sec"] = round(time.time() - t0, 1)
    return result


def _snapshot_game(game_id: str, result: dict) -> None:
    """Copy pipeline outputs into data/games/<game_id>/."""
    import shutil
    out_dir = os.path.join(_GAMES_DIR, game_id)
    os.makedirs(out_dir, exist_ok=True)

    src_files = [
        "tracking_data.csv", "ball_tracking.csv", "possessions.csv",
        "shot_log.csv", "features.csv", "stats.json",
        "shot_log_enriched.csv", "possessions_enriched.csv",
    ]
    for fname in src_files:
        src = os.path.join(_DATA_DIR, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(out_dir, fname))

    # Write per-game manifest
    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(result, f, indent=2)


# ── Quality assessment ─────────────────────────────────────────────────────────

def quality_grade(result: dict) -> str:
    """
    Return a letter grade A–F based on pipeline output quality.

    Criteria:
        A: stability ≥ 0.9, ball_det ≥ 80%, shots ≥ 10, possessions ≥ 50
        B: stability ≥ 0.8, ball_det ≥ 60%, shots ≥ 5,  possessions ≥ 20
        C: stability ≥ 0.7, ball_det ≥ 40%, shots ≥ 2,  possessions ≥ 5
        D: tracking succeeded but low quality
        F: tracking failed
    """
    if not result["success"]:
        return "F"
    s   = result["stability"]
    bd  = result["ball_detected_pct"]
    sh  = result["shots_detected"]
    pos = result["possessions_labeled"]
    if s >= 0.9 and bd >= 80 and sh >= 10 and pos >= 50:
        return "A"
    if s >= 0.8 and bd >= 60 and sh >= 5  and pos >= 20:
        return "B"
    if s >= 0.7 and bd >= 40 and sh >= 2  and pos >= 5:
        return "C"
    if s > 0:
        return "D"
    return "F"


# ── Vault logger ───────────────────────────────────────────────────────────────

def write_vault_report(session_results: List[dict], log_path: str, elapsed_min: float) -> None:
    """Write a Markdown summary of the loop run to vault/Sessions/."""
    grades = [quality_grade(r) for r in session_results]
    ok     = sum(1 for r in session_results if r["success"])
    total  = len(session_results)
    avg_fps = (
        sum(r["fps_estimate"] for r in session_results if r["success"]) / max(ok, 1)
    )
    total_rows = sum(r["tracking_rows"] for r in session_results)
    total_shots = sum(r["shots_detected"] for r in session_results)
    total_poss  = sum(r["possessions_labeled"] for r in session_results)

    lines = [
        f"# Game Test Loop — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"",
        f"**Runtime:** {elapsed_min:.0f} min   **Games processed:** {ok}/{total}",
        f"**Avg FPS:** {avg_fps:.1f}   **Total tracking rows:** {total_rows:,}",
        f"**Total shots detected:** {total_shots}   **Possessions labeled:** {total_poss}",
        f"",
        f"## Per-Game Results",
        f"",
        f"| Game | Size | Grade | Frames | FPS | Stability | Ball% | Shots | Poss | Time |",
        f"|------|------|-------|--------|-----|-----------|-------|-------|------|------|",
    ]
    for r, g in zip(session_results, grades):
        lines.append(
            f"| {r['stem'][:20]} | {r['size_mb']} MB | {g} "
            f"| {r['total_frames']} | {r['fps_estimate']} "
            f"| {r['stability']:.3f} | {r['ball_detected_pct']}% "
            f"| {r['shots_detected']} | {r['possessions_labeled']} "
            f"| {r['duration_sec']:.0f}s |"
        )

    lines += [
        f"",
        f"## Failures",
        f"",
    ]
    failures = [r for r in session_results if not r["success"]]
    if failures:
        for r in failures:
            lines.append(f"### {r['stem']}")
            lines.append(f"```")
            lines.append(r.get("error", "unknown"))
            lines.append(f"```")
    else:
        lines.append("No failures.")

    lines += [
        f"",
        f"## Grade Distribution",
        f"",
    ]
    from collections import Counter
    grade_counts = Counter(grades)
    for g in "ABCDF":
        if grade_counts[g]:
            lines.append(f"- **{g}**: {grade_counts[g]} game(s)")

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n  Report → {log_path}")


# ── Main loop ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="3-hour full-system game test loop")
    parser.add_argument("--hours",      type=float, default=3.0,
                        help="Total runtime cap in hours (default: 3)")
    parser.add_argument("--max-frames", type=int,   default=None,
                        help="Frame cap per clip (default: no cap)")
    parser.add_argument("--no-enrich",  action="store_true",
                        help="Skip NBA enrichment (faster for tracking-only tests)")
    parser.add_argument("--dry-run",    action="store_true",
                        help="Print plan without processing")
    parser.add_argument("--reprocess",  action="store_true",
                        help="Reprocess games even if already done")
    args = parser.parse_args()

    deadline = datetime.now() + timedelta(hours=args.hours)
    session_results: List[dict] = []
    vault_log = os.path.join(
        _VAULT_DIR,
        f"game_loop_{datetime.now().strftime('%Y-%m-%d_%H%M')}.md",
    )

    # ── Discover videos ──────────────────────────────────────────────────────
    videos = discover_videos()

    print(f"\n{'='*60}")
    print(f"  NBA AI — Game Test Loop")
    print(f"  Runtime : {args.hours:.1f} hours  ({deadline.strftime('%H:%M')} deadline)")
    print(f"  Videos  : {len(videos)} found")
    print(f"  Enrich  : {'OFF' if args.no_enrich else 'ON'}")
    print(f"  Frames  : {'all' if not args.max_frames else args.max_frames}")
    print(f"{'='*60}\n")

    for i, v in enumerate(videos):
        matched = f"game_id={v['game_id']}" if v["game_id"] else "no game_id match"
        done    = " [DONE]" if v["already_processed"] and not args.reprocess else ""
        print(f"  [{i+1:2d}] {v['stem'][:35]:<35} {v['size_mb']:>7.1f} MB  {matched}{done}")

    if args.dry_run:
        print("\nDry-run — exiting.")
        return

    # ── Processing loop ──────────────────────────────────────────────────────
    loop_num = 0
    while datetime.now() < deadline:
        loop_num += 1
        pending = [
            v for v in videos
            if not v["already_processed"] or args.reprocess
        ]

        if not pending:
            print("\n  All videos processed. Cycling back to reprocess all...")
            # Mark all as not done so we cycle
            for v in videos:
                v["already_processed"] = False
            pending = videos[:]

        print(f"\n{'─'*60}")
        print(f"  Loop {loop_num}  |  {len(pending)} pending  |  "
              f"{(deadline - datetime.now()).seconds // 60} min remaining")
        print(f"{'─'*60}")

        for v in pending:
            if datetime.now() >= deadline:
                print("\n  Time limit reached — stopping.")
                break

            mins_left = (deadline - datetime.now()).seconds // 60
            print(f"\n  [{v['stem']}]  {mins_left} min remaining")

            # Skip if we won't have enough time (< 5 min for large files)
            if mins_left < 5:
                print("  Skipping — < 5 min remaining, not enough for full game.")
                continue

            result = run_one_game(
                video=v,
                max_frames=args.max_frames,
                no_enrich=args.no_enrich,
            )
            session_results.append(result)
            v["already_processed"] = True

            # Print grade
            grade = quality_grade(result)
            status = "✓" if result["success"] else "✗"
            print(f"\n  {status} {v['stem']}")
            print(f"     Grade      : {grade}")
            print(f"     Frames     : {result['total_frames']}")
            print(f"     FPS        : {result['fps_estimate']}")
            print(f"     Stability  : {result['stability']}")
            print(f"     Ball det.  : {result['ball_detected_pct']}%")
            print(f"     Shots      : {result['shots_detected']}")
            print(f"     Possessions: {result['possessions_labeled']}")
            print(f"     Enriched   : shots={result['shots_enriched']} poss={result['possessions_enriched']}")
            print(f"     Duration   : {result['duration_sec']:.0f}s")

            # Save running results log
            try:
                with open(_RESULTS_PATH, "w") as f:
                    json.dump(session_results, f, indent=2)
            except Exception:
                pass

    # ── Final report ─────────────────────────────────────────────────────────
    elapsed_min = args.hours * 60 - (deadline - datetime.now()).seconds / 60

    print(f"\n{'='*60}")
    print(f"  LOOP COMPLETE — {len(session_results)} games processed")
    print(f"{'='*60}")

    if session_results:
        ok    = sum(1 for r in session_results if r["success"])
        total = len(session_results)
        avg_s = sum(r["stability"] for r in session_results if r["success"]) / max(ok, 1)
        avg_b = sum(r["ball_detected_pct"] for r in session_results if r["success"]) / max(ok, 1)
        t_rows = sum(r["tracking_rows"] for r in session_results)
        t_sh   = sum(r["shots_detected"] for r in session_results)
        t_pos  = sum(r["possessions_labeled"] for r in session_results)

        print(f"  Success rate  : {ok}/{total}")
        print(f"  Avg stability : {avg_s:.3f}")
        print(f"  Avg ball det. : {avg_b:.1f}%")
        print(f"  Total rows    : {t_rows:,}")
        print(f"  Total shots   : {t_sh}")
        print(f"  Total poss.   : {t_pos}")

        write_vault_report(session_results, vault_log, elapsed_min)

        print(f"\n  Full results → {_RESULTS_PATH}")

    print()


if __name__ == "__main__":
    main()
