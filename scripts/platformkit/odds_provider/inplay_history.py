"""scripts.platformkit.odds_provider.inplay_history -- HISTORICAL in-play price series.

Our OWN keyless connectors for in-play (live) price HISTORY from the two
prediction-market venues, normalised to ONE canonical tick-dict the CLV replay
harness consumes:

  {"sport": str, "game_id": str, "venue": "kalshi"|"polymarket",
   "market_type": str, "side": str, "ticker": str,
   "prob": float (implied YES probability in [0,1]),
   "ts": str (ISO-8601 UTC, e.g. "2026-06-18T22:30:00Z")}

Sources (NO auth -- only trading needs keys):
  * Kalshi candlesticks: GET /series/{series}/markets/{ticker}/candlesticks
    ?start_ts=&end_ts=&period_interval={1|60|1440}. Each candle: end_period_ts
    (unix s) + price.close_dollars (a YES dollar value in [0,1] == implied
    prob) with a yes_bid/yes_ask mid fallback. The live public API quotes
    *_dollars fields ALREADY in [0,1]; a raw integer-cents 'price' is divided
    by 100 (see _candle_prob).
  * Polymarket CLOB prices-history: GET /prices-history?market={clob_token_id}
    &interval={1h|1d|max}&fidelity=. Returns {"history":[{"t":unix_s,
    "p":prob_in_[0,1]}, ...]} -- p is already a probability, used directly.

The http getter is INJECTED so tests run offline on canned payloads. We NEVER
fabricate a point: a malformed / out-of-range candle is SKIPPED, not invented.
Cross-process pacing (finding 20, previously unpaced): the Kalshi candlestick
fetch takes an optional governor_caller (kalshi_rate_governor), None =
unpaced/byte-identical. Polymarket is a different venue, not Kalshi-paced.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only;
stdlib only; no $-edge claims. Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_inplay_history.py -q
"""
from __future__ import annotations

import json
import logging
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .http_cache import http_get_json
from .kalshi_pacing import is_429 as _is_429
from .kalshi_rate_governor import before_request as _governor_before
from .kalshi_rate_governor import report_429 as _governor_report_429, resolve_governor as _resolve_governor

logger = logging.getLogger(__name__)

KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
POLYMARKET_CLOB_BASE = "https://clob.polymarket.com"

Tick = Dict[str, Any]
HttpGet = Callable[[str], Any]


def _iso_utc(unix_seconds: Any) -> Optional[str]:
    """Unix epoch seconds -> ISO-8601 UTC with a trailing 'Z'; None if unusable."""
    try:
        ts = float(unix_seconds)
    except (TypeError, ValueError):
        return None
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_prob(value: Any) -> Optional[float]:
    """Coerce a price to an implied prob in [0,1].

    The Kalshi public API quotes *_dollars already in [0,1]; a bare INTEGER-
    cents value in [2,100] is divided by 100. A value in (1,2) is
    ambiguous/malformed and rejected. Out-of-range / non-numeric -> None."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if 0.0 <= v <= 1.0:
        return v
    if 2.0 <= v <= 100.0 and v == int(v):  # legacy integer-cents shape -> dollars
        return v / 100.0
    return None


def _candle_prob(candle: Dict[str, Any]) -> Optional[float]:
    """Best implied-YES prob for a Kalshi candle.

    Prefers price.close_dollars (the traded mid); falls back to the mid of
    yes_bid.close_dollars / yes_ask.close_dollars; then to a bare integer 'price'
    (cents). None if nothing usable.
    """
    price = candle.get("price")
    if isinstance(price, dict):
        p = _to_prob(price.get("close_dollars") or price.get("mean_dollars"))
        if p is not None:
            return p
    bid = candle.get("yes_bid")
    ask = candle.get("yes_ask")
    if isinstance(bid, dict) and isinstance(ask, dict):
        b = _to_prob(bid.get("close_dollars"))
        a = _to_prob(ask.get("close_dollars"))
        if b is not None and a is not None and (b > 0.0 or a > 0.0):
            return (b + a) / 2.0
        if a is not None and a > 0.0:
            return a
        if b is not None and b > 0.0:
            return b
    if isinstance(price, (int, float, str)):
        return _to_prob(price)
    return None


def series_from_ticker(market_ticker: str) -> str:
    """Derive a Kalshi series_ticker from a market ticker (prefix before '-')."""
    return str(market_ticker or "").split("-", 1)[0]


def fetch_price_history(
    series_ticker: str,
    market_ticker: str,
    start_ts: int,
    end_ts: int,
    period_interval: int = 1,
    *,
    sport: str = "",
    side: str = "",
    market_type: str = "moneyline",
    game_id: str = "",
    http: HttpGet = http_get_json,
    governor_caller: Optional[str] = None,
) -> List[Tick]:
    """Kalshi candlesticks -> list of canonical tick-dicts (chronological).

    *series_ticker* may be empty -> derived from *market_ticker*. *start_ts*/
    *end_ts* are unix seconds; *period_interval* is minutes (1|60|1440). *http*
    is injected for offline tests. *governor_caller* opt-in cross-process
    pacing (None = unpaced, byte-identical for every pre-existing caller).
    Never raises: a network/parse failure or empty body yields []; an unusable
    candle is skipped (never fabricated).
    """
    series = series_ticker or series_from_ticker(market_ticker)
    params = urllib.parse.urlencode({
        "start_ts": int(start_ts), "end_ts": int(end_ts),
        "period_interval": int(period_interval),
    })
    url = "%s/series/%s/markets/%s/candlesticks?%s" % (
        KALSHI_BASE, series, market_ticker, params)
    governor = _resolve_governor(governor_caller)
    _governor_before(governor, sport)
    try:
        body = http(url)
    except Exception as exc:  # noqa: BLE001 -- degrade, never bubble
        logger.warning("kalshi candlesticks failed for %s: %s", market_ticker, exc)
        if _is_429(exc):
            _governor_report_429(governor)
        return []
    candles = body.get("candlesticks") if isinstance(body, dict) else None
    if not isinstance(candles, list):
        return []
    gid = game_id or market_ticker
    out: List[Tick] = []
    for c in candles:
        if not isinstance(c, dict):
            continue
        prob = _candle_prob(c)
        ts = _iso_utc(c.get("end_period_ts"))
        if prob is None or ts is None:
            continue
        out.append({
            "sport": sport, "game_id": gid, "venue": "kalshi",
            "market_type": market_type, "side": side, "ticker": market_ticker,
            "prob": prob, "ts": ts,
        })
    return out


def fetch_price_history_polymarket(
    clob_token_id: str,
    interval: str = "max",
    fidelity: int = 1,
    *,
    sport: str = "",
    side: str = "",
    market_type: str = "moneyline",
    game_id: str = "",
    ticker: str = "",
    http: HttpGet = http_get_json,
) -> List[Tick]:
    """Polymarket CLOB prices-history -> list of canonical tick-dicts.

    *clob_token_id* is a market token id; *interval* one of {1h|1d|max};
    *fidelity* is the bar width in minutes. *http* injected for offline tests.
    Never raises: failures/empty -> []; an unusable point is skipped."""
    params = urllib.parse.urlencode({
        "market": str(clob_token_id), "interval": interval,
        "fidelity": int(fidelity),
    })
    url = "%s/prices-history?%s" % (POLYMARKET_CLOB_BASE, params)
    try:
        body = http(url)
    except Exception as exc:  # noqa: BLE001 -- degrade, never bubble
        logger.warning("polymarket prices-history failed for %s: %s",
                       clob_token_id, exc)
        return []
    history = body.get("history") if isinstance(body, dict) else None
    if not isinstance(history, list):
        return []
    gid = game_id or str(clob_token_id)
    tk = ticker or str(clob_token_id)
    out: List[Tick] = []
    for pt in history:
        if not isinstance(pt, dict):
            continue
        prob = _to_prob(pt.get("p"))
        ts = _iso_utc(pt.get("t"))
        if prob is None or ts is None:
            continue
        out.append({
            "sport": sport, "game_id": gid, "venue": "polymarket",
            "market_type": market_type, "side": side, "ticker": tk,
            "prob": prob, "ts": ts,
        })
    return out


def write_ticks_jsonl(ticks: List[Tick], path: str) -> int:
    """Write *ticks* one JSON dict per line to *path*; return the row count."""
    from pathlib import Path
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for t in ticks:
            fh.write(json.dumps(t) + "\n")
    return len(ticks)


def _capture_cli(argv: Optional[List[str]] = None) -> int:
    """Tiny live-capture CLI: fetch a real series and write it to a JSONL fixture.

    Examples:
      python -m scripts.platformkit.odds_provider.inplay_history kalshi \
        --ticker KXWCGAME-26JUN18MEXKOR-MEX --sport soccer_intl --side MEX \
        --out tests/fixtures/inplay/kalshi_soccer_intl_sample.jsonl
      python -m scripts.platformkit.odds_provider.inplay_history polymarket \
        --token <clob_token_id> --sport soccer_intl --out <path>
    """
    import argparse
    import time

    ap = argparse.ArgumentParser(prog="inplay_history")
    ap.add_argument("venue", choices=["kalshi", "polymarket"])
    ap.add_argument("--ticker", default="")
    ap.add_argument("--series", default="")
    ap.add_argument("--token", default="")
    ap.add_argument("--sport", default="")
    ap.add_argument("--side", default="")
    ap.add_argument("--market-type", default="moneyline")
    ap.add_argument("--interval", default="max")
    ap.add_argument("--period-interval", type=int, default=1)
    ap.add_argument("--fidelity", type=int, default=1)
    ap.add_argument("--lookback-days", type=int, default=3)
    ap.add_argument("--max-rows", type=int, default=200)
    ap.add_argument("--governor-caller", default="inplay_history",
                    help="kalshi_rate_governor caller id (empty string = unpaced)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    if a.venue == "kalshi":
        now = int(time.time())
        ticks = fetch_price_history(
            a.series, a.ticker, now - a.lookback_days * 86400, now,
            a.period_interval, sport=a.sport, side=a.side,
            market_type=a.market_type, governor_caller=a.governor_caller or None)
    else:
        ticks = fetch_price_history_polymarket(
            a.token, a.interval, a.fidelity, sport=a.sport, side=a.side,
            market_type=a.market_type, ticker=a.ticker)

    if len(ticks) > a.max_rows:
        ticks = ticks[-a.max_rows:]  # keep the tail (closest to close)
    n = write_ticks_jsonl(ticks, a.out)
    print("wrote %d ticks -> %s" % (n, a.out))
    if ticks:
        print("first:", json.dumps(ticks[0]))
        print("last: ", json.dumps(ticks[-1]))
    else:
        print("NO DATA RETURNED for this market (empty series)")
    return 0 if ticks else 2


if __name__ == "__main__":  # pragma: no cover -- thin CLI shim
    import sys
    raise SystemExit(_capture_cli(sys.argv[1:]))


__all__ = [
    "fetch_price_history",
    "fetch_price_history_polymarket",
    "series_from_ticker",
    "write_ticks_jsonl",
    "KALSHI_BASE",
    "POLYMARKET_CLOB_BASE",
]
