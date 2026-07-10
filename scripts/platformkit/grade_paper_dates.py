"""scripts.platformkit.grade_paper_dates -- MLB ticker date extraction + the
bet_expected_dates settle-time date guard, split out of grade_paper_asof.py
(LOC-rail extraction, 2026-07-10) to keep both grade_paper.py and
grade_paper_asof.py under the platform's <=300 LOC/file rail. Pure move: bodies
are byte-identical to their prior home in grade_paper_asof.py, no behavior change.

Per-file test (covered indirectly via the importers' own suites):
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_grade_paper_asof.py -q
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import Any, Dict, List, Optional

from scripts.platformkit.ingame.hist_mlb_outcome_resolver import (
    parse_mlb_ticker as _parse_mlb_ticker,
)

# MLB team-alias gap (gap ledger row: 36-row backlog, 2026-07): Kalshi in-play
# rows carry a Kalshi-house shorthand matchup label ("A's", "Chicago WS", "New
# York Y") that grade_paper._team_match's full-name token match cannot
# resolve. bet_id embeds the ORIGINAL Kalshi ticker though -- reused (not
# re-derived) via hist_mlb_outcome_resolver's proven parser/split, same module
# that already solves this exact Kalshi-shorthand-vs-ESPN-abbr gap for the
# offline hist_mlb_forward_gate corpus.
_MLB_TICKER_RE = re.compile(r"KXMLBGAME-[A-Z0-9]+")


def _mlb_ticker(bet: Dict[str, Any]) -> Optional[str]:
    """The raw KXMLBGAME-... ticker embedded in *bet*'s bet_id, or None."""
    m = _MLB_TICKER_RE.search(str(bet.get("bet_id") or ""))
    return m.group(0) if m else None


def _mlb_ticker_date(bet: Dict[str, Any]) -> Optional[str]:
    """The exact game date (ISO) embedded in *bet*'s KXMLBGAME ticker, or None.

    A hard fact straight from the ticker -- preferred over the ts-based guess
    in _candidate_dates below, since a Kalshi in-play row's ts (when our own
    system recorded/discovered the market) can trail the game's own calendar
    date by several days, well outside the ts/ts+1 heuristic window.
    """
    ticker = _mlb_ticker(bet)
    if ticker is None:
        return None
    parsed = _parse_mlb_ticker(ticker)
    return parsed[0].isoformat() if parsed else None


def bet_expected_dates(bet: Dict[str, Any]) -> List[str]:
    """Every calendar date *bet*'s own game could plausibly be on, INCLUDING today
    (_candidate_dates below excludes today, for its own bounded-backlog purpose).
    Used by grade_paper._find_final_game's settle-time date guard: a board queried
    for a date outside this list cannot hold *bet*'s real game. Unparseable/absent
    date info returns [] (honest "no info", never a guess) so the guard degrades to
    a no-op instead of false-positive-rejecting a legitimate match.
    """
    if str(bet.get("sport", "")).lower() == "mlb":
        tdate = _mlb_ticker_date(bet)
        if tdate is not None:
            return [tdate]
    gd = str(bet.get("game_date") or "").strip()[:10]
    if gd:
        return [gd]
    ts = str(bet.get("ts") or "")[:10]
    if not ts:
        return []
    try:
        d = _dt.date.fromisoformat(ts)
    except ValueError:
        return []
    return [ts, (d + _dt.timedelta(days=1)).isoformat()]


__all__ = ["bet_expected_dates", "_mlb_ticker", "_mlb_ticker_date"]
