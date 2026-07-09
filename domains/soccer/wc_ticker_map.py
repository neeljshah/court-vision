"""domains.soccer.wc_ticker_map -- ESPN (fifa.world) event <-> Kalshi KXWCGAME ticker
matching for the 2026 World Cup replay corpus.

Kalshi event tickers look like KXWCGAME-26JUN11MEXRSA: series-YYMONDD-CODE1CODE2, where
CODE1/CODE2 are 3-letter country codes (order not guaranteed home-first from the filename
alone -- matched as an unordered pair). Each event has 3 per-outcome market files:
KXWCGAME-<event>-<CODE>.jsonl (one per team) and KXWCGAME-<event>-TIE.jsonl.

ESPN's team.abbreviation field for soccer/fifa.world matches these codes directly for the
teams spot-checked (MEX, RSA) -- no separate country-name crosswalk needed. Matching is by
(datecode, {home_code, away_code}) as an unordered pair since Kalshi's own team-order
convention in the ticker is not documented; ambiguous/unmatched pairs are reported, never
guessed. Kickoff is UTC per ESPN; Kalshi's ticker date can differ by 1 calendar day for
late-UTC kickoffs (bucketed by their own market-open convention) so callers should try
datecode +/- 1 day before declaring unmatched (see match_event_any).

INVARIANTS: <=150 LOC; ASCII only; no network; no src/kernel imports.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple

_EVENT_RE = re.compile(r"^(KXWCGAME-(\d{2}[A-Z]{3}\d{2})([A-Z]{3})([A-Z]{3}))-[A-Z]{3}\.jsonl$")
_MONTH3 = ["", "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
          "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

TickerIndex = Dict[str, List[Tuple[str, FrozenSet[str]]]]


def datecode(d: date) -> str:
    """date -> Kalshi ticker datecode, e.g. date(2026,6,11) -> '26JUN11'."""
    return "%02d%s%02d" % (d.year % 100, _MONTH3[d.month], d.day)


def build_ticker_index(kalshi_dir: Path) -> TickerIndex:
    """Scan the soccer_intl venue-history dir -> {datecode: [(event_ticker, {code1,code2})]}.

    Dedupes the 3 market files per event down to one index entry.
    """
    idx: TickerIndex = {}
    seen: set = set()
    for f in sorted(Path(kalshi_dir).glob("KXWCGAME-*.jsonl")):
        m = _EVENT_RE.match(f.name)
        if not m:
            continue
        event_ticker, dc, c1, c2 = m.group(1), m.group(2), m.group(3), m.group(4)
        if event_ticker in seen:
            continue
        seen.add(event_ticker)
        idx.setdefault(dc, []).append((event_ticker, frozenset({c1, c2})))
    return idx


def match_event(dc: str, home_code: str, away_code: str, idx: TickerIndex) -> Optional[str]:
    """Exact-datecode match on the unordered {home_code, away_code} pair.
    None if zero or >1 candidates (ambiguous is reported, never guessed)."""
    codes = frozenset({home_code, away_code})
    cands = [t for t, c in idx.get(dc, []) if c == codes]
    return cands[0] if len(cands) == 1 else None


def match_event_any(kickoff_date: date, home_code: str, away_code: str,
                    idx: TickerIndex) -> Optional[str]:
    """match_event on kickoff_date, then +/-1 day (Kalshi's own date bucketing for
    late-UTC kickoffs can differ from ESPN's UTC calendar date by one day)."""
    for delta in (0, -1, 1):
        dc = datecode(kickoff_date + timedelta(days=delta))
        hit = match_event(dc, home_code, away_code, idx)
        if hit:
            return hit
    return None


__all__ = ["datecode", "build_ticker_index", "match_event", "match_event_any", "TickerIndex"]
