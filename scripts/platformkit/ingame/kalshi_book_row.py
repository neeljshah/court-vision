"""scripts.platformkit.ingame.kalshi_book_row -- Kalshi snapshot row + archive I/O.

Split out of kalshi_book_capture.py to keep both files under the 300 LOC cap: this
module owns the per-market SNAPSHOT ROW shape and the archive/heartbeat path
helpers; kalshi_book_capture.py owns the capture LOOP (GovernedClient, discovery
cache, the per-tick orchestration). Raw ladder extraction reuses mlb_book_capture's
own body parser and ingame_book_depth_kalshi's parse_orderbook rather than
re-stating the venue's field names here -- see book_row() for the exact derived-
price convention. ARCHIVE OWNERSHIP: this tree is data/cache/ingame_books/
kalshi_multi/<sport>/, NOT ingame_books/mlb/ -- the landed mlb_book_capture.py
already owns MLB GAME books at that path; a second writer there would collide.
_default_sports() therefore excludes mlb unless CV_KALSHI_MULTI_INCLUDE_MLB=1
(MLB derivative series only, never KXMLBGAME -- see kalshi_book_capture.py).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_kalshi_book_capture.py -q
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.ingame import kalshi_series_scope as scope
from scripts.platformkit.ingame.ingame_book_depth_kalshi import parse_orderbook
from scripts.platformkit.ingame.mlb_book_capture import _levels as _raw_ladders

_ROOT = Path(__file__).resolve().parents[3]
_BOOKS_ROOT = _ROOT / "data" / "cache" / "ingame_books"
LIVE_ARCHIVE_ROOT = _BOOKS_ROOT / "kalshi_multi"
SCRATCH_ARCHIVE_ROOT = _BOOKS_ROOT / "_scratch" / "kalshi_multi"
CAPTURE_VERSION = "kalshi_book_capture_v1"
ENV_INCLUDE_MLB = "CV_KALSHI_MULTI_INCLUDE_MLB"


def iso(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def live_archive_enabled(env: Optional[Dict[str, str]] = None) -> bool:
    """True only for the explicitly designated POD writer."""
    values = env if env is not None else os.environ
    return values.get("CV_CAPTURE_POD") == "1" and values.get("CV_KALSHI_BOOK_ARCHIVE_LIVE") == "1"


def default_sports(env: Optional[Dict[str, str]] = None) -> List[str]:
    """Every allowlisted sport except mlb, unless ENV_INCLUDE_MLB=1 -- see the
    ARCHIVE OWNERSHIP note in the module docstring."""
    values = env if env is not None else os.environ
    sports = list(scope.SERIES_BY_SPORT)
    if values.get(ENV_INCLUDE_MLB) != "1":
        sports = [s for s in sports if s != "mlb"]
    return sports


def _root(env: Optional[Dict[str, str]] = None) -> Path:
    return LIVE_ARCHIVE_ROOT if live_archive_enabled(env) else SCRATCH_ARCHIVE_ROOT


def archive_path(sport: str, now: datetime, env: Optional[Dict[str, str]] = None) -> Path:
    """Date-sharded, per-sport live path on the POD, scratch path everywhere else."""
    return _root(env) / sport / (now.strftime("%Y-%m-%d") + ".jsonl")


def heartbeat_path(sport: str, env: Optional[Dict[str, str]] = None) -> Path:
    return _root(env) / sport / "_heartbeat.json"


def append(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="ascii", errors="backslashreplace") as fh:
        fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    """Best-effort atomic tmp+replace write (mirrors kalshi_rate_governor's own
    state write) -- a heartbeat write failure is observability only, never
    fatal to capture."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=True, sort_keys=True), encoding="ascii")
        os.replace(str(tmp), str(path))
    except OSError:
        pass


def _ladder(rungs: Any) -> List[List[float]]:
    """Coerce one orderbook_fp ladder to [[price_float, size_float], ...] ASC,
    skipping any unusable rung. Never raises; malformed/absent -> []."""
    out: List[List[float]] = []
    if not isinstance(rungs, list):
        return out
    for rung in rungs:
        try:
            if not isinstance(rung, (list, tuple)) or len(rung) < 2:
                continue
            out.append([float(rung[0]), float(rung[1])])
        except (TypeError, ValueError, IndexError):
            continue
    return out


def book_row(market: Dict[str, Any], body: Any, ts_ms: int, capture_ts: str,
             enqueue_ts_ms: Optional[int] = None) -> Dict[str, Any]:
    """One snapshot row. DERIVED-PRICE CONVENTION: the venue's keyless orderbook
    endpoint returns only two resting-BID ladders, price units in [0,1] ASC (see
    ingame_book_depth_kalshi.py's docstring for the field layout; reused here via
    parse_orderbook and mlb_book_capture._levels rather than restated). No
    separate ask ladder exists: parse_orderbook already derives yes_ask from the
    raw no-side ladder; this function then derives no_bid/no_ask as the algebraic
    inverse of yes_ask/yes_bid (not re-derived from the raw no ladder again). The
    raw response is stored verbatim under "book" -- no transformation there."""
    best_yes_bid, best_yes_ask, _bid_thin, _ask_thin, _n = parse_orderbook(
        body if isinstance(body, dict) else {})
    best_no_bid = (1.0 - best_yes_ask) if best_yes_ask is not None else None
    best_no_ask = (1.0 - best_yes_bid) if best_yes_bid is not None else None
    raw = _raw_ladders(body)
    yes_ladder = _ladder(raw["yes"])
    no_ladder = _ladder(raw["no"])
    return {
        "record_type": "snapshot", "venue": "kalshi", "sport": market["sport"],
        "series": market.get("series_ticker"), "ticker": market.get("ticker"),
        "event_ticker": market.get("event_ticker"), "market_state": market.get("state"),
        "ts_ms": ts_ms, "enqueue_ts_ms": enqueue_ts_ms,
        "api_ts": body.get("ts") if isinstance(body, dict) else None,
        "capture_ts": capture_ts, "book": body,
        "yes_bid": best_yes_bid, "yes_ask": best_yes_ask,
        "no_bid": best_no_bid, "no_ask": best_no_ask,
        "yes_bid_size": yes_ladder[-1][1] if yes_ladder else None,
        "no_bid_size": no_ladder[-1][1] if no_ladder else None,
        "depth_bid": round(sum(sz for _p, sz in yes_ladder), 2),
        "depth_ask": round(sum(sz for _p, sz in no_ladder), 2),
        "yes_bid_top5_asc": yes_ladder[-5:], "no_bid_top5_asc": no_ladder[-5:],
        "capture_version": CAPTURE_VERSION,
    }


def fetch_error_row(market: Dict[str, Any], ts_ms: Optional[int], enqueue_ts_ms: Optional[int],
                     capture_ts: str, reason: Optional[str]) -> Dict[str, Any]:
    return {"record_type": "fetch_error", "venue": "kalshi", "sport": market["sport"],
            "series": market.get("series_ticker"), "ticker": market.get("ticker"),
            "event_ticker": market.get("event_ticker"), "capture_ts": capture_ts,
            "ts_ms": ts_ms, "enqueue_ts_ms": enqueue_ts_ms,
            "reason": reason or "fetch_failed", "capture_version": CAPTURE_VERSION}


__all__ = ["LIVE_ARCHIVE_ROOT", "SCRATCH_ARCHIVE_ROOT", "CAPTURE_VERSION", "ENV_INCLUDE_MLB",
           "iso", "live_archive_enabled", "default_sports", "archive_path", "heartbeat_path",
           "append", "write_json_atomic", "book_row", "fetch_error_row", "parse_orderbook"]
