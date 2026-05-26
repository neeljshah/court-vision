"""line_validator.py - probe R17_J2.

Pre-write validation gate for `scripts/place_bet.py`.

Why this exists
---------------
The slate-recommended (book, player, stat, line, odds) tuple is computed
from a snapshot that may be MINUTES old. Books move lines faster than
the slate refreshes, so a bet placed against a stale recommendation can
land at a line that no longer exists, or at odds the operator is no
longer offered. Both kill EV silently.

This module re-reads the line snapshot CSVs and confirms the tuple is
still LIVE before the ledger row is written.

Public API
----------
validate_bet_line(book, player_name, stat, line, side, odds,
                  max_staleness_sec=120, lines_dir=...) -> tuple[bool, str, dict]

Returns:
    (is_valid: bool, reason: str, current_snapshot: dict)

`current_snapshot` carries:
    captured_at, age_sec, book, player_name, stat, line, side, odds_current,
    odds_placed, line_placed, source_file
(values are best-effort: if no match was found at all the snapshot dict
will be empty.)

Design choices
--------------
- Snapshot freshness window is configurable (default 120 s = 2 min).
- We compare *book + player_name + stat* exactly, then match on `line` with
  a 0.01 tolerance (handles 3.50 vs 3.5).
- "Side" determines which odds column we read: OVER -> over_price,
  UNDER -> under_price.
- When the *line* moves we return INVALID with the new line surfaced so
  the caller can show "line moved 3.5 -> 4.5".
- When the *line* matches but the *odds* moved we return INVALID with a
  "odds moved" reason. (The cutoff is exact equality on integer odds.)
- When player is not in the book at all -> INVALID, reason "not found".
- All snapshots in `lines_dir` are scanned; the freshest matching row wins.

This module deliberately has zero dependencies on pandas / numpy so it can
be imported from CLI scripts and tests alike.
"""
from __future__ import annotations

import csv
import glob
import os
import re
import unicodedata
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")
DEFAULT_MAX_STALENESS_SEC = 120


_BOOK_ALIASES = {
    "pin": "pin", "pinnacle": "pin",
    "fd": "fd", "fanduel": "fd",
    "bov": "bov", "bovada": "bov",
    "dk": "dk", "draftkings": "dk",
    "mgm": "mgm", "betmgm": "mgm",
    "pp": "pp", "prizepicks": "pp",
}


def _book_canon(b: str) -> str:
    return _BOOK_ALIASES.get(str(b or "").lower().strip(), str(b or "").lower().strip())


def _name_key(s: str) -> str:
    """Strip accents + lowercase + collapse whitespace."""
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.lower().strip())


def _parse_captured_at(ts: str) -> Optional[datetime]:
    """Parse captured_at timestamps from the line CSVs.

    Observed formats in data/lines/:
        2026-05-26T12:27           (minute precision, pin scraper)
        2026-05-26T12:24:41        (second precision, fd / bov scrapers)
        2026-05-26T12:24:41Z       (Z suffix sometimes appears)

    All are treated as naive local timestamps (the scrapers run on the
    same host; comparing them against datetime.now() with the same naivety
    is the right semantic).
    """
    if not ts:
        return None
    s = str(ts).strip()
    if s.endswith("Z"):
        s = s[:-1]
    # Pad minute-only to seconds.
    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$", s):
        s = s + ":00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _now() -> datetime:
    """Indirection point for tests."""
    return datetime.now()


# --------------------------------------------------------------------------- #
# Snapshot loading                                                            #
# --------------------------------------------------------------------------- #
def _load_book_snapshots(lines_dir: str, book_canon: str) -> List[Dict]:
    """Load every CSV row across data/lines/*.csv that matches `book_canon`.

    Each row gets a `_source_file` field stamped with the basename for
    debug messages.
    """
    rows: List[Dict] = []
    if not os.path.isdir(lines_dir):
        return rows
    for path in sorted(glob.glob(os.path.join(lines_dir, "*.csv"))):
        try:
            with open(path, encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    if _book_canon(r.get("book", "")) != book_canon:
                        continue
                    r["_source_file"] = os.path.basename(path)
                    rows.append(r)
        except (OSError, csv.Error):
            continue
    return rows


def _odds_field(side: str) -> str:
    return "over_price" if side.upper() == "OVER" else "under_price"


def _coerce_int(v) -> Optional[int]:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _coerce_float(v) -> Optional[float]:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _snapshot_dict(row: Dict, age_sec: Optional[float], side: str) -> Dict:
    """Render a row into the public `current_snapshot` dict shape."""
    odds_field = _odds_field(side)
    return {
        "captured_at":   row.get("captured_at", ""),
        "age_sec":       age_sec,
        "book":          _book_canon(row.get("book", "")),
        "player_name":   row.get("player_name", ""),
        "stat":          (row.get("stat", "") or "").lower(),
        "line":          _coerce_float(row.get("line")),
        "side":          side.upper(),
        "odds_current":  _coerce_int(row.get(odds_field)),
        "source_file":   row.get("_source_file", ""),
    }


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #
def validate_bet_line(
    book: str,
    player_name: str,
    stat: str,
    line: float,
    side: str,
    odds: int,
    max_staleness_sec: int = DEFAULT_MAX_STALENESS_SEC,
    lines_dir: str = DEFAULT_LINES_DIR,
    now: Optional[datetime] = None,
) -> Tuple[bool, str, Dict]:
    """Confirm (book, player, stat, line, side, odds) still exists in a
    recent line snapshot.

    Parameters
    ----------
    book           : 'pin' / 'pinnacle' / 'fd' / ... (canonical or alias)
    player_name    : full display name; matched via name_key (accent-stripped)
    stat           : 'pts' / 'reb' / etc, case-insensitive
    line           : numeric line, tolerance 0.01
    side           : 'OVER' / 'UNDER'
    odds           : American odds (e.g. +157, -130)
    max_staleness_sec : reject snapshots older than this many seconds
    lines_dir      : data/lines/ override (for tests)
    now            : injectable clock (for tests). Defaults to datetime.now().

    Returns
    -------
    (is_valid, reason, current_snapshot)

    `current_snapshot` is populated whenever ANY row matches
    (book, player, stat) - even on INVALID returns - so the CLI can print
    "line moved to 4.5 @ -125" to the operator.
    """
    now_dt = now if now is not None else _now()
    book_c = _book_canon(book)
    pkey = _name_key(player_name)
    stat_l = (stat or "").lower().strip()
    side_u = (side or "").upper().strip()

    if side_u not in ("OVER", "UNDER"):
        return False, f"side must be OVER|UNDER, got {side!r}", {}

    placed_odds = _coerce_int(odds)
    placed_line = _coerce_float(line)
    if placed_odds is None:
        return False, f"odds not int-coercible: {odds!r}", {}
    if placed_line is None:
        return False, f"line not float-coercible: {line!r}", {}

    rows = _load_book_snapshots(lines_dir, book_c)
    if not rows:
        return False, (
            f"no snapshots for book={book_c} in {lines_dir} -- "
            f"is the scraper running?"
        ), {}

    # Filter to (player, stat).
    candidates: List[Tuple[datetime, Dict]] = []
    for r in rows:
        if _name_key(r.get("player_name", "")) != pkey:
            continue
        if (r.get("stat", "") or "").lower() != stat_l:
            continue
        ts = _parse_captured_at(r.get("captured_at", ""))
        if ts is None:
            continue
        candidates.append((ts, r))

    if not candidates:
        return False, (
            f"{player_name} {stat_l.upper()} not found at book={book_c}"
        ), {}

    # Freshest first.
    candidates.sort(key=lambda kv: kv[0], reverse=True)
    freshest_ts, freshest_row = candidates[0]
    age_sec = (now_dt - freshest_ts).total_seconds()

    if age_sec > max_staleness_sec:
        snap = _snapshot_dict(freshest_row, age_sec, side_u)
        return False, (
            f"stale snapshot: freshest is {age_sec:.0f}s old "
            f"(> {max_staleness_sec}s); freshest_captured_at={freshest_row.get('captured_at')}"
        ), snap

    # Among the most recent rows (within max_staleness_sec), look for one that
    # matches our line. We compare against the WHOLE recent window so a stale
    # line-mismatch row doesn't mask a fresh exact match.
    recent = [
        (ts, r) for ts, r in candidates
        if (now_dt - ts).total_seconds() <= max_staleness_sec
    ]
    # Prefer freshest exact-line match.
    line_matches = [
        (ts, r) for ts, r in recent
        if _coerce_float(r.get("line")) is not None
        and abs(_coerce_float(r.get("line")) - placed_line) <= 0.01
    ]
    if not line_matches:
        # Surface what the line moved TO (the freshest recent row).
        live_ts, live_row = recent[0]
        snap = _snapshot_dict(live_row, (now_dt - live_ts).total_seconds(), side_u)
        live_line = _coerce_float(live_row.get("line"))
        return False, (
            f"line moved: placed at {placed_line:g}, current live line "
            f"{live_line:g} (captured_at={live_row.get('captured_at')})"
        ), snap

    # Of the line-matching recent rows, look for one with the same odds on
    # the requested side.
    odds_field = _odds_field(side_u)
    odds_matches = [
        (ts, r) for ts, r in line_matches
        if _coerce_int(r.get(odds_field)) == placed_odds
    ]
    if not odds_matches:
        live_ts, live_row = line_matches[0]
        snap = _snapshot_dict(live_row, (now_dt - live_ts).total_seconds(), side_u)
        live_odds = _coerce_int(live_row.get(odds_field))
        return False, (
            f"odds moved: placed at {placed_odds:+d}, current live odds "
            f"{live_odds:+d} on {side_u} (line={placed_line:g}, "
            f"captured_at={live_row.get('captured_at')})"
        ), snap

    # We have a fresh, line-matching, odds-matching snapshot. VALID.
    fresh_ts, fresh_row = odds_matches[0]
    snap = _snapshot_dict(fresh_row, (now_dt - fresh_ts).total_seconds(), side_u)
    return True, (
        f"valid: snapshot {snap['age_sec']:.0f}s old "
        f"(captured_at={fresh_row.get('captured_at')})"
    ), snap


__all__ = ["validate_bet_line", "DEFAULT_MAX_STALENESS_SEC"]
