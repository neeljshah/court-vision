"""scripts.platformkit.espn_wp_reference -- ESPN win-probability EXTERNAL REFERENCE ingest.

STRICT RAIL: this module is an EXTERNAL REFERENCE MODEL used ONLY to MEASURE our
model against a third party. Its outputs are NEVER copied into our probabilities,
NEVER blended into a live model_prob, and NEVER used to place or size a bet. It is
a comparison corpus only (our model_prob vs ESPN WP vs venue price vs outcome).

SCOUT-VERIFIED COVERAGE (probed live 2026-07-03 against site.api.espn.com):
  - MLB  (baseball/mlb):        summary?event={id} HAS winprobability[] (verified,
                                 87 points on event 401815820) + plays[] with wallclock.
  - WNBA (basketball/wnba):     summary?event={id} HAS winprobability[] (verified,
                                 361 points on event 401857037) + plays[] with wallclock.
  - NBA (basketball/nba):       summary?event={id} HAS winprobability[] (verified
                                 2026-07-04, 506 points + 506 plays on a completed
                                 2025-26 STATUS_FINAL event 401811026) -- added wave-22
                                 lane 5, same route shape as WNBA (both basketball/*).
  - soccer (soccer/{league}):   summary?event={id} has NO winprobability key at all
                                 (verified empty/absent on eng.1 event 401879301).
                                 SKIPPED -- recorded here, not fetched.
  - tennis:                     summary?event={id} returns HTTP 400 (no summary
                                 endpoint for tennis). SKIPPED per scout finding.

Sidecars: data/domains/<sport>/espn_wp/<event_id>.jsonl (append-only live snapshots).
This module does not touch data/registry/, does not flip flags, does not place bets.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Optional, Sequence

_REPO = Path(__file__).resolve().parents[2]
_UA = "Mozilla/5.0 (compatible; courtvision-research/1.0)"
_PACE_SEC = 1.0

# Sports with a verified live winprobability[] feed. soccer/tennis intentionally absent.
SUPPORTED_SPORTS = {
    "mlb": "baseball/mlb",
    "wnba": "basketball/wnba",
    "nba": "basketball/nba",
}
UNSUPPORTED_SPORTS = {
    "soccer": "no winprobability[] key in summary response (verified empty 2026-07-03)",
    "tennis": "no summary?event endpoint (HTTP 400, verified 2026-07-03)",
}


def _sidecar_path(sport: str, event_id: str) -> Path:
    d = _REPO / "data" / "domains" / sport / "espn_wp"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{event_id}.jsonl"


def fetch_summary(sport: str, event_id: str, timeout: float = 10.0) -> Optional[Dict]:
    """Fetch the raw ESPN summary JSON for one event. Returns None on any failure
    (network error, non-2xx, bad JSON) -- caller decides how to handle absence."""
    espn_sport = SUPPORTED_SPORTS.get(sport)
    if espn_sport is None:
        return None
    url = f"https://site.api.espn.com/apis/site/v2/sports/{espn_sport}/summary?event={event_id}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError):
        return None


def extract_latest(sport: str, event_id: str, summary: Dict) -> Optional[Dict]:
    """Extract the compact latest-snapshot record: {event_id, ts, espn_wp_home,
    n_wp_points, last_play_id}. Returns None if winprobability[] is absent/empty."""
    wp = summary.get("winprobability") or []
    if not wp:
        return None
    last = wp[-1]
    meta = summary.get("meta", {}) or {}
    ts = meta.get("lastUpdatedAt") or _now_iso()
    return {
        "event_id": str(event_id),
        "sport": sport,
        "ts": ts,
        "espn_wp_home": float(last.get("homeWinPercentage", float("nan"))),
        "n_wp_points": len(wp),
        "last_play_id": last.get("playId"),
    }


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_asof_series(summary: Dict) -> List[Dict]:
    """Build a play-indexed as-of series joining winprobability[] to plays[] via
    playId==play.id, carrying each play's wallclock timestamp. Returns rows sorted
    by wallclock ascending: {play_id, wallclock, home_win_pct, home_score, away_score}.
    Rows whose playId has no matching play (missing wallclock) are dropped -- we
    refuse to fabricate a timestamp.
    """
    wp = summary.get("winprobability") or []
    plays = summary.get("plays") or []
    if not wp or not plays:
        return []
    play_by_id = {p.get("id"): p for p in plays if p.get("id") is not None}
    rows = []
    for point in wp:
        play_id = point.get("playId")
        play = play_by_id.get(play_id)
        if play is None or not play.get("wallclock"):
            continue
        rows.append({
            "play_id": play_id,
            "wallclock": play["wallclock"],
            "home_win_pct": float(point.get("homeWinPercentage", float("nan"))),
            "home_score": play.get("homeScore"),
            "away_score": play.get("awayScore"),
        })
    rows.sort(key=lambda r: r["wallclock"])
    return rows


def get_outcome(summary: Dict) -> Optional[Dict]:
    """Extract {home_win: bool, completed: bool} from header.competitions[0].
    Returns None if the game is not yet completed or structure is missing."""
    header = summary.get("header", {}) or {}
    comps = header.get("competitions") or []
    if not comps:
        return None
    comp = comps[0]
    competitors = comp.get("competitors") or []
    for c in competitors:
        if c.get("homeAway") == "home":
            winner = c.get("winner")
            if winner is None:
                return None
            return {"home_win": bool(winner), "completed": True}
    return None


def append_snapshot(sport: str, event_id: str, record: Dict) -> Path:
    """Append one snapshot record to the sidecar jsonl (idempotent-ish: this is a
    live capture log, duplicates across polling ticks are expected and harmless
    for the measurement script, which only ever needs the LATEST as-of series pull)."""
    path = _sidecar_path(sport, event_id)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return path


def capture_one(sport: str, event_id: str) -> Optional[Dict]:
    """Fetch + extract + append one live snapshot for one event. Returns the
    record written, or None if unsupported sport / no data available."""
    if sport in UNSUPPORTED_SPORTS:
        return None
    summary = fetch_summary(sport, event_id)
    if summary is None:
        return None
    record = extract_latest(sport, event_id, summary)
    if record is None:
        return None
    append_snapshot(sport, event_id, record)
    return record


def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sport", required=True,
                     choices=sorted(set(SUPPORTED_SPORTS) | set(UNSUPPORTED_SPORTS)))
    ap.add_argument("--event-id", required=True)
    args = ap.parse_args()
    if args.sport in UNSUPPORTED_SPORTS:
        print(json.dumps({
            "verdict": "SKIPPED",
            "sport": args.sport,
            "reason": UNSUPPORTED_SPORTS[args.sport],
        }))
        return
    rec = capture_one(args.sport, args.event_id)
    print(json.dumps(rec) if rec else json.dumps({"verdict": "NO_DATA", "sport": args.sport,
                                                    "event_id": args.event_id}))


if __name__ == "__main__":
    _cli()


# --------------------------------------------------------------------------- #
# WIRE SPEC (documented, NOT applied here -- future integration lane only).   #
# This module is standalone by design (lane rule: no shared capture/runner    #
# file may be edited this wave). To wire live capture into inplay_capture_    #
# loop.py, a future lane would ADD (never edit this file's logic) these       #
# additive lines to that runner's per-tick loop, guarded by a NEW env flag    #
# (default OFF) e.g. CV_ESPN_WP_REFERENCE=0:                                  #
#
#   from scripts.platformkit.espn_wp_reference import capture_one
#   if os.environ.get("CV_ESPN_WP_REFERENCE") == "1" and sport in ("mlb","wnba"):
#       capture_one(sport, event_id)   # best-effort; never raises; measurement-only
#
# This call is fire-and-forget (return value ignored by the runner), paced by
# the runner's own existing tick interval (no extra sleep needed since it rides
# the existing poll cadence). It writes ONLY to data/domains/<sport>/espn_wp/ --
# no registry write, no flag flip elsewhere, nothing touches bet placement.
# --------------------------------------------------------------------------- #
