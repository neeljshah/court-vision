"""scripts.platformkit.odds_provider.kalshi_series_spec -- per-sport Kalshi in-play series.

Split out of inplay_kalshi.py (which is near the 300 LOC cap) so the multi-series,
multi-market-type widening (moneyline + total + spread + team_total, and tennis)
has its own small, testable home.

Each sport maps to a LIST of (series_ticker, market_type) pairs. inplay_kalshi.
fetch_inplay iterates this list, issuing one /markets?series_ticker=... call per
pair and tagging every tick it parses from that series with the pair's
market_type. A sport absent here is unsupported in-play (-> [], never guessed).

Verified live 2026-07-03 via
  https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker=<S>&status=open&limit=3
OPEN right now: KXATPMATCH, KXWTAMATCH, KXMLBTOTAL, KXMLBSPREAD, KXMLBTEAMTOTAL,
KXWCTEAMTOTAL, KXWCSPREAD, KXWNBAGAME, KXWNBASPREAD, KXWNBATOTAL. Closed-now-but-
real (offseason): KXNBASPREAD, KXSOCCERTOTAL, KXFIFASPREAD. KXFIFASPREAD is NOT
wired below (soccer_intl already carries KXWCSPREAD for the same underlying World
Cup slate; adding a second spread series per sport is not needed until a concrete
gap shows up). KXWNBATEAMTOTAL was PROBED and does NOT exist (404 on the /series/
endpoint, 0 markets at any status 2026-07-03) -- correctly ABSENT below; re-probe
before adding.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; no I/O
at import (pure data). Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_kalshi_series_spec.py -q
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import re

# (series_ticker, market_type) pairs, in query order, per sport. market_type is one
# of "moneyline" | "total" | "spread" | "team_total" -- the ONLY value that is ever
# safe to treat as a WIN probability downstream is "moneyline"; the others carry a
# probability over a LINE (over/under or against-spread), never a team win-prob.
SERIES_SPEC: Dict[str, List[Tuple[str, str]]] = {
    "mlb": [
        ("KXMLBGAME", "moneyline"),
        ("KXMLBTOTAL", "total"),
        ("KXMLBSPREAD", "spread"),
        ("KXMLBTEAMTOTAL", "team_total"),
    ],
    "tennis": [
        ("KXATPMATCH", "moneyline"),
        ("KXWTAMATCH", "moneyline"),
    ],
    "soccer_intl": [
        ("KXWCGAME", "moneyline"),
        ("KXWCSPREAD", "spread"),
        ("KXWCTEAMTOTAL", "team_total"),
    ],
    "soccer": [
        ("KXEPLGAME", "moneyline"),
        ("KXSOCCERTOTAL", "total"),
    ],
    "nba": [
        ("KXNBAGAME", "moneyline"),
        ("KXNBASPREAD", "spread"),
    ],
    "wnba": [
        ("KXWNBAGAME", "moneyline"),
        ("KXWNBASPREAD", "spread"),
        ("KXWNBATOTAL", "total"),
    ],
}

# Back-compat: the pre-widening code (and any external import) expects a single
# series ticker per sport, the moneyline "...GAME" series (mlb/soccer/soccer_intl/
# nba/wnba only -- tennis has no per-GAME series, only per-MATCH, so it is
# correctly ABSENT here, matching pre-widening scope). Derived, never hand-
# duplicated, so it can never drift from SERIES_SPEC.
_GAME_SERIES: Dict[str, str] = {
    sport: series for sport, pairs in SERIES_SPEC.items()
    for series, mt in [pairs[0]] if mt == "moneyline" and series.endswith("GAME")
}


def series_for(sport: str) -> List[Tuple[str, str]]:
    """(series_ticker, market_type) pairs for *sport*, or [] if unsupported.

    Pure; never raises. Returns a COPY so a caller mutating the result can never
    corrupt the module-level spec.
    """
    return list(SERIES_SPEC.get(str(sport).lower(), []))


# --------------------------------------------------------------------------------------- #
# future-game ticker-date guard (shared by every series: game/total/spread/team_total/     #
# match tickers all embed the SAME '-DDMONYY' scheduled-date fragment)                    #
# --------------------------------------------------------------------------------------- #
# A Kalshi ticker embeds the scheduled DATE (KXWCGAME-26JUL04CANMAR -> 2026-07-04; a
# tennis KXATPMATCH-26JUL05SAFDJO-SAF ticker embeds the same '-26JUL05' fragment).
# Kalshi exposes NO commence_time on the live markets list, so a liquid FUTURE-dated
# contract (the next days' games, traded pre-tournament) would otherwise read as "in_play"
# and could pollute the in-play CLV corpus with a pregame price. We parse the date and drop
# a clearly-future game. The 1-day grace is deliberate: a today/tomorrow game (any
# timezone) is KEPT (its true liveness is decided downstream), so a live game is NEVER
# dropped -- only multi-day-out futures. An UNPARSEABLE ticker (incl. any future ticker
# shape) is kept -- degrades to None, never raises, never drops on a parse miss.
FUTURE_GRACE_DAYS = 1
_TICKER_DATE_RE = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})")
_TICKER_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
                  "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}


def ticker_game_date(ref: Any) -> Optional[date]:
    """Scheduled game date from a Kalshi ticker ('...-26JUL04...' -> 2026-07-04), or
    None if absent. Pure; never raises (a malformed ticker -> None -> the market is kept)."""
    try:
        m = _TICKER_DATE_RE.search(str(ref or "").upper())
        mo = _TICKER_MONTHS.get(m.group(2)) if m else None
        if mo is None:
            return None
        return date(2000 + int(m.group(1)), mo, int(m.group(3)))
    except (ValueError, TypeError):
        return None


def is_future_game(ref: Any, now_dt: datetime) -> bool:
    """True iff the ticker's game date is clearly FUTURE (> now + FUTURE_GRACE_DAYS).
    Timezone-tolerant: only a game >1 day out is dropped, so today/tomorrow is always kept."""
    gd = ticker_game_date(ref)
    return gd is not None and gd > (now_dt.date() + timedelta(days=FUTURE_GRACE_DAYS))


__all__ = ["SERIES_SPEC", "_GAME_SERIES", "series_for",
           "FUTURE_GRACE_DAYS", "ticker_game_date", "is_future_game"]
