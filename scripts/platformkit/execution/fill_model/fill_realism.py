"""scripts.platformkit.execution.fill_model.fill_realism -- MEASUREMENT ONLY:
for our own recorded paper Kalshi orders (data/frontend/clv_ledger.jsonl),
check whether the claimed entry price was actually marketable against the
CAPTURED book (data/cache/book_depth/kalshi/*.jsonl) and/or confirmed by an
actual trade print (data/cache/book_depth/kalshi_trades/*.jsonl). No order
path, no policy change, no $/ROI/edge claim -- price/probability terms only.
Reuses scripts.platformkit.execution.book_replay's load_jsonl/half_spread/
epoch helpers rather than re-implementing them (same archive, same parsing).

STEP-0 PREMISE CHECK (2026-07-11, this run):
  - clv_ledger.jsonl has 743 kalshi rows (647 with ts+market_id); taken_decimal
    is always present, taken_implied_prob only on graded rows -- computed
    fresh here as 1/taken_decimal for uniform coverage (open + graded).
  - book_depth/kalshi/*.jsonl (6 days, 07-04..07-09) shares 55 tickers with
    the ledger's market_ids -- usable for the spread-marketability check below.
  - book_depth/kalshi_trades/2026-07-09.jsonl (35,182 rows, 1 day, 46 unique
    tickers) is a REAL per-trade PRICE tape (trade_ts, price, taker_side) --
    this predates book_replay.py's "no per-trade price tape exists" note,
    which is now stale for kalshi_trades specifically (still true for
    depth_history's yes_bids/yes_asks ladders, which book_replay covers).
  - Ticker overlap between the ledger and this trade tape is 0 (checked):
    the tape's single captured day never coincides with a ledger market_id's
    game date. Trade-print CONFIRMATION is therefore NOT_TESTABLE today --
    not a capture-format bug, just insufficient calendar days accumulated
    yet. The join code below is generic and will start producing N>0 the
    day a paper order's ticker and a trade-tape day coincide.
  - The trade tape's "count" (trade size) field is null on all 35,182 rows
    (checked) -- Kalshi's trades endpoint is not returning size here (see
    ingame_book_depth_kalshi.py fetch_trades/normalize_trade, "best-effort").
    Order-size-vs-displayed-depth slippage modeling is therefore NOT_TESTABLE;
    the capture change needed is confirming/fixing the trades endpoint field
    name upstream -- that poller is outside this lane's ownership, flagged
    here as a PROPOSED capture change, not applied.
INVARIANTS: <=300 LOC; ASCII; stdlib only; local-only output; never writes
data/registry/; never flips a flag; no $/ROI/edge claim.
Test: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/execution/fill_model/test_fill_realism.py -q
"""
from __future__ import annotations

import argparse
import glob
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.execution.book_replay import _epoch, half_spread, load_jsonl

_REPO = Path(__file__).resolve().parents[4]
LEDGER_PATH = _REPO / "data" / "frontend" / "clv_ledger.jsonl"
BOOK_DEPTH_DIR = _REPO / "data" / "cache" / "book_depth" / "kalshi"
TRADE_TAPE_DIR = _REPO / "data" / "cache" / "book_depth" / "kalshi_trades"
DEPTH_MATCH_WINDOW_S = 600.0  # nearest book_depth snapshot must be within 10min of order ts
TRADE_CONFIRM_WINDOW_S = 300.0  # a confirming print must land within 5min after order ts
PRICE_TOL = 0.005  # Kalshi cent-level float noise tolerance


def load_kalshi_orders(sport: Optional[str] = None) -> List[Dict[str, Any]]:
    """Kalshi rows from the paper ledger with a usable ts+ticker+price. Never raises."""
    out: List[Dict[str, Any]] = []
    for r in load_jsonl(LEDGER_PATH):
        if r.get("taken_book") != "kalshi" or not r.get("ts") or not r.get("market_id"):
            continue
        if sport is not None and r.get("sport") != sport:
            continue
        try:
            decimal = float(r["taken_decimal"])
        except (TypeError, ValueError, KeyError):
            continue
        if decimal <= 1.0:
            continue
        out.append({**r, "implied_prob": round(1.0 / decimal, 6)})
    return out


def load_trade_tape(sport: Optional[str] = None) -> List[Dict[str, Any]]:
    """All book_depth/kalshi_trades rows (every captured day). Never raises."""
    out: List[Dict[str, Any]] = []
    for p in sorted(glob.glob(str(TRADE_TAPE_DIR / "*.jsonl"))):
        for r in load_jsonl(Path(p)):
            if sport is None or r.get("sport") == sport:
                out.append(r)
    return out


def load_book_depth_by_ticker(sport: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """{ticker: [rows sorted ASC by ts]} from book_depth/kalshi/*.jsonl."""
    rows: List[Dict[str, Any]] = []
    for p in sorted(glob.glob(str(BOOK_DEPTH_DIR / "*.jsonl"))):
        for r in load_jsonl(Path(p)):
            if (sport is None or r.get("sport") == sport) and r.get("ticker") and r.get("ts"):
                rows.append(r)
    by_ticker: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_ticker[r["ticker"]].append(r)
    for tk in by_ticker:
        by_ticker[tk].sort(key=lambda r: str(r["ts"]))
    return by_ticker


def nearest_snapshot(snaps: List[Dict[str, Any]], t0: float, window_s: float) -> Optional[Dict[str, Any]]:
    """Snapshot with min |ts-t0| within window_s, else None. snaps sorted ASC by ts."""
    best, best_dt = None, None
    for r in snaps:
        t = _epoch(r.get("ts"))
        if t is None:
            continue
        dt = abs(t - t0)
        if dt <= window_s and (best_dt is None or dt < best_dt):
            best, best_dt = r, dt
    return best


def marketability(order: Dict[str, Any], snap: Dict[str, Any]) -> Optional[str]:
    """'plausible' if implied_prob is within [best_bid-tol, best_ask+tol] of the
    matched snapshot (a taker buying at/inside the displayed book), else
    'optimistic' (claims a better price than the book showed). None if the
    snapshot is unquoted."""
    bid, ask = snap.get("best_bid"), snap.get("best_ask")
    if half_spread(bid, ask) is None:
        return None
    p = order["implied_prob"]
    return "plausible" if (bid - PRICE_TOL) <= p <= (ask + PRICE_TOL) else "optimistic"


def trade_confirms(order: Dict[str, Any], trades_by_ticker: Dict[str, List[Dict[str, Any]]],
                    window_s: float = TRADE_CONFIRM_WINDOW_S) -> Optional[bool]:
    """True if a trade printed at/through the order's implied price within
    window_s after order ts on the same ticker. None if no trade on that
    ticker exists in the tape at all (NOT_TESTABLE for this order)."""
    t0 = _epoch(order.get("ts"))
    ticker = order.get("market_id")
    trs = trades_by_ticker.get(ticker)
    if t0 is None or not trs:
        return None
    p = order["implied_prob"]
    for t in trs:
        tt = _epoch(t.get("trade_ts") or t.get("ts"))
        price = t.get("price")
        if tt is None or price is None or tt < t0 or tt - t0 > window_s:
            continue
        if abs(float(price) - p) <= PRICE_TOL or float(price) <= p:
            return True
    return False


def run_fill_realism(sport: Optional[str] = None, window_s: float = DEPTH_MATCH_WINDOW_S) -> Dict[str, Any]:
    orders = load_kalshi_orders(sport)
    depth_by_ticker = load_book_depth_by_ticker(sport)
    trade_rows = load_trade_tape(sport)
    trades_by_ticker: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t in trade_rows:
        if t.get("ticker"):
            trades_by_ticker[t["ticker"]].append(t)

    n_orders = len(orders)
    n_depth_matched = 0
    plausible, optimistic = 0, 0
    n_tape_ticker_present = 0
    n_confirmed = 0

    for o in orders:
        t0 = _epoch(o.get("ts"))
        snaps = depth_by_ticker.get(o.get("market_id"))
        if t0 is not None and snaps:
            snap = nearest_snapshot(snaps, t0, window_s)
            if snap is not None:
                verdict = marketability(o, snap)
                if verdict == "plausible":
                    n_depth_matched += 1
                    plausible += 1
                elif verdict == "optimistic":
                    n_depth_matched += 1
                    optimistic += 1
        if o.get("market_id") in trades_by_ticker:
            n_tape_ticker_present += 1
            if trade_confirms(o, trades_by_ticker):
                n_confirmed += 1

    depth_verdict = (
        "NOT_TESTABLE -- 0 orders had a book_depth snapshot within window"
        if n_depth_matched == 0
        else "measured"
    )
    tape_verdict = (
        "NOT_TESTABLE -- 0 ledger orders share a ticker with the (currently "
        "single-day) trade tape; needs more accumulated capture days, not a "
        "format fix"
        if n_tape_ticker_present == 0
        else "measured"
    )
    return {
        "sport_filter": sport,
        "edge_claimed": False,
        "n_kalshi_orders": n_orders,
        "spread_marketability": {
            "verdict": depth_verdict,
            "n_depth_matched": n_depth_matched,
            "pct_plausible": round(100.0 * plausible / n_depth_matched, 2) if n_depth_matched else None,
            "pct_optimistic": round(100.0 * optimistic / n_depth_matched, 2) if n_depth_matched else None,
        },
        "trade_tape_confirmation": {
            "verdict": tape_verdict,
            "n_ticker_overlap": n_tape_ticker_present,
            "n_confirmed": n_confirmed,
            "pct_confirmed": round(100.0 * n_confirmed / n_tape_ticker_present, 2) if n_tape_ticker_present else None,
        },
        "order_size_vs_depth_slippage": {
            "verdict": "NOT_TESTABLE -- trade tape 'count' (size) field is null "
                       "on every row; Kalshi trades endpoint is not returning "
                       "size in this capture (see ingame_book_depth_kalshi.py "
                       "fetch_trades) -- capture change proposed, not applied",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Kalshi paper-order fill-realism measurement (no $/edge claim)")
    ap.add_argument("--sport", default=None)
    ap.add_argument("--window", type=float, default=DEPTH_MATCH_WINDOW_S, help="book_depth match window (s)")
    args = ap.parse_args()
    report = run_fill_realism(sport=args.sport, window_s=args.window)
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0


__all__ = ["load_kalshi_orders", "load_trade_tape", "load_book_depth_by_ticker",
           "nearest_snapshot", "marketability", "trade_confirms", "run_fill_realism"]

if __name__ == "__main__":
    raise SystemExit(main())
