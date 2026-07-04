"""scripts.platformkit.ingame.ingame_book_depth_poly -- Polymarket depth-of-book reader.

Split out of ingame_book_depth.py (which would otherwise exceed the 300 LOC cap)
so the Polymarket gamma-slug-resolve + CLOB /book parsing has its own small,
testable home. See ingame_book_depth.py's module docstring for the full LANE 3
spec (venues, canonical row shape, stale_quote_flag rationale, WIRE SPEC).

  resolve_token(slug)  -- gamma events?slug= lookup -> ONE clobTokenIds[0], call
                          ONCE per market then cache (gamma is NOT a live-price
                          source, only a lookup; its outcomePrices field is a
                          LAGGED CACHE and is never read here).
  fetch_book(token_id) -- GET https://clob.polymarket.com/book?token_id=
                          -> {"bids":[{"price","size"}...] ASC, "asks":[...] DESC
                          -- in BOTH arrays the LAST entry is the best (highest
                          bid / lowest ask), verified live 2026-07-04}.

Both endpoints verified live 2026-07-04 (keyless, no auth needed).

INVARIANTS: build only under scripts/platformkit/ingame/; <=300 LOC; ASCII only;
stdlib only. Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_ingame_book_depth_poly.py -q
"""
from __future__ import annotations

import json
import logging
import urllib.parse
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"

HttpGet = Callable[[str], Any]


def _f(v: Any) -> Optional[float]:
    """Best-effort float coercion. None on any non-numeric value -- never 0-filled."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def resolve_token(slug: str, *, http: HttpGet, outcome_index: int = 0) -> Optional[str]:
    """Resolve a Polymarket gamma EVENT slug -> ONE clob_token_id (call ONCE per
    market, then cache it -- gamma is not a live-price source, only a lookup).
    *outcome_index* picks which market/outcome leg's token (0 = first market in
    the event). Returns None on any lookup failure (never guesses a token)."""
    url = "%s/events?slug=%s" % (GAMMA_BASE, urllib.parse.quote(slug, safe=""))
    try:
        body = http(url)
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingame_book_depth_poly slug lookup failed %s: %s", slug, exc)
        return None
    events = body if isinstance(body, list) else ([body] if isinstance(body, dict) else [])
    for ev in events:
        markets = ev.get("markets") if isinstance(ev, dict) else None
        if not isinstance(markets, list) or not markets:
            continue
        idx = outcome_index if outcome_index < len(markets) else 0
        raw = markets[idx].get("clobTokenIds")
        try:
            tokens = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            tokens = None
        if isinstance(tokens, list) and tokens:
            return str(tokens[0])
    return None


def parse_book(body: Dict[str, Any]) -> Tuple[Optional[float], Optional[float],
                                              float, float, int]:
    """Polymarket CLOB /book -> (best_bid, best_ask, bid_thin3, ask_thin3, n_levels).

    bids ASC by price (best = last), asks DESC by price (best = last) -- verified
    live 2026-07-04. Never raises; malformed body -> all None / 0 / 0."""
    bids = body.get("bids") if isinstance(body, dict) else None
    asks = body.get("asks") if isinstance(body, dict) else None
    bids = bids if isinstance(bids, list) else []
    asks = asks if isinstance(asks, list) else []

    best_bid = None
    bid_thin3 = 0.0
    if bids:
        top3 = bids[-3:]
        best_bid = _f(top3[-1].get("price")) if isinstance(top3[-1], dict) else None
        bid_thin3 = sum(v for v in (_f(lv.get("size")) for lv in top3 if isinstance(lv, dict))
                        if v is not None)

    best_ask = None
    ask_thin3 = 0.0
    if asks:
        top3 = asks[-3:]
        best_ask = _f(top3[-1].get("price")) if isinstance(top3[-1], dict) else None
        ask_thin3 = sum(v for v in (_f(lv.get("size")) for lv in top3 if isinstance(lv, dict))
                        if v is not None)

    n_levels = len(bids) + len(asks)
    return best_bid, best_ask, bid_thin3, ask_thin3, n_levels


def spread_bp(best_bid: Optional[float], best_ask: Optional[float]) -> Optional[float]:
    """Spread in basis points of a $1-notional contract (ask-bid)*10000. None if
    either side is unquoted or the spread is negative (crossed/bad book)."""
    if best_bid is None or best_ask is None:
        return None
    s = best_ask - best_bid
    if s < 0.0:
        return None
    return s * 10000.0


def fetch_book_row(token_id: str, *, http: HttpGet, ts: str) -> Optional[Dict[str, Any]]:
    """One Polymarket depth row for *token_id*, or None on any fetch/parse
    failure -- VOID, never a fabricated row. last_trade_ts/trades_last_5m stay
    None/0 -- Polymarket's CLOB has no public keyless trades-tape-by-token
    endpoint verified in this probe (documented gap, not fabricated)."""
    url = "%s/book?token_id=%s" % (CLOB_BASE, urllib.parse.quote(token_id, safe=""))
    try:
        body = http(url)
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingame_book_depth_poly book failed %s: %s", token_id, exc)
        return None
    if not isinstance(body, dict):
        return None
    best_bid, best_ask, bid_thin, ask_thin, n_levels = parse_book(body)
    return {
        "ts": ts, "venue": "polymarket", "ticker": token_id,
        "best_bid": best_bid, "best_ask": best_ask,
        "spread_bp": spread_bp(best_bid, best_ask), "book_thinness": bid_thin + ask_thin,
        "n_levels": n_levels, "last_trade_ts": None, "trades_last_5m": 0,
    }


__all__ = ["GAMMA_BASE", "CLOB_BASE", "resolve_token", "parse_book", "spread_bp",
           "fetch_book_row"]
