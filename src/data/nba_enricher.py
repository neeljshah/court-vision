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
from typing import Dict, List, Optional

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
        from nba_api.stats.endpoints import playbyplayv3
    except ImportError:
        raise RuntimeError("nba_api not installed. Run: pip install nba_api")

    import re as _re

    # V3 actionType → legacy EVENTMSGTYPE int mapping
    _ACTION_TO_EVTYPE = {
        "Made Shot":    1,
        "Missed Shot":  2,
        "Free Throw":   3,
        "Rebound":      4,
        "Turnover":     5,
        "Foul":         6,
        "Substitution": 8,
    }

    _rate_limit()
    raw = playbyplayv3.PlayByPlayV3(
        game_id=game_id, start_period=period, end_period=period
    )
    try:
        df = raw.get_data_frames()[0]
    except (KeyError, IndexError) as _e:
        # NBA Stats API occasionally changes result key (resultSet vs resultSets).
        # Log actual keys then attempt manual parse of both shapes.
        try:
            import json as _json
            nj = _json.loads(raw.get_json())
            _avail = list(nj.keys())
            print(f"  [nba_enricher] PBP response keys: {_avail} — retrying manual parse ({_e})")
            _rs_list = nj.get("resultSets") or ([nj["resultSet"]] if "resultSet" in nj else [])
            if not _rs_list:
                raise RuntimeError(f"No resultSet(s) found. Available keys: {_avail}") from _e
            _rs   = _rs_list[0]
            _cols = _rs.get("headers", [])
            _rows = _rs.get("rowSet", [])
            import pandas as _pd
            df = _pd.DataFrame(_rows, columns=_cols)
        except Exception as _inner:
            raise RuntimeError(
                f"PBP API parse failed for game {game_id} p{period}. "
                f"Original error: {_e}. Inner: {_inner}"
            ) from _e
    df = df[df["period"] == period].copy()

    rows = []
    for _, r in df.iterrows():
        # V3 clock is ISO 8601 duration: "PT11M44.00S" = 11 min 44 sec remaining
        clock_str = str(r.get("clock", "PT12M00.00S"))
        try:
            m = _re.match(r"PT(\d+)M([\d.]+)S", clock_str)
            remaining = int(m.group(1)) * 60 + float(m.group(2)) if m else 0
            period_len_sec = 5 * 60 if period > 4 else 12 * 60
            elapsed = period_len_sec - remaining
        except Exception:
            elapsed = 0

        action = str(r.get("actionType", "") or "")
        sub    = str(r.get("subType",    "") or "")
        ev_type = 13 if (action == "period" and sub == "end") else _ACTION_TO_EVTYPE.get(action, 0)

        sh = str(r.get("scoreHome", "") or "")
        sa = str(r.get("scoreAway", "") or "")
        score  = f"{sh}-{sa}" if sh and sa else ""
        try:
            margin = str(int(sh) - int(sa)) if sh and sa else ""
        except Exception:
            margin = ""

        rows.append({
            "period":          int(r.get("period", period)),
            "game_clock_sec":  int(elapsed),
            "event_type":      ev_type,
            "event_desc":      str(r.get("description", "") or ""),
            "player_name":     str(r.get("playerName",  "") or ""),
            "team_abbrev":     str(r.get("teamTricode", "") or ""),
            "score":           score,
            "score_margin":    margin,
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


# ── Live mask builder ─────────────────────────────────────────────────────────

def build_live_mask(game_id: str, video_fps: float = 30.0) -> Dict[int, str]:
    """Build a frame-level live/dead-ball mask from cached PBP data.

    Loads data/nba/pbp_{game_id}.json (bulk NBA API raw format).
    Converts game-clock timestamps to approximate video frame numbers.
    Returns {frame_idx: "live" | "dead_ball" | "unknown"}.

    Classification rules:
      - "live":      frame is within 5s (±150 frames at 30fps) of a live-play event
                     (EVENTMSGTYPE in {1, 2, 3, 4, 5, 6})
      - "dead_ball": frame is >30s gap between consecutive live events
      - "unknown":   everything else (transitions, near dead-ball boundaries)

    Game-clock to frame mapping:
      Each period is 12 minutes (720 seconds). Period N starts at (N-1)*720*fps frames.
      game_clock_sec within a period = 720 - (remaining seconds from PCTIMESTRING).
      Frame ≈ (period_start_sec + game_clock_sec) * fps.

    Falls back to empty dict {} if cache file not found.

    Args:
        game_id:   NBA game ID (e.g. "0022200001").
        video_fps: Video frame rate (default 30.0 fps).

    Returns:
        Dict mapping frame_idx (int) to "live", "dead_ball", or "unknown".
        Returns {} if cache file not found or no events could be parsed.
    """
    _LIVE_EVENT_TYPES = {1, 2, 3, 4, 5, 6}
    events: List[tuple] = []  # list of (frame_idx, is_live: bool)

    # Prefer per-period cache files (data/nba/pbp_{game_id}_p{N}.json).
    # These are created by fetch_playbyplay() and already have game_clock_sec parsed.
    # Bulk files (pbp_{game_id}.json) from the PBP scraper lack PCTIMESTRING so
    # every event maps to frame 0, making the mask useless.
    found_any_period = False
    for period in range(1, 5):
        period_cache = _cache_path(f"pbp_{game_id}_p{period}")
        if not os.path.exists(period_cache):
            continue
        try:
            rows = _load_json(period_cache)
        except Exception:
            continue
        found_any_period = True
        for row in rows:
            evt_type  = int(row.get("event_type", 0) or 0)
            p         = int(row.get("period", period) or period)
            gc_sec    = int(row.get("game_clock_sec", 0) or 0)
            total_sec = (p - 1) * 720 + gc_sec
            events.append((int(total_sec * video_fps), evt_type in _LIVE_EVENT_TYPES))

    if not found_any_period:
        # Fall back to bulk file — only works if it contains PCTIMESTRING
        cache_path = os.path.join(_NBA_CACHE, f"pbp_{game_id}.json")
        if not os.path.exists(cache_path):
            return {}
        try:
            raw = _load_json(cache_path)
        except Exception:
            return {}
        for row in raw:
            evt_type  = int(row.get("EVENTMSGTYPE", 0) or 0)
            period    = int(row.get("PERIOD", 1) or 1)
            clock_str = str(row.get("PCTIMESTRING", "") or "")
            if not clock_str or ":" not in clock_str:
                continue
            try:
                mm, ss = clock_str.split(":")
                remaining_sec = int(mm) * 60 + int(ss)
            except (ValueError, AttributeError):
                continue
            elapsed_in_period = 720 - remaining_sec
            total_elapsed_sec = (period - 1) * 720 + elapsed_in_period
            events.append((int(total_elapsed_sec * video_fps), evt_type in _LIVE_EVENT_TYPES))

    if not events:
        return {}

    events.sort(key=lambda x: x[0])

    # Build frame mask — mark ±150 frames around live events as "live"
    _LIVE_RADIUS_FRAMES = int(5 * video_fps)   # 5 seconds
    _DEAD_GAP_FRAMES    = int(30 * video_fps)  # 30-second gap → dead_ball

    mask: Dict[int, str] = {}

    # Mark live zones around each live-play event
    for frame_idx, is_live in events:
        if is_live:
            for f in range(max(0, frame_idx - _LIVE_RADIUS_FRAMES),
                           frame_idx + _LIVE_RADIUS_FRAMES + 1):
                mask[f] = "live"

    # Mark dead_ball zones in large gaps between consecutive live events
    live_frames = sorted(fi for fi, il in events if il)
    for i in range(len(live_frames) - 1):
        gap = live_frames[i + 1] - live_frames[i]
        if gap > _DEAD_GAP_FRAMES:
            gap_start = live_frames[i] + _LIVE_RADIUS_FRAMES
            gap_end   = live_frames[i + 1] - _LIVE_RADIUS_FRAMES
            for f in range(gap_start, gap_end):
                if f not in mask:
                    mask[f] = "dead_ball"

    # Everything else is "unknown" — caller uses mask.get(frame_idx, "unknown")
    return mask


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
        fieldnames = list(shots[0].keys())
        # Write back in-place so shot_log.csv has populated `made` column
        with open(shot_log_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(shots)
        # Also write _enriched.csv for backward compatibility
        with open(out_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(shots)
    print(f"  Shot log enriched  -> {shot_log_path} (also {os.path.basename(out_path)})")
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
        # Write back in-place so possessions.csv has populated result/outcome_score/score_diff
        with open(possessions_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=all_keys)
            w.writeheader()
            w.writerows(possessions)
        # Also write _enriched.csv for backward compatibility
        with open(out_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=all_keys)
            w.writeheader()
            w.writerows(possessions)
    print(f"  Possessions enriched -> {possessions_path} (also {os.path.basename(out_path)})")
    return out_path


def _infer_clip_start_sec(data_dir: str, max_rows: int = 200) -> Optional[float]:
    """
    Auto-calibrate clip_start_sec from ball_tracking.csv.

    Scans the first `max_rows` rows of data_dir/ball_tracking.csv for the
    lowest timestamp where detected=1 (the ball is first visible).  That
    timestamp is the video offset at which live gameplay started.

    Returns clip_start_sec = -clip_start_offset  (negative when clip starts
    before the period, positive when clip starts mid-period).  Returns None
    when ball_tracking.csv doesn't exist or the ball is never detected.
    """
    ball_csv = os.path.join(data_dir, "ball_tracking.csv")
    if not os.path.exists(ball_csv):
        return None
    try:
        first_detected_ts: Optional[float] = None
        with open(ball_csv, newline="") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i >= max_rows:
                    break
                if str(row.get("detected", "0")) == "1":
                    ts = float(row.get("timestamp", 0))
                    if first_detected_ts is None or ts < first_detected_ts:
                        first_detected_ts = ts
        if first_detected_ts is not None:
            # clip_start_sec = -(offset where game starts in video)
            # period_elapsed = clip_start_sec + video_ts
            #                = video_ts - first_detected_ts  ✓
            return round(-first_detected_ts, 2)
    except Exception:
        pass
    return None


def _infer_fps(data_dir: str, default: float = 30.0) -> float:
    """
    Infer clip frame rate from ball_tracking.csv.

    Computes fps = last_frame / last_timestamp using the final detected row.
    Falls back to ``default`` when the file is absent or timestamps are unusable.
    """
    ball_csv = os.path.join(data_dir, "ball_tracking.csv")
    if not os.path.exists(ball_csv):
        return default
    try:
        last_frame: Optional[float] = None
        last_ts:    Optional[float] = None
        with open(ball_csv, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    f_val = float(row.get("frame",     0))
                    t_val = float(row.get("timestamp", 0))
                except (ValueError, TypeError):
                    continue
                if f_val > 0 and t_val > 0:
                    last_frame = f_val
                    last_ts    = t_val
        if last_frame and last_ts and last_ts > 0:
            fps = last_frame / last_ts
            # Snap to nearest common frame rate if within 3%
            common_rates = (24.0, 25.0, 29.97, 30.0, 50.0, 59.94, 60.0, 120.0)
            nearest = min(common_rates, key=lambda c: abs(fps - c))
            if abs(fps - nearest) / nearest < 0.03:
                return nearest
            return round(fps, 2)
    except Exception:
        pass
    return default


def _infer_period_count(data_dir: str) -> tuple:
    """
    Infer how many periods the clip covers from ball_tracking.csv.

    Scans all rows for the last timestamp where detected=1.
    Divides by 720 to estimate how many 12-minute periods the clip spans.

    Returns:
        (periods: List[int], max_ts: float)
          periods = [1]          for max_ts < 720s
          periods = [1,2]        for 720s ≤ max_ts < 1440s
          periods = [1,2,3]      for 1440s ≤ max_ts < 2160s
          periods = [1,2,3,4]    for max_ts ≥ 2160s
          max_ts = last detected timestamp (0.0 if ball never detected)
    """
    ball_csv = os.path.join(data_dir, "ball_tracking.csv")
    if not os.path.exists(ball_csv):
        return [1], 0.0
    try:
        max_ts: Optional[float] = None
        with open(ball_csv, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if str(row.get("detected", "0")) == "1":
                    try:
                        ts = float(row.get("timestamp", 0))
                    except (ValueError, TypeError):
                        continue
                    if max_ts is None or ts > max_ts:
                        max_ts = ts
        if max_ts is None:
            return [1], 0.0
        n_periods = min(int(max_ts / 720) + 1, 4)
        return list(range(1, n_periods + 1)), max_ts
    except Exception:
        return [1], 0.0


def enrich(
    game_id: str,
    period: int = 1,
    clip_start_sec: float = 0.0,
    fps: float = 30.0,
    data_dir: str = None,
    periods: List[int] = None,
) -> dict:
    """
    Full enrichment pipeline.

    Fetches play-by-play, enriches shot_log.csv and possessions.csv.

    Args:
        game_id:        NBA Stats game ID (e.g. "0022301234")
        period:         Quarter the clip covers (1-4). Ignored when ``periods``
                        is provided.
        clip_start_sec: Seconds into the period when the clip starts (single-
                        period mode). For full-game mode (periods=[1,2,3,4])
                        set to 0 — shot timestamps are already absolute.
        fps:            Clip frame rate (used to convert frame numbers to seconds)
        data_dir:       Override default data/ directory
        periods:        List of period numbers to fetch (e.g. [1,2,3,4] for a
                        full game). When supplied, game_clock_sec for each event
                        is normalised to absolute game time so the enrichment
                        functions match correctly with clip_start_sec=0.

    Returns:
        Dict with paths to enriched output files.
    """
    d = data_dir or _DATA

    # Auto-calibrate clip_start_sec when caller didn't specify one.
    # Derives offset from first ball-detected timestamp in ball_tracking.csv.
    # Skipped in full-game mode (periods list) since timestamps are already absolute.
    if clip_start_sec == 0.0 and periods is None:
        inferred = _infer_clip_start_sec(d)
        if inferred is not None and inferred != 0.0:
            print(f"  [enrichment] Auto-calibrated clip_start_sec={inferred:.1f}s "
                  f"(from ball_tracking.csv first detected frame)")
            clip_start_sec = inferred

    if periods is not None:
        # ── Full-game mode: fetch all requested periods and normalise timestamps ──
        print(f"\nEnriching data for game {game_id} · periods {periods} · "
              f"clip_start={clip_start_sec:.0f}s")
        pbp: List[dict] = []
        for p in periods:
            p_rows = fetch_playbyplay(game_id, p)
            # Convert game_clock_sec (elapsed within period) to absolute game time
            # so enrich_shot_log / enrich_possessions can match against a tracker
            # timestamp that is already measured from the start of the broadcast.
            period_offset = sum(
                (5 * 60 if q > 4 else 12 * 60) for q in range(1, p)
            )
            for row in p_rows:
                row = dict(row)
                row["game_clock_sec"] = period_offset + int(row.get("game_clock_sec", 0) or 0)
                pbp.append(row)
        print(f"  Play-by-play: {len(pbp)} events across periods {periods}")
    else:
        # ── Single-period mode (original behaviour) ───────────────────────────
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
    ap.add_argument("--game-id",  default=None,           help="NBA game ID, e.g. 0022301234")
    ap.add_argument("--period",   type=int,   default=1,  help="Quarter (1-4)")
    ap.add_argument("--start",    type=float, default=0.0,
                    help="Seconds elapsed in the period when the clip starts")
    ap.add_argument("--fps",      type=float, default=30.0)
    ap.add_argument("--data-dir", default=None,
                    help="Directory containing shot_log.csv (default: data/). "
                         "Use data/tracking/<game_id>/ to re-enrich a processed game.")
    ap.add_argument("--backfill", action="store_true",
                    help="Re-enrich all processed games in data/tracking/ using "
                         "auto-calibrated clip_start_sec from ball_tracking.csv.")
    args = ap.parse_args()

    if args.backfill:
        _tracking_dir = os.path.join(PROJECT_DIR, "data", "tracking")
        if not os.path.isdir(_tracking_dir):
            print(f"data/tracking/ not found: {_tracking_dir}")
        else:
            for gid in sorted(os.listdir(_tracking_dir)):
                gdir = os.path.join(_tracking_dir, gid)
                if not os.path.isdir(gdir):
                    continue
                if not os.path.exists(os.path.join(gdir, "shot_log.csv")):
                    print(f"  {gid}: skipped (no shot_log.csv)")
                    continue
                print(f"\n{'='*60}\n  Backfilling {gid}\n{'='*60}")
                try:
                    periods, max_ts = _infer_period_count(gdir)
                    clip_fps = _infer_fps(gdir, default=args.fps)
                    if len(periods) == 1:
                        print(f"  {gid}: single-period (clip ends at {max_ts:.0f}s, fps={clip_fps})")
                        enrich(
                            game_id=gid,
                            period=1,
                            clip_start_sec=0.0,   # auto-calibration fires when 0
                            fps=clip_fps,
                            data_dir=gdir,
                        )
                    else:
                        print(f"  {gid}: multi-period {periods} (clip ends at {max_ts:.0f}s, fps={clip_fps})")
                        enrich(
                            game_id=gid,
                            periods=periods,
                            clip_start_sec=0.0,   # timestamps are absolute in full-game clips
                            fps=clip_fps,
                            data_dir=gdir,
                        )
                except Exception as exc:
                    print(f"  {gid}: enrichment failed — {exc}")
    else:
        if not args.game_id:
            ap.error("--game-id is required unless --backfill is used")
        enrich(
            game_id        = args.game_id,
            period         = args.period,
            clip_start_sec = args.start,
            fps            = args.fps,
            data_dir       = args.data_dir,
        )
