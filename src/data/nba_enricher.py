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
# R8: Second-pass widening — clock-drift cases (auto-calibrated clip_start_sec mis-fires,
# or scoreboard mapper had < 5 anchors) drift up to ~8s before becoming unmatchable.
_SHOT_MATCH_WINDOW_SEC_2 = 8.0
# How many seconds of slop for matching possession end to API possession events
# Raised 5.0→10.0 (ISSUE B): 0022401156 had 52% match rate at 5s; wider window
# catches clock drift without losing precision since PBP events are sparse (~2/min).
_POSS_MATCH_WINDOW_SEC = 10.0
# Second-pass fallback for possessions still unmatched after the primary window
_POSS_MATCH_WINDOW_SEC_2 = 15.0


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

def _parse_game_clock(s: str) -> float:
    """Parse "M:SS" or "MM:SS" or "S.S" game-clock string to seconds remaining.

    Returns None on failure.
    """
    if not s:
        return None
    s = str(s).strip()
    if not s or s.lower() in ("none", "nan", ""):
        return None
    try:
        if ":" in s:
            parts = s.split(":")
            mins = int(parts[0])
            secs = float(parts[1])
            return mins * 60.0 + secs
        return float(s)
    except (ValueError, TypeError):
        return None


def _build_video_to_pbp_mapper(data_dir: str, fps: float = 30.0):
    """Build a piecewise-linear mapper from video time (seconds) to PBP elapsed game time.

    Uses scoreboard_log.csv (frame, game_clock, period?, confidence) to derive:
      - period boundaries (game_clock reset from < 30s to > 700s)
      - per-frame PBP time = period_offset + (period_length - clock_remaining)

    Returns:
        (mapper, anchors) where:
          mapper(video_sec: float) -> Optional[float]   piecewise-linear PBP time
          anchors: list[(video_sec, pbp_sec, period)]   raw anchors used
        Returns (None, []) if scoreboard data is insufficient.

    The mapper enables shot/possession matching across periods even when
    halftime + timeouts make clip_start_sec unreliable as a single offset.
    """
    sb_csv = os.path.join(data_dir, "scoreboard_log.csv")
    if not os.path.exists(sb_csv):
        return None, []

    raw_rows = []
    try:
        with open(sb_csv, newline="") as f:
            for row in csv.DictReader(f):
                try:
                    fr = int(float(row.get("frame", 0)))
                    conf = float(row.get("confidence", 0) or 0)
                except (ValueError, TypeError):
                    continue
                if conf < 0.6:
                    continue
                clk = _parse_game_clock(row.get("game_clock", ""))
                if clk is None or clk < 0 or clk > 750:
                    continue
                per_str = str(row.get("period", "")).strip()
                per = None
                if per_str and per_str.lower() not in ("none", "nan"):
                    try:
                        per = int(float(per_str))
                        if per < 1 or per > 8:
                            per = None
                    except (ValueError, TypeError):
                        per = None
                raw_rows.append((fr, clk, per))
    except Exception:
        return None, []

    if len(raw_rows) < 5:
        return None, []

    raw_rows.sort(key=lambda r: r[0])

    # Filter single-row OCR outliers: a row's clock must not deviate by more than
    # 60s from BOTH neighbors. (Two consecutive rows tend to be within 1-2s
    # of each other in real OCR; large bidirectional spikes are misreads.)
    if len(raw_rows) >= 5:
        filtered_raw = [raw_rows[0]]
        for i in range(1, len(raw_rows) - 1):
            fr, clk, per = raw_rows[i]
            pfr, pclk, _ = raw_rows[i-1]
            nfr, nclk, _ = raw_rows[i+1]
            # Drop if this row is wildly off from both neighbors AND neighbors agree
            if abs(clk - pclk) > 120 and abs(clk - nclk) > 120 and abs(pclk - nclk) < 60:
                continue
            filtered_raw.append((fr, clk, per))
        filtered_raw.append(raw_rows[-1])
        raw_rows = filtered_raw

    # Infer period number by detecting clock resets.
    # Two kinds of period boundary:
    #   1. Tight reset: clock was near 0, then jumped to near 720 (typical)
    #   2. Sparse reset: scoreboard wasn't read in the final 60s of a period --
    #      we just see a large positive jump (clk - prev_clk > 500)
    # NBA periods reset to 12:00 = 720, so a +500 jump is unambiguous.
    cur_period = raw_rows[0][2] if raw_rows[0][2] else 1
    prev_clk = raw_rows[0][1]
    anchors = []  # (frame, video_sec, pbp_sec, period)

    for fr, clk, per_seen in raw_rows:
        if per_seen and per_seen >= cur_period:
            cur_period = per_seen
        else:
            # Any positive jump >= 500s = period reset (clock can only INCREASE
            # at period boundaries; mid-period it counts down).
            if clk - prev_clk >= 500:
                cur_period = min(cur_period + 1, 8)
        prev_clk = clk
        period_len = 5 * 60 if cur_period > 4 else 12 * 60
        elapsed_in_period = period_len - clk
        if elapsed_in_period < 0:
            elapsed_in_period = 0
        period_offset = sum(
            (5 * 60 if q > 4 else 12 * 60) for q in range(1, cur_period)
        )
        pbp_sec = period_offset + elapsed_in_period
        video_sec = fr / max(1.0, fps)
        anchors.append((video_sec, pbp_sec, cur_period))

    if not anchors:
        return None, []

    # Robust filter: drop anchors whose pbp_sec deviates strongly from the
    # MEDIAN of a local window. This handles OCR misreads in BOTH directions
    # (forward and backward jumps) without trapping the mapper at a single
    # bad reading. Window = +-10 anchors (~20s of video in dense regions).
    filtered = []
    win = 10
    sorted_anchors = sorted(anchors, key=lambda a: a[0])
    for i, a in enumerate(sorted_anchors):
        lo = max(0, i - win)
        hi = min(len(sorted_anchors), i + win + 1)
        window_pbp = sorted(b[1] for b in sorted_anchors[lo:hi])
        med = window_pbp[len(window_pbp)//2]
        # Tolerance: allow +-30s deviation from window median (OCR noise + real progression)
        if abs(a[1] - med) <= 30.0:
            filtered.append(a)
    if len(filtered) < 3:
        filtered = anchors  # fall back if filter killed too many

    # Quality check: refuse to build a mapper when scoreboard data is too sparse
    # or too uniform (OCR returned the same clock value repeatedly -- common when
    # a frame artifact is being misread as a clock).
    # Threshold lowered from < 20 to < 5: sparse OCR (e.g. 6 rows for game
    # 0022500757) is still better than no mapper at all; the linear clip_start_sec
    # fallback is broken for full-game broadcasts past halftime.
    if len(filtered) < 5:
        return None, []
    pbp_vals_unique = len(set(int(a[1]) for a in filtered))
    video_span = filtered[-1][0] - filtered[0][0] if len(filtered) > 1 else 0
    # Secondary quality checks scale with anchor count: if we have few anchors
    # (5-19), relax uniqueness and span requirements proportionally so sparse
    # OCR (e.g. 6 rows from game 0022500757) still builds a useful mapper.
    _min_unique = min(10, max(3, len(filtered) // 2))
    _min_span   = 600 if len(filtered) >= 20 else 60
    if pbp_vals_unique < _min_unique or video_span < _min_span:
        return None, []

    # Build sorted unique-video-sec anchor arrays for fast interpolation.
    filtered.sort(key=lambda a: a[0])
    vs_arr  = [a[0] for a in filtered]
    ps_arr  = [a[1] for a in filtered]
    per_arr = [a[2] for a in filtered]

    # Slopes for extrapolation beyond anchor range (defaults near 1.0).
    if len(vs_arr) >= 5:
        # Slope at start: use first 5 anchors
        _v0, _v1 = vs_arr[0], vs_arr[min(4, len(vs_arr)-1)]
        _p0, _p1 = ps_arr[0], ps_arr[min(4, len(vs_arr)-1)]
        _slope_start = (_p1 - _p0) / (_v1 - _v0) if _v1 != _v0 else 1.0
        # Slope at end: use last 5 anchors
        _v0e, _v1e = vs_arr[max(0, len(vs_arr)-5)], vs_arr[-1]
        _p0e, _p1e = ps_arr[max(0, len(vs_arr)-5)], ps_arr[-1]
        _slope_end = (_p1e - _p0e) / (_v1e - _v0e) if _v1e != _v0e else 1.0
        # Clamp slopes to sane range (game time can't compress faster than 1x or slower than 0.2x)
        _slope_start = max(0.2, min(1.0, _slope_start))
        _slope_end   = max(0.2, min(1.0, _slope_end))
    else:
        _slope_start = _slope_end = 1.0

    def mapper(video_sec: float):
        if video_sec is None:
            return None
        if video_sec <= vs_arr[0]:
            # Linear extrapolate backward from first anchor
            v = ps_arr[0] - (vs_arr[0] - video_sec) * _slope_start
            return max(0.0, v)
        if video_sec >= vs_arr[-1]:
            # Linear extrapolate forward from last anchor (capped at last pbp + 60s)
            v = ps_arr[-1] + (video_sec - vs_arr[-1]) * _slope_end
            return min(ps_arr[-1] + 60.0, v)
        import bisect
        i = bisect.bisect_left(vs_arr, video_sec)
        if i == 0:
            return ps_arr[0]
        v0, v1 = vs_arr[i-1], vs_arr[i]
        p0, p1 = ps_arr[i-1], ps_arr[i]
        if v1 == v0:
            return p0
        # Clamp dt: if anchors are >120s apart (broadcast went dead -- halftime, etc.),
        # linear interp may bridge a discontinuity. Cap interpolation distance.
        if v1 - v0 > 120.0:
            # Use nearest anchor instead of linear interp
            return p0 if (video_sec - v0) < (v1 - video_sec) else p1
        t = (video_sec - v0) / (v1 - v0)
        return p0 + t * (p1 - p0)

    return mapper, filtered


def _build_pbp_to_video_mapper(anchors):
    """Inverse of _build_video_to_pbp_mapper.

    anchors = list of (video_sec, pbp_sec, period) as returned by
    _build_video_to_pbp_mapper.  Builds a piecewise-linear function
    pbp_sec → video_sec so that pbp_fill frame numbers are computed
    from PBP game-clock time rather than from the game-clock value
    treated as if it were video time (which is wrong).

    Returns None when anchors is empty.
    """
    if not anchors:
        return None
    # Sort by pbp_sec, build piecewise-linear pbp→video mapping
    pairs = sorted([(a[1], a[0]) for a in anchors])
    pbp_arr = [p[0] for p in pairs]
    vid_arr = [p[1] for p in pairs]

    def mapper(pbp_sec):
        import bisect
        if pbp_sec <= pbp_arr[0]:
            return vid_arr[0]
        if pbp_sec >= pbp_arr[-1]:
            return vid_arr[-1]
        i = bisect.bisect_left(pbp_arr, pbp_sec)
        v0, v1 = vid_arr[i - 1], vid_arr[i]
        p0, p1 = pbp_arr[i - 1], pbp_arr[i]
        if p1 == p0:
            return v0
        t = (pbp_sec - p0) / (p1 - p0)
        return v0 + t * (v1 - v0)

    return mapper


def _best_global_offset(tracker_ts, fg_times, window, search=600.0, step=1.0):
    """Self-calibrating fallback: find a global time offset Δ maximizing matches.

    When the video→PBP mapper is absent or the auto-calibrated ``clip_start_sec``
    is wrong, the naive offset can leave a game with ~0 matched shots (63 games
    were stuck at zero PBP recall, 2026-05-30). This slides tracker timestamps
    across ±``search`` seconds and returns the offset giving the most shots
    within ``window`` of a PBP FG event, plus that match count. Caller decides
    whether the peak clears a spurious-fit guard before applying it.

    Returns (best_delta_sec, best_match_count).
    """
    if not tracker_ts or not fg_times:
        return 0.0, 0
    fg_sorted = sorted(fg_times)

    def _count(delta):
        m = 0
        for t in tracker_ts:
            x = t + delta
            i = bisect.bisect_left(fg_sorted, x)
            best = window + 1.0
            for j in (i - 1, i):
                if 0 <= j < len(fg_sorted):
                    d = abs(fg_sorted[j] - x)
                    if d < best:
                        best = d
            if best <= window:
                m += 1
        return m

    best_delta, best_m = 0.0, _count(0.0)
    n = int(search / step)
    for k in range(-n, n + 1):
        if k == 0:
            continue
        delta = k * step
        m = _count(delta)
        if m > best_m:
            best_m, best_delta = m, delta
    return best_delta, best_m


def enrich_shot_log(
    pbp: List[dict],
    shot_log_path: str,
    clip_start_sec: float,
    fps: float = 30.0,
    video_to_pbp=None,
) -> str:
    """
    Fill in the `made` column in shot_log.csv.

    Matches each tracked shot (by timestamp) to the nearest NBA made/missed
    FG event within _SHOT_MATCH_WINDOW_SEC.

    Also computes shots_pbp_coverage = PBP recall: fraction of real PBP FG
    events that were captured by at least one tracker shot within the window.
    This is written as a single-value column (same value on every row) so the
    audit script can read it from the first row.

    Returns path to enriched file.
    """
    if not os.path.exists(shot_log_path):
        print(f"  shot_log not found: {shot_log_path}")
        return shot_log_path

    with open(shot_log_path, newline="", encoding="utf-8", errors="replace") as f:
        shots = list(csv.DictReader(f))

    if not shots:
        return shot_log_path

    # Only FG events (made=1, missed=2)
    fg_events = [e for e in pbp if e["event_type"] in (1, 2)]

    # Resolve timestamp converter: use piecewise-linear mapper when available,
    # otherwise fall back to simple linear offset (clip_start_sec + video_ts).
    _ts_convert = video_to_pbp if video_to_pbp is not None else (
        lambda v: clip_start_sec + v
    )

    # Build tracker timestamp list for recall computation
    tracker_ts = []
    max_tracker_ts = 0.0
    for shot in shots:
        try:
            ts = _ts_convert(float(shot.get("timestamp", 0)))
            tracker_ts.append(ts)
            if ts > max_tracker_ts:
                max_tracker_ts = ts
        except (ValueError, TypeError):
            pass

    # --- Shot-side matching: label each tracker shot with made/missed ---
    # R8: two-pass — primary ±4s, fallback ±8s for clock-drift cases (mirrors
    # the second-pass approach already used in enrich_possessions for possessions).
    _unmatched_pass1 = []
    for shot in shots:
        try:
            ts = _ts_convert(float(shot.get("timestamp", 0)))
        except (ValueError, TypeError):
            continue
        best_ev, best_dt = None, _SHOT_MATCH_WINDOW_SEC + 1
        for ev in fg_events:
            dt = abs(ev["game_clock_sec"] - ts)
            if dt < best_dt:
                best_dt = dt
                best_ev = ev
        if best_ev is not None and best_dt <= _SHOT_MATCH_WINDOW_SEC:
            shot["made"] = int(best_ev["event_type"] == 1)
        else:
            shot["made"] = ""
            _unmatched_pass1.append((shot, ts))

    # Second pass: ±8s for the still-unmatched shots
    if _unmatched_pass1:
        _pass2_hits = 0
        for shot, ts in _unmatched_pass1:
            best_ev, best_dt = None, _SHOT_MATCH_WINDOW_SEC_2 + 1
            for ev in fg_events:
                dt = abs(ev["game_clock_sec"] - ts)
                if dt < best_dt:
                    best_dt = dt
                    best_ev = ev
            if best_ev is not None and best_dt <= _SHOT_MATCH_WINDOW_SEC_2:
                shot["made"] = int(best_ev["event_type"] == 1)
                _pass2_hits += 1
        print(f"  Shot match pass2 (±{_SHOT_MATCH_WINDOW_SEC_2}s): {_pass2_hits}/{len(_unmatched_pass1)} recovered")

    # --- Self-calibrating global-offset fallback for broken alignment ---
    # When the video→PBP mapper is absent/wrong, the naive clip_start_sec offset
    # can leave a game with near-zero matched shots (63 games at zero recall on
    # 2026-05-30). If coverage is poor, search for a global Δ that maximizes
    # tracker↔PBP matches and re-label. Guarded to avoid spurious fits: needs
    # >= 4 tracker shots and a match count that clears a margin over baseline.
    _matched = sum(1 for s in shots if str(s.get("made", "")).strip() in ("0", "1"))
    if shots and (_matched / len(shots)) < 0.30 and len(tracker_ts) >= 4:
        fg_times = [ev["game_clock_sec"] for ev in fg_events]
        delta, m_off = _best_global_offset(
            tracker_ts, fg_times, _SHOT_MATCH_WINDOW_SEC
        )
        if delta != 0.0 and m_off >= max(4, _matched + 3):
            print(f"  [shot-align] low coverage ({_matched}/{len(shots)} matched); "
                  f"applying global offset Δ={delta:+.0f}s → {m_off} matches "
                  f"within ±{_SHOT_MATCH_WINDOW_SEC:.0f}s")
            for shot in shots:
                try:
                    ts = _ts_convert(float(shot.get("timestamp", 0))) + delta
                except (ValueError, TypeError):
                    continue
                best_ev, best_dt = None, _SHOT_MATCH_WINDOW_SEC_2 + 1
                for ev in fg_events:
                    dt = abs(ev["game_clock_sec"] - ts)
                    if dt < best_dt:
                        best_dt, best_ev = dt, ev
                if best_ev is not None and best_dt <= _SHOT_MATCH_WINDOW_SEC_2:
                    shot["made"] = int(best_ev["event_type"] == 1)
            # Shift tracker timestamps so PBP recall reflects corrected alignment
            tracker_ts = [t + delta for t in tracker_ts]
            max_tracker_ts = max(tracker_ts) if tracker_ts else max_tracker_ts

    # --- PBP recall: what fraction of real FG events did the tracker capture? ---
    # Only consider PBP events that fall within the video's range (with a small buffer)
    # to avoid penalizing recall for events that tracker couldn't possibly see.
    relevant_fg = [e for e in fg_events if e["game_clock_sec"] <= (max_tracker_ts + 5.0)]
    
    pbp_matched = 0
    for ev in relevant_fg:
        pbp_t = ev["game_clock_sec"]
        if any(abs(t - pbp_t) <= _SHOT_MATCH_WINDOW_SEC for t in tracker_ts):
            pbp_matched += 1

    recall = pbp_matched / len(relevant_fg) if relevant_fg else 0.0
    print(f"  PBP recall (relevant): {pbp_matched}/{len(relevant_fg)} = {recall:.2%} "
          f"(total video FG: {len(fg_events)}, tracker shots: {len(tracker_ts)})")

    out_path = shot_log_path.replace(".csv", "_enriched.csv")
    if shots:
        fieldnames = list(shots[0].keys())
        # Ensure shots_pbp_coverage column exists
        if "shots_pbp_coverage" not in fieldnames:
            fieldnames.append("shots_pbp_coverage")
        # Write PBP recall into every row so audit script can read it
        for shot in shots:
            shot["shots_pbp_coverage"] = round(recall, 4)
        # Write back in-place
        with open(shot_log_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(shots)
        # Also write _enriched.csv for backward compatibility
        with open(out_path, "w", newline="", encoding="utf-8") as f:
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
    video_to_pbp=None,
    v2p_anchors=None,
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

    with open(possessions_path, newline="", encoding="utf-8", errors="replace") as f:
        possessions = list(csv.DictReader(f))

    if not possessions:
        return possessions_path

    # Resolve timestamp converter: piecewise-linear mapper or linear fallback
    _ts_convert = video_to_pbp if video_to_pbp is not None else (
        lambda v: clip_start_sec + v
    )

    # BUG 2 fix: build inverse mapper (pbp_sec → video_sec) for computing
    # pbp_fill frame numbers correctly.  Without this, fill rows were setting
    # end_frame = int(game_clock_sec * fps), treating PBP game-clock time as
    # video time — wrong for any broadcast with halftime or clock drift.
    _pbp_to_video = _build_pbp_to_video_mapper(v2p_anchors or [])

    # Build score-margin lookup: game_clock_sec → score_margin
    scored_events  = [e for e in pbp if e["event_type"] in (1, 2, 5, 6)]
    scoring_events = [e for e in pbp if e["event_type"] == 1 and e.get("score_margin") not in ("", None)]

    for poss in possessions:
        # BUG 2 fix: pbp_fill rows are already synthetic — skip re-match so
        # pbp_matched is never overwritten to False on a second enrichment pass.
        if poss.get("source") == "pbp_fill":
            continue

        try:
            end_f = int(poss.get("end_frame", 0))
            poss_end_sec = _ts_convert(end_f / max(1.0, fps))
        except (ValueError, TypeError):
            continue

        # BUG 4 fix: reject tracker artifacts with absurdly long duration.
        # Any real NBA possession is at most 24s (shot-clock) plus a few seconds
        # of clock-running disagreement between tracker and PBP timestamps.
        # A duration > 60s is a clip-boundary artifact — refuse to match.
        try:
            _dur = float(poss.get("duration_sec", 0) or 0)
        except (ValueError, TypeError):
            _dur = 0.0
        if _dur > 60.0:
            poss["result"]        = "unknown"
            poss["outcome_score"] = ""
            poss["pbp_play_type"] = ""
            poss["pbp_score_home"] = ""
            poss["pbp_score_away"] = ""
            poss["pbp_period"]    = ""
            poss["pbp_matched"]   = False
            continue

        best_ev, best_dt = None, _POSS_MATCH_WINDOW_SEC + 1
        for ev in scored_events:
            dt = abs(ev["game_clock_sec"] - poss_end_sec)
            if dt < best_dt:
                best_dt = dt
                best_ev = ev

        # FIX 6: helper to parse "score_home-score_away" from event "score" field
        def _parse_scores(ev: dict):
            """Return (home_score, away_score) or ("", "")."""
            sc = str(ev.get("score", "") or "")
            if "-" in sc:
                parts = sc.split("-", 1)
                try:
                    return int(parts[0]), int(parts[1])
                except (ValueError, TypeError):
                    pass
            return "", ""

        if best_ev is not None and best_dt <= _POSS_MATCH_WINDOW_SEC:
            etype = best_ev["event_type"]
            desc  = best_ev.get("event_desc", "").lower()
            if etype == 1:
                pts  = 3 if "3pt" in desc or "three" in desc else 2
                poss["result"]        = "scored"
                poss["outcome_score"] = pts
                # FIX 6: pbp play type
                poss["pbp_play_type"] = "made_3" if pts == 3 else "made_2"
            elif etype == 2:
                poss["result"]        = "missed_shot"
                poss["outcome_score"] = 0
                poss["pbp_play_type"] = "missed_3" if "3pt" in desc else "missed_2"
            elif etype == 3:
                poss["result"]        = "free_throw"
                poss["outcome_score"] = 1 if "makes" in desc else 0
                poss["pbp_play_type"] = "free_throw"
            elif etype == 5:
                poss["result"]        = "turnover"
                poss["outcome_score"] = 0
                poss["pbp_play_type"] = "turnover"
            elif etype == 6:
                poss["result"]        = "foul"
                poss["outcome_score"] = 0
                poss["pbp_play_type"] = "foul"
            else:
                poss["pbp_play_type"] = ""
            # FIX 6: pbp scores (only meaningful for scoring plays)
            if etype == 1:  # made FG — score is definitive
                _sh, _sa = _parse_scores(best_ev)
                poss["pbp_score_home"] = _sh
                poss["pbp_score_away"] = _sa
            else:  # turnover/foul/missed — score at this moment is misleading
                poss["pbp_score_home"] = ""
                poss["pbp_score_away"] = ""
            poss["pbp_period"]     = best_ev.get("period", "")
            poss["pbp_matched"]    = True
        else:
            poss["result"]         = "unknown"
            poss["outcome_score"]  = ""
            # FIX 6: mark unmatched rows explicitly
            poss["pbp_play_type"]  = ""
            poss["pbp_score_home"] = ""
            poss["pbp_score_away"] = ""
            poss["pbp_period"]     = ""
            poss["pbp_matched"]    = False

        # Nearest score_margin at/before possession end
        margin = None
        for ev in reversed(scoring_events):
            if ev["game_clock_sec"] <= poss_end_sec:
                margin = _parse_score_margin(str(ev.get("score_margin", "")))
                break
        poss["score_diff"] = margin if margin is not None else ""

    # Second pass: ±15s fallback for possessions still unmatched after primary window.
    # Handles clock drift cases where tracker/PBP timestamps diverge by 10-15s.
    _n_pass2 = 0
    for poss in possessions:
        if poss.get("pbp_matched"):
            continue
        # BUG 2 fix: never attempt to re-match synthetic fill rows in pass 2 either.
        if poss.get("source") == "pbp_fill":
            continue
        # BUG 4 fix: phantom possessions (duration > 60s) are already marked False
        # in pass 1; skip them in pass 2 as well to prevent erroneous late matching.
        try:
            _dur2 = float(poss.get("duration_sec", 0) or 0)
        except (ValueError, TypeError):
            _dur2 = 0.0
        if _dur2 > 60.0:
            continue
        try:
            end_f = int(poss.get("end_frame", 0))
            poss_end_sec = _ts_convert(end_f / max(1.0, fps))
        except (ValueError, TypeError):
            continue
        best_ev2, best_dt2 = None, _POSS_MATCH_WINDOW_SEC_2 + 1
        for ev in scored_events:
            dt = abs(ev["game_clock_sec"] - poss_end_sec)
            if dt < best_dt2:
                best_dt2 = dt
                best_ev2 = ev
        if best_ev2 is None or best_dt2 > _POSS_MATCH_WINDOW_SEC_2:
            continue
        etype2 = best_ev2["event_type"]
        desc2  = best_ev2.get("event_desc", "").lower()
        if etype2 == 1:
            pts2 = 3 if "3pt" in desc2 or "three" in desc2 else 2
            poss["result"] = "scored"; poss["outcome_score"] = pts2
            poss["pbp_play_type"] = "made_3" if pts2 == 3 else "made_2"
            _sc2 = str(best_ev2.get("score", "") or "")
            if "-" in _sc2:
                _sp2 = _sc2.split("-", 1)
                try:
                    poss["pbp_score_home"] = int(_sp2[0]); poss["pbp_score_away"] = int(_sp2[1])
                except (ValueError, TypeError):
                    poss["pbp_score_home"] = poss["pbp_score_away"] = ""
            else:
                poss["pbp_score_home"] = poss["pbp_score_away"] = ""
        elif etype2 == 2:
            poss["result"] = "missed_shot"; poss["outcome_score"] = 0
            poss["pbp_play_type"] = "missed_3" if "3pt" in desc2 else "missed_2"
            poss["pbp_score_home"] = poss["pbp_score_away"] = ""
        elif etype2 == 3:
            poss["result"] = "free_throw"; poss["outcome_score"] = 1 if "makes" in desc2 else 0
            poss["pbp_play_type"] = "free_throw"
            poss["pbp_score_home"] = poss["pbp_score_away"] = ""
        elif etype2 == 5:
            poss["result"] = "turnover"; poss["outcome_score"] = 0
            poss["pbp_play_type"] = "turnover"
            poss["pbp_score_home"] = poss["pbp_score_away"] = ""
        elif etype2 == 6:
            poss["result"] = "foul"; poss["outcome_score"] = 0
            poss["pbp_play_type"] = "foul"
            poss["pbp_score_home"] = poss["pbp_score_away"] = ""
        else:
            poss["pbp_play_type"] = ""
            poss["pbp_score_home"] = poss["pbp_score_away"] = ""
        poss["pbp_period"] = best_ev2.get("period", "")
        poss["pbp_matched"] = True
        _n_pass2 += 1
    if _n_pass2:
        print(f"  Second-pass (±15s) matched: {_n_pass2} additional possessions")

    _total_matched = sum(1 for p in possessions if p.get("pbp_matched") is True)
    print(f"  enriched_pct: {_total_matched}/{len(possessions)} = {_total_matched / max(1, len(possessions)):.2%}")

    # ── PBP possession gap-fill ───────────────────────────────────────────────
    # When CV coverage is <50% of PBP possession-change events, synthesize
    # possession rows from PBP for events with no nearby CV possession.
    # This bridges the gap until CV tracking quality improves.
    _POSS_CHANGE_TYPES = {1, 2, 5}  # made FG, missed FG, turnover
    poss_change_events = [e for e in pbp if e["event_type"] in _POSS_CHANGE_TYPES]
    if poss_change_events:
        # Build a set of covered timestamps from existing CV possessions
        _cv_ts_set = set()
        for _p in possessions:
            try:
                _ef = int(_p.get("end_frame", 0))
                _ts = _ts_convert(_ef / max(1.0, fps))
                _cv_ts_set.add(_ts)
            except (ValueError, TypeError):
                pass

        _GAP_FILL_WINDOW = 3.0  # seconds: no CV possession within ±3s → fill
        _n_cv = len(possessions)
        _n_pbp_events = len(poss_change_events)
        _fill_rows = []

        # Gap-fill when CV coverage is <50% of PBP events, OR when
        # absolute possession count is suspiciously low for the clip size.
        # The second condition handles full-game broadcasts where _infer_period_count
        # previously returned [1] (ball only detected in Q1), so only ~50 PBP events
        # were loaded and 49 CV possessions wrongly appeared "sufficient".
        _poss_per_pbp_event = _n_cv / max(1, _n_pbp_events)
        _undercovered = _n_cv < 0.5 * _n_pbp_events or (
            _n_pbp_events >= 40 and _poss_per_pbp_event < 0.6
        )
        if _undercovered:
            _play_type_map = {1: "made_fg", 2: "missed_fg", 5: "turnover"}
            for _ev in poss_change_events:
                _ev_ts = float(_ev.get("game_clock_sec", 0))
                # Check if any CV possession covers this timestamp
                _covered = any(abs(_ts - _ev_ts) <= _GAP_FILL_WINDOW for _ts in _cv_ts_set)
                if not _covered:
                    # BUG 2 fix: use inverse mapper to convert PBP game-clock time
                    # to video seconds before multiplying by fps.  The old code used
                    # int(_ev_ts * fps) which treats PBP game-clock as video time —
                    # wrong for full-game broadcasts where halftime shifts timestamps
                    # by ~1200s relative to video.
                    if _pbp_to_video is not None:
                        _fill_vid_end = _pbp_to_video(_ev_ts)
                        _fill_vid_start = _pbp_to_video(max(0.0, _ev_ts - 12.0))
                    else:
                        _fill_vid_end = _ev_ts
                        _fill_vid_start = max(0.0, _ev_ts - 12.0)
                    _fill_rows.append({
                        "game_id":       "",  # not available from PBP alone
                        "team":          _ev.get("team_abbrev", ""),
                        "start_frame":   int(_fill_vid_start * fps),
                        "end_frame":     int(_fill_vid_end * fps),
                        "start_time":    _fill_vid_start,
                        "duration_sec":  12.0,
                        "pbp_matched":   True,
                        "pbp_play_type": _play_type_map.get(_ev["event_type"], ""),
                        "pbp_period":    _ev.get("period", ""),
                        "pbp_score_home": "",
                        "pbp_score_away": "",
                        "result":        _play_type_map.get(_ev["event_type"], "unknown"),
                        "outcome_score": 2 if _ev["event_type"] == 1 else 0,
                        "score_diff":    "",
                        "source":        "pbp_fill",
                        "is_stub":       True,   # Bug 26 fix 2026-05-28: explicit stub flag for downstream filters
                    })

            if _fill_rows:
                possessions.extend(_fill_rows)
                print(f"  PBP gap-fill: added {len(_fill_rows)} synthetic possessions "
                      f"(CV={_n_cv}, PBP_events={_n_pbp_events}, ratio={_poss_per_pbp_event:.2f})")

    # FIX 6: Build field list including new pbp columns
    out_path = possessions_path.replace(".csv", "_enriched.csv")
    if possessions:
        all_keys = list(possessions[0].keys())
        for _new_col in ("score_diff", "pbp_play_type", "pbp_score_home",
                         "pbp_score_away", "pbp_period", "pbp_matched", "source"):
            if _new_col not in all_keys:
                all_keys.append(_new_col)
        # Write back in-place so possessions.csv has all enriched columns
        with open(possessions_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
            w.writeheader()
            w.writerows(possessions)
        # Also write _enriched.csv (now has new columns — no longer identical)
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
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
        max_ts_any: Optional[float] = None  # max across ALL rows (not just detected)
        with open(ball_csv, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ts = float(row.get("timestamp", 0))
                except (ValueError, TypeError):
                    continue
                if max_ts_any is None or ts > max_ts_any:
                    max_ts_any = ts
                if str(row.get("detected", "0")) == "1":
                    if max_ts is None or ts > max_ts:
                        max_ts = ts
        # Use detected max_ts if available; fall back to full-clip duration.
        # This handles full-game broadcasts where ball isn't detected during
        # pre-game / halftime — the clip is still 2-3 hours long.
        effective_ts = max_ts if max_ts is not None else (max_ts_any if max_ts_any is not None else None)
        if effective_ts is None:
            return [1], 0.0
        # For full-game clips: if total clip duration >> detected max_ts
        # (e.g. ball only detected in Q1 due to pre-game starting the clip),
        # use total clip duration to determine period count.
        if max_ts_any is not None and max_ts is not None and max_ts_any > max_ts * 1.5:
            effective_ts = max_ts_any
        n_periods = min(int(effective_ts / 720) + 1, 4)
        return list(range(1, n_periods + 1)), effective_ts
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
    # Applied in both single-period and full-game mode: full-game clips still have
    # pre-game broadcast content before tipoff, so video timestamps need offsetting
    # to align with PBP game_clock_sec (which counts from actual game start).
    if clip_start_sec == 0.0:
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
            # q > 4 (strict) correctly identifies OT periods (Q5, Q6, …) as 5-min;
            # q >= 4 was wrong — it treated Q4 as a 5-min period, placing OT events
            # 420 seconds (7 minutes) too early.
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

    if not pbp:
        print(f"  [enrichment] WARNING: No PBP events returned for game {game_id} — "
              "skipping enrichment (tracking data is still complete).")
        return {}

    # ── Build video→PBP mapper when scoreboard_log.csv is present ────────────
    # Full-game broadcasts accumulate ~1200 s of error by Q3 when using a simple
    # linear offset because video timestamps include halftime.  The mapper reads
    # OCR scoreboard anchors to build a piecewise-linear correction.
    # Returns (None, []) when the file is absent or has insufficient anchors.
    video_to_pbp, _v2p_anchors = _build_video_to_pbp_mapper(d, fps=fps)
    if video_to_pbp is not None:
        print(f"  [enrichment] Built video→PBP mapper from {len(_v2p_anchors)} scoreboard anchors")
    else:
        print("  [enrichment] No video→PBP mapper (insufficient scoreboard data); using clip_start_sec fallback")

    results = {}
    results["shot_log_enriched"] = enrich_shot_log(
        pbp,
        os.path.join(d, "shot_log.csv"),
        clip_start_sec, fps,
        video_to_pbp=video_to_pbp,
    )
    results["possessions_enriched"] = enrich_possessions(
        pbp,
        os.path.join(d, "possessions.csv"),
        clip_start_sec, fps,
        video_to_pbp=video_to_pbp,
        v2p_anchors=_v2p_anchors,
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
