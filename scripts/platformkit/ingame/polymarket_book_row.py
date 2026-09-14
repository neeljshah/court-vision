"""scripts.platformkit.ingame.polymarket_book_row -- Polymarket snapshot row + archive I/O.

Split out of polymarket_book_capture.py to keep both files under the 300 LOC
cap (mirrors kalshi_book_row.py / kalshi_book_capture.py's own split): this
module owns the per-TOKEN snapshot ROW shape and the archive/heartbeat path
helpers; polymarket_book_capture.py owns the capture LOOP (GovernedClient,
discovery cache, per-tick orchestration). iso/append/write_json_atomic are
reused verbatim from kalshi_book_row -- generic JSON-line/atomic-write helpers
with no Kalshi-specific logic.

ARCHIVE: data/cache/ingame_books/polymarket/<sport>/<date>.jsonl on the POD
(CV_CAPTURE_POD=1 and CV_POLYMARKET_BOOK_ARCHIVE_LIVE=1), else the _scratch
tree.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_polymarket_book_capture.py -q
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scripts.platformkit.ingame import kalshi_book_row as kb_row

_ROOT = Path(__file__).resolve().parents[3]
_BOOKS_ROOT = _ROOT / "data" / "cache" / "ingame_books"
LIVE_ARCHIVE_ROOT = _BOOKS_ROOT / "polymarket"
SCRATCH_ARCHIVE_ROOT = _BOOKS_ROOT / "_scratch" / "polymarket"
CAPTURE_VERSION = "polymarket_book_capture_v1"

# Generic, HTTP-free helpers reused verbatim -- see kalshi_book_row.py.
iso = kb_row.iso
append = kb_row.append
write_json_atomic = kb_row.write_json_atomic
compute_minutes_to_close = kb_row.compute_minutes_to_close


def live_archive_enabled(env: Optional[Dict[str, str]] = None) -> bool:
    values = env if env is not None else os.environ
    return values.get("CV_CAPTURE_POD") == "1" and values.get("CV_POLYMARKET_BOOK_ARCHIVE_LIVE") == "1"


def _root(env: Optional[Dict[str, str]] = None) -> Path:
    return LIVE_ARCHIVE_ROOT if live_archive_enabled(env) else SCRATCH_ARCHIVE_ROOT


def archive_path(sport: str, now: datetime, env: Optional[Dict[str, str]] = None) -> Path:
    return _root(env) / sport / (now.strftime("%Y-%m-%d") + ".jsonl")


def heartbeat_path(sport: str, env: Optional[Dict[str, str]] = None) -> Path:
    return _root(env) / sport / "_heartbeat.json"


def _f(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _levels(raw: Any) -> List[Tuple[float, float]]:
    """[(price, size), ...] from one /book side ([{'price','size'}, ...]).
    Never raises; malformed/absent -> []."""
    out: List[Tuple[float, float]] = []
    if not isinstance(raw, list):
        return out
    for lv in raw:
        if not isinstance(lv, dict):
            continue
        price, size = _f(lv.get("price")), _f(lv.get("size"))
        if price is not None and size is not None:
            out.append((price, size))
    return out


def book_metrics(body: Any) -> Tuple[Optional[float], Optional[float], Optional[float],
                                      Optional[float], float, float]:
    """(best_bid, best_ask, best_bid_size, best_ask_size, depth_bid, depth_ask).
    WIRE CONVENTION (ingame_book_depth_poly.py, verified live 2026-07-04): bids
    ASC by price (best = LAST entry), asks DESC by price (best = LAST entry)."""
    bids = _levels(body.get("bids") if isinstance(body, dict) else None)
    asks = _levels(body.get("asks") if isinstance(body, dict) else None)
    best_bid, best_bid_size = bids[-1] if bids else (None, None)
    best_ask, best_ask_size = asks[-1] if asks else (None, None)
    depth_bid = round(sum(sz for _p, sz in bids), 4)
    depth_ask = round(sum(sz for _p, sz in asks), 4)
    return best_bid, best_ask, best_bid_size, best_ask_size, depth_bid, depth_ask


def _mid(best_bid: Optional[float], best_ask: Optional[float], midpoint_body: Any) -> Optional[float]:
    """Prefer the venue's own /midpoint value; fall back to (bid+ask)/2 from the
    book when the midpoint fetch failed -- see NOT VERIFIED in
    polymarket_book_capture.py (the /midpoint response shape is assumed)."""
    api_mid = _f(midpoint_body.get("mid")) if isinstance(midpoint_body, dict) else None
    if api_mid is not None:
        return api_mid
    if best_bid is not None and best_ask is not None:
        return round((best_bid + best_ask) / 2.0, 6)
    return None


def book_row(market: Dict[str, Any], token_id: str, outcome_index: int, book_body: Any,
             midpoint_body: Any, ts_ms: int, capture_ts: str,
             enqueue_ts_ms: Optional[int] = None,
             close_time: Optional[str] = None) -> Dict[str, Any]:
    """One per-TOKEN snapshot row (a market has up to 2 outcome tokens, each
    polled and rowed separately). Raw /book payload stored verbatim under
    'book'; raw /midpoint payload verbatim under 'midpoint_raw' -- neither is
    transformed. best_bid/best_ask/sizes/depth derived via book_metrics().
    ADDITIVE (contract B2, mirrors kalshi_book_row.book_row): close_time (ISO
    8601 UTC string, or None) stored verbatim; minutes_to_close derived from it
    via the reused compute_minutes_to_close."""
    best_bid, best_ask, best_bid_size, best_ask_size, depth_bid, depth_ask = book_metrics(book_body)
    outcomes = market.get("outcomes") or []
    outcome_label = outcomes[outcome_index] if outcome_index < len(outcomes) else None
    return {
        "record_type": "snapshot", "venue": "polymarket", "sport": market.get("sport"),
        "event_id": market.get("event_id"), "event_slug": market.get("event_slug"),
        "condition_id": market.get("condition_id"), "question": market.get("question"),
        "token_id": token_id, "outcome_index": outcome_index, "outcome_label": outcome_label,
        "market_state": market.get("state"),
        "ts_ms": ts_ms, "enqueue_ts_ms": enqueue_ts_ms, "capture_ts": capture_ts,
        "book": book_body, "midpoint_raw": midpoint_body,
        "best_bid": best_bid, "best_ask": best_ask,
        "best_bid_size": best_bid_size, "best_ask_size": best_ask_size,
        "depth_bid": depth_bid, "depth_ask": depth_ask,
        "mid": _mid(best_bid, best_ask, midpoint_body),
        "close_time": close_time if isinstance(close_time, str) else None,
        "minutes_to_close": compute_minutes_to_close(close_time, ts_ms),
        "capture_version": CAPTURE_VERSION,
    }


def fetch_error_row(market: Dict[str, Any], token_id: str, outcome_index: int,
                     ts_ms: Optional[int], enqueue_ts_ms: Optional[int], capture_ts: str,
                     reason: Optional[str]) -> Dict[str, Any]:
    return {"record_type": "fetch_error", "venue": "polymarket", "sport": market.get("sport"),
            "event_id": market.get("event_id"), "event_slug": market.get("event_slug"),
            "condition_id": market.get("condition_id"), "token_id": token_id,
            "outcome_index": outcome_index, "capture_ts": capture_ts,
            "ts_ms": ts_ms, "enqueue_ts_ms": enqueue_ts_ms,
            "reason": reason or "fetch_failed", "capture_version": CAPTURE_VERSION}


__all__ = ["LIVE_ARCHIVE_ROOT", "SCRATCH_ARCHIVE_ROOT", "CAPTURE_VERSION",
           "iso", "append", "write_json_atomic", "compute_minutes_to_close", "live_archive_enabled",
           "archive_path", "heartbeat_path", "book_metrics", "book_row", "fetch_error_row"]
