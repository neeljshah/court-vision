"""scripts.platformkit.live_edge.paper.event_key -- the ONE canonical event
identity shared by shadow rows, close_lookup, and the paper-bet ledger.

An event_key is (sport, date, home, away, market_family). home/away are
canonicalized via scripts.platformkit.odds_provider.team_resolver.canonical
-- the SAME resolver omni.close_lookup.pregame_close calls internally on its
own home/away args -- so a bridge-built event_key always lines up with what
pregame_close can (or honestly cannot) grade. This module does no I/O and no
identity resolution; see resolve_identity.py for the opaque-id -> event_key
join.

INVARIANTS: stdlib + team_resolver only; ASCII; <=300 LOC; never raises.
"""
from __future__ import annotations

from typing import Any, NamedTuple, Optional

from scripts.platformkit.odds_provider.team_resolver import canonical


class EventKey(NamedTuple):
    sport: str
    date: str            # YYYY-MM-DD
    home: str             # canonical team key (team_resolver.canonical)
    away: str             # canonical team key
    market_family: str    # last dot-segment of a market string, e.g. "moneyline"


def market_family_of(market: Any) -> str:
    """Last dot-segment of a market string, e.g. 'pregame.moneyline' ->
    'moneyline' -- matches clv_trial.market_family's own convention exactly
    (kept as a tiny local copy so this module has zero cross-import onto
    clv_trial, which this lane must not depend on for identity)."""
    m = str(market or "")
    return m.rsplit(".", 1)[-1] if m else "unknown"


def make_event_key(sport: Any, date: Any, home_raw: Any, away_raw: Any,
                    market: Any) -> EventKey:
    """Build the canonical EventKey for one (sport, date, home, away, market)
    tuple. home_raw/away_raw are whatever raw team-name spelling the source
    record carried; canonicalization happens here, once, so every consumer
    (shadow, close_lookup, ledger) compares the SAME token."""
    sp = str(sport).strip().lower()
    d = str(date)[:10]
    return EventKey(
        sport=sp, date=d,
        home=canonical(sp, home_raw), away=canonical(sp, away_raw),
        market_family=market_family_of(market),
    )


__all__ = ["EventKey", "make_event_key", "market_family_of"]
