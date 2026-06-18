"""scripts.platformkit.odds_provider.polymarket -- best-effort Polymarket gamma.

Polymarket's Gamma API (https://gamma-api.polymarket.com) needs NO auth for
read-only market data. A market carries `outcomes` and `outcomePrices` as
JSON-STRING arrays that map 1:1; each price is an implied probability in [0, 1].
For a two-way sports market (e.g. ["TeamA", "TeamB"]) we map outcome[0]->home,
outcome[1]->away and convert each implied prob -> decimal (1/prob). Venue label
is "polymarket".

This is BEST-EFFORT: Polymarket's sports taxonomy and slugs shift, and many
markets are non-binary or non-sports. We only emit an OddsEvent for a market with
exactly two outcomes and two usable prices; anything else is skipped (never
guessed). An optional token is read from ENV (POLYMARKET_API_TOKEN) only and is
not required for public reads.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union

from .base import OddsEvent, prob_to_decimal, unavailable
from .http_cache import disk_cache_get, http_get_json

logger = logging.getLogger(__name__)

_BASE = "https://gamma-api.polymarket.com"

# Polymarket has no clean per-league filter on gamma /markets; we pull active
# markets and filter by a sport keyword present in the slug/question. Crude but
# honest -- a non-match is simply skipped.
_SPORT_HINT: Dict[str, List[str]] = {
    "nba": ["nba", "basketball"],
    "mlb": ["mlb", "baseball"],
    "soccer": ["epl", "premier-league", "soccer"],
    "soccer_intl": ["world-cup", "world cup", "fifa"],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _token() -> Optional[str]:
    t = os.environ.get("POLYMARKET_API_TOKEN")
    return t.strip() if t and t.strip() else None


def _as_list(value: Any) -> List[Any]:
    """Gamma encodes outcomes/outcomePrices as a JSON STRING (or sometimes a list)."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    return []


def parse_market(market: Dict[str, Any], sport: str) -> Optional[OddsEvent]:
    """Map one two-way gamma market -> OddsEvent, or None if not cleanly two-way.

    Pure: unit-tested on a canned market. outcome[0]->home, outcome[1]->away;
    each implied prob -> decimal. Non-two-way or unparseable -> None (no guess).
    """
    outcomes = [str(o).strip() for o in _as_list(market.get("outcomes"))]
    prices = _as_list(market.get("outcomePrices"))
    if len(outcomes) != 2 or len(prices) != 2:
        return None
    dec_home = prob_to_decimal_safe(prices[0])
    dec_away = prob_to_decimal_safe(prices[1])
    if dec_home is None or dec_away is None:
        return None
    eid = str(market.get("id") or market.get("slug") or market.get("conditionId") or "")
    if not eid:
        return None
    return OddsEvent(
        event_id=eid, sport=sport, home=outcomes[0], away=outcomes[1],
        commence_time=market.get("startDate") or market.get("endDate"),
        prices={"polymarket": {"home": dec_home, "away": dec_away, "draw": None}},
        source="polymarket", as_of=_now_iso())


def prob_to_decimal_safe(value: Any) -> Optional[float]:
    """prob_to_decimal but tolerant of string prices from gamma."""
    try:
        return prob_to_decimal(float(value))
    except (TypeError, ValueError):
        return None


def parse_markets(markets: List[Dict[str, Any]], sport: str) -> List[OddsEvent]:
    """Filter a gamma market list to *sport* and map each two-way market."""
    hints = _SPORT_HINT.get(sport.lower(), [])
    out: List[OddsEvent] = []
    for m in markets or []:
        blob = f"{m.get('slug','')} {m.get('question','')}".lower()
        if hints and not any(h in blob for h in hints):
            continue
        ev = parse_market(m, sport)
        if ev is not None:
            out.append(ev)
    return out


class PolymarketProvider:
    """Best-effort Polymarket gamma provider. fetch -> list[OddsEvent]|UNAVAILABLE."""

    name = "polymarket"

    def __init__(self,
                 http_get: Callable[[str], Any] = http_get_json,
                 *, use_cache: bool = True, page_limit: int = 200) -> None:
        self._http_get = http_get
        self._use_cache = use_cache
        self._page_limit = page_limit

    def _get(self, url: str) -> Any:
        if self._use_cache:
            return disk_cache_get(url, http_get=self._http_get)
        return self._http_get(url)

    def fetch(self, sport: str) -> Union[List[OddsEvent], Dict[str, str]]:
        sport = sport.lower()
        if sport not in _SPORT_HINT:
            return unavailable(f"polymarket: unsupported sport '{sport}'")
        params = {"limit": self._page_limit, "active": "true", "closed": "false"}
        url = f"{_BASE}/markets?" + urllib.parse.urlencode(params)
        try:
            body = self._get(url)
        except Exception as exc:  # noqa: BLE001 -- degrade, never bubble
            logger.warning("polymarket markets failed for %s: %s", sport, exc)
            return unavailable(f"polymarket call failed ({type(exc).__name__})")
        markets = body if isinstance(body, list) else (
            body.get("data") if isinstance(body, dict) else None)
        if not isinstance(markets, list):
            return unavailable("polymarket: unexpected markets shape")
        return parse_markets(markets, sport)


__all__ = ["PolymarketProvider", "parse_market", "parse_markets"]
