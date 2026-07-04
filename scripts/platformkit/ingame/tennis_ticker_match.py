"""scripts.platformkit.ingame.tennis_ticker_match -- pure ticker-parsing + name-
matching helpers for tennis_outcome_resolver, split out to keep that module
under the 300 LOC cap (mirrors kalshi_series_spec.py being split out of
inplay_kalshi.py for the same reason).

Pure functions only (no I/O, no network) -- see tennis_outcome_resolver.py's
module docstring for the full rationale (variable-width Kalshi codes, why a
lone code is ambiguous, why the split+match must be resolved jointly).

Per-file test: covered by test_tennis_outcome_resolver.py (imports both modules).
"""
from __future__ import annotations

import logging
import re
from datetime import date as _date
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
           "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}

# KX(ATP|WTA)MATCH-<YY><MON><DD><TAIL>[-<SIDE>]; TAIL is the raw, variable-width,
# undelimited code block (see tennis_outcome_resolver's docstring) -- captured
# whole (>=4 chars) and split by match_tail, never pre-split here (a fixed split
# would silently mis-parse a width!=3 code, e.g. 'Kwon'->KWON is 4 wide).
_TICKER_RE = re.compile(r"^KX(ATP|WTA)MATCH-(\d{2})([A-Z]{3})(\d{2})([A-Z]{4,})")
_LEAGUE_FOR_TOUR = {"ATP": "atp", "WTA": "wta"}

_PARTICLES = {"de", "van", "von", "der", "da", "di", "le", "la"}

# Kalshi codes verified live 2026-07-03 range from width 2 (a bare particle,
# 'DE') to width 4 (a short surname taken whole, 'KWON'); a split narrower than
# 2+2 or wider is never real, so the search is bounded to these widths.
MIN_CODE_WIDTH = 2
MAX_CODE_WIDTH = 4


def _norm(s: Any) -> str:
    return str(s or "").strip().upper()


def parse_tennis_ticker(ticker: str) -> Optional[Tuple[str, _date, str]]:
    """Parse a Kalshi ATP/WTA ticker -> (league, date, tail). *tail* is the RAW
    variable-width code block (not pre-split -- see module docstring). None on
    no match -- never a guess. Never raises."""
    try:
        m = _TICKER_RE.match(_norm(ticker))
        if not m:
            return None
        tour, yy, mon, dd, tail = m.groups()
        month = _MONTHS.get(mon)
        if month is None:
            return None
        league = _LEAGUE_FOR_TOUR.get(tour)
        if league is None:
            return None
        d = _date(2000 + int(yy), month, int(dd))
        return (league, d, tail)
    except Exception as exc:  # noqa: BLE001 -- a bad ticker is unresolvable, never fatal
        logger.debug("parse_tennis_ticker(%s) failed: %s", ticker, exc)
        return None


def surname_codes(name: str) -> set:
    """Candidate codes (widths 2-4) for a display name, covering every Kalshi
    shape verified live 2026-07-03: plain/hyphenated surname prefix width 3
    ('Djokovic'->DJO, 'Auger-Aliassime'->AUG, 'Davidovich Fokina'->DAV); a short
    surname taken whole when <=4 letters ('Kwon'->KWON, avoids a collision); a
    lowercase particle alone (width 2: 'de'->DE) or particle+1 ('De'+'J'->DEJ).
    ALL words contribute a candidate (not just words[1:]) -- ESPN displays some
    names family-name-first ('Zhang Shuai' -> surname is the FIRST word, ZHA),
    so we cannot assume word[0] is always a given name. Never a guess at which
    word is 'the' surname either way -- every plausible word (or particle pair)
    contributes a candidate; the split search only accepts a code consistent
    with EXACTLY one real match, so widening this set costs nothing but a wider
    (still-guarded) search."""
    words = str(name or "").replace("-", " ").split()
    codes: set = set()
    for i, w in enumerate(words):
        if len(w) >= 3:
            codes.add(w[:3].upper())
        if len(w) <= 4:
            codes.add(w.upper())
        if w.lower() in _PARTICLES:
            codes.add(w.upper())
            nxt = words[i + 1] if i + 1 < len(words) else ""
            if nxt:
                codes.add((w + nxt[:1]).upper())
    return codes


def match_tail(candidates: List[Tuple[str, str, str]], tail: str) -> Optional[bool]:
    """Try every valid 2-way split of the raw ticker *tail* against every
    candidate match's (name_a, name_b, winner_name); keep only a (split, match)
    pairing that is UNIQUE across the whole search space. Returns True if the
    split's FIRST half's player won (the "home" convention), False if the
    second half's player won, None if 0 or >1 pairings are consistent --
    ambiguous or unresolved, never guessed.

    Mirrors ingame_outcome_label.parse_mlb_ticker's ambiguous-split search, but
    resolves the split AND the name match jointly (a lone code is often
    ambiguous across the whole player pool, so splitting first and matching
    second would silently accept a wrong split)."""
    found: List[bool] = []
    n = len(tail)
    for i in range(MIN_CODE_WIDTH, n - MIN_CODE_WIDTH + 1):
        code_a, code_b = tail[:i], tail[i:]
        if not (MIN_CODE_WIDTH <= len(code_a) <= MAX_CODE_WIDTH):
            continue
        if not (MIN_CODE_WIDTH <= len(code_b) <= MAX_CODE_WIDTH):
            continue
        for na, nb, winner in candidates:
            ca, cb = surname_codes(na), surname_codes(nb)
            if code_a in ca and code_b in cb:
                found.append(winner == na)  # code_a labels player na ("home")
            elif code_a in cb and code_b in ca:
                found.append(winner == nb)  # code_a labels player nb ("home")
    if len(found) != 1:
        return None
    return found[0]


__all__ = [
    "MIN_CODE_WIDTH", "MAX_CODE_WIDTH", "parse_tennis_ticker",
    "surname_codes", "match_tail",
]
