"""Daily snapshot writer for Polymarket + Kalshi.

Mirrors the existing `scripts/morning_briefing.py` ergonomics:
single CLI entry point, writes one parquet per venue per date.

Usage:
    python -m predmarkets.snapshot                 # both venues, today
    python -m predmarkets.snapshot --venue pm      # PM only
    python -m predmarkets.snapshot --venue kalshi  # Kalshi only
    python -m predmarkets.snapshot --date 2026-05-27

Output:
    data/pm/markets_<YYYY-MM-DD>.parquet
    data/kalshi/markets_<YYYY-MM-DD>.parquet

Schema (both venues, unified columns where possible):
    venue, market_id, slug_or_ticker, event_id, question_or_title, category,
    end_date, status, yes_bid, yes_ask, last_price, volume, liquidity,
    open_interest, is_multivariate, snapshot_ts
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date as _date, datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from predmarkets.kalshi_client import KalshiClient, KalshiClientError
from predmarkets.pm_client import PMClient, PMClientError

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PM_DIR = os.path.join(PROJECT_DIR, "data", "pm")
KALSHI_DIR = os.path.join(PROJECT_DIR, "data", "kalshi")

_PM_OPEN_LIMIT = 1500
_PM_RESOLVED_LIMIT = 1500
_PM_RESOLVED_LOOKBACK_DAYS = 90
_KALSHI_OPEN_LIMIT = 1500
_KALSHI_SETTLED_LIMIT = 1500
_KALSHI_SETTLED_LOOKBACK_DAYS = 90


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Polymarket no longer attaches a `category` field to markets or events. Until we
# wire the dedicated /tags endpoint, derive a coarse category from slug keywords.
# Order matters — first match wins.
_PM_CATEGORY_KEYWORDS = (
    ("Crypto", ("bitcoin", "btc", "ethereum", "eth", "solana", "crypto", "dogecoin", "fdv", "token", "ftx", "memecoin")),
    ("Sports", ("nba", "nfl", "mlb", "nhl", "epl", "fifa", "ufc", "soccer", "tennis", "atp", "wta", "itf", "golf", "pga", "f1", "boxing", "ufc")),
    ("Politics", ("election", "president", "senate", "congress", "governor", "ballot", "polls", "trump", "biden", "harris", "putin", "xi", "regime")),
    ("Geopolitics", ("israel", "gaza", "iran", "ukraine", "russia", "china", "ceasefire", "war", "nuclear", "nato")),
    ("Economy", ("cpi", "inflation", "fed", "recession", "gdp", "nonfarm", "payrolls", "rate-hike", "rate-cut", "jobless")),
    ("Entertainment", ("oscars", "grammy", "emmy", "movie", "box-office", "album", "song", "celebrity")),
    ("Science", ("mars", "spacex", "starship", "ai", "openai", "anthropic", "agi", "fusion")),
    ("Weather", ("hurricane", "storm", "temperature", "snowfall", "heatwave")),
)


def _derive_pm_category(slug: str, question: str) -> str:
    """Best-effort category from slug + question keywords. Returns '' if unknown."""
    haystack = f"{slug} {question}".lower()
    for label, keywords in _PM_CATEGORY_KEYWORDS:
        for kw in keywords:
            if kw in haystack:
                return label
    return ""


def _pm_row(m: Dict[str, Any], status: str, snap_ts: str) -> Dict[str, Any]:
    outcome_prices = m.get("outcomePrices") or []
    yes_price = None
    no_price = None
    if isinstance(outcome_prices, list) and len(outcome_prices) >= 2:
        try:
            yes_price = float(outcome_prices[0])
            no_price = float(outcome_prices[1])
        except (TypeError, ValueError):
            pass
    slug = m.get("slug") or ""
    question = m.get("question") or ""
    category = m.get("category") or _derive_pm_category(slug, question)
    return {
        "venue": "polymarket",
        "market_id": str(m.get("id") or ""),
        "slug_or_ticker": slug,
        "event_id": m.get("conditionId") or "",
        "question_or_title": question,
        "category": category,
        "end_date": m.get("endDate") or m.get("endDateIso") or "",
        "closed_time": m.get("closedTime") or m.get("umaEndDate") or "",
        "status": status,
        "yes_bid": m.get("bestBid"),
        "yes_ask": m.get("bestAsk"),
        "last_price": yes_price,
        "no_price": no_price,
        "volume": _as_float(m.get("volume")),
        "volume_24h": _as_float(m.get("volume24hr")),
        "liquidity": _as_float(m.get("liquidity")),
        "open_interest": None,
        "is_multivariate": False,
        "enable_orderbook": bool(m.get("enableOrderBook")),
        "snapshot_ts": snap_ts,
    }


def _kalshi_row(m: Dict[str, Any], status: str, snap_ts: str) -> Dict[str, Any]:
    return {
        "venue": "kalshi",
        "market_id": m.get("ticker") or "",
        "slug_or_ticker": m.get("ticker") or "",
        "event_id": m.get("event_ticker") or "",
        "question_or_title": m.get("title") or m.get("subtitle") or "",
        "category": m.get("category") or "",
        "end_date": m.get("expiration_time") or m.get("close_time") or "",
        "closed_time": m.get("close_time") or "",
        "status": status,
        "yes_bid": m.get("yes_bid"),
        "yes_ask": m.get("yes_ask"),
        "last_price": m.get("last_price"),
        "no_price": None,
        "volume": _as_float(m.get("volume")),
        "volume_24h": _as_float(m.get("volume_24h")),
        "liquidity": _as_float(m.get("liquidity")),
        "open_interest": _as_float(m.get("open_interest")),
        "is_multivariate": bool(m.get("is_multivariate")),
        "enable_orderbook": True,
        "snapshot_ts": snap_ts,
        "result": m.get("result") or "",
        "settlement_value": m.get("settlement_value"),
    }


def _as_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def snapshot_polymarket(snap_date: _date, out_dir: str = PM_DIR) -> str:
    """Write a Polymarket snapshot parquet for `snap_date`. Returns the path."""
    snap_ts = _now_iso()
    pm = PMClient()
    open_markets = pm.list_markets(active=True, limit=_PM_OPEN_LIMIT)
    resolved = pm.get_resolved_markets(
        lookback_days=_PM_RESOLVED_LOOKBACK_DAYS, limit=_PM_RESOLVED_LIMIT
    )
    rows: List[Dict[str, Any]] = []
    rows.extend(_pm_row(m, "open", snap_ts) for m in open_markets)
    rows.extend(_pm_row(m, "resolved", snap_ts) for m in resolved)
    return _write_parquet(rows, out_dir, snap_date, "polymarket")


def snapshot_kalshi(snap_date: _date, out_dir: str = KALSHI_DIR) -> str:
    """Write a Kalshi snapshot parquet for `snap_date`. Returns the path."""
    snap_ts = _now_iso()
    ks = KalshiClient()
    open_markets = ks.get_markets(
        status="open", limit=_KALSHI_OPEN_LIMIT, exclude_multivariate=True
    )
    settled = ks.get_settlements(
        lookback_days=_KALSHI_SETTLED_LOOKBACK_DAYS,
        limit=_KALSHI_SETTLED_LIMIT,
        exclude_multivariate=True,
    )
    rows: List[Dict[str, Any]] = []
    rows.extend(_kalshi_row(m, "open", snap_ts) for m in open_markets)
    rows.extend(_kalshi_row(m, "settled", snap_ts) for m in settled)
    return _write_parquet(rows, out_dir, snap_date, "kalshi")


def _write_parquet(rows: List[Dict[str, Any]], out_dir: str, snap_date: _date, venue: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"markets_{snap_date.isoformat()}.parquet")
    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=["venue", "market_id", "status", "snapshot_ts"])
    try:
        df.to_parquet(path, index=False)
    except Exception:
        df.to_parquet(path, index=False, engine="pyarrow")
    return path


def snapshot_all(snap_date: Optional[_date] = None) -> Dict[str, Dict[str, Any]]:
    """Run both venue snapshots. Returns {venue: {path, n_rows, error?}}."""
    if snap_date is None:
        snap_date = datetime.now(timezone.utc).date()
    report: Dict[str, Dict[str, Any]] = {}
    for venue, fn in (("polymarket", snapshot_polymarket), ("kalshi", snapshot_kalshi)):
        try:
            path = fn(snap_date)
            n_rows = len(pd.read_parquet(path))
            report[venue] = {"path": path, "n_rows": n_rows, "error": None}
        except (PMClientError, KalshiClientError, Exception) as exc:
            report[venue] = {"path": None, "n_rows": 0, "error": f"{type(exc).__name__}: {exc}"}
    return report


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Daily PM + Kalshi market snapshot")
    p.add_argument("--venue", choices=["pm", "kalshi", "both"], default="both")
    p.add_argument("--date", default=None, help="YYYY-MM-DD (default: today UTC)")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    snap_date = (
        datetime.strptime(args.date, "%Y-%m-%d").date() if args.date
        else datetime.now(timezone.utc).date()
    )
    venues = ("polymarket", "kalshi") if args.venue == "both" else (
        "polymarket" if args.venue == "pm" else "kalshi",
    )
    rc = 0
    for venue in venues:
        try:
            if venue == "polymarket":
                path = snapshot_polymarket(snap_date)
            else:
                path = snapshot_kalshi(snap_date)
            n = len(pd.read_parquet(path))
            print(f"[{venue}] OK {n} rows -> {path}")
        except Exception as exc:
            rc = 1
            print(f"[{venue}] FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
