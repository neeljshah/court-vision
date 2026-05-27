"""Read-only Polymarket client (Gamma + CLOB + Data API).

Public surface: PMClient, PMClientError, PMGeoBlockedError.
No wallet, no signing, no orders.
"""

from __future__ import annotations

import json
import random
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
DATA = "https://data-api.polymarket.com"

_UA = "nba-ai-system/predmarkets-1.0"
_NUMERIC_FIELDS = (
    "volume",
    "volume24hr",
    "volume1wk",
    "volume1mo",
    "volume1yr",
    "liquidity",
    "liquidity24hr",
    "lastTradePrice",
    "bestBid",
    "bestAsk",
    "spread",
)
_JSON_STR_FIELDS = ("outcomes", "outcomePrices", "clobTokenIds")


class PMClientError(Exception):
    """Generic Polymarket client error."""


class PMGeoBlockedError(PMClientError):
    """Raised when Polymarket returns 403 (likely geo block)."""


class _RateLimiter:
    def __init__(self, rps: float) -> None:
        self._min_interval = 1.0 / max(rps, 0.1)
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delta = now - self._last
            if delta < self._min_interval:
                time.sleep(self._min_interval - delta)
            self._last = time.monotonic()


class PMClient:
    """Read-only Polymarket client across Gamma, CLOB, and Data API hosts."""

    def __init__(self, rps: float = 5.0, timeout: float = 10.0):
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": _UA, "Accept": "application/json"})
        self._limiter = _RateLimiter(rps)
        self._timeout = timeout

    def list_markets(
        self,
        active: bool = True,
        limit: int = 100,
        order: str = "volume24hr",
        ascending: bool = False,
    ) -> List[Dict[str, Any]]:
        """List active+open markets paginated from Gamma until limit reached."""
        page = 100
        out: List[Dict[str, Any]] = []
        offset = 0
        while len(out) < limit:
            params = {
                "limit": page,
                "offset": offset,
                "order": order,
                "ascending": str(ascending).lower(),
                "archived": "false",
            }
            if active:
                params["active"] = "true"
                params["closed"] = "false"
            rows = self._get(GAMMA, "/markets", params)
            if not isinstance(rows, list) or not rows:
                break
            for raw in rows:
                out.append(self._clean_market(raw))
                if len(out) >= limit:
                    break
            if len(rows) < page:
                break
            offset += page
        return out[:limit]

    def get_market(self, market_id: str) -> Dict[str, Any]:
        """Fetch a single Gamma market by id."""
        try:
            raw = self._get(GAMMA, f"/markets/{market_id}")
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                raise PMClientError(f"market not found: {market_id}") from exc
            raise
        if isinstance(raw, list):
            if not raw:
                raise PMClientError(f"market not found: {market_id}")
            raw = raw[0]
        return self._clean_market(raw)

    def get_orderbook(self, market_id: str, outcome: str = "YES") -> Dict[str, Any]:
        """Return orderbook + midpoint for the YES or NO token of a market."""
        market = self.get_market(market_id)
        if not market.get("enableOrderBook", False):
            raise PMClientError(f"orderbook not enabled for market {market_id}")
        token_ids = market.get("clobTokenIds") or []
        if not isinstance(token_ids, list) or len(token_ids) < 2:
            raise PMClientError(f"market {market_id} missing clobTokenIds")
        side = outcome.upper()
        if side not in ("YES", "NO"):
            raise PMClientError(f"outcome must be YES or NO, got {outcome!r}")
        token_id = token_ids[0] if side == "YES" else token_ids[1]
        book = self._get(CLOB, "/book", {"token_id": token_id})
        mid = self._get(CLOB, "/midpoint", {"token_id": token_id})
        bids = sorted(
            ((float(b["price"]), float(b["size"])) for b in book.get("bids", [])),
            key=lambda t: t[0],
            reverse=True,
        )
        asks = sorted(
            ((float(a["price"]), float(a["size"])) for a in book.get("asks", [])),
            key=lambda t: t[0],
        )
        midpoint = float(mid.get("mid")) if mid.get("mid") is not None else float("nan")
        return {"bids": bids, "asks": asks, "midpoint": midpoint, "token_id": token_id}

    def get_trades_history(
        self,
        market_id: str,
        lookback_days: int = 90,
        max_trades: int = 5000,
    ) -> List[Dict[str, Any]]:
        """Public trades for a market over the last lookback_days, capped at max_trades."""
        market = self.get_market(market_id)
        condition_id = market.get("conditionId")
        if not condition_id:
            raise PMClientError(f"market {market_id} missing conditionId")
        cutoff = time.time() - (lookback_days * 86400)
        out: List[Dict[str, Any]] = []
        page = 500
        offset = 0
        stop = False
        while len(out) < max_trades and not stop:
            params = {"market": condition_id, "limit": page, "offset": offset}
            rows = self._get(DATA, "/trades", params)
            if not isinstance(rows, list) or not rows:
                break
            for r in rows:
                ts_raw = r.get("timestamp")
                try:
                    ts = float(ts_raw)
                except (TypeError, ValueError):
                    continue
                if ts < cutoff:
                    stop = True
                    continue
                iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                out.append(
                    {
                        "timestamp": iso,
                        "price": float(r.get("price", 0.0) or 0.0),
                        "size": float(r.get("size", 0.0) or 0.0),
                        "side": str(r.get("side", "")).upper(),
                    }
                )
                if len(out) >= max_trades:
                    break
            if len(rows) < page:
                break
            offset += page
        return out

    def get_resolved_markets(
        self, lookback_days: int = 90, limit: int = 500
    ) -> List[Dict[str, Any]]:
        """Closed markets with endDate within the last lookback_days, newest first."""
        cutoff = time.time() - (lookback_days * 86400)
        page = 100
        out: List[Dict[str, Any]] = []
        offset = 0
        while len(out) < limit:
            params = {
                "closed": "true",
                "archived": "false",
                "limit": page,
                "offset": offset,
                "order": "closedTime",
                "ascending": "false",
            }
            rows = self._get(GAMMA, "/markets", params)
            if not isinstance(rows, list) or not rows:
                break
            stop = False
            for raw in rows:
                cleaned = self._clean_market(raw)
                # closedTime is the actual UMA resolution timestamp; endDate is the
                # contract's notional expiration and can be FAR in the future on
                # early-resolved markets — useless as a recency filter. Fall back
                # to endDate only when closedTime is missing.
                resolved_ts = _parse_iso(cleaned.get("closedTime")) or _parse_iso(
                    cleaned.get("umaEndDate")
                ) or _parse_iso(cleaned.get("endDate"))
                if resolved_ts is not None and resolved_ts < cutoff:
                    stop = True
                    break
                out.append(cleaned)
                if len(out) >= limit:
                    break
            if stop or len(rows) < page:
                break
            offset += page
        return out[:limit]

    def _get(
        self, host: str, path: str, params: Optional[Dict[str, Any]] = None
    ) -> Any:
        url = f"{host}{path}"
        delay = 1.0
        last_exc: Optional[Exception] = None
        for attempt in range(5):
            self._limiter.wait()
            try:
                resp = self._session.get(url, params=params, timeout=self._timeout)
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(min(delay, 60.0) + random.uniform(0, 0.25))
                delay *= 2
                continue
            if resp.status_code == 403:
                raise PMGeoBlockedError(
                    "Polymarket may have geo-blocked this IP"
                )
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                last_exc = requests.HTTPError(
                    f"{resp.status_code} on {url}", response=resp
                )
                time.sleep(min(delay, 60.0) + random.uniform(0, 0.25))
                delay *= 2
                continue
            try:
                resp.raise_for_status()
            except requests.HTTPError:
                raise
            try:
                return resp.json()
            except ValueError as exc:
                raise PMClientError(f"non-JSON response from {url}") from exc
        if isinstance(last_exc, requests.HTTPError):
            raise last_exc
        raise PMClientError(f"request failed after retries: {url}") from last_exc

    def _clean_market(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(raw)
        for f in _NUMERIC_FIELDS:
            if f in out and out[f] is not None:
                try:
                    out[f] = float(out[f])
                except (TypeError, ValueError):
                    pass
        for f in _JSON_STR_FIELDS:
            v = out.get(f)
            if isinstance(v, str):
                try:
                    out[f] = json.loads(v)
                except (TypeError, ValueError):
                    pass
        return out


_TZ_PAD_RE = re.compile(r"([+-]\d{2})$")


def _parse_iso(value: Optional[str]) -> Optional[float]:
    """Parse a UTC timestamp string. Tolerates ISO-T or space-separated formats
    and Gamma's '+00' (no-colon) tz suffix (e.g. '2026-03-19 23:20:15+00')."""
    if not value or not isinstance(value, str):
        return None
    cleaned = value.strip().replace("Z", "+00:00")
    cleaned = _TZ_PAD_RE.sub(r"\1:00", cleaned)
    try:
        return datetime.fromisoformat(cleaned).timestamp()
    except ValueError:
        return None
