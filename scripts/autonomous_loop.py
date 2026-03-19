"""
autonomous_loop.py — Self-improving NBA tracker loop.

Each run:
  1. Picks the next game clip from a diverse rotation of NBA teams/matchups
  2. Runs the full tracking pipeline on the clip
  3. Compares tracker metrics to real NBA stats targets
  4. Scores accuracy 0-100 and ranks issues by impact
  5. Writes data/loop_report.json — consumed by Claude to apply code fixes
  6. Appends run summary to vault/Improvements/Tracker Improvements Log.md

Deliberately rotates through different teams, jersey color combos, and arena
lighting conditions so the tracker generalises — not just one team's colours.

Usage:
    conda activate basketball_ai
    python autonomous_loop.py [--frames N] [--force-rerun] [--next-clip]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

DATA_DIR    = os.path.join(PROJECT_DIR, "data")
VAULT_DIR   = os.path.join(PROJECT_DIR, "vault")
STATE_PATH  = os.path.join(DATA_DIR, "loop_state.json")
REPORT_PATH = os.path.join(DATA_DIR, "loop_report.json")
LOG_PATH    = os.path.join(VAULT_DIR, "Improvements", "Tracker Improvements Log.md")

CONDA_ENV   = "basketball_ai"

# ── Target metrics ────────────────────────────────────────────────────────────
# What "perfect" looks like. Score starts at 100, deductions applied per gap.
TARGETS = {
    "avg_players":        9.0,   # ≥9 players per frame (10 on court, minus occlusions)
    "team_balance_min":   0.44,  # team 0 share between 44-56%
    "team_balance_max":   0.56,
    "ball_detection_pct": 0.65,  # ball found in ≥65% of frames
    "id_switch_rate":     0.005, # ≤0.5% of frames trigger an ID switch
    "shots_per_minute":   1.5,   # NBA avg ~87 FGA / 48 min ≈ 1.8/min
    "unique_players_min": 8,     # at least 8 distinct players in any clip
    "unique_players_max": 16,    # >16 = too many spurious IDs
    "passing_score":      90.0,  # loop declares victory above this
}

# ── Diverse NBA clip rotation ─────────────────────────────────────────────────
# Covers a wide range of jersey colours, arena lighting, and team styles so
# the tracker must generalise — not overfit to one team's colour palette.
#
# Format: (label, yt-dlp search query)
# Labels are used as filenames — keep them filesystem-safe and unique.
#
# Jersey colour notes per matchup:
#   white vs dark    — easiest for HSV classifier
#   similar colours  — hardest (both teams dark, both light)
#   coloured courts  — challenges homography + ball detection
NBA_CLIPS = [
    # White vs dark  ──────────────────────────────────────────────────────────
    ("gsw_lakers_2025",      "ytsearch:Warriors Lakers 2025 NBA broadcast highlights full game"),
    ("bos_mia_2025",         "ytsearch:Celtics Heat 2025 NBA broadcast game highlights"),
    ("mil_chi_2025",         "ytsearch:Bucks Bulls 2025 NBA broadcast full game highlights"),
    ("phi_tor_2025",         "ytsearch:76ers Raptors 2025 NBA broadcast game highlights"),
    # Coloured jersey matchups  ───────────────────────────────────────────────
    ("den_phx_2025",         "ytsearch:Nuggets Suns 2025 NBA broadcast highlights basketball"),
    ("okc_dal_2025",         "ytsearch:Thunder Mavericks 2025 NBA broadcast game highlights"),
    ("lal_sas_2025",         "ytsearch:Lakers Spurs 2025 NBA broadcast full game highlights"),
    # Dark vs dark  ───────────────────────────────────────────────────────────
    ("mia_bkn_2025",         "ytsearch:Heat Nets 2025 NBA broadcast game highlights"),
    ("mem_nop_2025",         "ytsearch:Grizzlies Pelicans 2025 NBA broadcast highlights"),
    # High-pace / high-shot-rate  ─────────────────────────────────────────────
    ("sac_por_2025",         "ytsearch:Kings Trail Blazers 2025 NBA broadcast full game"),
    ("atl_ind_2025",         "ytsearch:Hawks Pacers 2025 NBA broadcast full game highlights"),
    # Playoffs intensity  ──────────────────────────────────────────────────────
    ("bos_mia_playoffs",     "ytsearch:Celtics Heat 2024 NBA playoffs broadcast game highlights"),
    ("den_gsw_playoffs",     "ytsearch:Nuggets Warriors 2024 NBA playoffs broadcast highlights"),
    # Original Cavs clips (kept for continuity)  ──────────────────────────────
    ("cavs_broadcast_2025",  "ytsearch:Cleveland Cavaliers 2025 NBA broadcast full game highlights"),
    ("cavs_vs_celtics_2025", "ytsearch:Cavaliers Celtics 2025 NBA full game broadcast highlights"),
]


# ── State helpers ─────────────────────────────────────────────────────────────

def load_state() -> dict:
    """Load persistent loop state from disk."""
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {
        "runs":          [],
        "current_video": None,
        "best_score":    0.0,
        "fixes_applied": [],
        "clip_index":    0,
    }


def save_state(state: dict):
    """Persist loop state to disk."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


# ── Clip download ─────────────────────────────────────────────────────────────

def _find_video(stem: str) -> Optional[str]:
    """Return path to any existing video matching stem."""
    videos_dir = os.path.join(DATA_DIR, "videos")
    if not os.path.isdir(videos_dir):
        return None
    for ext in (".mp4", ".webm", ".mkv", ".mov"):
        p = os.path.join(videos_dir, f"{stem}{ext}")
        if os.path.exists(p):
            return p
    return None


def download_game_clip(state: dict) -> Optional[str]:
    """
    Download the next NBA clip from the rotation (or return cached path).

    Rotates through NBA_CLIPS covering diverse teams and jersey combos.
    Advances clip_index on failure so next run tries a different matchup.
    """
    idx = state.get("clip_index", 0) % len(NBA_CLIPS)
    label, query = NBA_CLIPS[idx]

    existing = _find_video(label)
    if existing:
        print(f"[Loop] Using cached clip: {existing}")
        return existing

    print(f"[Loop] Downloading clip #{idx}/{len(NBA_CLIPS)}: {label}")
    print(f"       Query: {query}")

    try:
        from src.data.video_fetcher import download_clip
        path = download_clip(query, label=label)
        print(f"[Loop] Downloaded: {path}")
        return path
    except Exception as e:
        print(f"[Loop] Download failed: {e}")
        # Advance to next matchup so next run tries a different team combo
        state["clip_index"] = (idx + 1) % len(NBA_CLIPS)
        save_state(state)

    # YouTube unavailable — fall back to any local video we can find
    local_fallbacks = [
        os.path.join(PROJECT_DIR, "resources", "Short4Mosaicing.mp4"),
        os.path.join(PROJECT_DIR, "resources", "Short4Mosaicing.avi"),
    ]
    # Also scan data/videos/ for any previously downloaded file
    vdir = os.path.join(DATA_DIR, "videos")
    if os.path.isdir(vdir):
        for f in os.listdir(vdir):
            if f.endswith((".mp4", ".webm", ".mkv", ".mov")):
                local_fallbacks.append(os.path.join(vdir, f))

    for fb in local_fallbacks:
        if os.path.exists(fb):
            print(f"[Loop] Falling back to local video: {fb}")
            return fb

    return None


# ── Pipeline runner ───────────────────────────────────────────────────────────

def _tracking_data_is_fresh(max_age_secs: int = 3600, video_path: str = "") -> bool:
    """Return True if tracking_data.csv was written within max_age_secs for the current video.

    Data is considered stale if the video has changed since the last pipeline run,
    even if the file is recent — each clip needs its own fresh tracking run.
    """
    td = os.path.join(DATA_DIR, "tracking_data.csv")
    if not os.path.exists(td):
        return False
    age = time.time() - os.path.getmtime(td)
    if age >= max_age_secs:
        return False
    # Also stale if the video differs from what generated the current data.
    if video_path:
        state = load_state()
        last_video = state.get("last_pipeline_video", "")
        if last_video and os.path.basename(last_video) != os.path.basename(video_path):
            print(f"[Loop] Video changed ({os.path.basename(last_video)} → {os.path.basename(video_path)}) — data is stale")
            return False
    return True


def run_pipeline(video_path: str, max_frames: int = 3000, force: bool = False) -> dict:
    """
    Run the full tracking pipeline via run_clip.py.

    Skips if tracking_data.csv was written in the last hour (unless force=True).

    Args:
        video_path:  Path to the video clip.
        max_frames:  Cap on frames to process (3000 ≈ 100s at 30fps).
        force:       Re-run even if fresh data exists.

    Returns:
        dict with keys: elapsed, stdout, error (if failed), skipped (if skipped).
    """
    if not force and _tracking_data_is_fresh(video_path=video_path):
        print("[Loop] tracking_data.csv is fresh — skipping pipeline re-run")
        return {"skipped": True, "elapsed": 0}

    print(f"[Loop] Running pipeline: {os.path.basename(video_path)} ({max_frames} frames)")
    cmd = [
        "conda", "run", "--no-capture-output",
        "-n", CONDA_ENV,
        "python", os.path.join(PROJECT_DIR, "run_clip.py"),
        "--video",  video_path,
        "--no-show",
        "--frames", str(max_frames),
    ]

    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", cwd=PROJECT_DIR, env=env)
    elapsed = time.time() - t0

    if result.returncode != 0:
        stderr_tail = result.stderr[-600:] if result.stderr else ""
        print(f"[Loop] Pipeline failed (code {result.returncode}):\n{stderr_tail}")
        return {"error": stderr_tail, "elapsed": elapsed}

    tail = result.stdout[-400:] if result.stdout else ""
    print(f"[Loop] Pipeline done in {elapsed:.1f}s\n{tail}")
    # Record which video generated this tracking data so freshness check works per-clip
    state = load_state()
    state["last_pipeline_video"] = video_path
    save_state(state)
    return {"elapsed": elapsed, "stdout": result.stdout}


# ── Metrics computation ───────────────────────────────────────────────────────

def compute_metrics() -> dict:
    """
    Read pipeline CSV outputs and compute tracker accuracy metrics.

    Returns a flat dict of numeric/boolean metrics.
    """
    try:
        import pandas as pd
        import numpy as np
    except ImportError:
        return {"error": "pandas/numpy not available"}

    metrics: dict = {}

    # ── tracking_data.csv ────────────────────────────────────────────────────
    td_path = os.path.join(DATA_DIR, "tracking_data.csv")
    if os.path.exists(td_path):
        try:
            df = pd.read_csv(td_path)
            metrics["tracking_data_rows"] = len(df)

            if "frame" in df.columns:
                metrics["total_frames"] = int(df["frame"].nunique())

            # Exclude referees for player-count metrics.
            # Handles both column names used across pipeline versions:
            #   "team_id" (int: 0,1,2)  — ref = 2
            #   "team"    (str)         — ref = 'referee'
            if "team_id" in df.columns:
                players_df = df[df["team_id"] != 2]
            elif "team" in df.columns:
                players_df = df[~df["team"].astype(str).str.lower().str.contains("ref")]
            else:
                players_df = df

            if "frame" in players_df.columns and "player_id" in players_df.columns:
                per_frame = players_df.groupby("frame")["player_id"].nunique()
                metrics["avg_players"]    = float(per_frame.mean())
                metrics["max_players"]    = int(per_frame.max())
                metrics["min_players"]    = int(per_frame.min())
                metrics["pct_frames_10+"] = float((per_frame >= 10).mean())

            # Team balance: fraction of unique *players* on team 0 (not rows).
            # Row counts are biased by screen time; player counts are fair.
            team_col = "team_id" if "team_id" in df.columns else ("team" if "team" in df.columns else None)
            if team_col and "player_id" in players_df.columns:
                player_teams = (players_df.groupby("player_id")[team_col]
                                .agg(lambda s: s.mode().iloc[0]))  # majority team per player
                if team_col == "team_id":
                    n_t0 = (player_teams == 0).sum()
                    n_total = len(player_teams)
                else:
                    teams_str = player_teams.astype(str).str.lower()
                    t_counts  = teams_str.value_counts()
                    if len(t_counts) >= 2:
                        # Assign the two most common non-ref teams as team0/team1
                        team0_label = t_counts.index[0]
                        n_t0    = (teams_str == team0_label).sum()
                        n_total = len(player_teams)
                    else:
                        n_t0 = n_total = 0
                if n_total > 0:
                    metrics["team_balance"]  = float(n_t0 / n_total)
                    metrics["team0_players"] = int(n_t0)
                    metrics["team1_players"] = int(n_total - n_t0)

            # Ball possession
            if "ball_possession" in df.columns and "frame" in df.columns:
                poss_frames = df[df["ball_possession"].astype(str).str.lower() == "true"]["frame"].nunique()
                total_f = metrics.get("total_frames", 1)
                metrics["possession_pct"] = float(poss_frames / max(1, total_f))

            # Shot events
            if "event" in df.columns and "frame" in df.columns:
                shot_frames = df[df["event"].astype(str).str.lower() == "shot"]["frame"].nunique()
                metrics["shot_events"] = int(shot_frames)
                total_f = metrics.get("total_frames", 1)
                fps_est  = 30.0
                dur_min  = total_f / fps_est / 60.0
                metrics["shots_per_minute"] = float(shot_frames / max(0.01, dur_min))

            # Velocity sanity check (column may be 'speed' or 'velocity')
            vel_col = "speed" if "speed" in df.columns else ("velocity" if "velocity" in df.columns else None)
            if vel_col:
                valid_vel = pd.to_numeric(df[vel_col], errors="coerce").dropna()
                metrics["avg_velocity"] = float(valid_vel.mean()) if len(valid_vel) > 0 else 0.0

        except Exception as e:
            metrics["tracking_data_error"] = str(e)
    else:
        metrics["tracking_data_missing"] = True

    # ── ball_tracking.csv ────────────────────────────────────────────────────
    bt_path = os.path.join(DATA_DIR, "ball_tracking.csv")
    if os.path.exists(bt_path):
        try:
            bt = pd.read_csv(bt_path)
            # Find a boolean 'detected' column or infer from x/y
            det_col = next((c for c in bt.columns if "detect" in c.lower()), None)
            if det_col:
                metrics["ball_detection_pct"] = float(
                    pd.to_numeric(bt[det_col], errors="coerce").fillna(0).astype(bool).mean()
                )
            else:
                x_col = next((c for c in bt.columns if c.lower() in ("x", "ball_x", "loc_x")), None)
                if x_col:
                    metrics["ball_detection_pct"] = float(bt[x_col].notna().mean())
        except Exception as e:
            metrics["ball_tracking_error"] = str(e)

    # ── shot_log.csv ─────────────────────────────────────────────────────────
    sl_path = os.path.join(DATA_DIR, "shot_log.csv")
    if os.path.exists(sl_path):
        try:
            sl = pd.read_csv(sl_path)
            metrics["shot_log_count"] = len(sl)
        except Exception:
            pass

    # ── player_clip_stats.csv ────────────────────────────────────────────────
    ps_path = os.path.join(DATA_DIR, "player_clip_stats.csv")
    if os.path.exists(ps_path):
        try:
            ps = pd.read_csv(ps_path)
            metrics["unique_players_tracked"] = len(ps)
        except Exception:
            pass

    return metrics


# ── Real stats reference ──────────────────────────────────────────────────────

def fetch_real_nba_stats(state: dict) -> dict:
    """
    Return real NBA game stats for the current clip as the comparison reference.

    Uses game_matcher to fetch actual box score + shot totals for the specific
    matchup in the current clip. Falls back to league averages if API fails.
    """
    idx   = state.get("clip_index", 0) % len(NBA_CLIPS)
    label, _ = NBA_CLIPS[idx]

    try:
        from src.data.game_matcher import get_comparison_stats
        stats = get_comparison_stats(label)
        return {
            "clip_label":        label,
            "team_hint":         stats.get("team1", label.split("_")[0].upper()),
            "season":            stats.get("season", "2024-25"),
            "season_type":       stats.get("season_type", "Regular Season"),
            "game_id":           stats.get("game_id"),
            "total_fga":         stats.get("total_fga", 177),
            "total_players":     stats.get("total_players", 10),
            "avg_fga_per_game":  stats.get("total_fga", 177) / 2,   # per team
            "avg_possessions":   100.5,
            "avg_shots_per_min": stats.get("shots_per_minute", 1.84),
            "expected_players":  stats.get("total_players", 10),
            "home_score":        stats.get("home_score", 0),
            "away_score":        stats.get("away_score", 0),
            "data_source":       stats.get("data_source", "league_average"),
            "note":              (
                f"Real game data via nba_api (game {stats.get('game_id')})"
                if stats.get("game_id") else
                "NBA 2024-25 league averages (game not found)"
            ),
        }
    except Exception as e:
        # Graceful fallback to league averages
        print(f"[Loop] game_matcher failed ({e}) — using league averages")
        team_abbrev = label.split("_")[0].upper()
        return {
            "clip_label":        label,
            "team_hint":         team_abbrev,
            "season":            "2024-25",
            "season_type":       "Regular Season",
            "game_id":           None,
            "total_fga":         177,
            "total_players":     10,
            "avg_fga_per_game":  88.5,
            "avg_possessions":   100.5,
            "avg_shots_per_min": 1.84,
            "expected_players":  10,
            "home_score":        0,
            "away_score":        0,
            "data_source":       "league_average",
            "note":              "NBA 2024-25 league averages (fallback)",
        }


# ── Scoring ───────────────────────────────────────────────────────────────────

def _load_current_config() -> dict:
    """Load tracker_params.json, falling back to empty dict."""
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "tracker_params.json")
    try:
        with open(cfg_path) as f:
            return json.load(f)
    except Exception:
        return {}


def _suggest_player_count_fix(current_cfg: dict) -> str:
    """Return a targeted fix suggestion based on the current tracker config."""
    conf  = current_cfg.get("conf_threshold", 0.5)
    fill  = current_cfg.get("kalman_fill_window", 5)
    top   = current_cfg.get("topcut", 60)
    hints = []
    if conf > 0.25:
        hints.append(f"Lower conf_threshold: {conf} → {round(conf - 0.05, 2)} in config/tracker_params.json")
    if fill < 10:
        hints.append(f"Extend kalman_fill_window: {fill} → {fill + 2} in config/tracker_params.json")
    if top < 120:
        hints.append(f"Try topcut={top + 60} to crop more scoreboard if broadcast has wide top bar")
    if not hints:
        hints.append("Config already at low-conf / high-fill limits. Clip may contain non-court frames (replays, timeouts). Consider pre-filtering frames with low court-line coverage.")
    return " | ".join(hints)


def score_metrics(metrics: dict, real_stats: dict) -> tuple[float, list]:
    """
    Score tracker accuracy 0-100 and rank all detected issues by impact.

    Returns:
        (score, issues_list) where issues are sorted highest-impact first.
    """
    current_cfg = _load_current_config()
    issues = []
    score  = 100.0

    # ── 1. Player count (30 pts) ─────────────────────────────────────────────
    avg_p  = metrics.get("avg_players", 0.0)
    target = TARGETS["avg_players"]
    if avg_p < 6.0:
        penalty = min(30.0, (target - avg_p) * 10)
        score  -= penalty
        issues.append({
            "rank":           1,
            "metric":         "avg_players",
            "actual":         round(avg_p, 2),
            "target":         f"≥{target}",
            "penalty":        round(penalty, 1),
            "impact":         "HIGH",
            "description":    (
                f"Only {avg_p:.1f} avg players/frame detected (target ≥{target}). "
                "YOLO is missing detections — confidence threshold may be too high "
                "or Kalman fill window too short."
            ),
            "files_to_fix":   [
                "src/tracking/advanced_tracker.py",
                "src/tracking/player_detection.py",
                "src/tracking/tracker_config.py",
            ],
            "suggested_fix":  _suggest_player_count_fix(current_cfg),
        })
    elif avg_p < 8.0:
        penalty = min(15.0, (target - avg_p) * 5)
        score  -= penalty
        issues.append({
            "rank":           1,
            "metric":         "avg_players",
            "actual":         round(avg_p, 2),
            "target":         f"≥{target}",
            "penalty":        round(penalty, 1),
            "impact":         "MEDIUM",
            "description":    f"Player count {avg_p:.1f} is below target {target}.",
            "files_to_fix":   ["src/tracking/advanced_tracker.py"],
            "suggested_fix":  _suggest_player_count_fix(current_cfg),
        })

    # ── 2. Team balance (20 pts) ─────────────────────────────────────────────
    balance = metrics.get("team_balance", 0.5)
    lo, hi  = TARGETS["team_balance_min"], TARGETS["team_balance_max"]
    if not (lo <= balance <= hi):
        penalty = min(20.0, abs(balance - 0.5) * 100)
        score  -= penalty
        bias    = "team 0" if balance > 0.5 else "team 1"
        issues.append({
            "rank":           2,
            "metric":         "team_balance",
            "actual":         round(balance, 3),
            "target":         f"{lo:.2f}-{hi:.2f}",
            "penalty":        round(penalty, 1),
            "impact":         "HIGH" if abs(balance - 0.5) > 0.12 else "MEDIUM",
            "description":    (
                f"Team 0 holds {balance*100:.0f}% of player detections (expect 44-56%). "
                f"HSV classifier is over-assigning to {bias}. "
                "Cavs jerseys (wine/gold) may be misclassified against opponent colors."
            ),
            "files_to_fix":   [
                "src/tracking/tracker_config.py",
                "src/tracking/player_detection.py",
                "src/tracking/advanced_tracker.py",
            ],
            "suggested_fix":  (
                "Check tracker_config.py HSV ranges for Cavs wine (#860038) and gold (#FDBB30). "
                "If wine is being flagged as 'white' (team 1), tighten the white S upper bound "
                "or add an explicit wine range. Use adaptive_colors() as a sanity check."
            ),
        })

    # ── 3. Ball detection (20 pts) ───────────────────────────────────────────
    ball_pct = metrics.get("ball_detection_pct", None)
    if ball_pct is not None:
        tgt = TARGETS["ball_detection_pct"]
        if ball_pct < tgt:
            penalty = min(20.0, (tgt - ball_pct) * 50)
            score  -= penalty
            issues.append({
                "rank":           3,
                "metric":         "ball_detection_pct",
                "actual":         round(ball_pct, 3),
                "target":         f"≥{tgt}",
                "penalty":        round(penalty, 1),
                "impact":         "HIGH" if ball_pct < 0.40 else "MEDIUM",
                "description":    (
                    f"Ball detected in {ball_pct*100:.0f}% of frames (target ≥{tgt*100:.0f}%). "
                    "Hough circles are failing on fast passes or poor lighting. "
                    "Optical flow fallback may be expiring too quickly."
                ),
                "files_to_fix":   ["src/tracking/ball_detect_track.py"],
                "suggested_fix":  (
                    "In ball_detect_track.py: extend optical-flow fallback from 8 → 14 frames "
                    "(_MAX_FLOW_FRAMES). Also try loosening Hough param2 from current value by 5."
                ),
            })
    else:
        # ball_tracking.csv missing entirely
        score -= 10
        issues.append({
            "rank":           3,
            "metric":         "ball_detection_pct",
            "actual":         "N/A (ball_tracking.csv missing)",
            "target":         f"≥{TARGETS['ball_detection_pct']}",
            "penalty":        10.0,
            "impact":         "MEDIUM",
            "description":    "ball_tracking.csv was not produced — ball tracker may have crashed.",
            "files_to_fix":   ["src/tracking/ball_detect_track.py", "src/pipeline/unified_pipeline.py"],
            "suggested_fix":  "Check BallDetectTrack initialisation in unified_pipeline.py.",
        })

    # ── 4. Shot events (15 pts) ──────────────────────────────────────────────
    shots_pm = metrics.get("shots_per_minute", None)
    tgt_pm   = real_stats.get("avg_shots_per_min", 1.84)
    if shots_pm is not None and shots_pm < 0.5:
        penalty = 15.0
        score  -= penalty
        issues.append({
            "rank":           4,
            "metric":         "shots_per_minute",
            "actual":         round(shots_pm, 3),
            "target":         f"~{tgt_pm:.1f} (NBA avg)",
            "penalty":        penalty,
            "impact":         "HIGH",
            "description":    (
                f"Only {shots_pm:.2f} shots/min detected (NBA avg: {tgt_pm:.1f}/min). "
                "EventDetector shot trigger likely too strict or ball tracking failing."
            ),
            "files_to_fix":   [
                "src/tracking/event_detector.py",
                "src/tracking/ball_detect_track.py",
            ],
            "suggested_fix":  (
                "In event_detector.py: check shot trigger distance to basket — "
                "if SHOT_DIST_THRESHOLD is too small, real shots are missed. "
                "Also confirm ball_possession flags are being set correctly."
            ),
        })

    # ── 5. Unique player IDs (15 pts) ────────────────────────────────────────
    unique = metrics.get("unique_players_tracked", None)
    if unique is not None:
        if unique > TARGETS["unique_players_max"]:
            penalty = min(15.0, (unique - TARGETS["unique_players_max"]) * 1.5)
            score  -= penalty
            issues.append({
                "rank":           5,
                "metric":         "unique_players_tracked",
                "actual":         unique,
                "target":         f"{TARGETS['unique_players_min']}-{TARGETS['unique_players_max']}",
                "penalty":        round(penalty, 1),
                "impact":         "MEDIUM",
                "description":    (
                    f"{unique} unique player IDs created in clip (target ≤{TARGETS['unique_players_max']}). "
                    "Too many ID switches — gallery TTL or appearance threshold needs tuning."
                ),
                "files_to_fix":   ["src/tracking/advanced_tracker.py"],
                "suggested_fix":  (
                    "Reduce GALLERY_TTL from 300 → 200 frames or tighten REID_THRESHOLD from 0.45 → 0.40."
                ),
            })
        elif unique < TARGETS["unique_players_min"]:
            penalty = min(15.0, (TARGETS["unique_players_min"] - unique) * 3.0)
            score  -= penalty
            issues.append({
                "rank":           5,
                "metric":         "unique_players_tracked",
                "actual":         unique,
                "target":         f"≥{TARGETS['unique_players_min']}",
                "penalty":        round(penalty, 1),
                "impact":         "HIGH",
                "description":    (
                    f"Only {unique} unique players tracked in clip — players being merged. "
                    "Re-ID threshold may be too loose."
                ),
                "files_to_fix":   ["src/tracking/advanced_tracker.py"],
                "suggested_fix":  "Increase REID_THRESHOLD from 0.45 → 0.55 to make re-ID stricter.",
            })

    score = max(0.0, min(100.0, score))

    # Sort by penalty descending
    issues.sort(key=lambda x: x.get("penalty", 0), reverse=True)

    return round(score, 1), issues


# ── Report writer ─────────────────────────────────────────────────────────────

def generate_report(
    video_path:  str,
    metrics:     dict,
    real_stats:  dict,
    score:       float,
    issues:      list,
    state:       dict,
    run_result:  dict,
) -> dict:
    """Write data/loop_report.json. Claude reads this to decide what to fix."""
    top = issues[0] if issues else None

    # Detect clip ceiling: if max observed players < target avg, no tracker
    # tuning can close the gap — the video simply doesn't have enough people.
    max_seen = metrics.get("max_players", 0)
    clip_ceiling = max_seen < TARGETS["avg_players"]

    # Also detect score plateau: same score for last 3+ runs on same clip
    recent = state.get("runs", [])[-3:]
    same_clip_runs = [r for r in recent if r.get("video") == os.path.basename(video_path)]
    score_plateau = (
        len(same_clip_runs) >= 3
        and max(r.get("score", 0) for r in same_clip_runs) -
            min(r.get("score", 0) for r in same_clip_runs) < 2.0
    )

    next_action: dict = {}
    if score >= TARGETS["passing_score"]:
        next_action = {
            "description": "Score >= 90 — advance to next game clip.",
            "type":    "advance_clip",
            "files":   [],
            "approach": "Run: python autonomous_loop.py --next-clip",
        }
    elif clip_ceiling or score_plateau:
        reason = (
            f"max_players={max_seen} < target {TARGETS['avg_players']} (clip ceiling)"
            if clip_ceiling else
            f"score stable at {score:.1f} for {len(same_clip_runs)} runs (plateau)"
        )
        next_action = {
            "description": f"ADVANCE CLIP — {reason}. No tracker fix can help here.",
            "type":        "advance_clip",
            "files":       [],
            "approach":    "Run: python autonomous_loop.py --next-clip --force-rerun",
            "reason":      reason,
        }
    elif top:
        next_action = {
            "description": f"Apply fix for '{top['metric']}' issue ({top['impact']} impact, -{top['penalty']} pts)",
            "type":        "code_fix",
            "files":       top.get("files_to_fix", []),
            "approach":    top.get("suggested_fix", ""),
            "expected_pts": top.get("penalty", 0),
            "verify_cmd":  (
                f"conda run -n {CONDA_ENV} python run_clip.py "
                f"--video \"{os.path.basename(video_path)}\" "
                "--no-show --frames 500"
            ),
        }

    # Trend: score improvement over last 5 runs
    history = state.get("runs", [])[-5:]
    trend   = "improving" if len(history) >= 2 and history[-1].get("score", 0) > history[0].get("score", 0) else \
              "stable"    if len(history) >= 2 and abs(history[-1].get("score", 0) - history[0].get("score", 0)) < 2 else \
              "degrading" if len(history) >= 2 else "new"

    report = {
        "generated_at":       datetime.now().isoformat(),
        "run_number":         len(state.get("runs", [])) + 1,
        "video":              os.path.basename(video_path),
        "video_path":         video_path,
        "overall_score":      score,
        "target_score":       TARGETS["passing_score"],
        "passed":             score >= TARGETS["passing_score"],
        "trend":              trend,
        "metrics":            {k: (round(v, 4) if isinstance(v, float) else v) for k, v in metrics.items()},
        "targets":            TARGETS,
        "real_stats":         real_stats,
        "issues_ranked":      issues,
        "top_issue":          top,
        "next_action":        next_action,
        "history":            history,
        "fixes_applied":      state.get("fixes_applied", []),
        "best_score_ever":    max(state.get("best_score", 0), score),
        "pipeline_elapsed_s": run_result.get("elapsed", 0),
        "pipeline_skipped":   run_result.get("skipped", False),
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)

    print(f"[Loop] Report written: {REPORT_PATH}")
    return report


# ── Improvement log ───────────────────────────────────────────────────────────

def append_improvement_log(report: dict):
    """Append a structured run summary to the Obsidian improvement log."""
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    score    = report["overall_score"]
    issues   = report.get("issues_ranked", [])
    video    = report.get("video", "unknown")
    run_num  = report.get("run_number", "?")
    trend    = report.get("trend", "?")
    m        = report.get("metrics", {})

    lines = [
        f"\n---\n",
        f"## Auto-Loop Run #{run_num} — {date_str}\n",
        f"**Score:** {score}/100 | **Trend:** {trend} | **Video:** `{video}`\n",
        f"\n**Key Metrics:**\n",
        f"| Metric | Actual | Target | Status |\n",
        f"|---|---|---|---|\n",
        f"| avg_players | {m.get('avg_players', 'N/A')!r} | ≥9.0 | "
        f"{'✅' if (m.get('avg_players') or 0) >= 9.0 else '❌'} |\n",
        f"| team_balance | {m.get('team_balance', 'N/A')!r} | 0.44-0.56 | "
        f"{'✅' if 0.44 <= (m.get('team_balance') or 0) <= 0.56 else '❌'} |\n",
        f"| ball_detection_pct | {m.get('ball_detection_pct', 'N/A')!r} | ≥0.65 | "
        f"{'✅' if (m.get('ball_detection_pct') or 0) >= 0.65 else '❌'} |\n",
        f"| shots_per_minute | {m.get('shots_per_minute', 'N/A')!r} | ~1.8 | "
        f"{'✅' if (m.get('shots_per_minute') or 0) >= 1.5 else '❌'} |\n",
        f"| unique_players | {m.get('unique_players_tracked', 'N/A')} | 8-16 | "
        f"{'✅' if 8 <= (m.get('unique_players_tracked') or 0) <= 16 else '❌'} |\n",
    ]

    if issues:
        top = issues[0]
        lines += [
            f"\n**Top Issue:** {top['metric']} ({top['impact']}, -{top['penalty']} pts)\n",
            f"> {top['description']}\n",
            f"\n**Suggested Fix:** {top.get('suggested_fix', '')}\n",
            f"**Files:** {', '.join(top.get('files_to_fix', []))}\n",
        ]
    else:
        lines.append("\n**Status:** All metrics passing — tracker is performing well on this clip.\n")

    entry = "".join(lines)

    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(entry)
        print(f"[Loop] Improvement log updated")
    else:
        print(f"[Loop] WARNING: Log path not found: {LOG_PATH}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="NBA Tracker Autonomous Improvement Loop")
    ap.add_argument("--frames",      type=int,  default=3000,  help="Max frames to process (default 3000)")
    ap.add_argument("--force-rerun", action="store_true",       help="Re-run pipeline even if fresh data exists")
    ap.add_argument("--next-clip",   action="store_true",       help="Advance to next clip before running")
    ap.add_argument("--video",       default=None,              help="Use this local video instead of downloading")
    args = ap.parse_args()

    print(f"\n{'='*62}")
    print(f"  NBA Tracker Autonomous Loop — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*62}\n")

    state = load_state()

    # Advance clip if requested
    if args.next_clip:
        state["clip_index"] = (state.get("clip_index", 0) + 1) % len(NBA_CLIPS)
        state["current_video"] = None
        save_state(state)
        print(f"[Loop] Advanced to clip #{state['clip_index']}: {NBA_CLIPS[state['clip_index']][0]}")

    # ── Step 1: Get video ────────────────────────────────────────────────────
    # --video flag overrides everything (useful when YouTube is blocked)
    if args.video:
        video_path = args.video
        if not os.path.exists(video_path):
            print(f"[Loop] --video path not found: {video_path}")
            sys.exit(1)
        state["current_video"] = video_path
        save_state(state)
    else:
        video_path = state.get("current_video")
        if not video_path or not os.path.exists(str(video_path)):
            video_path = download_game_clip(state)
            if not video_path:
                print("[Loop] No clip available. Fix options:")
                print("  A) Close Chrome/Edge completely and retry")
                print("  B) Export cookies: Install 'Get cookies.txt LOCALLY' Chrome extension,")
                print(f"     visit youtube.com, export to: {os.path.join(DATA_DIR, 'videos', 'youtube_cookies.txt')}")
                print("  C) Use a local video: python autonomous_loop.py --video path/to/clip.mp4")
                sys.exit(1)
            state["current_video"] = video_path
            save_state(state)

    print(f"[Loop] Video: {video_path}")

    # ── Step 2: Run pipeline ─────────────────────────────────────────────────
    run_result = run_pipeline(video_path, max_frames=args.frames, force=args.force_rerun)
    if "error" in run_result:
        print("[Loop] Pipeline failed — check stderr above for details.")
        sys.exit(1)

    # ── Step 3: Compute metrics ──────────────────────────────────────────────
    metrics = compute_metrics()
    if "error" in metrics:
        print(f"[Loop] Metrics error: {metrics['error']}")
        sys.exit(1)

    print(f"\n[Loop] Metrics summary:")
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"  {k:<30} {v:.4f}")
        elif isinstance(v, (int, bool)):
            print(f"  {k:<30} {v}")

    # ── Step 4: Real stats reference ─────────────────────────────────────────
    real_stats = fetch_real_nba_stats(state)

    # ── Step 5: Score and rank issues ────────────────────────────────────────
    score, issues = score_metrics(metrics, real_stats)

    print(f"\n[Loop] --- SCORE: {score:.1f}/100 ---")
    for iss in issues[:3]:
        tgt = str(iss['target']).replace('\u2265', '>=').replace('\u2264', '<=')
        print(f"  [X] {iss['metric']}: {iss['actual']} (target {tgt}) "
              f"[{iss['impact']}, -{iss['penalty']} pts]")
    if not issues:
        print("  [OK] All metrics passing!")

    # ── Step 6: Generate report ──────────────────────────────────────────────
    report = generate_report(video_path, metrics, real_stats, score, issues, state, run_result)

    # ── Step 7: Update state ─────────────────────────────────────────────────
    state["runs"].append({
        "timestamp": datetime.now().isoformat(),
        "video":     os.path.basename(video_path),
        "score":     score,
        "metrics": {
            k: round(v, 3) if isinstance(v, float) else v
            for k, v in metrics.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        },
    })
    prev_best = state.get("best_score", 0)
    state["best_score"] = max(prev_best, score)
    save_state(state)

    if score > prev_best:
        print(f"[Loop] ✨ New best score: {score:.1f} (was {prev_best:.1f})")

    # ── Step 8: Update improvement log ──────────────────────────────────────
    append_improvement_log(report)

    # ── Step 9: Auto-advance clip on ceiling/plateau (if not --video forced) ─
    na = report.get("next_action", {})
    if na.get("type") == "advance_clip" and not args.video:
        old_idx = state.get("clip_index", 0) % len(NBA_CLIPS)
        state["clip_index"] = (old_idx + 1) % len(NBA_CLIPS)
        state["current_video"] = None
        save_state(state)
        new_label = NBA_CLIPS[state["clip_index"]][0]
        print(f"[Loop] Clip ceiling/plateau detected — auto-advanced to clip #{state['clip_index']}: {new_label}")

    # ── Final summary ────────────────────────────────────────────────────────
    print(f"\n{'='*62}")
    print(f"  Score:    {score:.1f}/100  (best ever: {state['best_score']:.1f})")
    print(f"  Report:   {REPORT_PATH}")
    if na:
        print(f"  Action:   {na.get('description', '')}")
    print(f"{'='*62}\n")


if __name__ == "__main__":
    main()
