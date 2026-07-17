"""scripts.platformkit.odds_provider.snapshot -- team-market line-history WRITER.

Generalises the prop_line_history pattern (scripts.platformkit.prop_line_history)
from player props to the THREE team markets (moneyline / spread / total). Every
tick, append one append-only JSONL row per (game, market, side) MarketQuote to a
per-sport, per-date history file under data/cache/line_history/<sport>/<date>.jsonl
(data/ is gitignored runtime). The last row captured for a (game, market, side)
before tip is the CLOSING-line source for CLV (line_store.get_close reads it).

HONESTY (binding):
  * Append-only TIME SERIES -- no dedup, never overwrites; the loop calls this
    every tick up to lock time so the history accrues a real open->close path.
  * Never fabricates a quote: a malformed / under-priced row is SKIPPED, not
    invented. write_quotes NEVER raises -- it degrades to a skip + status.
  * A captured-at-lock close is a TRUE close; a last-observed-only line is a
    PROXY. This writer only RECORDS; line_store decides true-vs-proxy from the
    lock window. We never stamp is_true_close here.

JSONL ROW SHAPE (one line per quote; the contract line_store.py reads):
  {
    "sport": str, "game_id": str, "home": str, "away": str,
    "market_type": "moneyline"|"spread"|"total",
    "side": "home"|"away"|"over"|"under",
    "line": float|None, "odds": float (decimal > 1.0), "book": str,
    "devigged_prob": float|None,
    "captured_at": ISO-8601 UTC,        # when this quote was observed
    "captured_at_suspect": bool,        # True -> poller-clock guard tripped;
                                         # line_store never treats this as a TRUE close
    "commence_time": ISO-8601 UTC|None  # tipoff/lock time, when known
  }

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only;
stdlib only; no network here (quotes + now injected by the caller / loop).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_snapshot.py -q
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .markets import MarketQuote

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
# data/ is the gitignored runtime tree (see data-vault-nocommit rule).
DEFAULT_HISTORY_DIR = _HERE.parents[2] / "data" / "cache" / "line_history"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _date_of(iso_ts: str, fallback: datetime) -> str:
    """UTC calendar date (YYYY-MM-DD) of an ISO timestamp; fallback on parse fail."""
    try:
        dt = datetime.fromisoformat(str(iso_ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).date().isoformat()
    except (TypeError, ValueError):
        return fallback.astimezone(timezone.utc).date().isoformat()


def _row_from_quote(q: MarketQuote, commence: Optional[str]) -> Optional[Dict[str, Any]]:
    """A history row from a MarketQuote, or None if the quote is unusable.

    Mirrors MarketQuote.to_dict() exactly (so line_store can rebuild a quote) plus
    a 'commence_time' lock-time field. A quote with no usable decimal price (odds
    <= 1.0) is dropped -- never logged as a fabricated line.
    """
    try:
        odds = float(q.odds)
    except (TypeError, ValueError):
        return None
    if not (odds > 1.0):
        return None
    game_id = str(getattr(q, "game_id", "") or "").strip()
    side = str(getattr(q, "side", "") or "").strip()
    market_type = str(getattr(q, "market_type", "") or "").strip()
    captured_at = str(getattr(q, "captured_at", "") or "").strip()
    if not game_id or not side or not market_type or not captured_at:
        return None
    line = getattr(q, "line", None)
    return {
        "sport": str(getattr(q, "sport", "") or ""),
        "game_id": game_id,
        "home": str(getattr(q, "home", "") or ""),
        "away": str(getattr(q, "away", "") or ""),
        "market_type": market_type,
        "side": side,
        "line": (float(line) if line is not None else None),
        "odds": odds,
        "book": str(getattr(q, "book", "") or ""),
        "devigged_prob": (float(q.devigged_prob)
                          if getattr(q, "devigged_prob", None) is not None else None),
        "captured_at": captured_at,
        # markets.py's clock-trust guard (CAPTURED_AT_SUSPECT_WINDOW_SEC): True
        # when this tick's captured_at disagreed with the poller's own clock --
        # line_store treats a suspect row as PROXY-only, never a TRUE close.
        "captured_at_suspect": bool(getattr(q, "captured_at_suspect", False)),
        "commence_time": (str(commence) if commence else None),
    }


def write_quotes(
    quotes: List[MarketQuote],
    *,
    out_dir: Optional[Path] = None,
    now: Optional[datetime] = None,
    commence_by_game: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Append one history row per usable MarketQuote to the per-sport/date JSONL.

    Each quote lands in data/cache/line_history/<sport>/<date>.jsonl where <date>
    is the UTC date of the quote's captured_at (so a slate's history stays in one
    file even across many ticks). *commence_by_game* maps game_id -> tipoff ISO so
    line_store can later decide a TRUE close (captured within the lock window) from
    a last-observed PROXY. Append-only; never overwrites; a bad row is skipped.

    Injectables (offline-testable): *out_dir* overrides DEFAULT_HISTORY_DIR; *now*
    is the UTC fallback used only for the date bucket when a quote has no
    captured_at. NEVER raises -- returns {logged, skipped, files, status}.
    """
    base = Path(out_dir) if out_dir is not None else DEFAULT_HISTORY_DIR
    nowdt = now if now is not None else _now()
    cmap = commence_by_game or {}
    out: Dict[str, Any] = {"logged": 0, "skipped": 0, "files": []}
    # Group rows by destination file so one open()+append covers a whole tick.
    grouped: Dict[Path, List[str]] = {}
    try:
        for q in quotes or []:
            row = _row_from_quote(q, cmap.get(str(getattr(q, "game_id", "") or "").strip()))
            if row is None:
                out["skipped"] += 1
                continue
            sport = (row["sport"] or "unknown").lower()
            date = _date_of(row["captured_at"], nowdt)
            target = base / sport / ("%s.jsonl" % date)
            grouped.setdefault(target, []).append(json.dumps(row, default=str))
        files: List[str] = []
        for target, lines in grouped.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
            out["logged"] += len(lines)
            files.append(str(target))
        out["files"] = files
        out["status"] = "ok"
    except Exception as exc:  # noqa: BLE001 -- public writer must never raise
        logger.warning("write_quotes failed: %s", exc)
        out["status"] = "error: %s" % type(exc).__name__
    return out


__all__ = ["DEFAULT_HISTORY_DIR", "write_quotes"]
