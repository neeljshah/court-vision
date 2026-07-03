"""scripts.platformkit.odds_provider.kalshi -- keyless Kalshi public market data.

Kalshi's public market-data REST endpoints need NO auth (only trading does).
Base: https://api.elections.kalshi.com/trade-api/v2 (also reachable as
external-api.kalshi.com). Prices are quoted in DOLLARS in [0, 1] -- i.e. the
implied probability of the YES side -- in the *_dollars fields (yes_ask_dollars,
yes_bid_dollars, no_ask_dollars, ...). An optional bearer token is read from ENV
(KALSHI_API_TOKEN) ONLY; absent is fine for public reads.

Sports mapping: a Kalshi sports game is an EVENT (event_ticker) holding two
team-winner MARKETS (one per team), each a YES/NO contract "<team> wins". We group
markets by event_ticker, treat the higher-volume / alphabetically-first team as
home only when an explicit home hint is absent (caller-supplied team match in
aggregate.py disambiguates). We expose BOTH teams' YES asks as the two sides; the
venue label is "kalshi". Implied prob (yes_ask_dollars) -> decimal = 1/prob.

A market we cannot confidently map to a two-team game is skipped (never guessed).
"""
from __future__ import annotations

import logging
import os
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .base import OddsEvent, prob_to_decimal, unavailable
from .http_cache import disk_cache_get_meta, http_get_json

logger = logging.getLogger(__name__)

_BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Sport -> Kalshi series-ticker prefixes for team game-winner markets. Kalshi's
# sports series use KX<LEAGUE>GAME naming; we filter client-side by event_ticker
# prefix since the public list endpoint paginates across all categories.
_SERIES_HINT: Dict[str, str] = {
    "nba": "KXNBA",
    "wnba": "KXWNBA",
    "mlb": "KXMLB",
    "soccer": "KXEPL",
    "soccer_intl": "KXWC",
    "tennis": "KXATP",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _token() -> Optional[str]:
    """Optional bearer token from ENV ONLY (public reads work without it)."""
    t = os.environ.get("KALSHI_API_TOKEN")
    return t.strip() if t and t.strip() else None


def _yes_ask_prob(market: Dict[str, Any]) -> Optional[float]:
    """YES ask as an implied probability in (0,1) from the *_dollars field.

    Falls back to last_price_dollars when no ask is quoted. None if unusable.
    """
    for key in ("yes_ask_dollars", "last_price_dollars", "yes_bid_dollars"):
        v = market.get(key)
        try:
            p = float(v)
        except (TypeError, ValueError):
            continue
        if 0.0 < p < 1.0:
            return p
    return None


def group_markets(markets: List[Dict[str, Any]],
                  ) -> Dict[str, List[Dict[str, Any]]]:
    """Group market dicts by event_ticker (a Kalshi game holds 2 team markets)."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for m in markets or []:
        ev = m.get("event_ticker")
        if ev:
            out.setdefault(ev, []).append(m)
    return out


def _team_label(market: Dict[str, Any]) -> str:
    """Best-effort team label for a YES contract (yes_sub_title or title tail)."""
    return (market.get("yes_sub_title") or market.get("title") or "").strip()


def parse_events(markets: List[Dict[str, Any]], sport: str,
                 as_of: Optional[str] = None,
                 ) -> List[OddsEvent]:
    """Turn a flat Kalshi market list into normalized two-team OddsEvents.

    Pure: unit-tested on canned markets. Only events with exactly two team
    markets BOTH carrying a usable YES ask become an OddsEvent; the two YES asks
    are surfaced as the two sides under venue "kalshi". Home/away here is the
    market order (caller matches by team name to fix orientation); a one-sided or
    >2-leg event is skipped (never guessed into a line).

    *as_of* is the TRUE fetched-at time of the source body (the original fetch
    time on a cache hit, never now()) so a cached/dead feed cannot read fresh.
    Defaults to now() only when the caller has no fetched-at (pure-test path).
    """
    as_of = as_of or _now_iso()
    out: List[OddsEvent] = []
    for ev_ticker, legs in group_markets(markets).items():
        if len(legs) != 2:
            continue
        priced = [(l, _yes_ask_prob(l)) for l in legs]
        if any(p is None for _l, p in priced):
            continue
        (m_a, p_a), (m_b, p_b) = priced
        dec_a, dec_b = prob_to_decimal(p_a), prob_to_decimal(p_b)
        if dec_a is None or dec_b is None:
            continue
        home, away = _team_label(m_a), _team_label(m_b)
        # Kalshi's close_time is a SETTLEMENT/expiry bound (at or after game end),
        # NOT the tip-off time. Putting it in commence_time would let a near-final
        # in-play price be labeled is_true_close=True by line_store._within_lock,
        # inflating CLV. Leave commence_time=None so a Kalshi-only game can never
        # satisfy the lock window and is always honestly marked clv_is_proxy=True.
        out.append(OddsEvent(
            event_id=ev_ticker, sport=sport, home=home, away=away,
            commence_time=None,
            prices={"kalshi": {"home": dec_a, "away": dec_b, "draw": None}},
            source="kalshi", as_of=as_of))
    return out


class KalshiProvider:
    """Keyless Kalshi public-market-data provider. fetch -> list[OddsEvent]|UNAVAILABLE."""

    name = "kalshi"

    def __init__(self,
                 http_get: Callable[[str], Any] = http_get_json,
                 *, use_cache: bool = True, page_limit: int = 200) -> None:
        self._http_get = http_get
        self._use_cache = use_cache
        self._page_limit = page_limit

    def _get(self, url: str) -> Tuple[Any, str]:
        """Return (body, fetched_at_iso) -- the TRUE network fetch time of the body
        (original fetch time on a cache hit, never now()) so a cached/dead Kalshi
        body cannot re-stamp itself fresh within the freshness TTL."""
        if self._use_cache:
            body, fetched_at, _hit = disk_cache_get_meta(url, http_get=self._http_get)
            return body, fetched_at
        return self._http_get(url), _now_iso()

    def fetch(self, sport: str) -> Union[List[OddsEvent], Dict[str, str]]:
        sport = sport.lower()
        prefix = _SERIES_HINT.get(sport)
        if not prefix:
            return unavailable(f"kalshi: unsupported sport '{sport}'")
        params = {"limit": self._page_limit, "status": "open"}
        url = f"{_BASE}/markets?" + urllib.parse.urlencode(params)
        try:
            body, fetched_at = self._get(url)
        except Exception as exc:  # noqa: BLE001 -- degrade, never bubble
            logger.warning("kalshi markets failed for %s: %s", sport, exc)
            return unavailable(f"kalshi call failed ({type(exc).__name__})")
        markets = body.get("markets") if isinstance(body, dict) else None
        if not isinstance(markets, list):
            return unavailable("kalshi: unexpected markets shape")
        relevant = [m for m in markets
                    if str(m.get("event_ticker", "")).startswith(prefix)]
        return parse_events(relevant, sport, fetched_at)


__all__ = ["KalshiProvider", "parse_events", "group_markets"]
