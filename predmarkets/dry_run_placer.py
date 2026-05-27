"""Dry-run order placer + auto-settle for the predmarkets pipeline.

Pipeline ergonomics mirror scripts/strategy_d_auto_settle.py:
    scan -> place_dry_run_batch -> CSV ledger with status='dry-run-pending'
    settle_ledger -> auto-grades pending rows once the market resolves

This module DOES NOT and CANNOT place real orders. All output goes to a CSV
ledger; promoting to live requires a separate, deliberate code path (TIER 5+)
gated by an explicit --live flag and per-session reauthorization.

CSV columns (one per intended order):
    placed_at, venue, market_id, question, category, side, model_prob,
    edge_pp, price, stake_dollars, ev_dollars, kelly_used, confidence,
    model_name, reasoning, status, settled_at, market_resolution,
    actual_payout, profit, running_pnl

status flow:
    dry-run-pending  -> WIN | LOSS | PUSH | VOID | UNRESOLVED
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from predmarkets.edge_scanner import (
    EdgeScanner,
    EdgeScannerConfig,
    Forecaster,
    load_snapshot,
)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_LEDGER_DIR = os.path.join(PROJECT_DIR, "data", "predmarkets_ledger")

LEDGER_COLS = [
    "placed_at", "venue", "market_id", "question", "category", "side",
    "model_prob", "edge_pp", "price", "stake_dollars", "ev_dollars",
    "kelly_used", "confidence", "model_name", "reasoning",
    "status", "settled_at", "market_resolution", "actual_payout",
    "profit", "running_pnl",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_ledger(path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8", newline="") as fh:
            csv.DictWriter(fh, fieldnames=LEDGER_COLS).writeheader()


def _read_rows(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _write_rows(path: str, rows: Sequence[Dict[str, str]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LEDGER_COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in LEDGER_COLS})


def _edge_to_row(edge: Dict[str, Any]) -> Dict[str, str]:
    return {
        "placed_at": _now_iso(),
        "venue": str(edge.get("venue") or ""),
        "market_id": str(edge.get("market_id") or ""),
        "question": str(edge.get("question") or ""),
        "category": str(edge.get("category") or ""),
        "side": str(edge.get("side") or ""),
        "model_prob": f"{float(edge.get('model_prob') or 0.0):.4f}",
        "edge_pp": f"{float(edge.get('edge_pp') or 0.0):+.4f}",
        "price": f"{float(edge.get('price') or 0.0):.4f}",
        "stake_dollars": f"{float(edge.get('stake_dollars') or 0.0):.2f}",
        "ev_dollars": f"{float(edge.get('expected_value_dollars') or 0.0):.2f}",
        "kelly_used": f"{float(edge.get('kelly_used') or 0.0):.4f}",
        "confidence": f"{float(edge.get('confidence') or 0.0):.3f}",
        "model_name": str(edge.get("model_name") or ""),
        "reasoning": str(edge.get("reasoning") or ""),
        "status": "dry-run-pending",
        "settled_at": "",
        "market_resolution": "",
        "actual_payout": "",
        "profit": "",
        "running_pnl": "",
    }


def place_dry_run_batch(
    edges: Sequence[Dict[str, Any]],
    ledger_path: str,
    min_stake: float = 0.01,
) -> Dict[str, Any]:
    """Append edges (from EdgeScanner.scan) to the dry-run ledger.

    Skips zero-stake rows (cap shrunk them to zero) unless `min_stake` is 0.
    Returns {"placed": n, "skipped_zero_stake": n, "ledger": path}.
    """
    _ensure_ledger(ledger_path)
    existing = _read_rows(ledger_path)
    existing_keys = {(r["venue"], r["market_id"], r["side"]) for r in existing}
    placed = 0
    skipped = 0
    deduped = 0
    rows: List[Dict[str, str]] = list(existing)
    for e in edges:
        stake = float(e.get("stake_dollars") or 0.0)
        if stake < min_stake:
            skipped += 1
            continue
        key = (str(e.get("venue") or ""), str(e.get("market_id") or ""), str(e.get("side") or ""))
        if key in existing_keys:
            deduped += 1
            continue
        rows.append(_edge_to_row(e))
        existing_keys.add(key)
        placed += 1
    _write_rows(ledger_path, rows)
    return {
        "placed": placed,
        "skipped_zero_stake": skipped,
        "skipped_duplicate": deduped,
        "ledger": ledger_path,
        "total_rows_in_ledger": len(rows),
    }


def _pm_resolution(venue_clients: Dict[str, Any], market_id: str) -> Optional[Dict[str, Any]]:
    """Return {resolved: bool, yes_won: bool|None, closed_time: iso|None} for a PM market."""
    pm = venue_clients.get("polymarket")
    if pm is None:
        return None
    try:
        m = pm.get_market(market_id)
    except Exception:
        return None
    if not m.get("closed"):
        return {"resolved": False, "yes_won": None, "closed_time": None}
    op = m.get("outcomePrices") or []
    yes_won: Optional[bool] = None
    if isinstance(op, list) and len(op) >= 2:
        try:
            yes_price = float(op[0])
            no_price = float(op[1])
            if yes_price > 0.99 and no_price < 0.01:
                yes_won = True
            elif no_price > 0.99 and yes_price < 0.01:
                yes_won = False
        except (TypeError, ValueError):
            pass
    return {
        "resolved": True,
        "yes_won": yes_won,
        "closed_time": m.get("closedTime") or m.get("umaEndDate"),
    }


def _kalshi_resolution(venue_clients: Dict[str, Any], ticker: str) -> Optional[Dict[str, Any]]:
    ks = venue_clients.get("kalshi")
    if ks is None:
        return None
    try:
        m = ks.get_market(ticker)
    except Exception:
        return None
    status = (m.get("status") or "").lower()
    if status != "settled":
        return {"resolved": False, "yes_won": None, "closed_time": None}
    result = (m.get("result") or "").lower()
    yes_won: Optional[bool] = None
    if result == "yes":
        yes_won = True
    elif result == "no":
        yes_won = False
    return {
        "resolved": True,
        "yes_won": yes_won,
        "closed_time": m.get("close_time"),
    }


def _grade_row(row: Dict[str, str], resolution: Dict[str, Any]) -> Dict[str, str]:
    """Update a pending row based on a resolution payload."""
    if not resolution.get("resolved"):
        return row
    yes_won = resolution.get("yes_won")
    side = (row.get("side") or "").upper()
    stake = float(row.get("stake_dollars") or 0.0)
    price = float(row.get("price") or 0.0)
    row["settled_at"] = _now_iso()
    row["market_resolution"] = "YES" if yes_won is True else ("NO" if yes_won is False else "VOID")
    if yes_won is None:
        row["status"] = "VOID"
        row["actual_payout"] = "0.00"
        row["profit"] = "0.00"
        return row
    bet_won = (side == "YES" and yes_won) or (side == "NO" and not yes_won)
    if bet_won:
        contracts = stake / price if price > 0 else 0.0
        payout = contracts * 1.0  # each contract pays $1 on win
        profit = payout - stake
        row["status"] = "WIN"
        row["actual_payout"] = f"{payout:.2f}"
        row["profit"] = f"{profit:+.2f}"
    else:
        row["status"] = "LOSS"
        row["actual_payout"] = "0.00"
        row["profit"] = f"{-stake:+.2f}"
    return row


def settle_ledger(ledger_path: str, venue_clients: Dict[str, Any]) -> Dict[str, Any]:
    """Sweep all pending rows; grade any whose market has resolved."""
    rows = _read_rows(ledger_path)
    if not rows:
        return {"checked": 0, "graded": 0, "still_pending": 0}
    checked = 0
    graded = 0
    for r in rows:
        if (r.get("status") or "").strip() != "dry-run-pending":
            continue
        checked += 1
        venue = (r.get("venue") or "").lower()
        if venue == "polymarket":
            res = _pm_resolution(venue_clients, r.get("market_id") or "")
        elif venue == "kalshi":
            res = _kalshi_resolution(venue_clients, r.get("market_id") or "")
        else:
            res = None
        if res is None:
            continue
        if res.get("resolved"):
            _grade_row(r, res)
            graded += 1
    # Recompute running_pnl across all rows in chronological order
    running = 0.0
    rows_sorted = sorted(rows, key=lambda r: r.get("settled_at") or r.get("placed_at") or "")
    for r in rows_sorted:
        try:
            running += float(r.get("profit") or 0.0)
        except (TypeError, ValueError):
            pass
        if (r.get("status") or "") != "dry-run-pending":
            r["running_pnl"] = f"{running:+.2f}"
    _write_rows(ledger_path, rows_sorted)
    still = sum(1 for r in rows if (r.get("status") or "") == "dry-run-pending")
    return {"checked": checked, "graded": graded, "still_pending": still, "ledger": ledger_path}


def _rollup(rows: Sequence[Dict[str, str]]) -> Dict[str, Any]:
    """Compute hit_rate / pnl / ROI / wins / losses over a set of graded rows."""
    wins = sum(1 for r in rows if (r.get("status") or "") == "WIN")
    losses = sum(1 for r in rows if (r.get("status") or "") == "LOSS")
    pnl = 0.0
    staked = 0.0
    for r in rows:
        try:
            pnl += float(r.get("profit") or 0.0)
            staked += float(r.get("stake_dollars") or 0.0)
        except (TypeError, ValueError):
            pass
    hit_rate = (wins / (wins + losses)) if (wins + losses) else None
    roi = (pnl / staked) if staked > 0 else None
    return {
        "graded": len(rows),
        "wins": wins,
        "losses": losses,
        "hit_rate": hit_rate,
        "pnl_dollars": round(pnl, 2),
        "staked_dollars": round(staked, 2),
        "roi": roi,
    }


def summarize_ledger(ledger_path: str) -> Dict[str, Any]:
    """Compute roll-up stats: hit rate, PnL, ROI, exposure. Includes per-model
    and per-category breakdowns so we can see which forecasters are pulling
    their weight and which are dragging."""
    rows = _read_rows(ledger_path)
    n_total = len(rows)
    n_pending = sum(1 for r in rows if (r.get("status") or "") == "dry-run-pending")
    graded = [r for r in rows if (r.get("status") or "") in {"WIN", "LOSS", "PUSH", "VOID"}]
    overall = _rollup(graded)
    overall.update({
        "total_rows": n_total,
        "pending": n_pending,
    })
    # By model
    by_model: Dict[str, Any] = {}
    models = sorted({(r.get("model_name") or "unknown") for r in graded})
    for m in models:
        subset = [r for r in graded if (r.get("model_name") or "unknown") == m]
        by_model[m] = _rollup(subset)
    overall["by_model"] = by_model
    # By category
    by_cat: Dict[str, Any] = {}
    cats = sorted({(r.get("category") or "uncategorized") for r in graded})
    for c in cats:
        subset = [r for r in graded if (r.get("category") or "uncategorized") == c]
        by_cat[c] = _rollup(subset)
    overall["by_category"] = by_cat
    return overall


def _cli(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Place dry-run orders and auto-settle.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_place = sub.add_parser("place", help="Scan a snapshot and place dry-run orders.")
    p_place.add_argument("--snapshot", required=True)
    p_place.add_argument("--ledger", default=os.path.join(DEFAULT_LEDGER_DIR, "ledger.csv"))
    p_place.add_argument("--bankroll", type=float, default=1000.0)
    p_place.add_argument("--threshold", type=float, default=0.05)
    p_place.add_argument("--category", default=None, help="Limit to this category (e.g. Crypto)")

    p_settle = sub.add_parser("settle", help="Auto-grade resolved markets in the ledger.")
    p_settle.add_argument("--ledger", default=os.path.join(DEFAULT_LEDGER_DIR, "ledger.csv"))

    p_summary = sub.add_parser("summary", help="Print roll-up stats for the ledger.")
    p_summary.add_argument("--ledger", default=os.path.join(DEFAULT_LEDGER_DIR, "ledger.csv"))

    args = parser.parse_args(argv)

    if args.cmd == "place":
        from predmarkets.forecasters import CryptoThresholdForecaster
        markets = load_snapshot(args.snapshot, status="open")
        if args.category:
            markets = [m for m in markets if (m.get("category") or "") == args.category]
        forecasters: List[Forecaster] = [CryptoThresholdForecaster()]
        cfg = EdgeScannerConfig(bankroll=args.bankroll, edge_threshold=args.threshold)
        scan = EdgeScanner(forecasters, cfg).scan(markets)
        report = place_dry_run_batch(scan["edges"], args.ledger)
        print(json.dumps({"scan": {k: v for k, v in scan.items() if k != "edges"}, "placement": report}, indent=2))
        return 0

    if args.cmd == "settle":
        from predmarkets import KalshiClient, PMClient
        clients = {"polymarket": PMClient(), "kalshi": KalshiClient()}
        report = settle_ledger(args.ledger, clients)
        print(json.dumps(report, indent=2))
        return 0

    if args.cmd == "summary":
        print(json.dumps(summarize_ledger(args.ledger), indent=2, default=str))
        return 0

    parser.error(f"unknown cmd {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(_cli())


__all__ = [
    "LEDGER_COLS",
    "place_dry_run_batch",
    "settle_ledger",
    "summarize_ledger",
]
