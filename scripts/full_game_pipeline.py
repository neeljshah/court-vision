"""
full_game_pipeline.py — Automated full-game download + process loop.

Picks high-profile 2024-25 NBA games, searches YouTube for full-game
replays (≥ 90 min), downloads them with yt-dlp, then runs the complete
4-stage pipeline (track → features → enrich → retrain check).

Runs until the time budget is exhausted, skipping games already on disk.

Usage
-----
    conda activate basketball_ai

    python scripts/full_game_pipeline.py                  # 3-hour default
    python scripts/full_game_pipeline.py --hours 6        # longer run
    python scripts/full_game_pipeline.py --max-frames 3000 # cap frames (faster)
    python scripts/full_game_pipeline.py --no-enrich      # skip NBA enrichment
    python scripts/full_game_pipeline.py --dry-run        # plan only

Output
------
    data/videos/full_games/<game_id>.mp4   downloaded videos
    data/games/<game_id>/                  pipeline outputs per game
      tracking_data.csv, features.csv, enriched CSVs, manifest.json
      predictions.json                     full model stack (win prob + per-player props)
      props_context.json                   copy of props lines when --refresh-context
    data/full_game_results.json            running metrics log
    vault/Sessions/full_game_<date>.md     final quality report

    Use --refresh-context to refresh injury reports + sportsbook props before predictions
    (same sources as scripts/daily_pipeline.py). Default: run predictions using cached data.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

# ── Paths ──────────────────────────────────────────────────────────────────────

_DATA_DIR      = os.path.join(PROJECT_DIR, "data")
_SCHEDULE_DIR  = os.path.join(_DATA_DIR, "nba", "schedule")
_VIDEOS_DIR    = os.path.join(_DATA_DIR, "videos", "full_games")
_GAMES_DIR     = os.path.join(_DATA_DIR, "games")
_COOKIES_FILE  = os.path.join(_DATA_DIR, "videos", "youtube_cookies.txt")
_RESULTS_PATH  = os.path.join(_DATA_DIR, "full_game_results.json")
_VAULT_DIR     = os.path.join(PROJECT_DIR, "vault", "Sessions")

os.makedirs(_VIDEOS_DIR, exist_ok=True)
os.makedirs(_GAMES_DIR, exist_ok=True)
os.makedirs(_VAULT_DIR, exist_ok=True)

# ── Full team name map (abbr → display name for search queries) ────────────────

_TEAM_NAMES: Dict[str, str] = {
    "ATL": "Hawks",   "BKN": "Nets",    "BOS": "Celtics", "CHA": "Hornets",
    "CHI": "Bulls",   "CLE": "Cavaliers","DAL": "Mavericks","DEN": "Nuggets",
    "DET": "Pistons", "GSW": "Warriors","HOU": "Rockets", "IND": "Pacers",
    "LAC": "Clippers","LAL": "Lakers",  "MEM": "Grizzlies","MIA": "Heat",
    "MIL": "Bucks",   "MIN": "Timberwolves","NOP": "Pelicans","NYK": "Knicks",
    "OKC": "Thunder", "ORL": "Magic",   "PHI": "76ers",   "PHX": "Suns",
    "POR": "Blazers", "SAC": "Kings",   "SAS": "Spurs",   "TOR": "Raptors",
    "UTA": "Jazz",    "WAS": "Wizards",
}

# ── High-value target matchups — prioritise these for download ─────────────────
# Format: (home_abbr, away_abbr) — best games of 2024-25 season

_PRIORITY_MATCHUPS: List[Tuple[str, str]] = [
    ("BOS", "NYK"),   # East rivalry
    ("OKC", "DAL"),   # SGA vs Doncic
    ("GSW", "LAL"),   # Classic rivalry
    ("MIL", "IND"),   # Giannis vs Haliburton
    ("DEN", "MIN"),   # Jokic vs Edwards
    ("CLE", "BOS"),   # Top East seeds
    ("PHX", "DAL"),   # KD vs Luka
    ("MIA", "BOS"),   # Playoff rematch
    ("LAL", "GSW"),   # LeBron vs Steph
    ("OKC", "HOU"),   # Young guns
    ("MEM", "NOP"),   # Deep South
    ("SAC", "LAL"),   # Fox vs LeBron
    ("CHI", "MIL"),   # Division game
    ("ATL", "IND"),   # Trae vs Hali
    ("PHI", "TOR"),   # Process vs North
    ("DEN", "PHX"),   # Rocky Mountain
    ("BKN", "NYK"),   # NYC derby
    ("SAS", "LAL"),   # Wemby vs LeBron
    ("NOP", "MEM"),   # Zion vs Morant
    ("HOU", "SAC"),   # West up-and-comers
]

# ── Schedule loader ────────────────────────────────────────────────────────────

_SCHED_CACHE: Dict[str, dict] = {}   # game_id → {game_id, date, home, away}

def _build_schedule_index() -> Dict[str, dict]:
    """Build a full game_id → matchup index from all schedule files (2024-25 + 2025-26)."""
    if _SCHED_CACHE:
        return _SCHED_CACHE

    import glob
    files = glob.glob(os.path.join(_SCHEDULE_DIR, "schedule_*_2024-25*.json"))
    files += glob.glob(os.path.join(_SCHEDULE_DIR, "schedule_*_2025-26*.json"))
    for fpath in files:
        # Extract team abbrev: schedule_ATL_2024-25_v2.json → ATL
        _base = os.path.basename(fpath).split("schedule_")[1]
        team = _base.split("_20")[0]  # split on _20 to handle any season year
        try:
            with open(fpath, encoding="utf-8") as _fh:
                data = json.load(_fh)
        except Exception:
            continue
        games = data if isinstance(data, list) else []
        for g in games:
            gid = g.get("game_id", "")
            if not gid or gid in _SCHED_CACHE:
                continue
            opp  = g.get("opponent", "")
            home = g.get("home", False)
            _SCHED_CACHE[gid] = {
                "game_id": gid,
                "date":    g.get("date", ""),
                "home":    team if home else opp,
                "away":    opp  if home else team,
            }
    return _SCHED_CACHE


def find_game_for_matchup(home: str, away: str) -> Optional[dict]:
    """
    Return the most recent 2024-25 game_id for a home/away matchup.
    Tries both home/away orderings.
    """
    idx = _build_schedule_index()
    matches = []
    for g in idx.values():
        if (g["home"] == home and g["away"] == away) or \
           (g["home"] == away and g["away"] == home):
            matches.append(g)
    if not matches:
        return None
    # Most recent game first
    return sorted(matches, key=lambda x: x["date"], reverse=True)[0]


def lookup_game_by_id(game_id: str) -> Optional[dict]:
    """Return schedule row for a known NBA game_id, or None."""
    return _build_schedule_index().get(game_id)


def _json_safe(obj: object):
    """Recursively convert numpy scalars for JSON."""
    try:
        import numpy as np
        if isinstance(obj, np.generic):
            return float(obj) if isinstance(obj, np.floating) else int(obj)
    except ImportError:
        pass
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(x) for x in obj]
    if isinstance(obj, float):
        if obj != obj or obj in (float("inf"), float("-inf")):
            return None
    return obj


def run_predictions_for_game(
    game: dict,
    season: str = "2024-25",
    refresh_context: bool = False,
) -> dict:
    """Run PredictionOrchestrator; write predictions.json under data/games/<id>/."""
    from dataclasses import asdict

    gid = game["game_id"]
    out: dict = {
        "success": False,
        "predictions_path": None,
        "props_context_path": None,
        "injuries_refreshed": False,
        "props_count": 0,
        "error": None,
    }
    game_out = os.path.join(_GAMES_DIR, gid)
    os.makedirs(game_out, exist_ok=True)

    if refresh_context:
        try:
            from src.data.injury_monitor import InjuryMonitor
            summary = InjuryMonitor().refresh()
            out["injuries_refreshed"] = True
            out["injury_entries"] = len(summary) if isinstance(summary, (list, dict)) else 0
        except Exception as e:
            out["injury_refresh_error"] = str(e)
        try:
            from src.data.props_scraper import get_current_props
            props = get_current_props("draftkings")
            out["props_count"] = len(props) if props else 0
            props_dir = os.path.join(_DATA_DIR, "props")
            os.makedirs(props_dir, exist_ok=True)
            props_path = os.path.join(props_dir, f"props_{game['date']}.json")
            with open(props_path, "w", encoding="utf-8") as f:
                json.dump(props, f, indent=2)
            ctx_copy = os.path.join(game_out, "props_context.json")
            with open(ctx_copy, "w", encoding="utf-8") as f:
                json.dump(props, f, indent=2)
            out["props_context_path"] = ctx_copy
        except Exception as e:
            out["props_refresh_error"] = str(e)

    try:
        from src.pipeline.prediction_orchestrator import PredictionOrchestrator

        orch = PredictionOrchestrator(season=season)
        gp = orch.predict_game(
            game_id=gid,
            date=game["date"],
            home_team=game["home"],
            away_team=game["away"],
        )
        payload = _json_safe(asdict(gp))
        pred_path = os.path.join(game_out, "predictions.json")
        with open(pred_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        out["predictions_path"] = pred_path
        out["success"] = True
    except Exception as e:
        out["error"] = str(e)
        out["traceback"] = traceback.format_exc()

    return out


def build_target_list() -> List[dict]:
    """
    Build ordered download target list.

    1. Priority matchups (curated list above)
    2. Remaining 2024-25 games not yet processed, sorted by date descending
    """
    idx   = _build_schedule_index()
    seen  = set()
    targets = []

    # First: priority matchups
    for home, away in _PRIORITY_MATCHUPS:
        g = find_game_for_matchup(home, away)
        if g and g["game_id"] not in seen:
            seen.add(g["game_id"])
            targets.append(g)

    # Then: everything else sorted by recency
    remaining = sorted(
        [g for g in idx.values() if g["game_id"] not in seen],
        key=lambda x: x["date"],
        reverse=True,
    )
    targets.extend(remaining)
    return targets


# ── YouTube search + download ──────────────────────────────────────────────────

def _search_query(game: dict) -> str:
    """Build a YouTube search query optimised for full-game replay videos."""
    home_name = _TEAM_NAMES.get(game["home"], game["home"])
    away_name = _TEAM_NAMES.get(game["away"], game["away"])
    # Parse date for month/day in query
    try:
        from datetime import datetime as _dt
        d = _dt.strptime(game["date"], "%Y-%m-%d")
        date_str = d.strftime("%B %d").replace(" 0", " ")   # "March 5"
    except Exception:
        date_str = game["date"]

    return (
        f"{home_name} vs {away_name} {date_str} 2025 "
        f"NBA full game replay"
    )


def _video_path(game_id: str) -> str:
    return os.path.join(_VIDEOS_DIR, f"{game_id}.mp4")


def download_full_game(game: dict, timeout_min: int = 30) -> Optional[str]:
    """
    Search YouTube and download the best full-game replay (≥ 90 min).

    Uses yt-dlp with:
      - ytsearch5 — checks top 5 results
      - match-filter duration >= 5400 (90 min)
      - 720p max resolution (balance quality / disk space)
      - cookies from data/videos/youtube_cookies.txt

    Returns local video path on success, None on failure.
    """
    out_path = _video_path(game["game_id"])
    if os.path.exists(out_path) and os.path.getsize(out_path) > 50_000_000:
        print(f"    Already downloaded: {out_path}")
        return out_path

    query   = _search_query(game)
    tmp_out = os.path.join(_VIDEOS_DIR, f"{game['game_id']}.%(ext)s")

    print(f"    Searching: {query}")

    cmd = [
        "yt-dlp",
        f"ytsearch5:{query}",
        "--match-filter", "duration >= 5400",   # ≥ 90 min = full game
        "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", tmp_out,
        "--no-playlist",
        "--max-downloads", "1",
        "--no-warnings",
        "--quiet",
        "--progress",
    ]
    if os.path.exists(_COOKIES_FILE):
        cmd += ["--cookies", _COOKIES_FILE]

    print(f"    Downloading (≥ 90 min filter, 720p max)...")
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            timeout=timeout_min * 60,
            capture_output=False,
        )
        elapsed = time.time() - t0

        if os.path.exists(out_path):
            size_mb = os.path.getsize(out_path) / (1024 * 1024)
            print(f"    ✓ Downloaded {size_mb:.0f} MB in {elapsed/60:.1f} min → {out_path}")
            return out_path

        # yt-dlp may have written to a slightly different path
        for f in os.listdir(_VIDEOS_DIR):
            if f.startswith(game["game_id"]) and f.endswith(".mp4"):
                actual = os.path.join(_VIDEOS_DIR, f)
                os.rename(actual, out_path)
                size_mb = os.path.getsize(out_path) / (1024 * 1024)
                print(f"    ✓ Downloaded {size_mb:.0f} MB → {out_path}")
                return out_path

        print(f"    ✗ No full-game video found (all results < 90 min or search failed)")
        return None

    except subprocess.TimeoutExpired:
        print(f"    ✗ Download timeout ({timeout_min} min)")
        return None
    except Exception as e:
        print(f"    ✗ Download error: {e}")
        return None


# ── Tip-off detection ──────────────────────────────────────────────────────────

def _detect_clip_start(tracking_path: str, gap_threshold_sec: float = 300.0) -> float:
    """Return clip_start_sec for enrichment by finding the actual game tip-off.

    Broadcast videos have pre-game coverage before tip-off.  The tracking data
    will have a large gap (> gap_threshold_sec) between warmup rows and the
    first real gameplay rows.  The timestamp immediately after this gap is the
    estimated tip-off second.

    Falls back to 0.0 when no large gap is found (short clips, or warmup-only).
    """
    import csv as _csv
    ts_set: set = set()
    try:
        with open(tracking_path) as f:
            for row in _csv.DictReader(f):
                try:
                    ts_set.add(round(float(row["timestamp"]), 1))
                except Exception:
                    pass
    except Exception:
        return 0.0
    if len(ts_set) < 2:
        return 0.0
    ts_sorted = sorted(ts_set)
    gaps = [(ts_sorted[i + 1] - ts_sorted[i], ts_sorted[i + 1])
            for i in range(len(ts_sorted) - 1)]
    max_gap_sec, post_gap_ts = max(gaps, key=lambda g: g[0])
    if max_gap_sec > gap_threshold_sec:
        print(f"  [ENRICH] Detected tip-off gap: {max_gap_sec:.0f}s "
              f"→ clip_start_sec={post_gap_ts:.1f}s")
        return float(post_gap_ts)
    # No large pre-game gap: started at or near tip-off (e.g. --start-frame used).
    # Use the minimum timestamp as clip_start_sec so enrichment maps correctly.
    min_ts = ts_sorted[0]
    if min_ts > 60.0:
        print(f"  [ENRICH] No pre-game gap detected; using min_ts={min_ts:.1f}s as clip_start_sec")
        return float(min_ts)
    return 0.0


# ── Pipeline runner ────────────────────────────────────────────────────────────

def run_pipeline(
    game: dict,
    video_path: str,
    max_frames: Optional[int],
    no_enrich: bool,
    run_predictions: bool = True,
    season: str = "2024-25",
    refresh_context: bool = False,
    start_frame: int = 0,
) -> dict:
    """Run tracking → features → enrich → snapshot; optionally model predictions."""
    import inspect
    from src.pipeline.unified_pipeline import UnifiedPipeline
    from src.features.feature_engineering import run as run_features

    t0 = time.time()
    result = {
        "game_id":       game["game_id"],
        "date":          game["date"],
        "home":          game["home"],
        "away":          game["away"],
        "video_path":    video_path,
        "started_at":    datetime.now().isoformat(),
        "success":       False,
        "error":         None,
        "traceback":     None,
        "total_frames":      0,
        "tracking_rows":     0,
        "stability":         0.0,
        "id_switches":       0,
        "fps_estimate":      0.0,
        "ball_detected_pct": 0.0,
        "shots_detected":        0,
        "possessions_labeled":   0,
        "shots_enriched":        0,
        "shots_pbp_coverage":    0,   # % of reachable PBP FG events matched (true metric)
        "possessions_enriched":  0,
        "stages_completed": [],
        "predictions": None,
    }

    try:
        # Stage 1: Tracking
        print(f"\n  [TRACKING] {game['home']} vs {game['away']}  {game['date']}")
        t_track = time.time()
        up_kwargs = dict(
            video_path=video_path,
            yolo_weight_path=None,
            max_frames=max_frames,
            show=False,
            game_id=game["game_id"],
        )
        sig = inspect.signature(UnifiedPipeline.__init__).parameters
        if "frame_skip" in sig:
            up_kwargs["frame_skip"] = 1
        if start_frame > 0 and "start_frame" in sig:
            up_kwargs["start_frame"] = start_frame
        pipeline = UnifiedPipeline(**up_kwargs)
        tr = pipeline.run()

        result["total_frames"] = max(0, tr.get("total_frames", 0))  # guard sentinel -1
        result["stability"]    = round(float(tr.get("stability", 0)), 3)
        result["id_switches"]  = tr.get("id_switches", 0)
        elapsed_track = time.time() - t_track
        result["fps_estimate"] = round(result["total_frames"] / max(elapsed_track, 1), 1) if result["total_frames"] > 0 else 0.0
        result["stages_completed"].append("tracking")

        # Ball detection rate — prefer game-specific file to avoid accumulation across runs
        _game_dir = os.path.join(_GAMES_DIR, game["game_id"])
        bt_path = os.path.join(_game_dir, "ball_tracking.csv")
        if not os.path.exists(bt_path):
            bt_path = os.path.join(_DATA_DIR, "ball_tracking.csv")
        if os.path.exists(bt_path):
            try:
                import csv
                total_bt = detected_bt = 0
                with open(bt_path, newline="") as f:
                    for row in csv.DictReader(f):
                        total_bt += 1
                        if row.get("detected", "0") == "1":
                            detected_bt += 1
                if total_bt > 0:
                    result["ball_detected_pct"] = round(100.0 * detected_bt / total_bt, 1)
            except Exception:
                pass

        # Use game-specific checkpoint file when available; fall back to tracking_data.csv
        import glob as _glob
        from datetime import date as _date
        _ckpt_pattern = os.path.join(_DATA_DIR, "tracking", f"{game['game_id']}_{_date.today().isoformat()}.csv")
        _tracking_input = _ckpt_pattern if os.path.exists(_ckpt_pattern) else os.path.join(_DATA_DIR, "tracking_data.csv")
        result["tracking_rows"]       = _count_rows(_tracking_input)
        result["shots_detected"]      = _count_rows(os.path.join(_DATA_DIR, "shot_log.csv"))
        result["possessions_labeled"] = _count_rows(os.path.join(_DATA_DIR, "possessions.csv"))

        print(f"  ✓ Tracked {result['total_frames']} frames @ {result['fps_estimate']} fps  "
              f"stability={result['stability']}  ball={result['ball_detected_pct']}%")

        # Stage 2: Features
        print(f"  [FEATURES]")
        try:
            run_features(
                input_path=_tracking_input,
                output_path=os.path.join(_DATA_DIR, "features.csv"),
            )
            result["stages_completed"].append("features")
            print(f"  ✓ Features — {_count_rows(os.path.join(_DATA_DIR, 'features.csv'))} rows")
        except Exception as e:
            print(f"  ⚠ Features failed: {e}")

        # Stage 3: NBA enrichment
        if not no_enrich:
            print(f"  [ENRICH]")
            try:
                import csv
                from src.data.nba_enricher import enrich
                _clip_start = _detect_clip_start(_tracking_input)
                # In full-game mode PBP game_clock_sec is absolute (0-2880s).
                # Shot timestamps are absolute video timestamps (ts), so game time
                # = ts - clip_start_sec.  enrich_shot_log adds clip_start_sec to ts,
                # so negate here: ts + (-clip_start) = ts - clip_start. ✓
                enrich_result = enrich(
                    game_id=game["game_id"],
                    periods=[1, 2, 3, 4],   # full-game: normalise all periods to abs time
                    clip_start_sec=-_clip_start,
                    fps=result["fps_estimate"] or 30.0,
                    data_dir=_DATA_DIR,
                )
                result["stages_completed"].append("enrichment")
                for key, pkey in [("shots_enriched", "shot_log_enriched"),
                                   ("possessions_enriched", "possessions_enriched")]:
                    p = enrich_result.get(pkey, "")
                    if p and os.path.exists(p):
                        with open(p, newline="") as fh:
                            rows_e = list(csv.DictReader(fh))
                        if pkey == "shot_log_enriched":
                            result[key] = sum(1 for r in rows_e if r.get("made", "") != "")
                        else:
                            result[key] = sum(1 for r in rows_e if r.get("result", "") not in ("", "unknown"))
                # ── True PBP coverage: % of reachable PBP FG events with a tracker match ──
                # The raw shots_enriched / shots_detected rate is misleading because the
                # tracker generates many false-positive "shot" detections. The correct metric
                # is: how many real NBA FG events (from PBP) have at least one tracker
                # detection within _SHOT_MATCH_WINDOW_SEC (4s)?  Typical result: 86-99%.
                try:
                    import json as _json2
                    _sl_path = enrich_result.get("shot_log_enriched", "")
                    _gid     = game["game_id"]
                    _nba_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "nba")
                    _MATCH_WIN = 4.0
                    if _sl_path and os.path.exists(_sl_path):
                        with open(_sl_path, newline="") as _fh:
                            _sl_rows = list(csv.DictReader(_fh))
                        _ts_vals = [float(r["timestamp"]) for r in _sl_rows if r.get("timestamp")]
                        _max_ts  = max(_ts_vals) if _ts_vals else 0.0
                        _all_fg: list = []
                        _offset = 0
                        for _p in range(1, 5):
                            _pbp_path = os.path.join(_nba_dir, f"pbp_{_gid}_p{_p}.json")
                            if not os.path.exists(_pbp_path):
                                break
                            with open(_pbp_path) as _fh2:
                                _pbp_p = _json2.load(_fh2)
                            for _e in _pbp_p:
                                if _e.get("event_type") in (1, 2):
                                    _all_fg.append(_offset + int(_e.get("game_clock_sec", 0) or 0))
                            _offset += 12 * 60
                        _in_range = [gc for gc in _all_fg if gc <= _max_ts + _MATCH_WIN]
                        _covered  = sum(
                            1 for gc in _in_range if any(abs(gc - ts) <= _MATCH_WIN for ts in _ts_vals)
                        )
                        if _in_range:
                            result["shots_pbp_coverage"] = round(100.0 * _covered / len(_in_range), 1)
                except Exception:
                    pass
                _pbp_cov = result.get("shots_pbp_coverage", 0)
                _cov_str = f"  pbp_coverage={_pbp_cov}%" if _pbp_cov else ""
                print(f"  ✓ Enriched — {result['shots_enriched']} shots / "
                      f"{result['possessions_enriched']} possessions{_cov_str}")
            except Exception as e:
                print(f"  ⚠ Enrich failed: {e}")
        else:
            print(f"  [ENRICH] skipped")

        if run_predictions:
            print(f"  [PREDICTIONS] season={season}  refresh_context={refresh_context}")
            try:
                pred_meta = run_predictions_for_game(
                    game, season=season, refresh_context=refresh_context,
                )
                result["predictions"] = pred_meta
                if pred_meta.get("success"):
                    result["stages_completed"].append("predictions")
                    n_players = 0
                    try:
                        with open(pred_meta["predictions_path"], encoding="utf-8") as pf:
                            pj = json.load(pf)
                            n_players = len(pj.get("player_predictions") or [])
                    except Exception:
                        pass
                    print(f"  ✓ Predictions → {pred_meta.get('predictions_path')}  ({n_players} players)")
                else:
                    print(f"  ⚠ Predictions failed: {pred_meta.get('error')}")
            except Exception as e:
                result["predictions"] = {"success": False, "error": str(e)}
                print(f"  ⚠ Predictions failed: {e}")
        else:
            print(f"  [PREDICTIONS] skipped")

        result["stages_completed"].append("snapshot")
        result["success"] = True
        _snapshot(game["game_id"], result)

    except KeyboardInterrupt:
        raise
    except Exception as e:
        result["error"]     = str(e)
        result["traceback"] = traceback.format_exc()
        print(f"\n  ✗ Pipeline failed: {e}")
        print(result["traceback"])

    result["duration_sec"] = round(time.time() - t0, 1)
    return result


def _count_rows(path: str) -> int:
    if not os.path.exists(path):
        return 0
    try:
        import csv
        with open(path, newline="") as f:
            return sum(1 for _ in csv.DictReader(f))
    except Exception:
        return 0


def _snapshot(game_id: str, result: dict) -> None:
    import shutil
    out = os.path.join(_GAMES_DIR, game_id)
    os.makedirs(out, exist_ok=True)
    for fname in [
        "tracking_data.csv", "ball_tracking.csv", "possessions.csv",
        "shot_log.csv", "features.csv", "stats.json",
        "shot_log_enriched.csv", "possessions_enriched.csv",
    ]:
        src = os.path.join(_DATA_DIR, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(out, fname))
    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump(result, f, indent=2)


# ── Quality grade ──────────────────────────────────────────────────────────────

def grade(r: dict) -> str:
    if not r["success"]:
        return "F"
    if r.get("total_frames", 0) <= 0:
        return "F"  # frame count sentinel or zero means the run didn't complete properly
    s, bd, sh, pos = r["stability"], r["ball_detected_pct"], r["shots_detected"], r["possessions_labeled"]
    if s >= 0.9 and bd >= 80 and sh >= 10 and pos >= 50: return "A"
    if s >= 0.8 and bd >= 60 and sh >= 5  and pos >= 20: return "B"
    if s >= 0.7 and bd >= 40 and sh >= 2  and pos >= 5:  return "C"
    if s > 0: return "D"
    return "F"


# ── Vault report ───────────────────────────────────────────────────────────────

def write_report(results: List[dict], path: str, hours: float) -> None:
    from collections import Counter
    ok    = sum(1 for r in results if r["success"])
    total = len(results)
    grades = [grade(r) for r in results]
    avg_s  = sum(r["stability"] for r in results if r["success"]) / max(ok, 1)
    avg_b  = sum(r["ball_detected_pct"] for r in results if r["success"]) / max(ok, 1)
    _fps_ok = [r["fps_estimate"] for r in results if r["success"] and r["fps_estimate"] > 0]
    avg_f  = sum(_fps_ok) / max(len(_fps_ok), 1)
    t_rows = sum(r["tracking_rows"] for r in results)
    t_sh   = sum(r["shots_detected"] for r in results)
    t_pos  = sum(r["possessions_labeled"] for r in results)
    t_enr  = sum(r["shots_enriched"] for r in results)

    lines = [
        f"# Full Game Pipeline — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"",
        f"**Runtime:** {hours:.1f}h   **Games processed:** {ok}/{total}",
        f"**Avg FPS:** {avg_f:.1f}   **Avg stability:** {avg_s:.3f}   **Avg ball det.:** {avg_b:.1f}%",
        f"**Total tracking rows:** {t_rows:,}   **Shots detected:** {t_sh}   "
        f"**Possessions:** {t_pos}   **Shots enriched:** {t_enr}",
        f"",
        f"## Results",
        f"",
        f"| Date | Matchup | Grade | Frames | FPS | Stab | Ball% | Shots | Poss | Enriched | PBP Cov% |",
        f"|------|---------|-------|--------|-----|------|-------|-------|------|----------|----------|",
    ]
    for r, g in zip(results, grades):
        matchup = f"{r['home']} vs {r['away']}"
        pbp_cov = r.get("shots_pbp_coverage", "")
        lines.append(
            f"| {r['date']} | {matchup} | {g} | {r['total_frames']} | {r['fps_estimate']} "
            f"| {r['stability']:.3f} | {r['ball_detected_pct']}% "
            f"| {r['shots_detected']} | {r['possessions_labeled']} | {r['shots_enriched']} "
            f"| {pbp_cov}% |"
        )

    grade_dist = Counter(grades)
    lines += ["", "## Grade Distribution", ""]
    for g in "ABCDF":
        if grade_dist[g]:
            lines.append(f"- **{g}**: {grade_dist[g]}")

    failures = [r for r in results if not r["success"]]
    lines += ["", "## Failures", ""]
    if failures:
        for r in failures:
            lines.append(f"### {r['home']} vs {r['away']}  {r['date']}")
            lines.append(f"```\n{r.get('error', '')}\n```")
    else:
        lines.append("None.")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n  Report → {path}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    if sys.platform == "win32":
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Full-game download + pipeline loop")
    parser.add_argument("--hours",        type=float, default=3.0)
    parser.add_argument("--max-frames",   type=int,   default=None)
    parser.add_argument("--no-enrich",    action="store_true")
    parser.add_argument("--dry-run",      action="store_true")
    parser.add_argument("--download-only",action="store_true",
                        help="Only download, don't process")
    parser.add_argument("--process-only", action="store_true",
                        help="Only process already-downloaded videos, skip yt-dlp")
    parser.add_argument("--download-timeout", type=int, default=30,
                        help="Max minutes to wait per download (default 30)")
    parser.add_argument("--game-id", type=str, default=None,
                        help="Only this schedule game_id (must exist in schedule JSON)")
    parser.add_argument("--force", action="store_true",
                        help="With --game-id, allow re-run even if marked success before")
    parser.add_argument("--no-predictions", action="store_true",
                        help="Skip PredictionOrchestrator after tracking/enrichment")
    parser.add_argument("--season", default="2024-25", help="Season string for models")
    parser.add_argument("--refresh-context", action="store_true",
                        help="Refresh injuries + DK props before predictions (network)")
    parser.add_argument("--start-frame", type=int, default=0,
                        help="Skip to this video frame before processing (e.g. 203994 to jump to tip-off at ts=3403s)")
    parser.add_argument("--post-game", action="store_true",
                        help="High-quality post-game mode: yolov8x + imgsz=1280 (~3x slower, +7%% detection accuracy)")
    args = parser.parse_args()

    if args.post_game:
        os.environ["TRACKER_POST_GAME"] = "1"

    deadline = datetime.now() + timedelta(hours=args.hours)
    vault_log = os.path.join(
        _VAULT_DIR,
        f"full_game_{datetime.now().strftime('%Y-%m-%d_%H%M')}.md",
    )

    targets = build_target_list()
    if args.game_id:
        g = lookup_game_by_id(args.game_id)
        if not g:
            print(f"Unknown game_id {args.game_id!r} — not in schedule files")
            sys.exit(1)
        targets = [g]

    done_ids: set = set()
    results: List[dict] = []
    if os.path.exists(_RESULTS_PATH):
        try:
            with open(_RESULTS_PATH, encoding="utf-8") as _rfh:
                existing = json.load(_rfh)
            for r in existing:
                if r.get("success"):
                    done_ids.add(r["game_id"])
            results = existing
        except Exception:
            pass

    if args.game_id and args.force:
        done_ids.discard(args.game_id)

    print(f"\n{'='*60}")
    print(f"  NBA AI — Full Game Pipeline")
    print(f"  Runtime  : {args.hours}h  (deadline {deadline.strftime('%H:%M')})")
    print(f"  Targets  : {len(targets)} games  ({len(done_ids)} already done)")
    print(f"  Mode     : {'download only' if args.download_only else 'process only' if args.process_only else 'download + process'}")
    print(f"  Enrich   : {'OFF' if args.no_enrich else 'ON'}")
    print(f"  Predict  : {'OFF' if args.no_predictions else 'ON'}  (season {args.season})")
    if args.refresh_context:
        print(f"  Context  : refresh injuries + props before predict")
    print(f"  Frames   : {'all' if not args.max_frames else args.max_frames}")
    print(f"  Detector : {'yolov8x + imgsz=1280 (post-game)' if args.post_game else 'yolov8n + imgsz=640 (default)'}")
    print(f"{'='*60}")

    if args.dry_run:
        print("\nFirst 10 targets:")
        for t in targets[:10]:
            vid = _video_path(t["game_id"])
            on_disk = " [on disk]" if os.path.exists(vid) else ""
            done    = " [DONE]"   if t["game_id"] in done_ids else ""
            print(f"  {t['date']}  {t['home']:3s} vs {t['away']:3s}  {t['game_id']}{on_disk}{done}")
        print("\nDry-run — exiting.")
        return

    # ── Main loop ──────────────────────────────────────────────────────────────
    for game in targets:
        if datetime.now() >= deadline:
            print("\n  Time limit reached.")
            break

        if game["game_id"] in done_ids:
            continue

        mins_left = int((deadline - datetime.now()).total_seconds() // 60)
        print(f"\n{'─'*60}")
        print(f"  {game['date']}  {game['home']} vs {game['away']}  "
              f"[{game['game_id']}]  {mins_left} min left")
        print(f"{'─'*60}")

        # Step 1: Download (skip if --process-only or already on disk)
        video_path = _video_path(game["game_id"])
        if not args.process_only:
            if os.path.exists(video_path) and os.path.getsize(video_path) > 50_000_000:
                print(f"  Video already on disk ({os.path.getsize(video_path)//1_000_000} MB) — skip download")
            else:
                video_path = download_full_game(game, timeout_min=args.download_timeout)
                if video_path is None:
                    print(f"  No full-game video found — skipping this game")
                    continue

        if args.download_only:
            continue

        # Step 2: Verify we have a video
        if not os.path.exists(video_path):
            print(f"  No video at {video_path} — skipping")
            continue

        size_mb = os.path.getsize(video_path) / (1024 * 1024)
        if size_mb < 50:
            print(f"  Video too small ({size_mb:.0f} MB) — likely not a full game, skipping")
            continue

        # Step 3: Check time budget — skip if < 10 min left
        if (deadline - datetime.now()).total_seconds() < 600:
            print(f"  < 10 min left — stopping before processing more games.")
            break

        # Step 4: Process
        result = run_pipeline(
            game=game,
            video_path=video_path,
            max_frames=args.max_frames,
            no_enrich=args.no_enrich,
            run_predictions=not args.no_predictions,
            season=args.season,
            refresh_context=args.refresh_context,
            start_frame=args.start_frame,
        )
        results.append(result)
        if result["success"]:
            done_ids.add(game["game_id"])

        # Print grade summary
        g = grade(result)
        status = "✓" if result["success"] else "✗"
        print(f"\n  {status} Grade: {g}  |  "
              f"frames={result['total_frames']}  fps={result['fps_estimate']}  "
              f"stab={result['stability']}  ball={result['ball_detected_pct']}%  "
              f"shots={result['shots_detected']}  poss={result['possessions_labeled']}  "
              f"enriched={result['shots_enriched']}  time={result['duration_sec']:.0f}s")

        # Save running log
        try:
            with open(_RESULTS_PATH, "w") as f:
                json.dump(results, f, indent=2)
        except Exception:
            pass

    # ── Final report ───────────────────────────────────────────────────────────
    elapsed = args.hours - (deadline - datetime.now()).total_seconds() / 3600
    processed = [r for r in results if r.get("started_at")]

    print(f"\n{'='*60}")
    print(f"  DONE — {len(processed)} games processed")
    print(f"{'='*60}")

    if processed:
        write_report(processed, vault_log, elapsed)
        print(f"  Results → {_RESULTS_PATH}")

    print()


if __name__ == "__main__":
    main()
