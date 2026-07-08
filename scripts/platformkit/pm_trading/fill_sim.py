"""scripts.platformkit.pm_trading.fill_sim -- realistic PAPER fill simulator.

Prices a paper execution against CAPTURED Kalshi order-book depth
(data/cache/depth_history/<sport>/<date>.jsonl, written by
odds_provider.depth_capture ~every 20 min per ticker, measured 2026-07-07)
instead of the snapshot mid/last the placers record today. PAPER ONLY:
measurement, no order path, no edge claim.

Book row shape (depth_capture.CAPTURE_VERSION=1):
  {"ts", "ticker", "event_ticker", "yes_bids": [[price, size]...],
   "yes_asks": [[price, size]...]}    # yes_asks is the RAW no_dollars ladder
Ladders are ASC by price; a resting NO bid at p fills a YES buy at 1-p (and
vice versa), so BUYING side X walks the OPPOSITE side's bid ladder from its
highest price down.

Fail-closed: stale (> max_age_sec) or missing/empty book -> None, and the
wrapper stamps fill_quality="no_book" so a caller can still write the bet at
its snapshot price but never pretend a mid-fill was a book-fill.

INVARIANTS: scripts/platformkit only; <=300 LOC; ASCII; stdlib only; paper.
Per-file test:
  python -m pytest scripts/platformkit/pm_trading/test_fill_sim.py -q
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parents[3]
DEFAULT_DEPTH_DIR = _REPO / "data" / "cache" / "depth_history"

FILL_MAX_AGE_SEC = 120.0
# Wrapper default matches the measured capture cadence (~20 min/ticker) + slack;
# a 120s bar against a 20-min feed would stamp nearly every live bet no_book.
LOOKUP_MAX_AGE_SEC = 1500.0
# ponytail: documented mapping choice -- 1 paper unit = 100 contracts (a modest
# real order); make it a caller param if unit sizing ever gets a real notional.
CONTRACTS_PER_UNIT = 100.0

_NO_BOOK: Dict[str, Any] = {
    "fill_prob": None, "n_filled": 0.0, "slippage_prob": None,
    "book_age_sec": None, "fill_quality": "no_book",
}


def _parse_ts(s: Any) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _rungs(ladder: Any) -> List[List[float]]:
    """Valid [[price, size]...] rungs sorted DESC by price (best-crossable first)."""
    out: List[List[float]] = []
    for r in ladder if isinstance(ladder, list) else []:
        try:
            p, sz = float(r[0]), float(r[1])
        except (TypeError, ValueError, IndexError):
            continue
        if 0.0 < p < 1.0 and sz > 0.0:
            out.append([p, sz])
    return sorted(out, key=lambda r: -r[0])


def fill_price(side: str, stake_contracts: float, book_snapshot: Any, *,
               max_age_sec: float = FILL_MAX_AGE_SEC,
               now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """VWAP fill for BUYING *side* ("yes"|"no") of *stake_contracts* against one
    captured book row. Walks the opposite side's bid ladder best-first; partial
    fill when depth is short. Returns {fill_prob, n_filled, slippage_prob,
    book_age_sec} or None on stale/missing/empty book (fail closed)."""
    if not isinstance(book_snapshot, dict) or side not in ("yes", "no"):
        return None
    ts = _parse_ts(book_snapshot.get("ts"))
    if ts is None:
        return None
    age = ((now or datetime.now(timezone.utc)) - ts).total_seconds()
    if age > float(max_age_sec):
        return None
    yes_bids = _rungs(book_snapshot.get("yes_bids"))
    no_bids = _rungs(book_snapshot.get("yes_asks"))  # raw no_dollars ladder
    if not yes_bids or not no_bids:
        return None  # need both sides for a mid -- fail closed
    mid_yes = (yes_bids[0][0] + (1.0 - no_bids[0][0])) / 2.0
    mid = mid_yes if side == "yes" else 1.0 - mid_yes
    cross = no_bids if side == "yes" else yes_bids
    try:
        remaining = float(stake_contracts)
    except (TypeError, ValueError):
        return None
    if remaining <= 0.0:
        return None
    cost = filled = 0.0
    for p, sz in cross:
        take = min(remaining, sz)
        cost += take * (1.0 - p)
        filled += take
        remaining -= take
        if remaining <= 0.0:
            break
    if filled <= 0.0:
        return None
    vwap = cost / filled
    return {"fill_prob": round(vwap, 6), "n_filled": round(filled, 2),
            "slippage_prob": round(vwap - mid, 6), "book_age_sec": round(age, 1)}


def _scan_file(path: Path, needle: str) -> Optional[Dict[str, Any]]:
    """Last (freshest) JSONL row in *path* whose line contains *needle*."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if needle in line:
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


def _sport_dirs(sport: Optional[str], base: Path) -> List[Path]:
    if sport:
        d = base / str(sport)
        return [d] if d.is_dir() else []
    return [d for d in base.iterdir() if d.is_dir()] if base.is_dir() else []


def freshest_book(ticker: str, *, sport: Optional[str] = None,
                  base_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Freshest captured depth row for *ticker* across the 2 newest dated files
    per sport dir (narrowed by *sport* when the caller knows it). None-safe."""
    base = Path(base_dir) if base_dir is not None else DEFAULT_DEPTH_DIR
    needle = '"ticker": %s' % json.dumps(str(ticker))
    best: Optional[Dict[str, Any]] = None
    for d in _sport_dirs(sport, base):
        for f in sorted(d.glob("*.jsonl"), reverse=True)[:2]:
            row = _scan_file(f, needle)
            if row is not None and (best is None or str(row.get("ts", "")) > str(best.get("ts", ""))):
                best = row
            if row is not None:
                break  # newer file already had it; older file cannot be fresher
    return best


def simulate_fill(ticker: str, side: str, stake_units: float, *,
                  ts: Optional[str] = None, sport: Optional[str] = None,
                  base_dir: Optional[Path] = None,
                  max_age_sec: float = LOOKUP_MAX_AGE_SEC,
                  contracts_per_unit: float = CONTRACTS_PER_UNIT) -> Dict[str, Any]:
    """Placement-path wrapper: find the freshest captured book for *ticker* and
    price a *stake_units* paper order. Always returns the 5 additive ledger
    fields; fill_quality="no_book" when there is no usable (fresh) book --
    book_age_sec still reported when a book existed but was stale."""
    if not ticker:
        return dict(_NO_BOOK)
    row = freshest_book(str(ticker), sport=sport, base_dir=base_dir)
    if row is None:
        return dict(_NO_BOOK)
    now_dt = _parse_ts(ts) or datetime.now(timezone.utc)
    res = fill_price(side, float(stake_units) * float(contracts_per_unit), row,
                     max_age_sec=max_age_sec, now=now_dt)
    if res is None:
        out = dict(_NO_BOOK)
        bts = _parse_ts(row.get("ts"))
        if bts is not None:
            out["book_age_sec"] = round((now_dt - bts).total_seconds(), 1)
        return out
    res["fill_quality"] = "book"
    return res


def stamp_fill(ticker: str, side: str, stake_units: float, *,
               sport: Optional[str] = None,
               base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Never-raises simulate_fill for ledger stamping (callers row.update this)."""
    try:
        return simulate_fill(ticker, side, stake_units, sport=sport, base_dir=base_dir)
    except Exception as exc:  # noqa: BLE001 -- a stamp failure must never block a bet write
        logger.debug("fill_sim stamp failed for %s: %s", ticker, exc)
        return dict(_NO_BOOK)


def event_side_tickers(event_ticker: str, *, sport: Optional[str] = None,
                       base_dir: Optional[Path] = None) -> Dict[str, Optional[str]]:
    """{'home': ticker|None, 'away': ticker|None} for a Kalshi game event.
    Market tickers are <event>-<TEAMCODE> and the event ticker ends with the
    HOME code (verified vs line_history home/away 2026-07-07), so the suffix
    the event endswith is home."""
    out: Dict[str, Optional[str]] = {"home": None, "away": None}
    ev = str(event_ticker or "")
    if not ev:
        return out
    base = Path(base_dir) if base_dir is not None else DEFAULT_DEPTH_DIR
    needle = '"event_ticker": %s' % json.dumps(ev)
    tickers: set = set()
    for d in _sport_dirs(sport, base):
        for f in sorted(d.glob("*.jsonl"), reverse=True)[:2]:
            try:
                for line in f.read_text(encoding="utf-8").splitlines():
                    if needle in line:
                        try:
                            tickers.add(str(json.loads(line).get("ticker") or ""))
                        except ValueError:
                            continue
            except OSError:
                continue
    for t in sorted(t for t in tickers if t.startswith(ev + "-")):
        role = "home" if ev.endswith(t.rsplit("-", 1)[-1]) else "away"
        out[role] = t
    return out


__all__ = [
    "DEFAULT_DEPTH_DIR", "FILL_MAX_AGE_SEC", "LOOKUP_MAX_AGE_SEC",
    "CONTRACTS_PER_UNIT", "fill_price", "freshest_book", "simulate_fill",
    "stamp_fill", "event_side_tickers",
]
