"""scripts.platformkit.odds_provider.depth_capture -- Kalshi order-book DEPTH capture.

LANE 4b: order-book DEPTH accrual (memory ingame_data_sources_2026_07_04, item 5).
Kalshi's public KEYLESS ``GET /trade-api/v2/markets/{ticker}/orderbook`` returns
{"orderbook_fp": {"yes_dollars": [[price_str, size_str], ...], "no_dollars": [...]}}
-- a price-ladder rung list, not a single best bid/ask. DATA CAPTURE ONLY: no
model, no gate, no edge framing. Snapshots the FULL ladder for every in-play
market the widened in-play capture already tracks (kalshi_series_spec.series_for,
same list inplay_kalshi iterates), append-only JSONL, one row per (ticker, snapshot).

REUSE: kalshi._BASE (base URL) + kalshi_pacing (stagger + 429 cool-down) +
transport.resilient_get_json. Cross-process pacing: kalshi_rate_governor, opt-in
via governor_caller (None default = no governor, byte-identical for every
pre-existing caller/test -- finding 20, this daemon was previously unpaced).

Row shape (append-only JSONL): {"ts": iso8601Z, "sport", "ticker", "event_ticker",
"yes_bids": [[price, size], ...], "yes_asks": [[price, size], ...], "depth_totals":
{"yes_bid_total", "yes_ask_total"}, "source": "kalshi", "source_url", "fetched_at":
iso8601Z, "capture_version": 1}. *fetched_at* is the TRUE network-fetch time
(never recomputed now()); *ts* is the snapshot-cycle time shared across tickers.

An orderbook fetch failure (network, 429, malformed body) for ONE ticker is
skipped (never fabricated/zero-filled), isolated per-ticker.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only;
stdlib + repo-internal only; no data/registry write; no flag flip; paper/
measurement only -- no $ / edge claims. Per-file test:
  python -m pytest scripts/platformkit/odds_provider/test_depth_capture.py -q
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .kalshi import _BASE
from .kalshi_pacing import (
    cooldown_after_429, is_429, record_429, record_request, stagger_sleep, REQUEST_STAGGER_SEC)
from .kalshi_rate_governor import before_request as _governor_before
from .kalshi_rate_governor import report_429 as _governor_report_429, resolve_governor as _resolve_governor
from .kalshi_series_spec import is_future_game, series_for
from .transport import resilient_get_json

logger = logging.getLogger(__name__)

CAPTURE_VERSION = 1

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DEPTH_DIR = _REPO_ROOT / "data" / "cache" / "depth_history"

HttpGet = Callable[[str], Any]
SleepFn = Callable[[float], None]
Row = Dict[str, Any]


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ladder(rungs: Any) -> List[List[float]]:
    """Coerce one orderbook_fp ladder ([["0.42","150.00"], ...]) to
    [[price_float, size_float], ...], skipping any unusable rung. Never raises;
    a malformed/absent ladder yields []."""
    out: List[List[float]] = []
    if not isinstance(rungs, list):
        return out
    for rung in rungs:
        try:
            if not isinstance(rung, (list, tuple)) or len(rung) < 2:
                continue
            price, size = float(rung[0]), float(rung[1])
        except (TypeError, ValueError, IndexError):
            continue
        out.append([price, size])
    return out


def _depth_totals(yes_bids: List[List[float]], yes_asks: List[List[float]]
                   ) -> Dict[str, float]:
    """Sum of quoted size (contracts) across every rung of each side. Pure."""
    return {
        "yes_bid_total": round(sum(sz for _p, sz in yes_bids), 2),
        "yes_ask_total": round(sum(sz for _p, sz in yes_asks), 2),
    }


def fetch_orderbook_row(sport: str, ticker: str, event_ticker: str, ts: str, *,
                         http: HttpGet = resilient_get_json,
                         stats: Optional[Dict[str, Any]] = None,
                         sleep_fn: SleepFn = time.sleep,
                         governor: Optional[Any] = None) -> Optional[Row]:
    """One depth snapshot ROW for *ticker*, or None on any failure (VOID, never
    fabricated). *stats*, if given, is mutated in place with the same
    n_requests/n_429 convention kalshi_pacing uses elsewhere. *governor*, if
    given (a resolved KalshiRateGovernor), paces this request cross-process and
    is told about a 429. Never raises."""
    record_request(stats)
    url = "%s/markets/%s/orderbook" % (_BASE, urllib.parse.quote(str(ticker)))
    _governor_before(governor, sport)
    try:
        body = http(url)
    except Exception as exc:  # noqa: BLE001 -- one ticker's failure isolates here
        logger.debug("depth_capture orderbook failed for %s: %s", ticker, exc)
        if is_429(exc):
            record_429(stats)
            _governor_report_429(governor)
            cooldown_after_429(exc, sleep_fn)
        return None
    book = body.get("orderbook_fp") if isinstance(body, dict) else None
    if not isinstance(book, dict):
        return None
    yes_bids = _ladder(book.get("yes_dollars"))
    # "yes_dollars"=YES-bid rungs; "no_dollars" prices NO contracts (algebraically
    # a YES-ask at 1-p) but is stored RAW -- never derive a synthetic 1-p price
    # the venue didn't itself publish.
    no_bids = _ladder(book.get("no_dollars"))
    if not yes_bids and not no_bids:
        return None
    return {
        "ts": ts,
        "sport": sport,
        "ticker": str(ticker),
        "event_ticker": str(event_ticker or ticker),
        "yes_bids": yes_bids,
        "yes_asks": no_bids,  # raw no_dollars ladder, see comment above (never derived)
        "depth_totals": _depth_totals(yes_bids, no_bids),
        "source": "kalshi",
        "source_url": url,
        "fetched_at": ts,
        "capture_version": CAPTURE_VERSION,
    }


def _list_tickers(sport: str, *, http: HttpGet, stats: Optional[Dict[str, Any]],
                   sleep_fn: SleepFn, stagger_sec: float,
                   governor: Optional[Any] = None) -> List[Dict[str, str]]:
    """Active (ticker, event_ticker) pairs for *sport* across every wired series
    (kalshi_series_spec.series_for, same list inplay_kalshi iterates). One
    /markets?series_ticker=...&status=open call per series; a series failure is
    isolated (skipped, never sinks the others). Never raises."""
    pairs = series_for(sport)
    out: List[Dict[str, str]] = []
    for i, (series, _market_type) in enumerate(pairs):
        stagger_sleep(sleep_fn, stagger_sec, is_first=(i == 0))
        record_request(stats)
        params = {"series_ticker": series, "limit": 200, "status": "open"}
        url = "%s/markets?%s" % (_BASE, urllib.parse.urlencode(params))
        _governor_before(governor, sport)
        try:
            body = http(url)
        except Exception as exc:  # noqa: BLE001 -- one series never sinks the others
            logger.debug("depth_capture listing failed for %s/%s: %s", sport, series, exc)
            if is_429(exc):
                record_429(stats)
                _governor_report_429(governor)
                cooldown_after_429(exc, sleep_fn)
            continue
        markets = body.get("markets") if isinstance(body, dict) else None
        if not isinstance(markets, list):
            continue
        for m in markets:
            if not isinstance(m, dict):
                continue
            t = str(m.get("ticker") or "").strip()
            if not t or is_future_game(t, datetime.now(timezone.utc)):  # S105: live budget
                continue
            out.append({"ticker": t, "event_ticker": str(m.get("event_ticker") or t)})
    return out


def capture_depth_snapshot(sport: str, *, http: HttpGet = resilient_get_json,
                            now_iso: Optional[str] = None,
                            stats: Optional[Dict[str, Any]] = None,
                            sleep_fn: SleepFn = time.sleep,
                            stagger_sec: float = 0.0,
                            max_tickers: Optional[int] = None,
                            governor_caller: Optional[str] = None) -> List[Row]:
    """ONE depth snapshot pass across every active market in *sport*'s wired
    Kalshi series: list active tickers then fetch ONE orderbook row per ticker.
    *stats* aggregates n_requests/n_429. *max_tickers* bounds a pass (None = no
    cap). *governor_caller* opt-in cross-process pacing (None = unpaced, byte-
    identical). Never raises: an unsupported sport or dead feed yields []."""
    ts = now_iso or _utc_iso()
    governor = _resolve_governor(governor_caller)
    tickers = _list_tickers(sport, http=http, stats=stats, sleep_fn=sleep_fn,
                            stagger_sec=stagger_sec, governor=governor)
    if max_tickers is not None:
        tickers = tickers[: int(max_tickers)]
    rows: List[Row] = []
    for i, ref in enumerate(tickers):
        stagger_sleep(sleep_fn, stagger_sec, is_first=(i == 0 and not tickers))
        row = fetch_orderbook_row(sport, ref["ticker"], ref["event_ticker"], ts,
                                   http=http, stats=stats, sleep_fn=sleep_fn,
                                   governor=governor)
        if row is not None:
            rows.append(row)
    return rows


def _depth_path(sport: str, dated: str, *, base_dir: Optional[Path] = None) -> Path:
    base = Path(base_dir) if base_dir is not None else DEFAULT_DEPTH_DIR
    return base / str(sport) / ("%s.jsonl" % dated)


def append_rows_atomic(rows: List[Row], path: Path) -> int:
    """Append *rows* (one JSON dict per line) to *path* via tmp + os.replace so
    a reader never sees a partial line. Returns the count written; 0 (logged)
    on a write failure -- callers must also check rows was non-empty."""
    if not rows:
        return 0
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = ""
        if path.is_file():
            with path.open("r", encoding="utf-8") as fh:
                existing = fh.read()
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(existing)
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=True) + "\n")
        os.replace(str(tmp), str(path))
        return len(rows)
    except Exception as exc:  # noqa: BLE001 -- a write failure must never crash the caller
        logger.warning("depth_capture append failed for %s: %s", path, exc)
        return 0


def run_capture_pass(sports: List[str], *, http: HttpGet = resilient_get_json,
                      base_dir: Optional[Path] = None,
                      stats: Optional[Dict[str, Any]] = None,
                      sleep_fn: SleepFn = time.sleep,
                      stagger_sec: float = REQUEST_STAGGER_SEC,
                      max_tickers_per_sport: Optional[int] = 50,
                      now_iso: Optional[str] = None,
                      governor_caller: Optional[str] = None) -> Dict[str, Any]:
    """ONE bounded capture pass across *sports*: snapshot depth + append JSONL
    per sport, dated by the pass's UTC date. Returns {"sports": {...}, "ts",
    "n_requests_total", "n_429_total"}. *governor_caller* opt-in cross-process
    pacing (None = unpaced, byte-identical). Never raises: a per-sport failure
    isolates (0 rows, logged)."""
    ts = now_iso or _utc_iso()
    dated = ts[:10]
    summary: Dict[str, Any] = {"ts": ts, "sports": {}, "n_requests_total": 0,
                               "n_429_total": 0}
    for sport in sports:
        sport_stats: Dict[str, Any] = {}
        try:
            rows = capture_depth_snapshot(
                sport, http=http, now_iso=ts, stats=sport_stats,
                sleep_fn=sleep_fn, stagger_sec=stagger_sec,
                max_tickers=max_tickers_per_sport, governor_caller=governor_caller)
        except Exception as exc:  # noqa: BLE001 -- one sport never sinks the pass
            logger.warning("depth_capture pass failed sport=%s: %s", sport, exc)
            rows = []
        path = _depth_path(sport, dated, base_dir=base_dir)
        n_written = append_rows_atomic(rows, path)
        summary["sports"][sport] = {
            "n_markets": len(rows), "n_rows_written": n_written, "path": str(path),
        }
        summary["n_requests_total"] += int(sport_stats.get("n_requests", 0))
        summary["n_429_total"] += int(sport_stats.get("n_429", 0))
        if stats is not None:
            stats["n_requests"] = stats.get("n_requests", 0) + int(sport_stats.get("n_requests", 0))
            stats["n_429"] = stats.get("n_429", 0) + int(sport_stats.get("n_429", 0))
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    """CLI: a BOUNDED live depth-capture pass. NOT a daemon -- one pass, prints
    a summary, exits. --sports comma list (default: sports the widened in-play
    capture already tracks); --max-tickers bounds per-sport breadth."""
    import argparse
    ap = argparse.ArgumentParser(prog="depth_capture")
    ap.add_argument("--sports", default="mlb,soccer_intl,tennis,wnba,npb,kbo", help="comma sports")
    ap.add_argument("--max-tickers", type=int, default=50, help="cap tickers/sport this pass")
    ap.add_argument("--governor-caller", default="depth_capture",
                    help="kalshi_rate_governor caller id (empty string = unpaced)")
    args = ap.parse_args(argv)
    sports = [s.strip() for s in args.sports.split(",") if s.strip()]
    summary = run_capture_pass(sports, max_tickers_per_sport=args.max_tickers,
                               governor_caller=args.governor_caller or None)
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CAPTURE_VERSION", "DEFAULT_DEPTH_DIR",
    "fetch_orderbook_row", "capture_depth_snapshot", "append_rows_atomic",
    "run_capture_pass",
]
