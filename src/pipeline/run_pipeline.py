"""
run_pipeline.py — Full game processing orchestrator.

Wires together:
  tracking_pipeline  →  feature_pipeline  →  analytics  →  summary JSON

Functions
---------
    run_game(video_path, game_id, season) -> dict

CLI
---
    python src/pipeline/run_pipeline.py \\
        --video data/videos/game.mp4 \\
        --game-id 0022401001 \\
        --season 2024-25

Output
------
    data/game_results/{game_id}_summary.json
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_DATA_DIR    = os.path.join(PROJECT_DIR, "data")
_RESULTS_DIR = os.path.join(_DATA_DIR, "game_results")


# ── run_game ──────────────────────────────────────────────────────────────────

def run_game(
    video_path: str,
    game_id: str,
    season: str = "2024-25",
    period: int = 1,
    clip_start_sec: float = 0.0,
    fps: float = 30.0,
    max_frames: int = None,
) -> dict:
    """
    End-to-end game processing: tracking → features → analytics → summary.

    Pipeline steps
    ~~~~~~~~~~~~~~
    1. **Tracking**     — ``tracking_pipeline.run_tracking`` runs
                          ``unified_pipeline.py`` in a subprocess and writes
                          ``data/tracking_data.csv``.
    2. **Features**     — ``feature_pipeline.run_features`` adds 60+ engineered
                          columns and writes ``data/features.csv``.
    3. **NBA Enrich**   — ``feature_pipeline.enrich_with_nba`` labels shots and
                          possessions from the NBA Stats API.
    4. **Shot quality** — ``src.analytics.shot_quality.run`` scores each shot
                          and writes ``data/shot_quality.csv``.
    5. **Defense**      — ``src.analytics.defense_pressure.run`` scores
                          per-frame pressure and writes
                          ``data/defense_pressure.csv``.
    6. **Momentum**     — ``src.analytics.momentum.run`` scores team momentum
                          per frame and writes ``data/momentum.csv``.
    7. **Summary**      — Aggregates key metrics into a JSON summary saved to
                          ``data/game_results/{game_id}_summary.json``.

    Args:
        video_path:     Path to the .mp4 clip.
        game_id:        NBA game ID string (e.g. '0022401001').
        season:         NBA season string (e.g. '2024-25').
        period:         Game quarter the clip covers (1–4, 5 for OT).
        clip_start_sec: Seconds into the period when the clip starts.
        fps:            Frames-per-second of the source video.

    Returns:
        Summary dict with keys:
            game_id, season, video_path, status,
            tracking   — {rows, frames, players, status},
            features   — {rows, cols},
            shot_quality  — {shots_scored, avg_quality},
            defense       — {frames_scored, avg_pressure},
            momentum      — {frames_scored},
            output_path   — path to the summary JSON,
            timestamp     — ISO-8601 UTC string.

    On any fatal error the summary ``status`` is ``"error"`` with an
    ``error`` key containing the message; prior successful steps are still
    reported.
    """
    os.makedirs(_RESULTS_DIR, exist_ok=True)

    summary: dict = {
        "game_id":    game_id,
        "season":     season,
        "video_path": video_path,
        "status":     "error",
        "error":      None,
        "tracking":   {},
        "features":   {},
        "shot_quality":  {},
        "defense":       {},
        "momentum":      {},
        "output_path":   os.path.join(_RESULTS_DIR, f"{game_id}_summary.json"),
        "timestamp":  datetime.now(timezone.utc).isoformat(),
    }

    # ── Step 1: Tracking ──────────────────────────────────────────────────────
    try:
        from src.pipeline.tracking_pipeline import run_tracking

        tracking_csv = os.path.join(_DATA_DIR, "tracking_data.csv")
        tracking_entry = run_tracking(video_path, game_id, tracking_csv, max_frames=max_frames)
        summary["tracking"] = {
            "rows":    tracking_entry.get("rows", 0),
            "frames":  tracking_entry.get("frames", 0),
            "players": tracking_entry.get("players", 0),
            "status":  tracking_entry.get("status", "error"),
        }
        if tracking_entry.get("status") != "ok":
            summary["error"] = f"Tracking failed: {tracking_entry.get('error')}"
            _save_summary(summary)
            return summary
    except Exception as exc:
        summary["error"] = f"Tracking step exception: {exc}"
        _save_summary(summary)
        return summary

    # ── Step 2: Feature engineering ───────────────────────────────────────────
    features_df = None
    try:
        from src.pipeline.feature_pipeline import run_features

        features_csv = os.path.join(_DATA_DIR, "features.csv")
        features_df  = run_features(tracking_csv, features_csv)
        summary["features"] = {
            "rows": len(features_df),
            "cols": len(features_df.columns),
        }
    except Exception as exc:
        print(f"[run_pipeline] feature step failed (non-fatal): {exc}")
        summary["features"] = {"rows": 0, "cols": 0}

    # ── Step 3: NBA API enrichment ────────────────────────────────────────────
    if features_df is not None and not features_df.empty:
        try:
            from src.pipeline.feature_pipeline import enrich_with_nba

            features_df = enrich_with_nba(
                features_df, game_id, season, period, clip_start_sec, fps
            )
        except Exception as exc:
            print(f"[run_pipeline] NBA enrich step failed (non-fatal): {exc}")

    # ── Step 4: Shot quality ──────────────────────────────────────────────────
    try:
        from src.analytics.shot_quality import run as sq_run

        sq_df = sq_run()
        summary["shot_quality"] = {
            "shots_scored": len(sq_df),
            "avg_quality":  round(float(sq_df["shot_quality"].mean()), 3)
                            if "shot_quality" in sq_df.columns and len(sq_df) else 0.0,
        }
    except Exception as exc:
        print(f"[run_pipeline] shot_quality step failed (non-fatal): {exc}")
        summary["shot_quality"] = {"shots_scored": 0, "avg_quality": 0.0}

    # ── Step 5: Defense pressure ──────────────────────────────────────────────
    try:
        from src.analytics.defense_pressure import run as dp_run

        dp_df = dp_run()
        summary["defense"] = {
            "frames_scored": len(dp_df),
            "avg_pressure":  round(float(dp_df["pressure"].mean()), 3)
                             if "pressure" in dp_df.columns and len(dp_df) else 0.0,
        }
    except Exception as exc:
        print(f"[run_pipeline] defense_pressure step failed (non-fatal): {exc}")
        summary["defense"] = {"frames_scored": 0, "avg_pressure": 0.0}

    # ── Step 6: Momentum ──────────────────────────────────────────────────────
    try:
        from src.analytics.momentum import run as mom_run

        mom_df = mom_run()
        summary["momentum"] = {"frames_scored": len(mom_df)}
    except Exception as exc:
        print(f"[run_pipeline] momentum step failed (non-fatal): {exc}")
        summary["momentum"] = {"frames_scored": 0}

    # ── Finalize ──────────────────────────────────────────────────────────────
    summary["status"] = "ok"
    _save_summary(summary)

    print(
        f"[run_pipeline] {game_id} done — "
        f"tracking={summary['tracking'].get('rows', 0)} rows, "
        f"features={summary['features'].get('cols', 0)} cols, "
        f"shots={summary['shot_quality'].get('shots_scored', 0)}"
    )
    return summary


# ── Helpers ────────────────────────────────────────────────────────────────────

def _save_summary(summary: dict) -> None:
    """Write summary dict to disk."""
    os.makedirs(_RESULTS_DIR, exist_ok=True)
    path = summary.get("output_path",
                        os.path.join(_RESULTS_DIR,
                                     f"{summary['game_id']}_summary.json"))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="NBA AI full game pipeline")
    ap.add_argument("--video",           required=True, help="Path to video clip")
    ap.add_argument("--game-id",         required=True, help="NBA game ID")
    ap.add_argument("--season",          default="2024-25")
    ap.add_argument("--period",          type=int,   default=1)
    ap.add_argument("--clip-start-sec",  type=float, default=0.0,
                    help="Seconds into the quarter when clip starts")
    ap.add_argument("--fps",             type=float, default=30.0)
    ap.add_argument("--max-frames",      type=int,   default=None,
                    help="Hard cap on frames processed (e.g. 300 for quick test)")
    args = ap.parse_args()

    result = run_game(
        video_path     = args.video,
        game_id        = args.game_id,
        season         = args.season,
        period         = args.period,
        clip_start_sec = args.clip_start_sec,
        fps            = args.fps,
        max_frames     = args.max_frames,
    )
    print(json.dumps(
        {k: v for k, v in result.items() if k not in ("features",)},
        indent=2
    ))
