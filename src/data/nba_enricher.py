"""
nba_enricher.py — Label tracked data with official NBA play-by-play outcomes.

Takes the raw outputs from UnifiedPipeline (shot_log.csv, possessions.csv) and
cross-references them against the NBA Stats API to add:

  shot_log.csv     → made (1/0) column filled in
  possessions.csv  → result (scored/missed_shot/turnover/foul/unknown)
                   → outcome_score (1=points scored, 0=no score)
                   → score_diff (score differential at possession start)

Usage
-----
    from src.data.nba_enricher import enrich

    enrich(
        game_id       = "0022301234",   # NBA game ID
        period        = 1,              # which quarter the clip covers
        clip_start_sec = 420,           # seconds into the period when clip starts
        fps           = 30.0,
    )

    # Or from CLI:
    python -m src.data.nba_enricher --game-id 0022301234 --period 1 --start 420
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from typing import List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DATA       = os.path.join(PROJECT_DIR, "data")
_NBA_CACHE  = os.path.join(_DATA, "nba")

# How many seconds of slop to allow when matching tracker shot timing to API events
_SHOT_MATCH_WINDOW_SEC = 4.0
# How many seconds of slop for matching possession end to API possession events
_POSS_MATCH_WINDOW_SEC = 5.0


# ── NBA API helpers ───────────────────────────────────────────────────────────

def _rate_limit():
    time.sleep(0.6)


def _cache_path(key: str) -> str:
    os.makedirs(_NBA_CACHE, exist_ok=True)
    import re
    return os.path.join(_NBA_CACHE, re.sub(r"[^A-Za-z0-9_-]", "_", key) + ".json")


def _load_json(path: str):
    with open(path) as f:
        return json.load(f)


def _save_json(path: str, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def fetch_playbyplay(game_id: str, period: int) -> List[dict]:
    """
    Fetch NBA play-by-play for a specific period.

    Returns list of dicts with keys:
        period, game_clock_sec, event_type, event_desc,
        player_name, team_abbrev, score, score_margin
    """
    cache = _cache_path(f"pbp_{game_id}_p{period}")
    if os.path.exists(cache):
        cached = _load_json(cache)
        # Only trust the cache if the period fully completed (event_type 13 = period end).
        # A cache written mid-game has no period-end event and is permanently stale otherwise.
        if any(r.get("event_type") == 13 for r in cached):
            return cached

    try:
        from nba_api.stats.endpoints import playbyplay
    except ImportError:
        raise RuntimeError("nba_api not installed. Run: pip install nba_api")

    _rate_limit()
    pbp = playbyplay.PlayByPlay(game_id=game_id)
    df  = pbp.get_data_frames()[0]

    # Filter to requested period
    df = df[df["PERIOD"] == period].copy()

    # Event type codes:
    # 1=made FG, 2=missed FG, 3=FT, 4=rebound, 5=turnover, 6=foul, 8=substitution
    rows = []
    for _, r in df.iterrows():
        # NBA game clock is "MM:SS" remaining in the period
        clock_str = str(r.get("PCTIMESTRING", "12:00"))
        try:
            mm, ss = clock_str.split(":")
            remaining = int(mm) * 60 + int(ss)
            elapsed   = 12 * 60 - remaining   # seconds elapsed in period
        except Exception:
            elapsed = 0

        rows.append({
            "period":          int(r.get("PERIOD", period)),
            "game_clock_sec":  elapsed,
            "event_type":      int(r.get("EVENTMSGTYPE", 0)),
            "event_desc":      str(r.get("HOMEDESCRIPTION", "") or r.get("VISITORDESCRIPTION", "") or ""),
            "player_name":     str(r.get("PLAYER1_NAME", "") or ""),
            "score":           str(r.get("SCORE", "") or ""),
            "score_margin":    str(r.get("SCOREMARGIN", "") or ""),
        })

    _save_json(cache, rows)
    return rows


def _parse_score_margin(margin_str: str) -> Optional[int]:
    """Return integer score margin (home - away), or None if unavailable."""
    try:
        if margin_str in ("", "TIE", None):
            return 0
        return int(margin_str)
    except (ValueError, TypeError):
        return None


# ── Main enrichment functions ─────────────────────────────────────────────────

def enrich_shot_log(
    pbp: List[dict],
    shot_log_path: str,
    clip_start_sec: float,
    fps: float = 30.0,
) -> str:
    """
    Fill in the `made` column in shot_log.csv.

    Matches each tracked shot (by timestamp) to the nearest NBA made/missed
    FG event within _SHOT_MATCH_WINDOW_SEC.

    Returns path to enriched file.
    """
    if not os.path.exists(shot_log_path):
        print(f"  shot_log not found: {shot_log_path}")
        return shot_log_path

    with open(shot_log_path, newline="") as f:
        shots = list(csv.DictReader(f))

    if not shots:
        return shot_log_path

    # Only FG events (made=1, missed=2)
    fg_events = [e for e in pbp if e["event_type"] in (1, 2)]

    for shot in shots:
        try:
            ts = float(shot.get("timestamp", 0))
        except (ValueError, TypeError):
            continue
        # Convert tracker timestamp to period elapsed seconds
        period_elapsed = clip_start_sec + ts
        best_ev, best_dt = None, _SHOT_MATCH_WINDOW_SEC + 1

        for ev in fg_events:
            dt = abs(ev["game_clock_sec"] - period_elapsed)
            if dt < best_dt:
                best_dt = dt
                best_ev = ev

        if best_ev is not None and best_dt <= _SHOT_MATCH_WINDOW_SEC:
            shot["made"] = int(best_ev["event_type"] == 1)
        else:
            shot["made"] = ""   # no match found

    out_path = shot_log_path.replace(".csv", "_enriched.csv")
    if shots:
        with open(out_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(shots[0].keys()))
            w.writeheader()
            w.writerows(shots)
    print(f"  Shot log enriched  → {out_path}")
    return out_path


def enrich_possessions(
    pbp: List[dict],
    possessions_path: str,
    clip_start_sec: float,
    fps: float = 30.0,
) -> str:
    """
    Fill in `result` and `outcome_score` in possessions.csv.

    For each possession end timestamp, find the nearest play-by-play event:
      - made FG (type 1)  → result="scored",        outcome_score=2 or 3
      - missed FG (type 2) → result="missed_shot",   outcome_score=0
      - turnover (type 5) → result="turnover",       outcome_score=0
      - foul (type 6)     → result="foul",           outcome_score=0

    Also adds `score_diff` from the most recent scoring play at/before possession end.

    Returns path to enriched file.
    """
    if not os.path.exists(possessions_path):
        print(f"  possessions not found: {possessions_path}")
        return possessions_path

    with open(possessions_path, newline="") as f:
        possessions = list(csv.DictReader(f))

    if not possessions:
        return possessions_path

    # Build score-margin lookup: game_clock_sec → score_margin
    scored_events  = [e for e in pbp if e["event_type"] in (1, 2, 5, 6)]
    scoring_events = [e for e in pbp if e["event_type"] == 1 and e.get("score_margin") not in ("", None)]

    for poss in possessions:
        try:
            end_f = int(poss.get("end_frame", 0))
            poss_end_sec = clip_start_sec + end_f / max(1.0, fps)
        except (ValueError, TypeError):
            continue

        best_ev, best_dt = None, _POSS_MATCH_WINDOW_SEC + 1
        for ev in scored_events:
            dt = abs(ev["game_clock_sec"] - poss_end_sec)
            if dt < best_dt:
                best_dt = dt
                best_ev = ev

        if best_ev is not None and best_dt <= _POSS_MATCH_WINDOW_SEC:
            etype = best_ev["event_type"]
            if etype == 1:
                # Determine 2pt vs 3pt from description
                desc = best_ev.get("event_desc", "").lower()
                pts  = 3 if "3pt" in desc or "three" in desc else 2
                poss["result"]        = "scored"
                poss["outcome_score"] = pts
            elif etype == 2:
                poss["result"]        = "missed_shot"
                poss["outcome_score"] = 0
            elif etype == 5:
                poss["result"]        = "turnover"
                poss["outcome_score"] = 0
            elif etype == 6:
                poss["result"]        = "foul"
                poss["outcome_score"] = 0
        else:
            poss["result"]        = "unknown"
            poss["outcome_score"] = ""

        # Nearest score_margin at/before possession end
        margin = None
        for ev in reversed(scoring_events):
            if ev["game_clock_sec"] <= poss_end_sec:
                margin = _parse_score_margin(str(ev.get("score_margin", "")))
                break
        poss["score_diff"] = margin if margin is not None else ""

    out_path = possessions_path.replace(".csv", "_enriched.csv")
    if possessions:
        all_keys = list(possessions[0].keys())
        if "score_diff" not in all_keys:
            all_keys.append("score_diff")
        with open(out_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=all_keys)
            w.writeheader()
            w.writerows(possessions)
    print(f"  Possessions enriched → {out_path}")
    return out_path


def enrich(
    game_id: str,
    period: int = 1,
    clip_start_sec: float = 0.0,
    fps: float = 30.0,
    data_dir: str = None,
) -> dict:
    """
    Full enrichment pipeline.

    Fetches play-by-play, enriches shot_log.csv and possessions.csv.

    Args:
        game_id:        NBA Stats game ID (e.g. "0022301234")
        period:         Quarter the clip covers (1-4)
        clip_start_sec: Seconds into the period when the clip starts.
                        e.g. if clip starts at 8:30 left in Q1,
                        clip_start_sec = (12 - 8.5) * 60 = 210
        fps:            Clip frame rate (used to convert frame numbers to seconds)
        data_dir:       Override default data/ directory

    Returns:
        Dict with paths to enriched output files.
    """
    d = data_dir or _DATA
    print(f"\nEnriching data for game {game_id} · period {period} · "
          f"clip_start={clip_start_sec:.0f}s")

    pbp = fetch_playbyplay(game_id, period)
    print(f"  Play-by-play: {len(pbp)} events in period {period}")

    results = {}
    results["shot_log_enriched"] = enrich_shot_log(
        pbp,
        os.path.join(d, "shot_log.csv"),
        clip_start_sec, fps,
    )
    results["possessions_enriched"] = enrich_possessions(
        pbp,
        os.path.join(d, "possessions.csv"),
        clip_start_sec, fps,
    )
    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Enrich tracker outputs with NBA play-by-play")
    ap.add_argument("--game-id",  required=True,          help="NBA game ID, e.g. 0022301234")
    ap.add_argument("--period",   type=int,   default=1,  help="Quarter (1-4)")
    ap.add_argument("--start",    type=float, default=0.0,
                    help="Seconds elapsed in the period when the clip starts")
    ap.add_argument("--fps",      type=float, default=30.0)
    args = ap.parse_args()

    enrich(
        game_id        = args.game_id,
        period         = args.period,
        clip_start_sec = args.start,
        fps            = args.fps,
    )
