"""scripts.platformkit.odds_provider.polymarket -- best-effort Polymarket gamma.

Polymarket's Gamma API (https://gamma-api.polymarket.com) needs NO auth for
read-only market data. A market carries `outcomes` and `outcomePrices` as
JSON-STRING arrays that map 1:1; each price is an implied probability in [0, 1].

Two market shapes are handled:

  Two-leg sport market: outcomes = ["TeamA", "TeamB"]
    -> OddsEvent(home="TeamA", away="TeamB", ...) via parse_market().

  Single-sided YES/NO binary: outcomes = ["Yes", "No"] or ["No", "Yes"]
    -> plain PM-row dict with binary_title + binary_yes_prob via
       parse_market_binary().  home/away/pm_prob are all None; Path-4 in
       active_pairs() resolves the title against the game slate.
    -> parse_market() returns None for these (not a two-team event).

parse_markets_with_binaries() returns (list[OddsEvent], list[dict]) so
PolymarketPMProvider can emit both shapes in one pass.

This is BEST-EFFORT: Polymarket's sports taxonomy and slugs shift. A non-match
is simply skipped; nothing is guessed. POLYMARKET_API_TOKEN from ENV is optional.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .base import OddsEvent, prob_to_decimal, unavailable
from .http_cache import disk_cache_get_meta, http_get_json

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
    "tennis": ["tennis", "atp", "wta"],
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


# Literal outcome labels that mark a single-sided YES/NO binary contract.
# These must NOT be mapped to home/away -- they are not team names.
_YESNO_LABELS: frozenset = frozenset({"yes", "no"})


def _is_yesno_market(outcomes: List[str]) -> bool:
    """True iff outcomes are the literal YES/NO labels of a binary contract."""
    return (len(outcomes) == 2
            and all(o.lower() in _YESNO_LABELS for o in outcomes))


def parse_market(market: Dict[str, Any], sport: str,
                 as_of: Optional[str] = None) -> Optional[OddsEvent]:
    """Map one two-way gamma market -> OddsEvent, or None if not cleanly two-way.

    Pure: unit-tested on a canned market. outcome[0]->home, outcome[1]->away;
    each implied prob -> decimal. Non-two-way or unparseable -> None (no guess).

    YES/NO single-sided binary contracts (outcomes = ["Yes","No"]) are REJECTED
    here and handled separately by parse_market_binary(); mapping them to
    home="Yes"/away="No" would produce bogus keys that never match a game slate.

    *as_of* is the TRUE fetched-at time of the source body (original fetch time on
    a cache hit, never now()) so a cached/dead feed cannot read fresh. Defaults to
    now() only when no fetched-at is supplied (pure-test path).
    """
    outcomes = [str(o).strip() for o in _as_list(market.get("outcomes"))]
    prices = _as_list(market.get("outcomePrices"))
    if len(outcomes) != 2 or len(prices) != 2:
        return None
    # Single-sided YES/NO binary -> route to parse_market_binary, not here.
    if _is_yesno_market(outcomes):
        return None
    dec_home = prob_to_decimal_safe(prices[0])
    dec_away = prob_to_decimal_safe(prices[1])
    if dec_home is None or dec_away is None:
        return None
    eid = str(market.get("id") or market.get("slug") or market.get("conditionId") or "")
    if not eid:
        return None
    # Use only startDate as the tip-off anchor. endDate is the RESOLUTION/settlement
    # date (same honesty hazard as Kalshi's close_time): a near-final price captured
    # before endDate would be labeled is_true_close=True by line_store._within_lock,
    # inflating CLV. A missing startDate leaves commence_time=None (proxy), which is
    # correct -- we cannot prove lock-window proximity without a real tip-off time.
    return OddsEvent(
        event_id=eid, sport=sport, home=outcomes[0], away=outcomes[1],
        commence_time=market.get("startDate") or None,
        prices={"polymarket": {"home": dec_home, "away": dec_away, "draw": None}},
        source="polymarket", as_of=(as_of or _now_iso()))


def parse_market_binary(market: Dict[str, Any], sport: str) -> Optional[Dict[str, Any]]:
    """Map a single-sided YES/NO gamma contract -> PM-row dict, or None.

    Returns the live_feed PMProvider row shape:
      {market_id, sport, home=None, away=None, pm_prob=None,
       binary_title=<question>, binary_yes_prob=<yes_price>}

    Only handles ["Yes","No"] / ["No","Yes"] outcomes. The YES price is extracted
    regardless of which index carries it. The question becomes binary_title for
    Path-4 team-name matching in active_pairs(). Returns None when outcomes are
    not YES/NO, prices are unparseable, or no question/title is present.
    """
    outcomes = [str(o).strip() for o in _as_list(market.get("outcomes"))]
    prices = _as_list(market.get("outcomePrices"))
    if len(outcomes) != 2 or len(prices) != 2:
        return None
    if not _is_yesno_market(outcomes):
        return None
    eid = str(market.get("id") or market.get("slug") or market.get("conditionId") or "")
    if not eid:
        return None
    title = (market.get("question") or market.get("title")
             or market.get("slug") or "").strip()
    if not title:
        return None
    # Locate the YES price: index of the outcome that lowercases to "yes".
    yes_idx = next((i for i, o in enumerate(outcomes) if o.lower() == "yes"), None)
    if yes_idx is None:
        return None
    yes_price_raw = prices[yes_idx]
    try:
        yes_prob = float(yes_price_raw)
    except (TypeError, ValueError):
        return None
    if not (0.0 < yes_prob < 1.0):
        return None
    return {
        "market_id": eid,
        "sport": str(sport),
        "home": None,
        "away": None,
        "pm_prob": None,
        "binary_title": title,
        "binary_yes_prob": yes_prob,
    }


def prob_to_decimal_safe(value: Any) -> Optional[float]:
    """prob_to_decimal but tolerant of string prices from gamma."""
    try:
        return prob_to_decimal(float(value))
    except (TypeError, ValueError):
        return None


def parse_markets(markets: List[Dict[str, Any]], sport: str,
                  as_of: Optional[str] = None) -> List[OddsEvent]:
    """Filter a gamma market list to *sport* and map each two-way market.

    *as_of* (the source body's TRUE fetched-at) is stamped on every emitted event.
    YES/NO binary contracts are silently skipped here; use parse_markets_with_binaries
    when you also want the binary rows.
    """
    hints = _SPORT_HINT.get(sport.lower(), [])
    out: List[OddsEvent] = []
    for m in markets or []:
        blob = f"{m.get('slug','')} {m.get('question','')}".lower()
        if hints and not any(h in blob for h in hints):
            continue
        ev = parse_market(m, sport, as_of)
        if ev is not None:
            out.append(ev)
    return out


def parse_markets_with_binaries(
    markets: List[Dict[str, Any]], sport: str, as_of: Optional[str] = None,
) -> Tuple[List[OddsEvent], List[Dict[str, Any]]]:
    """Filter *markets* to *sport* and split into two-leg events + binary rows.

    Returns:
      (events, binaries)
      events   -- list[OddsEvent]  two-team sport markets (home/away pair).
      binaries -- list[dict]       single-sided YES/NO contracts in PM-row shape:
                    {market_id, sport, home=None, away=None, pm_prob=None,
                     binary_title=<question>, binary_yes_prob=<yes_price>}

    This is the primary parse entry-point for PolymarketPMProvider so it can
    emit BOTH shapes and route binaries through Path-4 (title matching) in
    active_pairs() instead of silently dropping them.
    """
    hints = _SPORT_HINT.get(sport.lower(), [])
    events: List[OddsEvent] = []
    binaries: List[Dict[str, Any]] = []
    for m in markets or []:
        blob = f"{m.get('slug','')} {m.get('question','')}".lower()
        if hints and not any(h in blob for h in hints):
            continue
        outcomes = [str(o).strip() for o in _as_list(m.get("outcomes"))]
        if _is_yesno_market(outcomes):
            row = parse_market_binary(m, sport)
            if row is not None:
                binaries.append(row)
        else:
            ev = parse_market(m, sport, as_of)
            if ev is not None:
                events.append(ev)
    return events, binaries


class PolymarketProvider:
    """Best-effort Polymarket gamma provider. fetch -> list[OddsEvent]|UNAVAILABLE."""

    name = "polymarket"

    def __init__(self,
                 http_get: Callable[[str], Any] = http_get_json,
                 *, use_cache: bool = True, page_limit: int = 200) -> None:
        self._http_get = http_get
        self._use_cache = use_cache
        self._page_limit = page_limit

    def _get(self, url: str) -> Tuple[Any, str]:
        """Return (body, fetched_at_iso) -- the TRUE network fetch time of the body
        (original fetch time on a cache hit, never now()) so a cached/dead
        Polymarket body cannot re-stamp itself fresh within the freshness TTL."""
        if self._use_cache:
            body, fetched_at, _hit = disk_cache_get_meta(url, http_get=self._http_get)
            return body, fetched_at
        return self._http_get(url), _now_iso()

    def fetch(self, sport: str) -> Union[List[OddsEvent], Dict[str, str]]:
        """Fetch two-leg sport events only (OddsEvent list). YES/NO binaries skipped.

        Use fetch_with_binaries() when you also need binary contracts routed
        through Path-4 in active_pairs().
        """
        result = self.fetch_with_binaries(sport)
        if isinstance(result, dict):  # unavailable sentinel
            return result
        events, _binaries = result
        return events

    def fetch_with_binaries(
        self, sport: str,
    ) -> Union[Tuple[List[OddsEvent], List[Dict[str, Any]]], Dict[str, str]]:
        """Fetch gamma markets and return (events, binaries) or unavailable sentinel.

        events   -- list[OddsEvent]  two-team sport markets.
        binaries -- list[dict]       single-sided YES/NO PM-row dicts.
        """
        sport = sport.lower()
        if sport not in _SPORT_HINT:
            return unavailable(f"polymarket: unsupported sport '{sport}'")
        params = {"limit": self._page_limit, "active": "true", "closed": "false"}
        url = f"{_BASE}/markets?" + urllib.parse.urlencode(params)
        try:
            body, fetched_at = self._get(url)
        except Exception as exc:  # noqa: BLE001 -- degrade, never bubble
            logger.warning("polymarket markets failed for %s: %s", sport, exc)
            return unavailable(f"polymarket call failed ({type(exc).__name__})")
        markets = body if isinstance(body, list) else (
            body.get("data") if isinstance(body, dict) else None)
        if not isinstance(markets, list):
            return unavailable("polymarket: unexpected markets shape")
        return parse_markets_with_binaries(markets, sport, fetched_at)


__all__ = [
    "PolymarketProvider",
    "parse_market",
    "parse_market_binary",
    "parse_markets",
    "parse_markets_with_binaries",
]
