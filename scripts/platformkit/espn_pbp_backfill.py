"""Fetch NBA play-by-play from the ESPN core API into the repo's EXISTING
``data/nba/pbp_<game_id>_p<period>.json`` layout (S314 step 1).

Why a new fetcher rather than ``scripts/fetch_pbp_backfill_fast.py``: probed
2026-09-07 from this host, ``stats.nba.com`` times out, ``cdn.nba.com`` returns
403 and ``site.api.espn.com`` returns an Akamai 403 "Access Denied"; only
``sports.core.api.espn.com`` answers 200.  Rows are written in the schema
``scripts/fetch_pbp_backfill_fast.py`` writes, so existing readers are unchanged:
``{period, game_clock_sec, event_type, event_desc, player_name, team_abbrev,
score, score_margin}`` with ``game_clock_sec`` ELAPSED in period and ``score``
formatted ``home-away``.

Additive only: an existing per-period file is never overwritten.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.request

CORE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_HDRS = {"User-Agent": _UA, "Accept": "application/json"}

# NBA tricode -> ESPN shortName token, where the two differ.
_ESPN_ALIAS = {"GSW": "GS", "NOP": "NO", "NYK": "NY", "SAS": "SA",
               "UTA": "UTAH", "WAS": "WSH"}

# ESPN play type text -> the event_type integers fetch_pbp_backfill_fast writes.
# Heuristic on type/text keywords; event_type is NOT load-bearing for clock
# alignment (period, clock, sequence and score are) -- see the S314 memo.
_EVTYPE_RULES = (
    ("end period", 13), ("end of period", 13), ("end game", 13),
    ("substitution", 8), ("free throw", 3), ("rebound", 4),
    ("foul", 6), ("turnover", 5), ("steal", 5), ("traveling", 5),
    ("bad pass", 5), ("lost ball", 5), ("offensive charge", 5),
)
_SHOT_WORDS = ("shot", "layup", "dunk", "jumper", "hook", "tip", "three point")


def _get(url, retries=3, pause=0.25):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=_HDRS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
            time.sleep(pause)
            return json.loads(body)
        except Exception as exc:  # transient network / rate limit
            last = exc
            time.sleep(pause * (attempt + 2))
    raise RuntimeError("ESPN core GET failed after %d tries: %s -- %s"
                       % (retries, url, last))


def _tok(tricode):
    return _ESPN_ALIAS.get(tricode.upper(), tricode.upper())


def resolve_event(date_yyyymmdd, home, away):
    """Return (event_id, shortnames_seen). Raises unless the match is UNIQUE."""
    listing = _get("%s/events?dates=%s" % (CORE, date_yyyymmdd))
    want = "%s @ %s" % (_tok(away), _tok(home))
    seen, hits = [], []
    for item in listing.get("items", []):
        ev = _get(item["$ref"])
        name = str(ev.get("shortName", ""))
        seen.append("%s=%s" % (ev.get("id"), name))
        if name.strip().upper() == want:
            hits.append(str(ev["id"]))
    if len(hits) != 1:
        raise RuntimeError("event match not unique for %s on %s: %r (saw %s)"
                           % (want, date_yyyymmdd, hits, seen))
    return hits[0], seen


def fetch_plays(event_id, page_size=1000):
    """All plays for an event, in source order, paged until exhausted."""
    url = "%s/events/%s/competitions/%s/plays?limit=%d" % (
        CORE, event_id, event_id, page_size)
    first = _get(url)
    plays = list(first.get("items", []))
    for page in range(2, int(first.get("pageCount", 1)) + 1):
        plays.extend(_get(url + "&page=%d" % page).get("items", []))
    return plays


def _ref_id(ref):
    match = re.search(r"/(\d+)\?", str(ref) or "")
    return match.group(1) if match else ""


def _resolve_names(plays):
    """(athlete_id -> lastName, team_id -> abbreviation) resolved once each."""
    athletes, teams = {}, {}
    for play in plays:
        tid = _ref_id((play.get("team") or {}).get("$ref"))
        if tid and tid not in teams:
            teams[tid] = str(_get("%s/seasons/2026/teams/%s" % (CORE, tid))
                             .get("abbreviation", ""))
        for part in play.get("participants") or []:
            aid = _ref_id((part.get("athlete") or {}).get("$ref"))
            if aid and aid not in athletes:
                rec = _get("%s/seasons/2026/athletes/%s" % (CORE, aid))
                athletes[aid] = str(rec.get("lastName")
                                    or rec.get("displayName") or "")
    return athletes, teams


def event_type_of(type_text, text, scoring):
    """Map an ESPN play to the integer event_type the local schema carries."""
    blob = ("%s %s" % (type_text, text)).lower()
    for needle, code in _EVTYPE_RULES:
        if needle in blob:
            return code
    if any(word in blob for word in _SHOT_WORDS):
        return 1 if scoring else 2
    return 0


def elapsed_sec(period, clock_remaining):
    """Seconds ELAPSED in the period -- the local schema's game_clock_sec."""
    period_len = 300 if int(period) > 4 else 720
    return int(round(period_len - float(clock_remaining)))


def to_period_rows(plays, athletes, teams):
    """Group mapped rows by period, preserving ESPN sequenceNumber order."""
    ordered = sorted(plays, key=lambda p: int(p.get("sequenceNumber") or 0))
    by_period = {}
    for play in ordered:
        period = int((play.get("period") or {}).get("number") or 0)
        if period <= 0:
            continue
        clock = (play.get("clock") or {}).get("value")
        if clock is None:
            continue
        home, away = play.get("homeScore"), play.get("awayScore")
        try:
            margin = str(int(home) - int(away))
            score = "%d-%d" % (int(home), int(away))
        except (TypeError, ValueError):
            score, margin = "", ""
        parts = play.get("participants") or []
        aid = _ref_id((parts[0].get("athlete") or {}).get("$ref")) if parts else ""
        by_period.setdefault(period, []).append({
            "period": period,
            "game_clock_sec": elapsed_sec(period, clock),
            "event_type": event_type_of(
                str((play.get("type") or {}).get("text", "")),
                str(play.get("text") or ""),
                bool(play.get("scoringPlay"))),
            "event_desc": str(play.get("text") or ""),
            "player_name": athletes.get(aid, ""),
            "team_abbrev": teams.get(_ref_id((play.get("team") or {}).get("$ref")), ""),
            "score": score,
            "score_margin": margin,
        })
    return by_period


def write_periods(game_id, by_period, out_dir):
    """Write per-period files. Refuses to overwrite an existing file."""
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for period, rows in sorted(by_period.items()):
        path = os.path.join(out_dir, "pbp_%s_p%d.json" % (game_id, period))
        if os.path.exists(path):
            raise RuntimeError("refusing to overwrite existing file: %s" % path)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(rows, handle)
        written.append(path)
    return written


def backfill(game_id, date_yyyymmdd, home, away, out_dir):
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    event_id, seen = resolve_event(date_yyyymmdd, home, away)
    plays = fetch_plays(event_id)
    athletes, teams = _resolve_names(plays)
    by_period = to_period_rows(plays, athletes, teams)
    written = write_periods(game_id, by_period, out_dir)
    return {
        "game_id": game_id, "espn_event_id": event_id, "date": date_yyyymmdd,
        "home": home, "away": away, "source_host": "sports.core.api.espn.com",
        "plays_url": "%s/events/%s/competitions/%s/plays?limit=1000"
                     % (CORE, event_id, event_id),
        "events_url": "%s/events?dates=%s" % (CORE, date_yyyymmdd),
        "as_of_utc": started, "n_plays": len(plays),
        "rows_by_period": {str(k): len(v) for k, v in sorted(by_period.items())},
        "files": [p.replace(os.sep, "/") for p in written],
        "candidates_on_date": seen,
    }


def main():
    ap = argparse.ArgumentParser(description="S314 ESPN core-API PBP backfill")
    ap.add_argument("--game", action="append", required=True,
                    metavar="GID:YYYYMMDD:HOME:AWAY")
    ap.add_argument("--out-dir", default=os.path.join("data", "nba"))
    ap.add_argument("--provenance", help="write the provenance JSON here")
    args = ap.parse_args()
    records = []
    for spec in args.game:
        gid, date, home, away = spec.split(":")
        try:
            rec = backfill(gid, date, home, away, args.out_dir)
        except Exception as exc:
            rec = {"game_id": gid, "date": date, "home": home, "away": away,
                   "error": "%s: %s" % (type(exc).__name__, exc)}
        records.append(rec)
        print(json.dumps(rec))
    if args.provenance:
        os.makedirs(os.path.dirname(args.provenance) or ".", exist_ok=True)
        with open(args.provenance, "w", encoding="utf-8") as handle:
            json.dump(records, handle, indent=1)


if __name__ == "__main__":
    main()
