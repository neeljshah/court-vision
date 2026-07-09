"""scripts.platformkit.ingame.ingame_book_depth_kalshi -- Kalshi depth-of-book reader.

Split out of ingame_book_depth.py (which would otherwise exceed the 300 LOC cap)
so the Kalshi orderbook + trades-tape parsing has its own small, testable home.
See ingame_book_depth.py's module docstring for the full LANE 3 spec (venues,
canonical row shape, stale_quote_flag rationale, WIRE SPEC). This file owns ONLY:

  GET {KALSHI_BASE}/markets/{ticker}/orderbook
    -> {"orderbook_fp": {"yes_dollars": [[price_str, size_str], ...] ASC,
                        "no_dollars":  [[price_str, size_str], ...] ASC}}
    yes_dollars = resting YES-BID ladder (best bid = LAST entry, highest price).
    no_dollars  = resting NO-BID ladder; a no-buyer at price p prices a YES-ASK
    at (1-p), so the BEST (lowest) yes_ask sits at the HIGHEST no_price level,
    i.e. also the LAST entry of the ASCENDING no_dollars ladder.

  GET {KALSHI_BASE}/markets/trades?ticker=&limit=
    -> {"trades": [{"created_time": ISO-ms, "yes_price_dollars", ...}]}
    ms-precision tape, used for last_trade_ts / trades_last_5m recency AND
    (2026-07-09, execution-profile lane) the actual trade prices -- see
    normalize_trade/new_trades_since below. Same fetch as always; no new
    request, just no longer discarding the tape's prices after recency is
    computed.

Both endpoints verified live 2026-07-04 (keyless, no auth header needed for
either read). No discovery/listing logic here -- that stays in
ingame_book_depth.py (_live_kalshi_tickers, READ-ONLY reuse of
kalshi_series_spec.series_for, mirroring inplay_kalshi's own discovery call).

INVARIANTS: build only under scripts/platformkit/ingame/; <=300 LOC; ASCII only;
stdlib only. Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_ingame_book_depth_kalshi.py -q
"""
from __future__ import annotations

import logging
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"

HttpGet = Callable[[str], Any]


def _f(v: Any) -> Optional[float]:
    """Best-effort float coercion of a Kalshi *_dollars/price/size string field.
    None on any non-numeric or missing value -- NEVER 0-filled."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_orderbook(body: Dict[str, Any]) -> Tuple[Optional[float], Optional[float],
                                                    float, float, int]:
    """Kalshi orderbook_fp -> (best_bid, best_ask, bid_thin3, ask_thin3, n_levels).

    Thinness = sum of size across the top-3 levels (closest to best) per side.
    Never raises; malformed/missing book -> all None with n_levels=0.
    """
    ob = body.get("orderbook_fp") if isinstance(body, dict) else None
    if not isinstance(ob, dict):
        return None, None, 0.0, 0.0, 0
    yes_levels = ob.get("yes_dollars") or []
    no_levels = ob.get("no_dollars") or []
    if not isinstance(yes_levels, list):
        yes_levels = []
    if not isinstance(no_levels, list):
        no_levels = []

    best_bid = None
    bid_thin3 = 0.0
    if yes_levels:
        top3 = yes_levels[-3:]  # ASC order -> closest-to-best are the LAST entries
        best_bid = _f(top3[-1][0]) if len(top3[-1]) >= 1 else None
        bid_thin3 = sum(sz for sz in (_f(lv[1]) for lv in top3 if len(lv) >= 2)
                        if sz is not None)

    best_ask = None
    ask_thin3 = 0.0
    if no_levels:
        top3 = no_levels[-3:]  # ASC by no_price -> highest no_price = best yes_ask
        best_no_price = _f(top3[-1][0]) if len(top3[-1]) >= 1 else None
        best_ask = (1.0 - best_no_price) if best_no_price is not None else None
        ask_thin3 = sum(sz for sz in (_f(lv[1]) for lv in top3 if len(lv) >= 2)
                        if sz is not None)

    n_levels = len(yes_levels) + len(no_levels)
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


def fetch_orderbook_row(ticker: str, *, http: HttpGet, ts: str) -> Optional[Dict[str, Any]]:
    """One Kalshi depth row (sans trades tape) for *ticker*, or None on any
    fetch/parse failure -- VOID, never a fabricated row."""
    url = "%s/markets/%s/orderbook" % (KALSHI_BASE, urllib.parse.quote(ticker, safe=""))
    try:
        body = http(url)
    except Exception as exc:  # noqa: BLE001 -- one bad market never sinks the poll
        logger.debug("ingame_book_depth_kalshi orderbook failed %s: %s", ticker, exc)
        return None
    if not isinstance(body, dict):
        return None
    best_bid, best_ask, bid_thin, ask_thin, n_levels = parse_orderbook(body)
    return {
        "ts": ts, "venue": "kalshi", "ticker": ticker,
        "best_bid": best_bid, "best_ask": best_ask,
        "spread_bp": spread_bp(best_bid, best_ask), "book_thinness": bid_thin + ask_thin,
        "n_levels": n_levels,
    }


def fetch_trades(ticker: str, *, http: HttpGet, limit: int = 20) -> List[Dict[str, Any]]:
    """Recent trades tape for *ticker* (ms-precision created_time). [] on failure."""
    params = {"ticker": ticker, "limit": limit}
    url = "%s/markets/trades?%s" % (KALSHI_BASE, urllib.parse.urlencode(params))
    try:
        body = http(url)
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingame_book_depth_kalshi trades failed %s: %s", ticker, exc)
        return []
    trades = body.get("trades") if isinstance(body, dict) else None
    return trades if isinstance(trades, list) else []


def parse_trade_ts(created_time: Any) -> Optional[datetime]:
    """Parse a Kalshi ISO ms-precision trade timestamp -> aware UTC datetime.
    None on any parse failure."""
    try:
        v = str(created_time).strip()
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        dt = datetime.fromisoformat(v)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def trade_recency(trades: List[Dict[str, Any]], now_dt: datetime,
                  ts_key: str = "created_time") -> Tuple[Optional[str], int]:
    """(last_trade_ts ISO, trades_last_5m count) from a trades list. Never raises."""
    parsed = [(parse_trade_ts(t.get(ts_key)), t) for t in trades if isinstance(t, dict)]
    parsed = [(dt, t) for dt, t in parsed if dt is not None]
    if not parsed:
        return None, 0
    parsed.sort(key=lambda pair: pair[0], reverse=True)
    last_ts = parsed[0][0].strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    cutoff = now_dt.timestamp() - 300.0
    n_recent = sum(1 for dt, _ in parsed if dt.timestamp() >= cutoff)
    return last_ts, n_recent


def normalize_trade(t: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One raw Kalshi trade dict -> {trade_ts, trade_id, price, count,
    taker_side}. None if the trade has no parseable created_time (nothing to
    watermark/order it by -- never a fabricated record). trade_id/count/
    taker_side are best-effort (None if the field is absent), price is the
    yes_price_dollars the tape actually printed at."""
    if not isinstance(t, dict):
        return None
    dt = parse_trade_ts(t.get("created_time"))
    if dt is None:
        return None
    return {
        "trade_ts": dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "trade_id": t.get("trade_id"),
        "price": _f(t.get("yes_price_dollars")),
        "count": _f(t.get("count")),
        "taker_side": t.get("taker_side"),
    }


def new_trades_since(trades: List[Dict[str, Any]], watermark: Optional[str] = None,
                     limit: int = 50) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Normalize *trades*, keep only those strictly newer than *watermark* (a
    trade_ts high-water-mark; dedup mechanism is this ts comparison, not a
    trade_id set -- ms-precision trade_ts is unique in practice). watermark=None
    (cold start, no prior poll) -> the whole fetched tape counts as new, so the
    first poll is not silently empty. Sorts ascending, caps at *limit* (most
    recent). Returns (new_trades, next_watermark); next_watermark is the
    newest trade_ts seen, or the unchanged input watermark if *trades* is
    empty/unparseable."""
    normalized = [n for n in (normalize_trade(t) for t in trades) if n is not None]
    if not normalized:
        return [], watermark
    normalized.sort(key=lambda n: n["trade_ts"])
    next_watermark = normalized[-1]["trade_ts"]
    if watermark:
        next_watermark = max(watermark, next_watermark)
        normalized = [n for n in normalized if n["trade_ts"] > watermark]
    return normalized[-limit:], next_watermark


def snapshot_market(ticker: str, *, http: HttpGet, now_dt: datetime,
                    now_iso_fn: Callable[[], str], trade_watermark: Optional[str] = None,
                    trade_limit: int = 50) -> Optional[Dict[str, Any]]:
    """One full depth snapshot for a Kalshi *ticker*: orderbook + trades tape.
    Returns None if the orderbook fetch fails entirely (no fake row). Does NOT
    set stale_quote_flag -- the caller (ingame_book_depth.py) does that with the
    prior-snapshot comparison, kept out of this venue-only reader.

    Carries two TRANSIENT keys on the returned row -- "_new_trades" (normalized,
    watermark-deduped, capped at trade_limit) and "_trade_watermark" (the next
    high-water-mark to thread into the following poll) -- for the poller to pop
    off and persist to the trades sidecar before writing the row to the depth
    sidecar (the canonical depth row shape is unchanged on disk)."""
    ts = now_iso_fn()
    row = fetch_orderbook_row(ticker, http=http, ts=ts)
    if row is None:
        return None
    trades = fetch_trades(ticker, http=http)
    last_ts, n_recent = trade_recency(trades, now_dt)
    row["last_trade_ts"] = last_ts
    row["trades_last_5m"] = n_recent
    new_trades, next_watermark = new_trades_since(trades, trade_watermark, limit=trade_limit)
    row["_new_trades"] = new_trades
    row["_trade_watermark"] = next_watermark
    return row


__all__ = [
    "KALSHI_BASE", "parse_orderbook", "spread_bp", "fetch_orderbook_row",
    "fetch_trades", "parse_trade_ts", "trade_recency", "normalize_trade",
    "new_trades_since", "snapshot_market",
]
