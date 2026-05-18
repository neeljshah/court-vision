"""
validate_game.py — Compare tracker output against NBA API ground truth.

For each processed game, loads tracker CSVs and NBA play-by-play / box score,
then computes accuracy metrics and writes a full-game summary to the vault.

Usage
-----
    conda activate basketball_ai

    # Validate an already-processed snapshot (fast, no tracking):
    python scripts/validate_game.py --game-id 0022400625

    # Run pipeline first, then validate (low-usage: auto stride=3):
    python scripts/validate_game.py --game-id 0022400625 --run

    # Validate all games in data/games/:
    python scripts/validate_game.py --all

Output
------
    vault/Sessions/fullgame_summary_<date>.md   — per-game accuracy report
    data/games/<game_id>/validation.json        — raw metric dict

Ground-truth sources
--------------------
    NBA PBP  — data/nba/pbp_<game_id>.json (cached bulk) + per-period cache
    Box score — nba_api BoxScoreTraditionalV2 (fetched fresh, 30-min TTL)
    Shot chart — data/nba/shot_chart_*.json (per-player, already scraped)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

# ── Paths ──────────────────────────────────────────────────────────────────────

_DATA_DIR   = os.path.join(PROJECT_DIR, "data")
_NBA_DIR    = os.path.join(_DATA_DIR, "nba")
_GAMES_DIR  = os.path.join(_DATA_DIR, "games")
_VAULT_DIR  = os.path.join(PROJECT_DIR, "vault", "Sessions")

# ── Thresholds ─────────────────────────────────────────────────────────────────

# Shot enrichment: tracker timestamp must be within this many seconds of a PBP
# FGA event to count as a match.  Generous because we don't have clock sync.
_SHOT_MATCH_SEC   = 8.0

# Possession length heuristic: NBA averages ~14s per possession.
# We use it to estimate expected possession count from video coverage.
_AVG_POSS_SEC     = 14.0

# Grade thresholds
_GRADE = [
    (0.70, 0.70, 0.80, "A"),   # shot_recall, ball_det, stab
    (0.50, 0.55, 0.70, "B"),
    (0.30, 0.40, 0.60, "C"),
    (0.10, 0.25, 0.50, "D"),
]

# ── Helpers ─────────────────────────────────────────────────────────────────────

def _load_csv(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def _rate_limit() -> None:
    time.sleep(0.8)


# ── NBA API fetch helpers ──────────────────────────────────────────────────────

def _fetch_boxscore(game_id: str) -> Optional[dict]:
    """Return box score dict {player_name: {pts,reb,ast,fga,fgm,...}} from NBA API."""
    cache_path = os.path.join(_NBA_DIR, f"boxscore_{game_id}.json")
    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < 1800:   # 30-min TTL
            return _load_json(cache_path)

    def _to_int(v, default: int = 0) -> int:
        """Safe int conversion — handles NaN, None, empty string."""
        try:
            f = float(v)
            return default if (f != f) else int(f)  # NaN != NaN
        except (TypeError, ValueError):
            return default

    try:
        try:
            from nba_api.stats.endpoints import boxscoretraditionalv3
            _rate_limit()
            bs  = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id)
            dfs = bs.get_data_frames()
            player_df = dfs[0]
            col_map = {
                "PLAYER_NAME": "personName",
                "TEAM_ABBREVIATION": "teamTricode",
                "MIN": "minutes",
                "PTS": "points",
                "REB": "reboundsTotal",
                "AST": "assists",
                "FGA": "fieldGoalsAttempted",
                "FGM": "fieldGoalsMade",
                "FG3A": "threePointersAttempted",
                "FG3M": "threePointersMade",
                "STL": "steals",
                "BLK": "blocks",
                "TOV": "turnovers",
                "PLUS_MINUS": "plusMinusPoints",
            }
            # V3 uses firstName + familyName, not personName
            _get_name = lambda row: f"{row.get('firstName', '')} {row.get('familyName', '')}".strip()
            _get = lambda row, old, new, d="": row.get(new, row.get(old, d))
        except Exception:
            from nba_api.stats.endpoints import boxscoretraditionalv2
            _rate_limit()
            bs  = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
            dfs = bs.get_data_frames()
            player_df = dfs[0]
            col_map = {}  # use V2 column names directly
            _get_name = lambda row: str(row.get("PLAYER_NAME", "") or "")
            _get = lambda row, old, new, d="": row.get(old, d)

        result: dict = {}
        for _, row in player_df.iterrows():
            name = _get_name(row)
            if not name:
                continue
            result[name] = {
                "team_abbr":  str(_get(row, "TEAM_ABBREVIATION", "teamTricode", "") or ""),
                "min":        str(_get(row, "MIN", "minutes", "0") or "0"),
                "pts":        _to_int(_get(row, "PTS", "points", 0)),
                "reb":        _to_int(_get(row, "REB", "reboundsTotal", 0)),
                "ast":        _to_int(_get(row, "AST", "assists", 0)),
                "fga":        _to_int(_get(row, "FGA", "fieldGoalsAttempted", 0)),
                "fgm":        _to_int(_get(row, "FGM", "fieldGoalsMade", 0)),
                "fg3a":       _to_int(_get(row, "FG3A", "threePointersAttempted", 0)),
                "fg3m":       _to_int(_get(row, "FG3M", "threePointersMade", 0)),
                "stl":        _to_int(_get(row, "STL", "steals", 0)),
                "blk":        _to_int(_get(row, "BLK", "blocks", 0)),
                "tov":        _to_int(_get(row, "TOV", "turnovers", 0)),
                "plus_minus": _to_int(_get(row, "PLUS_MINUS", "plusMinusPoints", 0)),
            }
        os.makedirs(_NBA_DIR, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(result, f, indent=2)
        return result
    except Exception as e:
        print(f"  [WARN] boxscore fetch failed: {e}")
        return None


def _load_pbp(game_id: str) -> List[dict]:
    """Load PBP from bulk cache.  Returns list of raw event dicts."""
    path = os.path.join(_NBA_DIR, f"pbp_{game_id}.json")
    if not os.path.exists(path):
        return []
    return _load_json(path)


def _pbp_fga_events(pbp_raw: List[dict]) -> List[dict]:
    """Parse raw PBP rows into FGA events with absolute game seconds."""
    events = []
    for row in pbp_raw:
        etype = int(row.get("EVENTMSGTYPE", 0) or 0)
        if etype not in (1, 2):   # 1=made, 2=missed
            continue
        period = int(row.get("PERIOD", 1) or 1)
        clock  = str(row.get("PCTIMESTRING", "") or "")
        elapsed = 0
        if ":" in clock:
            try:
                mm, ss = clock.split(":")
                remaining = int(mm) * 60 + int(ss)
                period_len = 5 * 60 if period > 4 else 12 * 60
                elapsed = period_len - remaining
            except (ValueError, AttributeError):
                pass
        period_offset = sum(5 * 60 if q > 4 else 12 * 60 for q in range(1, period))
        player = str(row.get("PLAYER1_NAME", "") or "")
        desc   = str(row.get("HOMEDESCRIPTION", "") or row.get("VISITORDESCRIPTION", "") or "")
        events.append({
            "abs_game_sec": period_offset + elapsed,
            "period":       period,
            "gc_elapsed":   elapsed,
            "made":         int(etype == 1),
            "player":       player,
            "desc":         desc,
            "is_3pt":       int("3PT" in desc.upper() or "THREE" in desc.upper()),
        })
    return sorted(events, key=lambda e: e["abs_game_sec"])


# ── Core metrics ───────────────────────────────────────────────────────────────

def _compute_metrics(
    game_id:    str,
    manifest:   dict,
    shot_log:   List[dict],
    tracking:   List[dict],
    possessions: List[dict],
    ball_csv:   List[dict],
    pbp_raw:    List[dict],
    box_score:  Optional[dict],
) -> dict:
    """
    Return a metrics dict comparing tracker vs NBA ground truth.
    """
    fps     = float(manifest.get("fps_estimate", 30.0) or 30.0)
    n_frames = int(manifest.get("total_frames", 0) or 0)
    video_sec = n_frames / fps if fps > 0 else 0.0

    # ── PBP ground truth ───────────────────────────────────────────────────
    fga_events  = _pbp_fga_events(pbp_raw)
    n_fga       = len(fga_events)
    n_made      = sum(e["made"] for e in fga_events)
    n_missed    = n_fga - n_made
    n_3pt_att   = sum(e["is_3pt"] for e in fga_events)

    # Fraction of real game time covered by the video (rough: 48 min regulation)
    game_min_total = 48.0
    video_coverage = min(1.0, (video_sec / 60.0) / game_min_total) if video_sec > 0 else 0.0
    expected_shots = n_fga * video_coverage

    # ── Tracker shot metrics ───────────────────────────────────────────────
    n_tracked_shots = len(shot_log)
    # Shot recall: among PBP FGA events in the video window, how many did we catch?
    # Use a simple count ratio adjusted for coverage.
    shot_recall = (n_tracked_shots / expected_shots) if expected_shots > 0 else 0.0
    shot_recall = round(min(shot_recall, 1.0), 3)

    # Enrichment match rate: shots where made/missed is resolved
    n_enriched  = sum(1 for r in shot_log if r.get("made", "") not in ("", None))
    enrich_rate = round(n_enriched / n_tracked_shots, 3) if n_tracked_shots > 0 else 0.0

    # ── Ball detection ─────────────────────────────────────────────────────
    ball_det_pct = float(manifest.get("ball_detected_pct", 0.0) or 0.0)

    # ── Possession metrics ─────────────────────────────────────────────────
    n_possessions = len(possessions)
    expected_poss = (video_sec / _AVG_POSS_SEC) if video_sec > 0 else 0.0
    poss_recall   = round(min(n_possessions / expected_poss, 1.0), 3) if expected_poss > 0 else 0.0

    # ── Player tracking ────────────────────────────────────────────────────
    stability = float(manifest.get("stability", 0.0) or 0.0)
    id_switches = int(manifest.get("id_switches", 0) or 0)

    unique_players = len(set(r.get("player_id", "") for r in tracking))
    team_a_rows = sum(1 for r in tracking if r.get("team") == "green")
    team_b_rows = sum(1 for r in tracking if r.get("team") == "white")
    ref_rows    = sum(1 for r in tracking if r.get("team") == "referee")
    team_balance = round(min(team_a_rows, team_b_rows) / max(max(team_a_rows, team_b_rows), 1), 3)

    # Average players per frame
    if tracking:
        frames_seen = set(r.get("frame") for r in tracking)
        avg_players_per_frame = round(len(tracking) / max(len(frames_seen), 1), 2)
    else:
        avg_players_per_frame = 0.0

    # ── Shot location sanity (vs box score FGA) ────────────────────────────
    box_total_fga = sum(p.get("fga", 0) for p in (box_score or {}).values()) if box_score else 0
    box_fg_pct    = 0.0
    if box_score:
        box_fgm = sum(p.get("fgm", 0) for p in box_score.values())
        box_fg_pct = round(box_fgm / box_total_fga, 3) if box_total_fga > 0 else 0.0

    # ── Error identification ───────────────────────────────────────────────
    errors: List[str] = []

    if shot_recall < 0.30:
        errors.append(f"SHOT-RECALL LOW: tracker found only {n_tracked_shots} shots vs "
                      f"~{expected_shots:.0f} expected ({shot_recall*100:.0f}%)")
    if ball_det_pct < 50:
        errors.append(f"BALL-DETECTION LOW: {ball_det_pct:.1f}% frames — "
                      f"Hough params or CSRT drift may need tuning")
    if poss_recall < 0.25:
        errors.append(f"POSSESSION-RECALL LOW: {n_possessions} detected vs "
                      f"~{expected_poss:.0f} expected ({poss_recall*100:.0f}%) — "
                      f"possession classifier threshold too strict")
    if team_balance < 0.60:
        errors.append(f"TEAM-IMBALANCE: green={team_a_rows} white={team_b_rows} rows "
                      f"(balance={team_balance}) — HSV thresholds may misclassify one team")
    if unique_players < 8:
        errors.append(f"PLAYER-COUNT LOW: only {unique_players} unique IDs tracked "
                      f"(expected 10) — re-ID gallery TTL or lost-track threshold too strict")
    if avg_players_per_frame < 6:
        errors.append(f"AVG-PLAYERS LOW: {avg_players_per_frame:.1f}/frame "
                      f"— YOLO conf or NMS may need adjusting")
    if enrich_rate < 0.40 and n_tracked_shots > 0:
        errors.append(f"ENRICHMENT-MATCH LOW: only {enrich_rate*100:.0f}% of tracker shots "
                      f"matched a PBP event — clock sync or window (_SHOT_MATCH_SEC) too tight")
    if n_fga == 0:
        errors.append("PBP-MISSING: no FGA events found in cached PBP — run fetch for this game_id")

    # ── Grade ──────────────────────────────────────────────────────────────
    grade = "F"
    for sr_thr, bd_thr, stab_thr, g in _GRADE:
        if shot_recall >= sr_thr and ball_det_pct / 100 >= bd_thr and stability >= stab_thr:
            grade = g
            break

    return {
        "game_id":              game_id,
        "grade":                grade,
        "video_sec":            round(video_sec, 1),
        "video_coverage_pct":   round(video_coverage * 100, 1),
        "fps_estimate":         fps,
        "total_frames":         n_frames,
        # PBP ground truth
        "pbp_fga":              n_fga,
        "pbp_made":             n_made,
        "pbp_missed":           n_missed,
        "pbp_3pt_att":          n_3pt_att,
        "box_total_fga":        box_total_fga,
        "box_fg_pct":           box_fg_pct,
        # Tracker shots
        "shots_tracked":        n_tracked_shots,
        "shots_enriched":       n_enriched,
        "expected_shots":       round(expected_shots, 1),
        "shot_recall":          shot_recall,
        "enrich_rate":          enrich_rate,
        # Ball
        "ball_det_pct":         ball_det_pct,
        # Possessions
        "possessions_tracked":  n_possessions,
        "expected_poss":        round(expected_poss, 1),
        "poss_recall":          poss_recall,
        # Players
        "unique_players":       unique_players,
        "avg_players_per_frame": avg_players_per_frame,
        "stability":            stability,
        "id_switches":          id_switches,
        "team_balance":         team_balance,
        "team_a_rows":          team_a_rows,
        "team_b_rows":          team_b_rows,
        # Box score top players
        "top_scorers":          _top_scorers(box_score, n=5),
        "errors":               errors,
        "generated_at":         datetime.now().isoformat(),
    }


def _top_scorers(box_score: Optional[dict], n: int = 5) -> List[dict]:
    if not box_score:
        return []
    players = sorted(box_score.items(), key=lambda kv: kv[1].get("pts", 0), reverse=True)
    return [
        {"name": name, **{k: v for k, v in stats.items() if k in ("team_abbr","pts","reb","ast","fga","fgm")}}
        for name, stats in players[:n]
    ]


# ── Report writer ──────────────────────────────────────────────────────────────

def _write_report(metrics: List[dict], path: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# Full-Game Tracker Validation — {now}",
        f"",
        f"> Ground truth: NBA API play-by-play + box score",
        f"> Tracker: CV pipeline (YOLOv8n + SIFT homography + BallDetectTrack)",
        f"",
    ]

    for m in metrics:
        gid   = m["game_id"]
        grade = m["grade"]
        lines += [
            f"---",
            f"## Game {gid}  |  Grade: **{grade}**",
            f"",
            f"**Video:** {m['video_sec']:.0f}s ({m['video_coverage_pct']:.0f}% of 48-min game) "
            f"@ {m['fps_estimate']:.1f} fps  ·  {m['total_frames']:,} frames",
            f"",
            f"### Shot Detection vs NBA API",
            f"",
            f"| Metric | Tracker | NBA Ground Truth | Accuracy |",
            f"|--------|---------|-----------------|---------|",
            f"| FGA detected | {m['shots_tracked']} | {m['pbp_fga']} full game "
            f"(~{m['expected_shots']:.0f} in window) | **{m['shot_recall']*100:.0f}% recall** |",
            f"| FG% | — | {m['box_fg_pct']*100:.1f}% ({m['box_total_fga']} att) | box score ref |",
            f"| Shots enriched | {m['shots_enriched']}/{m['shots_tracked']} | — | "
            f"**{m['enrich_rate']*100:.0f}% match rate** |",
            f"| 3PT attempts | — | {m['pbp_3pt_att']} | — |",
            f"",
            f"### Ball & Possession Tracking",
            f"",
            f"| Metric | Tracker | Expected | Accuracy |",
            f"|--------|---------|---------|---------|",
            f"| Ball detection | {m['ball_det_pct']:.1f}% frames | 60%+ | "
            f"{'OK' if m['ball_det_pct']>=60 else 'LOW'} |",
            f"| Possessions | {m['possessions_tracked']} | ~{m['expected_poss']:.0f} | "
            f"**{m['poss_recall']*100:.0f}% recall** |",
            f"",
            f"### Player Tracking Quality",
            f"",
            f"| Metric | Value | Target |",
            f"|--------|-------|--------|",
            f"| Stability | {m['stability']:.3f} | ≥0.85 |",
            f"| ID switches | {m['id_switches']} | <5/min |",
            f"| Unique player IDs | {m['unique_players']} | 10 |",
            f"| Avg players/frame | {m['avg_players_per_frame']:.1f} | 8–10 |",
            f"| Team balance (green/white rows) | {m['team_a_rows']}/{m['team_b_rows']} "
            f"(ratio {m['team_balance']:.2f}) | ≥0.70 |",
            f"",
        ]

        if m.get("top_scorers"):
            lines += ["### Box Score (Top 5 Scorers — NBA API)", ""]
            lines += ["| Player | Team | PTS | REB | AST | FGA | FGM |",
                      "|--------|------|-----|-----|-----|-----|-----|"]
            for p in m["top_scorers"]:
                lines.append(
                    f"| {p['name']} | {p.get('team_abbr','')} | {p.get('pts',0)} "
                    f"| {p.get('reb',0)} | {p.get('ast',0)} | {p.get('fga',0)} | {p.get('fgm',0)} |"
                )
            lines.append("")

        if m["errors"]:
            lines += ["### Errors / Issues Found", ""]
            for e in m["errors"]:
                lines.append(f"- {e}")
            lines.append("")
        else:
            lines += ["### Errors / Issues Found", "", "None — all metrics within targets.", ""]

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nReport → {path}")


# ── Run pipeline helper ────────────────────────────────────────────────────────

def _run_pipeline(game_id: str) -> bool:
    """
    Invoke full_game_pipeline.py for a single game_id (already downloaded video).
    Uses low-usage settings: auto stride=3 kicks in for full games, no cap on frames.
    Returns True on success.
    """
    script = os.path.join(PROJECT_DIR, "scripts", "full_game_pipeline.py")
    video  = os.path.join(_DATA_DIR, "videos", "full_games", f"{game_id}.mp4")
    if not os.path.exists(video):
        print(f"  [SKIP] No video for {game_id}: {video}")
        return False

    import subprocess
    cmd = [
        sys.executable, script,
        "--game-id",    game_id,
        "--process-only",       # video already on disk — skip yt-dlp
        "--force",              # allow re-run even if prior success exists
        "--no-predictions",     # skip model stack; we only need tracking + enrichment
        "--hours", "6",         # cap total run time
    ]
    print(f"  [RUN] {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT_DIR)
    return result.returncode == 0


# ── Main ───────────────────────────────────────────────────────────────────────

def validate_game(game_id: str, run: bool = False) -> Optional[dict]:
    """Validate one game. Returns metrics dict or None on failure."""
    snap_dir = os.path.join(_GAMES_DIR, game_id)

    if run or not os.path.exists(snap_dir):
        print(f"\n[{game_id}] Running pipeline (low-usage)...")
        _run_pipeline(game_id)

    if not os.path.exists(snap_dir):
        print(f"  [SKIP] No snapshot for {game_id}")
        return None

    # Load manifest
    manifest_path = os.path.join(snap_dir, "manifest.json")
    manifest = _load_json(manifest_path) if os.path.exists(manifest_path) else {}

    # Check for stale snapshot (mixed runs): tracking and shot_log written >10 min apart
    _td_path  = os.path.join(snap_dir, "tracking_data.csv")
    _sl_path  = os.path.join(snap_dir, "shot_log.csv")
    if os.path.exists(_td_path) and os.path.exists(_sl_path):
        age_diff = abs(os.path.getmtime(_td_path) - os.path.getmtime(_sl_path))
        if age_diff > 600:
            print(f"  [WARN] Stale snapshot for {game_id}: tracking_data and shot_log "
                  f"differ by {age_diff/60:.0f} min — consider --run to refresh")

    # Load tracker outputs
    shot_log    = _load_csv(os.path.join(snap_dir, "shot_log.csv"))
    tracking    = _load_csv(os.path.join(snap_dir, "tracking_data.csv"))
    possessions = _load_csv(os.path.join(snap_dir, "possessions.csv"))
    ball_csv    = _load_csv(os.path.join(snap_dir, "ball_tracking.csv"))

    # Enrich from enriched files if available
    shot_log_enr = _load_csv(os.path.join(snap_dir, "shot_log_enriched.csv"))
    if shot_log_enr:
        shot_log = shot_log_enr

    print(f"\n[{game_id}] Loaded snapshot: {len(tracking)} tracking rows, "
          f"{len(shot_log)} shots, {len(possessions)} possessions")

    # Load NBA ground truth
    pbp_raw   = _load_pbp(game_id)
    box_score = _fetch_boxscore(game_id)

    if not pbp_raw:
        print(f"  [WARN] No PBP cache for {game_id}")
    if not box_score:
        print(f"  [WARN] Box score unavailable for {game_id}")

    fga_events = _pbp_fga_events(pbp_raw)
    print(f"  NBA API: {len(fga_events)} FGA events in PBP  |  "
          f"box score: {len(box_score or {})} players")

    metrics = _compute_metrics(
        game_id, manifest, shot_log, tracking, possessions, ball_csv, pbp_raw, box_score
    )

    # Save per-game validation JSON
    val_path = os.path.join(snap_dir, "validation.json")
    _save_json(val_path, metrics)
    print(f"  Saved → {val_path}")

    return metrics


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate tracker accuracy against NBA API")
    ap.add_argument("--game-id",  help="Single game ID to validate")
    ap.add_argument("--game-ids", nargs="+", help="Multiple game IDs")
    ap.add_argument("--all",      action="store_true",
                    help="Validate all games in data/games/")
    ap.add_argument("--run",      action="store_true",
                    help="Run pipeline before validating (low-usage, auto stride=3)")
    ap.add_argument("--output",   default=None,
                    help="Output report path (default: vault/Sessions/fullgame_summary_<date>.md)")
    args = ap.parse_args()

    # Gather game IDs
    if args.all:
        game_ids = [
            d for d in os.listdir(_GAMES_DIR)
            if os.path.isdir(os.path.join(_GAMES_DIR, d))
        ] if os.path.exists(_GAMES_DIR) else []
    elif args.game_ids:
        game_ids = args.game_ids
    elif args.game_id:
        game_ids = [args.game_id]
    else:
        ap.print_help()
        return

    if not game_ids:
        print("No game IDs found.")
        return

    print(f"\nValidating {len(game_ids)} game(s): {game_ids}")

    all_metrics: List[dict] = []
    for gid in game_ids:
        m = validate_game(gid, run=args.run)
        if m:
            all_metrics.append(m)
            # Print summary line
            print(
                f"\n  [{gid}] Grade={m['grade']}  "
                f"shots={m['shots_tracked']}/{m['pbp_fga']} FGA  "
                f"ball={m['ball_det_pct']:.0f}%  "
                f"poss={m['possessions_tracked']}/{m['expected_poss']:.0f}  "
                f"stab={m['stability']:.3f}  "
                f"players={m['unique_players']}"
            )
            if m["errors"]:
                for err in m["errors"]:
                    print(f"    ERROR: {err}")

    if not all_metrics:
        print("No metrics computed.")
        return

    # Write report
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = args.output or os.path.join(
        _VAULT_DIR, f"fullgame_summary_{date_str}.md"
    )
    _write_report(all_metrics, out_path)

    # Print aggregate
    n = len(all_metrics)
    avg_recall  = sum(m["shot_recall"]  for m in all_metrics) / n
    avg_ball    = sum(m["ball_det_pct"] for m in all_metrics) / n
    avg_stab    = sum(m["stability"]    for m in all_metrics) / n
    avg_poss    = sum(m["poss_recall"]  for m in all_metrics) / n
    grade_dist  = {}
    for m in all_metrics:
        grade_dist[m["grade"]] = grade_dist.get(m["grade"], 0) + 1

    print(f"\n{'='*60}")
    print(f"AGGREGATE  ({n} game(s))")
    print(f"  Shot recall:    {avg_recall*100:.1f}%")
    print(f"  Ball detection: {avg_ball:.1f}%")
    print(f"  Poss recall:    {avg_poss*100:.1f}%")
    print(f"  Stability:      {avg_stab:.3f}")
    print(f"  Grades:         {grade_dist}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
