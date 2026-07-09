"""scripts.platformkit.venue_history.kalshi_intragame -- Kalshi settled-market candle backfill.

LANE 2: (1) enumerate settled markets via GET /markets?series_ticker&status=settled, cursor-
paginated (resumable); ``min_close_ts`` is a server no-op (verified live 2026-07-03), never
relied on; ``max_close_ts`` DOES filter. (2) per market, fetch full lifetime of 1-min candles:
GET /series/{s}/markets/{t}/candlesticks?period_interval=1&start_ts&end_ts -- capped at 5000
candles/call (verified live); window to [close_time-5000min-pad, close_time+pad] so every call
fits. (3) a candle's ``price`` is EMPTY {} on a tradeless minute (verified live) -- handled
distinctly, falls back to yes_bid/yes_ask mid, never fabricated. (4) settlement/result comes
from the market row (``result`` in {"yes","no",""}), never invented from candles.

Output: data/venue_history/kalshi/<sport>/<ticker>.jsonl, one JSON doc per market:
  {"ticker", "event_ticker", "series_ticker", "sport", "close_time", "result",
   "candles": [{"ts": iso, "prob": float, "traded": bool}, ...]}

PROVENANCE (binding): VALIDATION corpus, physically separate from lane 1's file and from the
forward pre-registered gates (ingame_tail_gate). Never pooled with forward evidence. Sport-blind
(series_ticker + sport are both params, e.g. KXMLBGAME/mlb, KXNBAGAME/nba); the discovery-window
flag (see in_discovery_window) is MLB-only -- never set for a sport that never had that capture.
Politeness: 1 req/s (sleep injected, tests instant) plus an opt-in kalshi_rate_governor share
(run_backfill's governor_caller); progress persisted to a JSON sidecar so an interrupted run
resumes from its last cursor instead of re-fetching.

INVARIANTS: platformkit-only; <=300 LOC; ASCII; stdlib only; no $-edge claims; no data/registry
writes; no flag flips.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/venue_history/test_kalshi_intragame.py -q
"""
from __future__ import annotations

import json
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.odds_provider.http_cache import http_get_json
from scripts.platformkit.odds_provider.kalshi_pacing import is_429
from scripts.platformkit.odds_provider.kalshi_rate_governor import before_request as _governor_before, report_429 as _governor_report_429, resolve_governor as _resolve_governor

KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
MAX_CANDLES_PER_CALL = 5000          # server-enforced cap on 1-min candlesticks
CANDLE_WINDOW_PAD_SEC = 3600         # small pad around the exact game window

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = _REPO_ROOT / "data" / "venue_history" / "kalshi"
DEFAULT_PROGRESS = DEFAULT_OUT_DIR / "_progress.json"

HttpGet = Callable[[str], Any]

# The MLB discovery-in-play-capture window (see ingame_tail_gate.py); a close_time inside it
# is NOT an independent sample for cross-venue validation (MLB only -- see DISCOVERY_WINDOW_SPORTS).
DISCOVERY_WINDOW_START = "2026-06-19T00:00:00Z"
DISCOVERY_WINDOW_END = "2026-07-02T23:59:59Z"


def _get(http: HttpGet, url: str, *, governor: Optional[Any] = None, sport: str = "") -> Optional[Dict[str, Any]]:
    _governor_before(governor, sport)  # gates + reports any 429 (fail-open); no-op if governor=None
    try:
        body = http(url)
    except Exception as exc:  # noqa: BLE001 -- a failed page must not kill the whole run
        if is_429(exc):
            _governor_report_429(governor)
        return None
    return body if isinstance(body, dict) else None


def list_settled_markets_page(
    series_ticker: str, cursor: str = "", limit: int = 200, max_close_ts: Optional[int] = None,
    *, http: HttpGet = http_get_json, governor: Optional[Any] = None, sport: str = "",
) -> Dict[str, Any]:
    """One page of GET /markets?series_ticker&status=settled. Returns {"markets": [...],
    "cursor": str}. ``min_close_ts`` is deliberately NEVER sent (server-side no-op,
    verified live). ``max_close_ts`` is honoured server-side for the backward walk."""
    params: Dict[str, Any] = {"series_ticker": series_ticker, "status": "settled", "limit": int(limit)}
    if cursor:
        params["cursor"] = cursor
    if max_close_ts is not None:
        params["max_close_ts"] = int(max_close_ts)
    url = "%s/markets?%s" % (KALSHI_BASE, urllib.parse.urlencode(params))
    body = _get(http, url, governor=governor, sport=sport)
    if body is None:
        return {"markets": [], "cursor": ""}
    markets = body.get("markets")
    return {
        "markets": markets if isinstance(markets, list) else [],
        "cursor": str(body.get("cursor") or ""),
    }


def _parse_iso(ts: str) -> Optional[int]:
    from datetime import datetime, timezone
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def _to_prob(value: Any) -> Optional[float]:
    """Coerce a *_dollars string/number to a prob in [0,1]; None if unusable."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if 0.0 <= v <= 1.0 else None


def _candle_to_point(c: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One candle -> {"ts", "prob", "traded"}; None if nothing usable.

    price={} means TRADELESS minute (handled distinctly from an always-populated
    yes_bid/yes_ask, which we fall back to for a quote-only prob)."""
    ts = c.get("end_period_ts")
    ts_sec = None
    try:
        ts_sec = int(ts)
    except (TypeError, ValueError):
        return None
    price = c.get("price")
    traded = isinstance(price, dict) and bool(price) and _to_prob(price.get("close_dollars")) is not None
    prob = None
    if traded:
        prob = _to_prob(price.get("close_dollars"))
    if prob is None:
        bid = c.get("yes_bid") if isinstance(c.get("yes_bid"), dict) else {}
        ask = c.get("yes_ask") if isinstance(c.get("yes_ask"), dict) else {}
        pb, pa = _to_prob(bid.get("close_dollars")), _to_prob(ask.get("close_dollars"))
        if pb is not None and pa is not None:
            prob = (pb + pa) / 2.0
        elif pa is not None:
            prob = pa
        elif pb is not None:
            prob = pb
    if prob is None:
        return None
    from datetime import datetime, timezone
    iso = datetime.fromtimestamp(ts_sec, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"ts": iso, "prob": round(prob, 4), "traded": traded}


def fetch_market_candles(
    series_ticker: str, ticker: str, close_time_iso: str,
    *, http: HttpGet = http_get_json, governor: Optional[Any] = None, sport: str = "",
) -> List[Dict[str, Any]]:
    """Full-lifetime 1-min candles for one settled market, windowed to fit the
    server's 5000-candle cap: [close_time - 5000min - pad, close_time + pad]."""
    close_ts = _parse_iso(close_time_iso)
    if close_ts is None:
        return []
    end_ts = close_ts + CANDLE_WINDOW_PAD_SEC
    start_ts = end_ts - MAX_CANDLES_PER_CALL * 60
    params = urllib.parse.urlencode({
        "start_ts": start_ts, "end_ts": end_ts, "period_interval": 1,
    })
    url = "%s/series/%s/markets/%s/candlesticks?%s" % (KALSHI_BASE, series_ticker, ticker, params)
    body = _get(http, url, governor=governor, sport=sport)
    if body is None:
        return []
    candles = body.get("candlesticks")
    if not isinstance(candles, list):
        return []
    out: List[Dict[str, Any]] = []
    for c in candles:
        if isinstance(c, dict):
            pt = _candle_to_point(c)
            if pt is not None:
                out.append(pt)
    return out


DISCOVERY_WINDOW_SPORTS = ("mlb",)  # only sport whose live capture overlaps this window;
                                     # others (e.g. nba) never flagged, even on date overlap.


def in_discovery_window(close_time_iso: str, sport: str = "mlb") -> bool:
    """True iff *close_time_iso* is inside the capture window (06-19..07-02) AND
    *sport* actually had that capture (mlb only) -- a date-only coincidence for an
    unlisted sport (e.g. nba) never counts; the window is a capture property."""
    if str(sport).lower() not in DISCOVERY_WINDOW_SPORTS:
        return False
    return DISCOVERY_WINDOW_START <= close_time_iso <= DISCOVERY_WINDOW_END


def _load_progress(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_progress(path: Path, doc: Dict[str, Any]) -> None:
    import os
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    os.replace(str(tmp), str(path))


def run_backfill(
    series_ticker: str, sport: str, *, out_dir: Optional[Path] = None,
    progress_path: Optional[Path] = None, max_requests: int = 1200, page_limit: int = 200,
    sleep_sec: float = 1.0, http: HttpGet = http_get_json,
    sleep_fn: Callable[[float], None] = time.sleep, governor_caller: Optional[str] = None,
) -> Dict[str, Any]:
    """Bounded, resumable tranche of ALL settled *series_ticker* markets: enumerate pages
    (cursor-resumable), fetch candles per market, write one JSONL per ticker. Politeness:
    sleeps *sleep_sec* between requests, stops at *max_requests*; resumes from
    *progress_path* (cursor + already-fetched tickers) if present.

    *governor_caller* defaults to None (byte-identical opt-in, as inplay_kalshi.fetch_inplay);
    run_all_backfills opts in with caller="backfill" so a fleet of these shares the live
    daemons' cross-process budget/429-backoff (kalshi_rate_governor) instead of stacking unpaced."""
    governor = _resolve_governor(governor_caller)
    out_base = Path(out_dir) if out_dir is not None else DEFAULT_OUT_DIR / sport.lower()
    prog_path = Path(progress_path) if progress_path is not None else out_base / "_progress.json"
    progress = _load_progress(prog_path)
    cursor = str(progress.get("cursor", ""))
    done_tickers = set(progress.get("done_tickers", []))
    earliest_close: Optional[str] = progress.get("earliest_close_time")

    n_requests = n_markets = n_candles = 0
    exhausted = False

    while n_requests < max_requests:
        page = list_settled_markets_page(series_ticker, cursor=cursor, limit=page_limit,
                                         http=http, governor=governor, sport=sport)
        n_requests += 1
        sleep_fn(sleep_sec)
        markets = page["markets"]
        if not markets:
            exhausted = True
            break
        for m in markets:
            ticker = str(m.get("ticker") or "")
            if not ticker or ticker in done_tickers:
                continue
            close_time, result = str(m.get("close_time") or ""), str(m.get("result") or "")
            if n_requests >= max_requests:
                break
            candles = fetch_market_candles(series_ticker, ticker, close_time, http=http,
                                           governor=governor, sport=sport)
            n_requests += 1
            sleep_fn(sleep_sec)
            doc = {
                "ticker": ticker, "event_ticker": str(m.get("event_ticker") or ""),
                "series_ticker": series_ticker, "sport": sport,
                "close_time": close_time, "result": result,
                "in_discovery_window": in_discovery_window(close_time, sport) if close_time else None,
                "n_candles": len(candles), "candles": candles,
            }
            out_path = out_base / ("%s.jsonl" % ticker)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with out_path.open("w", encoding="utf-8") as fh:
                fh.write(json.dumps(doc) + "\n")
            done_tickers.add(ticker)
            n_markets += 1
            n_candles += len(candles)
            if close_time and (earliest_close is None or close_time < earliest_close):
                earliest_close = close_time
        cursor = page["cursor"]
        progress = {"series_ticker": series_ticker, "cursor": cursor,
                    "done_tickers": sorted(done_tickers), "earliest_close_time": earliest_close}
        _save_progress(prog_path, progress)
        if not cursor:
            exhausted = True
            break

    return {
        "series_ticker": series_ticker, "sport": sport,
        "n_requests": n_requests, "n_markets_fetched_this_run": n_markets,
        "n_candles_fetched_this_run": n_candles,
        "n_markets_total_done": len(done_tickers),
        "earliest_close_time_reached": earliest_close,
        "exhausted": exhausted, "out_dir": str(out_base),
    }


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(prog="kalshi_intragame")
    ap.add_argument("--series", default="KXMLBGAME")
    ap.add_argument("--sport", default="mlb")
    ap.add_argument("--max-requests", type=int, default=1200)
    ap.add_argument("--sleep-sec", type=float, default=1.0)
    a = ap.parse_args()
    result = run_backfill(a.series, a.sport, max_requests=a.max_requests, sleep_sec=a.sleep_sec)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()


__all__ = [
    "list_settled_markets_page", "fetch_market_candles", "run_backfill",
    "in_discovery_window", "DISCOVERY_WINDOW_START", "DISCOVERY_WINDOW_END",
    "DISCOVERY_WINDOW_SPORTS", "KALSHI_BASE", "MAX_CANDLES_PER_CALL",
]
