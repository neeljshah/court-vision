"""Read-only client for the Kalshi public market data REST API.

No auth, no RSA — public endpoints only (events, markets, orderbook, trades).
Reference: vault/Strategy/PredictionMarkets/kalshi_research.md
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

_DEFAULT_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
_USER_AGENT = "nba-ai-system/predmarkets-1.0"
_MAX_ATTEMPTS = 5
_BACKOFF_MAX = 60.0


class KalshiClientError(Exception):
    """Raised when a Kalshi API call cannot be completed."""


def _cents_to_dollars(value: Any) -> Optional[float]:
    """Convert Kalshi cents (int 1-99) to a float dollar price, or None."""
    if value is None:
        return None
    try:
        return round(float(value) / 100.0, 4)
    except (TypeError, ValueError):
        return None


def _dollars_string(value: Any) -> Optional[float]:
    """Parse Kalshi's '*_dollars' string fields (e.g. '0.9730') to float, or None."""
    if value is None or value == "":
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _prefer_dollars(market: Dict[str, Any], dollar_key: str, cents_key: str) -> Optional[float]:
    """Read a dollar-denominated price from a Kalshi market dict, preferring the
    newer '*_dollars' string field over the legacy integer-cents field."""
    v = _dollars_string(market.get(dollar_key))
    if v is not None:
        return v
    return _cents_to_dollars(market.get(cents_key))


def _normalize_market(m: Dict[str, Any]) -> Dict[str, Any]:
    """Augment a raw Kalshi market dict with normalized price/volume fields and
    an `is_multivariate` flag. Mutates and returns `m`."""
    m["yes_bid"] = _prefer_dollars(m, "yes_bid_dollars", "yes_bid")
    m["yes_ask"] = _prefer_dollars(m, "yes_ask_dollars", "yes_ask")
    m["no_bid"] = _prefer_dollars(m, "no_bid_dollars", "no_bid")
    m["no_ask"] = _prefer_dollars(m, "no_ask_dollars", "no_ask")
    m["last_price"] = _prefer_dollars(m, "last_price_dollars", "last_price")
    if m.get("volume") is None:
        vd = _dollars_string(m.get("volume_dollars"))
        if vd is not None:
            m["volume"] = vd
    if m.get("liquidity") is None:
        ld = _dollars_string(m.get("liquidity_dollars"))
        if ld is not None:
            m["liquidity"] = ld
    cs = m.get("custom_strike") or {}
    m["is_multivariate"] = bool(
        m.get("mve_selected_legs")
        or m.get("mve_collection_ticker")
        or cs.get("Multivariate Event Ticker")
    )
    return m


def _iso_utc(value: Any) -> Optional[str]:
    """Normalize a timestamp (ISO or unix int) to an ISO-8601 UTC string."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return str(value)


class _TokenBucket:
    """Minimal token-bucket rate limiter (single-threaded)."""

    def __init__(self, rps: float) -> None:
        self.rate = max(0.1, float(rps))
        self.capacity = self.rate
        self.tokens = self.rate
        self.last = time.monotonic()

    def take(self) -> None:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
        self.last = now
        if self.tokens < 1.0:
            time.sleep((1.0 - self.tokens) / self.rate)
            self.tokens = 0.0
        else:
            self.tokens -= 1.0


class KalshiClient:
    """Read-only Kalshi REST client (no auth)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        rps: float = 10.0,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("KALSHI_BASE_URL") or _DEFAULT_BASE_URL).rstrip("/")
        self.timeout = float(timeout)
        self._bucket = _TokenBucket(rps)
        self._sess = requests.Session()
        self._sess.headers.update({"User-Agent": _USER_AGENT, "Accept": "application/json"})

    # --- HTTP plumbing ----------------------------------------------------

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        delay = 1.0
        last_err: Optional[str] = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            self._bucket.take()
            try:
                resp = self._sess.get(url, params=clean, timeout=self.timeout)
            except requests.RequestException as exc:
                last_err = f"network error: {exc}"
                if attempt == _MAX_ATTEMPTS:
                    raise KalshiClientError(f"{last_err} url={url}") from exc
                time.sleep(min(delay, _BACKOFF_MAX))
                delay *= 2
                continue
            if resp.status_code == 404:
                raise KalshiClientError(f"not found: {url} body={resp.text[:200]}")
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                last_err = f"http {resp.status_code} body={resp.text[:200]}"
                if attempt == _MAX_ATTEMPTS:
                    if resp.status_code == 429:
                        raise KalshiClientError("rate limit exhausted")
                    raise KalshiClientError(f"{last_err} url={url}")
                time.sleep(min(delay, _BACKOFF_MAX))
                delay *= 2
                continue
            if not resp.ok:
                raise KalshiClientError(f"http {resp.status_code} url={url} body={resp.text[:200]}")
            try:
                return resp.json()
            except ValueError as exc:
                raise KalshiClientError(f"invalid json from {url}: {exc}") from exc
        raise KalshiClientError(last_err or f"unknown failure: {url}")

    def _paginate(
        self,
        path: str,
        params: Dict[str, Any],
        key: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Cursor-paginate a list endpoint until `limit` rows or cursor empty."""
        rows: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        page_size = min(int(params.get("limit", 100) or 100), 1000)
        while True:
            q = dict(params)
            q["limit"] = min(page_size, max(1, limit - len(rows))) if limit else page_size
            if cursor:
                q["cursor"] = cursor
            data = self._get(path, q)
            batch = data.get(key) or []
            rows.extend(batch)
            cursor = (data.get("cursor") or "").strip() or None
            if not cursor or (limit and len(rows) >= limit) or not batch:
                break
        return rows[:limit] if limit else rows

    # --- Public API -------------------------------------------------------

    def get_events(
        self,
        status: str = "open",
        series_ticker: Optional[str] = None,
        limit: int = 100,
        with_nested_markets: bool = False,
    ) -> List[Dict[str, Any]]:
        """List events; cursor-paginates until `limit` reached."""
        params: Dict[str, Any] = {"status": status, "limit": min(limit, 200)}
        if series_ticker:
            params["series_ticker"] = series_ticker
        if with_nested_markets:
            params["with_nested_markets"] = "true"
        return self._paginate("/events", params, "events", limit)

    def get_markets(
        self,
        event_ticker: Optional[str] = None,
        series_ticker: Optional[str] = None,
        status: Optional[str] = None,
        tickers: Optional[List[str]] = None,
        limit: int = 100,
        exclude_multivariate: bool = False,
    ) -> List[Dict[str, Any]]:
        """List markets; cursor-paginates until `limit` reached.

        Each row is normalized: yes_bid/yes_ask/last_price/volume populated from
        either integer-cents or '*_dollars' string fields, plus `is_multivariate`.
        Set `exclude_multivariate=True` to drop parlay/MVE markets.
        """
        params: Dict[str, Any] = {"limit": min(limit, 1000)}
        if event_ticker:
            params["event_ticker"] = event_ticker
        if series_ticker:
            params["series_ticker"] = series_ticker
        if status:
            params["status"] = status
        if tickers:
            params["tickers"] = ",".join(tickers)
        if exclude_multivariate:
            # /markets default ordering buries non-MVE rows under thousands of parlay
            # markets. Walking events with nested markets avoids the flood entirely.
            ev_params: Dict[str, Any] = {"status": status or "open", "with_nested_markets": "true", "limit": 100}
            if series_ticker:
                ev_params["series_ticker"] = series_ticker
            events = self._paginate("/events", ev_params, "events", max(limit, 50))
            rows: List[Dict[str, Any]] = []
            for ev in events:
                ev_category = ev.get("category")
                ev_title = ev.get("title")
                ev_sub = ev.get("sub_title")
                ev_series = ev.get("series_ticker")
                for m in ev.get("markets") or []:
                    if event_ticker and m.get("event_ticker") != event_ticker:
                        continue
                    # Carry event-level metadata onto the market row so downstream
                    # consumers (snapshotter, edge scanner) don't need to re-join.
                    if not m.get("category") and ev_category:
                        m["category"] = ev_category
                    if not m.get("title") and (ev_title or ev_sub):
                        m["title"] = ev_title or ev_sub
                    if not m.get("series_ticker") and ev_series:
                        m["series_ticker"] = ev_series
                    rows.append(_normalize_market(m))
                    if len(rows) >= limit:
                        break
                if len(rows) >= limit:
                    break
            return rows[:limit] if limit else rows
        return [_normalize_market(m) for m in self._paginate("/markets", params, "markets", limit)]

    def get_market(self, ticker: str) -> Dict[str, Any]:
        """Fetch a single market by ticker."""
        try:
            data = self._get(f"/markets/{ticker}", None)
        except KalshiClientError as exc:
            if "not found" in str(exc):
                raise KalshiClientError(f"market not found: {ticker}") from exc
            raise
        return _normalize_market(data.get("market") or data)

    def get_orderbook(self, ticker: str) -> Dict[str, Any]:
        """Fetch the two-sided orderbook for a market, prices in dollars.

        Handles both the legacy `orderbook` (integer cents) and newer
        `orderbook_fp` (fractional `*_dollars` strings) schemas.
        """
        data = self._get(f"/markets/{ticker}/orderbook", None)
        ob = data.get("orderbook") or {}
        ob_fp = data.get("orderbook_fp") or {}

        def _norm_cents(side: Any) -> List[Tuple[float, float]]:
            rows: List[Tuple[float, float]] = []
            for entry in side or []:
                if not entry or len(entry) < 2:
                    continue
                price = _cents_to_dollars(entry[0])
                if price is None:
                    continue
                rows.append((price, float(entry[1])))
            return rows

        def _norm_dollars(side: Any) -> List[Tuple[float, float]]:
            rows: List[Tuple[float, float]] = []
            for entry in side or []:
                if not entry or len(entry) < 2:
                    continue
                price = _dollars_string(entry[0])
                if price is None:
                    continue
                try:
                    qty = float(entry[1])
                except (TypeError, ValueError):
                    continue
                rows.append((price, qty))
            return rows

        yes = _norm_dollars(ob_fp.get("yes_dollars")) or _norm_cents(ob.get("yes"))
        no = _norm_dollars(ob_fp.get("no_dollars")) or _norm_cents(ob.get("no"))
        yes.sort(key=lambda x: x[0], reverse=True)
        no.sort(key=lambda x: x[0], reverse=True)
        yes_bid = yes[0][0] if yes else None
        # buying NO at price P == selling YES at (1 - P). Top NO bid -> implied YES ask.
        yes_ask = round(1.0 - no[0][0], 4) if no else None
        return {"yes": yes, "no": no, "yes_bid": yes_bid, "yes_ask": yes_ask}

    def get_settlements(
        self,
        lookback_days: int = 90,
        limit: int = 1000,
        exclude_multivariate: bool = False,
    ) -> List[Dict[str, Any]]:
        """Derived: pull settled markets and filter to close_time >= now - lookback_days."""
        rows = self.get_markets(status="settled", limit=limit, exclude_multivariate=exclude_multivariate)
        cutoff = time.time() - max(0, lookback_days) * 86400.0
        out: List[Dict[str, Any]] = []
        for m in rows:
            ct_iso = _iso_utc(m.get("close_time"))
            ct_unix: Optional[float] = None
            if ct_iso:
                try:
                    ct_unix = datetime.fromisoformat(ct_iso).timestamp()
                except ValueError:
                    ct_unix = None
            if ct_unix is not None and ct_unix < cutoff:
                continue
            # Return the full normalized market plus a canonicalized close_time
            # so downstream consumers keep category/title/series and don't need
            # to re-fetch the market dict.
            m["close_time"] = ct_iso
            out.append(m)
        return out

    def get_trades(
        self,
        ticker: str,
        lookback_days: int = 90,
        max_trades: int = 5000,
    ) -> List[Dict[str, Any]]:
        """Cursor-paginate /markets/trades for `ticker`; prices normalized to dollars."""
        min_ts = int(time.time() - max(0, lookback_days) * 86400)
        params: Dict[str, Any] = {"ticker": ticker, "min_ts": min_ts, "limit": 1000}
        raw = self._paginate("/markets/trades", params, "trades", max_trades)
        out: List[Dict[str, Any]] = []
        for t in raw:
            out.append({
                "trade_id": t.get("trade_id"),
                "ticker": t.get("ticker"),
                "count": t.get("count"),
                "yes_price": _cents_to_dollars(t.get("yes_price")),
                "no_price": _cents_to_dollars(t.get("no_price")),
                "taker_side": t.get("taker_side"),
                "created_time": _iso_utc(t.get("created_time")),
            })
        return out


__all__ = ["KalshiClient", "KalshiClientError"]
