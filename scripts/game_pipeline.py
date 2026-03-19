"""
game_pipeline.py — End-to-end pipeline: download → track → evaluate → log.

Downloads a real NBA game clip, runs the full tracking pipeline on it,
evaluates tracker quality against NBA API ground truth, and logs a report
to the Obsidian vault.

Usage
-----
    # Download + process by team name (uses CURATED_CLIPS search queries)
    python scripts/game_pipeline.py --team gsw

    # Download + process a specific YouTube URL
    python scripts/game_pipeline.py --url "https://youtube.com/watch?v=..." --game-id 0022401001

    # Process an already-downloaded local video
    python scripts/game_pipeline.py --video data/videos/nba_gsw_full_2024.mp4 --game-id 0022401001

    # Process first N frames only (quick sanity check — ~5 min)
    python scripts/game_pipeline.py --team gsw --frames 3000

    # List curated clip options
    python scripts/game_pipeline.py --list-clips

Outputs
-------
    data/game_results/<game_id>_summary.json    Full pipeline summary
    data/game_results/<game_id>_eval.json       Tracker evaluation report
    vault/Sessions/eval_<game_id>.md            Obsidian-readable quality report
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_DATA_DIR    = os.path.join(PROJECT_DIR, "data")
_RESULTS_DIR = os.path.join(_DATA_DIR, "game_results")
_VAULT_DIR   = os.path.join(PROJECT_DIR, "vault", "Sessions")

os.makedirs(_RESULTS_DIR, exist_ok=True)
os.makedirs(_VAULT_DIR, exist_ok=True)


# ── Quality thresholds ────────────────────────────────────────────────────────

QUALITY_THRESHOLDS = {
    "players_per_frame_min":  8.0,    # expect ~10 players, 8+ is acceptable
    "ball_detection_min":    0.50,    # 50% frame-level ball detection
    "jersey_ocr_min":        0.30,    # 30%+ rows with a jersey number
    "valid_position_min":    0.95,    # 95%+ rows have valid x/y coords
    "possession_dur_min":    4.0,     # avg possession > 4 sec (not noise)
    "shot_recall_min":       0.40,    # detect 40%+ of NBA API shots in window
}


# ── Step 1: Download ──────────────────────────────────────────────────────────

def download_game(
    team: Optional[str] = None,
    url: Optional[str] = None,
    video: Optional[str] = None,
) -> str:
    """Return path to local video file, downloading if necessary."""
    if video:
        if not os.path.exists(video):
            raise FileNotFoundError(f"Video not found: {video}")
        print(f"[pipeline] Using local video: {video}")
        return video

    from src.data.video_fetcher import download_clip, CURATED_CLIPS

    if url:
        print(f"[pipeline] Downloading from URL: {url[:80]}")
        return download_clip(url)

    if team:
        # Find a curated clip matching the team
        team_lower = team.lower()
        matches = {k: v for k, v in CURATED_CLIPS.items()
                   if team_lower in k.lower()}
        if not matches:
            available = list(CURATED_CLIPS.keys())
            raise ValueError(
                f"No curated clip found for team '{team}'.\n"
                f"Available: {available}\n"
                f"Or pass --url directly."
            )
        # Prefer condensed replays (shorter, still full game action)
        condensed = {k: v for k, v in matches.items() if "condensed" in k}
        label, query = next(iter(condensed.items() if condensed else matches.items()))
        print(f"[pipeline] Downloading curated clip: {label}")
        print(f"           Query: {query}")
        return download_clip(query, label=label)

    raise ValueError("Provide --team, --url, or --video.")


# ── Step 2: Match to NBA game ID ──────────────────────────────────────────────

def resolve_game_id(video_path: str, game_id: Optional[str] = None) -> Optional[str]:
    """Resolve NBA game ID from explicit arg or by matching clip label."""
    if game_id:
        print(f"[pipeline] Using game ID: {game_id}")
        return game_id

    label = Path(video_path).stem
    try:
        from src.data.game_matcher import match_clip_to_game
        match = match_clip_to_game(label)
        if match and match.game_id:
            print(f"[pipeline] Matched game ID: {match.game_id} ({match.home_team} vs {match.away_team})")
            return match.game_id
        print("[pipeline] WARNING: Could not auto-match game ID — enrichment will be skipped.")
        return None
    except Exception as exc:
        print(f"[pipeline] Game ID match failed (non-fatal): {exc}")
        return None


# ── Step 3: Run tracking pipeline ────────────────────────────────────────────

def run_tracking_pipeline(
    video_path: str,
    game_id: Optional[str],
    frames: Optional[int] = None,
    season: str = "2024-25",
) -> dict:
    """Run the full tracking → features → analytics pipeline via subprocess."""
    from src.pipeline.run_pipeline import run_game

    print(f"\n[pipeline] Running tracking pipeline...")
    print(f"           Video:   {video_path}")
    print(f"           Game ID: {game_id or 'None (enrichment skipped)'}")
    if frames:
        print(f"           Frames:  {frames} (limited mode)")

    summary = run_game(
        video_path=video_path,
        game_id=game_id or "UNKNOWN",
        season=season,
    )

    status = summary.get("status", "error")
    if status == "error":
        print(f"[pipeline] Pipeline error: {summary.get('error')}")
    else:
        t = summary.get("tracking", {})
        print(f"[pipeline] Tracking done: {t.get('rows',0)} rows, "
              f"{t.get('frames',0)} frames, {t.get('players',0)} players")

    return summary


# ── Step 4: Evaluate tracker quality ─────────────────────────────────────────

def evaluate_quality(game_id: Optional[str]) -> dict:
    """
    Compare tracking output against ground truth from NBA API.

    Checks:
    - Player detection rate (players/frame)
    - Ball detection rate
    - Jersey OCR hit rate
    - Position coverage
    - Possession duration (noise filter)
    - Shot recall vs NBA API play-by-play
    """
    print("\n[pipeline] Evaluating tracker quality...")

    eval_result: dict = {
        "game_id": game_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metrics": {},
        "grades": {},
        "overall_grade": "F",
        "issues": [],
    }

    metrics = eval_result["metrics"]
    issues  = eval_result["issues"]

    # ── tracking_data.csv ────────────────────────────────────────────────────
    tracking_csv = os.path.join(_DATA_DIR, "tracking_data.csv")
    if os.path.exists(tracking_csv):
        with open(tracking_csv) as f:
            rows = list(csv.DictReader(f))

        total = len(rows)
        if total > 0:
            # Players per frame
            frames: dict = {}
            for r in rows:
                frames.setdefault(r.get("frame", ""), []).append(r)
            counts = [len(v) for v in frames.values()]
            metrics["players_per_frame_mean"] = round(
                sum(counts) / len(counts), 2) if counts else 0.0
            metrics["frames_ge10_pct"] = round(
                sum(1 for c in counts if c >= 10) / len(counts) * 100, 1) if counts else 0.0

            # Jersey OCR
            jerseys = [r.get("jersey_number", r.get("jersey", "")) for r in rows]
            named = sum(1 for j in jerseys
                        if j and j not in ("", "-1", "None", "-1.0"))
            metrics["jersey_ocr_rate"] = round(named / total, 3)

            # Valid positions
            xs = [r.get("x_position", "") for r in rows]
            valid = sum(1 for x in xs if x and x not in ("None", ""))
            metrics["valid_position_rate"] = round(valid / total, 3)

            # Team separation
            from collections import Counter
            teams = Counter(r.get("team", "") for r in rows)
            metrics["team_distribution"] = dict(teams)
            metrics["team_separation_ok"] = len(
                [t for t in teams if t not in ("", "None", "unknown")]) >= 2
    else:
        issues.append("tracking_data.csv not found")

    # ── ball_tracking.csv ────────────────────────────────────────────────────
    ball_csv = os.path.join(_DATA_DIR, "ball_tracking.csv")
    if os.path.exists(ball_csv):
        with open(ball_csv) as f:
            ball_rows = list(csv.DictReader(f))
        if ball_rows:
            detected = sum(1 for r in ball_rows
                           if r.get("ball_detected", "") in ("True", "true", "1"))
            metrics["ball_detection_rate"] = round(detected / len(ball_rows), 3)
    else:
        issues.append("ball_tracking.csv not found")

    # ── possessions.csv ──────────────────────────────────────────────────────
    poss_csv = os.path.join(_DATA_DIR, "possessions.csv")
    if os.path.exists(poss_csv):
        with open(poss_csv) as f:
            poss_rows = list(csv.DictReader(f))
        if poss_rows:
            import statistics
            durs = [float(r["duration_sec"]) for r in poss_rows
                    if r.get("duration_sec")]
            if durs:
                metrics["possession_count"]    = len(durs)
                metrics["possession_dur_mean"] = round(statistics.mean(durs), 2)
                metrics["possession_dur_median"] = round(statistics.median(durs), 2)

    # ── shot recall vs NBA API ────────────────────────────────────────────────
    shot_csv = os.path.join(_DATA_DIR, "shot_log.csv")
    if game_id and os.path.exists(shot_csv):
        with open(shot_csv) as f:
            cv_shots = list(csv.DictReader(f))
        metrics["cv_shots_detected"] = len(cv_shots)

        try:
            from src.data.game_matcher import fetch_game_box_score
            box = fetch_game_box_score(game_id)
            total_fga = sum(
                p.get("fga", 0) for team in box.get("teams", {}).values()
                for p in team.get("players", [])
            )
            metrics["nba_api_fga"] = total_fga
            if total_fga > 0:
                metrics["shot_recall"] = round(len(cv_shots) / total_fga, 3)
        except Exception as exc:
            print(f"[eval] Shot recall vs API failed (non-fatal): {exc}")

    # ── Grade each metric ────────────────────────────────────────────────────
    grades = eval_result["grades"]
    thresholds = QUALITY_THRESHOLDS

    def grade(val: Optional[float], threshold: float, label: str) -> str:
        if val is None:
            issues.append(f"Missing metric: {label}")
            return "?"
        g = "PASS" if val >= threshold else "FAIL"
        if g == "FAIL":
            issues.append(f"{label}: {val:.3f} < threshold {threshold}")
        return g

    grades["players_per_frame"] = grade(
        metrics.get("players_per_frame_mean"),
        thresholds["players_per_frame_min"], "players_per_frame")
    grades["ball_detection"] = grade(
        metrics.get("ball_detection_rate"),
        thresholds["ball_detection_min"], "ball_detection_rate")
    grades["jersey_ocr"] = grade(
        metrics.get("jersey_ocr_rate"),
        thresholds["jersey_ocr_min"], "jersey_ocr_rate")
    grades["valid_positions"] = grade(
        metrics.get("valid_position_rate"),
        thresholds["valid_position_min"], "valid_position_rate")
    grades["possession_quality"] = grade(
        metrics.get("possession_dur_mean"),
        thresholds["possession_dur_min"], "possession_dur_mean")
    if "shot_recall" in metrics:
        grades["shot_recall"] = grade(
            metrics.get("shot_recall"),
            thresholds["shot_recall_min"], "shot_recall")

    passes = sum(1 for g in grades.values() if g == "PASS")
    total_grades = sum(1 for g in grades.values() if g in ("PASS", "FAIL"))
    pct = passes / total_grades if total_grades else 0
    eval_result["overall_grade"] = (
        "A" if pct >= 0.9 else
        "B" if pct >= 0.75 else
        "C" if pct >= 0.6 else
        "D" if pct >= 0.4 else "F"
    )
    eval_result["pass_rate"] = f"{passes}/{total_grades}"

    return eval_result


# ── Step 5: Save + log to vault ───────────────────────────────────────────────

def save_and_log(
    pipeline_summary: dict,
    eval_result: dict,
    game_id: Optional[str],
    video_path: str,
) -> str:
    """Save JSON results and write a readable vault report."""
    label = game_id or Path(video_path).stem

    # Save eval JSON
    eval_path = os.path.join(_RESULTS_DIR, f"{label}_eval.json")
    with open(eval_path, "w") as f:
        json.dump(eval_result, f, indent=2, default=str)

    # Build vault markdown report
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    m   = eval_result.get("metrics", {})
    g   = eval_result.get("grades", {})
    issues = eval_result.get("issues", [])

    def _grade_icon(grade: str) -> str:
        return {"PASS": "✅", "FAIL": "❌"}.get(grade, "❓")

    report_lines = [
        f"# Tracker Evaluation — {label}",
        f"**Date:** {now}  ",
        f"**Video:** `{video_path}`  ",
        f"**Overall Grade:** {eval_result.get('overall_grade')} "
        f"({eval_result.get('pass_rate')} checks passing)",
        "",
        "## Metrics",
        "",
        "| Check | Value | Grade |",
        "|-------|-------|-------|",
        f"| Players/frame | {m.get('players_per_frame_mean', 'N/A')} | {_grade_icon(g.get('players_per_frame','?'))} |",
        f"| Ball detection | {m.get('ball_detection_rate', 'N/A')} | {_grade_icon(g.get('ball_detection','?'))} |",
        f"| Jersey OCR rate | {m.get('jersey_ocr_rate', 'N/A')} | {_grade_icon(g.get('jersey_ocr','?'))} |",
        f"| Valid positions | {m.get('valid_position_rate', 'N/A')} | {_grade_icon(g.get('valid_positions','?'))} |",
        f"| Possession duration | {m.get('possession_dur_mean', 'N/A')}s | {_grade_icon(g.get('possession_quality','?'))} |",
        f"| Shot recall | {m.get('shot_recall', 'N/A')} | {_grade_icon(g.get('shot_recall','?'))} |",
        "",
        f"Team distribution: `{m.get('team_distribution', {})}`  ",
        f"Frames ≥10 players: `{m.get('frames_ge10_pct', 'N/A')}%`",
        "",
    ]

    if issues:
        report_lines += ["## Issues", ""]
        for issue in issues:
            report_lines.append(f"- {issue}")
        report_lines.append("")

    t = pipeline_summary.get("tracking", {})
    report_lines += [
        "## Pipeline Stats",
        "",
        f"- Tracking rows: {t.get('rows', 0)}",
        f"- Frames processed: {t.get('frames', 0)}",
        f"- Players tracked: {t.get('players', 0)}",
        f"- Shot quality avg: {pipeline_summary.get('shot_quality', {}).get('avg_quality', 'N/A')}",
        f"- Defense pressure avg: {pipeline_summary.get('defense', {}).get('avg_pressure', 'N/A')}",
        "",
        "## Next Steps",
        "",
    ]

    grade = eval_result.get("overall_grade", "F")
    if grade in ("A", "B"):
        report_lines += [
            "- Tracker performing well — ready for Phase 6 full game runs",
            "- Run with `--game-id` for enrichment",
        ]
    else:
        failing = [k for k, v in g.items() if v == "FAIL"]
        if "ball_detection" in failing:
            report_lines.append("- Fix ball detection — check BallDetectTrack Hough params")
        if "jersey_ocr" in failing:
            report_lines.append("- Jersey OCR low — Phase 025 Part B (CLAHE+2x) may not be active")
        if "players_per_frame" in failing:
            report_lines.append("- Low player count — check YOLOv8 conf threshold (broadcast_mode=True?)")
        if "possession_quality" in failing:
            report_lines.append("- Possessions are noise — EventDetector needs real game to calibrate")

    vault_path = os.path.join(_VAULT_DIR, f"eval_{label}.md")
    with open(vault_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"\n[pipeline] Eval saved: {eval_path}")
    print(f"[pipeline] Vault log:  {vault_path}")
    return vault_path


# ── CLI ───────────────────────────────────────────────────────────────────────

def print_results(eval_result: dict) -> None:
    """Print a clean summary table to stdout."""
    m = eval_result.get("metrics", {})
    g = eval_result.get("grades", {})

    icons = {"PASS": "✓", "FAIL": "✗", "?": "?"}
    print("\n" + "="*55)
    print(f"  TRACKER EVALUATION — Game {eval_result.get('game_id','?')}")
    print(f"  Overall grade: {eval_result.get('overall_grade')}  "
          f"({eval_result.get('pass_rate')} checks pass)")
    print("="*55)
    rows = [
        ("Players/frame",      m.get("players_per_frame_mean"),  g.get("players_per_frame"), "≥8.0"),
        ("Ball detection",     m.get("ball_detection_rate"),      g.get("ball_detection"),    "≥50%"),
        ("Jersey OCR rate",    m.get("jersey_ocr_rate"),          g.get("jersey_ocr"),        "≥30%"),
        ("Valid positions",    m.get("valid_position_rate"),      g.get("valid_positions"),   "≥95%"),
        ("Possession dur(s)",  m.get("possession_dur_mean"),      g.get("possession_quality"),"≥4.0s"),
        ("Shot recall",        m.get("shot_recall"),              g.get("shot_recall"),       "≥40%"),
    ]
    for label, val, grade, target in rows:
        icon = icons.get(grade or "?", "?")
        val_str = f"{val:.3f}" if isinstance(val, float) else str(val or "N/A")
        print(f"  [{icon}] {label:<22} {val_str:<10} target {target}")
    print("="*55)

    issues = eval_result.get("issues", [])
    if issues:
        print(f"\n  Issues ({len(issues)}):")
        for issue in issues[:8]:
            print(f"    - {issue}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(
        description="NBA AI — full game download → track → evaluate pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--team",     help="Team shortname (gsw, bos, lal, okc, den, mia)")
    ap.add_argument("--url",      help="YouTube URL or ytsearch: query")
    ap.add_argument("--video",    help="Path to already-downloaded local .mp4")
    ap.add_argument("--game-id",  dest="game_id", help="NBA Stats game ID (e.g. 0022401001)")
    ap.add_argument("--season",   default="2024-25", help="NBA season (default: 2024-25)")
    ap.add_argument("--frames",   type=int, default=None,
                    help="Limit processing to N frames (for quick tests)")
    ap.add_argument("--eval-only", action="store_true",
                    help="Skip download + tracking, just re-evaluate existing CSVs")
    ap.add_argument("--list-clips", action="store_true",
                    help="List available curated clip options and exit")
    ap.add_argument("--show", action="store_true",
                    help="Show live preview window (default: headless/no window)")
    args = ap.parse_args()

    if args.list_clips:
        from src.data.video_fetcher import CURATED_CLIPS
        print("\nAvailable curated clips (use with --team):\n")
        for label, query in CURATED_CLIPS.items():
            print(f"  {label:<35} {query[:60]}")
        print()
        return

    pipeline_summary: dict = {}

    if not args.eval_only:
        # Step 1: Download
        video_path = download_game(
            team=args.team, url=args.url, video=args.video
        )

        # Step 2: Match game ID
        game_id = resolve_game_id(video_path, args.game_id)

        # Step 3: Track
        pipeline_summary = run_tracking_pipeline(
            video_path=video_path,
            game_id=game_id,
            frames=args.frames,
            season=args.season,
        )
    else:
        game_id = args.game_id
        video_path = args.video or "unknown"
        print("[pipeline] --eval-only: skipping download + tracking")

    # Step 4: Evaluate
    eval_result = evaluate_quality(game_id)

    # Step 5: Save + log
    vault_path = save_and_log(pipeline_summary, eval_result, game_id, video_path)

    # Step 6: Print summary
    print_results(eval_result)
    print(f"Full report: {vault_path}")


if __name__ == "__main__":
    main()
