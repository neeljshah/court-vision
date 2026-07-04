"""scripts.platformkit.espn_wp_backfill_measure -- one-shot BACKFILL of ESPN win-prob
series for recently-completed games + a three-way MEASUREMENT (our model_prob vs
espn_wp vs venue price, against outcome) on the overlap with our own capture corpus.

STRICT RAIL: same as espn_wp_reference -- ESPN WP here is an EXTERNAL REFERENCE ONLY,
never blended into our probabilities, never used for placement. Output is a printed
Brier comparison table (or an honest INSUFFICIENT_DATA verdict) -- measurement only.

Ticker resolution: our own capture files under data/cache/ingame_grade/<sport>/ use
either a raw ESPN numeric event id ("401815820.jsonl") or a Kalshi-style ticker
("KXMLBGAME-26JUL011310TEXCLE.jsonl" = date 2026-07-01, teams TEX@CLE, i.e. the
ticker's trailing letters == away_abbr + home_abbr concatenated with NO separator,
verified against ESPN's own scoreboard for that date). This module resolves a
ticker to its ESPN event id via one scoreboard lookup per unique date (bounded,
~1s paced), then reuses espn_wp_reference for the summary fetch + WP extraction.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from scripts.platformkit.espn_wp_reference import (
    SUPPORTED_SPORTS, _UA, fetch_summary, build_asof_series, get_outcome,
)

_REPO = Path(__file__).resolve().parents[2]
_PACE_SEC = 1.0
_MIN_OVERLAP = 20  # games needed per segment before we trust a Brier number

_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
           "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
_TICKER_RE = re.compile(r"^KX[A-Z]+GAME-(\d{2})([A-Z]{3})(\d{2})(\d{4})([A-Z]+)$")


def parse_ticker(name: str) -> Optional[Tuple[str, str]]:
    """Parse a Kalshi-style ticker filename stem -> (yyyymmdd, team_suffix), or
    None if it's already a raw numeric ESPN event id (caller uses it directly)."""
    m = _TICKER_RE.match(name)
    if not m:
        return None
    yy, mon, dd, _hhmm, suffix = m.groups()
    month = _MONTHS.get(mon)
    if month is None:
        return None
    yyyymmdd = f"20{yy}{month:02d}{dd}"
    return yyyymmdd, suffix


def resolve_event_id(sport: str, yyyymmdd: str, team_suffix: str) -> Optional[str]:
    """One ESPN scoreboard lookup for a date; match the event whose away+home
    abbreviation concat equals team_suffix. Returns the ESPN numeric event id."""
    espn_sport = SUPPORTED_SPORTS.get(sport)
    if espn_sport is None:
        return None
    url = f"https://site.api.espn.com/apis/site/v2/sports/{espn_sport}/scoreboard?dates={yyyymmdd}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError):
        return None
    for e in data.get("events", []):
        comps = e.get("competitions", [{}])[0].get("competitors", [])
        abbr = {c.get("homeAway"): c.get("team", {}).get("abbreviation") for c in comps}
        concat = f"{abbr.get('away','')}{abbr.get('home','')}"
        if concat == team_suffix:
            return e.get("id")
    return None


def list_capture_games(sport: str) -> List[str]:
    d = _REPO / "data" / "cache" / "ingame_grade" / sport
    if not d.exists():
        return []
    return sorted(os.path.basename(f)[:-6] for f in glob.glob(str(d / "*.jsonl")))


def backfill_sport(sport: str, limit: int = 50) -> Dict:
    """Resolve every capture-corpus game's ESPN event id (if not already numeric),
    fetch its WP series, and write the as-of series sidecar. Returns counters."""
    names = list_capture_games(sport)[:limit]
    n_ok, n_skip, event_ids = 0, 0, []
    date_cache: Dict[Tuple[str, str], Optional[str]] = {}
    for name in names:
        if name.isdigit():
            event_id = name
        else:
            parsed = parse_ticker(name)
            if parsed is None:
                n_skip += 1
                continue
            yyyymmdd, suffix = parsed
            key = (yyyymmdd, suffix)
            if key not in date_cache:
                date_cache[key] = resolve_event_id(sport, yyyymmdd, suffix)
                time.sleep(_PACE_SEC)
            event_id = date_cache[key]
        if event_id is None:
            n_skip += 1
            continue
        summary = fetch_summary(sport, event_id)
        time.sleep(_PACE_SEC)
        if summary is None:
            n_skip += 1
            continue
        series = build_asof_series(summary)
        if not series:
            n_skip += 1
            continue
        out_dir = _REPO / "data" / "domains" / sport / "espn_wp"
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / f"{event_id}_series.json", "w", encoding="utf-8") as f:
            json.dump({"event_id": event_id, "capture_name": name, "series": series,
                       "outcome": get_outcome(summary)}, f)
        n_ok += 1
        event_ids.append(event_id)
    return {"sport": sport, "n_resolved": n_ok, "n_skipped": n_skip, "event_ids": event_ids}


def _brier(preds: List[float], outcomes: List[int]) -> Optional[float]:
    if not preds:
        return None
    return sum((p - y) ** 2 for p, y in zip(preds, outcomes)) / len(preds)


def _nearest_prior(series: List[Dict], ts: str) -> Optional[Dict]:
    """Nearest WP series point with wallclock <= ts (never look ahead)."""
    best = None
    for pt in series:
        if pt["wallclock"] <= ts:
            best = pt
        else:
            break
    return best


def measure_mlb() -> Dict:
    """Three-way Brier (our model_prob vs espn_wp vs venue price) on the overlap
    between data/cache/ingame_grade/mlb/ ticks and backfilled espn_wp series,
    joined via wallclock (WP point strictly <= tick ts; never a future point)."""
    grade_dir = _REPO / "data" / "cache" / "ingame_grade" / "mlb"
    wp_dir = _REPO / "data" / "domains" / "mlb" / "espn_wp"
    if not grade_dir.exists() or not wp_dir.exists():
        return {"verdict": "INSUFFICIENT_DATA", "reason": "no capture or no backfilled wp series"}

    our_preds, espn_preds, venue_preds, outcomes = [], [], [], []
    n_games_used = 0
    for series_path in glob.glob(str(wp_dir / "*_series.json")):
        with open(series_path, encoding="utf-8") as f:
            blob = json.load(f)
        outcome = blob.get("outcome")
        series = blob.get("series") or []
        capture_name = blob.get("capture_name")
        if outcome is None or not series or capture_name is None:
            continue
        y = 1 if outcome.get("home_win") else 0
        tick_path = grade_dir / f"{capture_name}.jsonl"
        if not tick_path.exists():
            continue
        used_this_game = 0
        with open(tick_path, encoding="utf-8") as f:
            for line in f:
                try:
                    tick = json.loads(line)
                except ValueError:
                    continue
                ts = tick.get("ts")
                if not ts:
                    continue
                wp_point = _nearest_prior(series, ts)
                if wp_point is None:
                    continue  # never use a future WP point
                our_preds.append(float(tick.get("model_prob", float("nan"))))
                espn_preds.append(wp_point["home_win_pct"])
                venue_preds.append(float(tick.get("market_prob", float("nan"))))
                outcomes.append(y)
                used_this_game += 1
        if used_this_game:
            n_games_used += 1

    n = len(outcomes)
    if n < _MIN_OVERLAP:
        return {"verdict": "INSUFFICIENT_DATA", "n_overlap_ticks": n,
                "n_games": n_games_used, "floor": _MIN_OVERLAP}
    return {
        "verdict": "MEASURED",
        "n_overlap_ticks": n,
        "n_games": n_games_used,
        "brier_our_model": _brier(our_preds, outcomes),
        "brier_espn_wp": _brier(espn_preds, outcomes),
        "brier_venue": _brier(venue_preds, outcomes),
    }


def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sport", default="mlb", choices=sorted(SUPPORTED_SPORTS))
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--measure-only", action="store_true")
    args = ap.parse_args()
    result = {}
    if not args.measure_only:
        result["backfill"] = backfill_sport(args.sport, limit=args.limit)
    if args.sport == "mlb":
        result["measurement"] = measure_mlb()
    else:
        result["measurement"] = {"verdict": "INSUFFICIENT_DATA",
                                  "reason": f"no {args.sport} capture corpus on disk"}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
