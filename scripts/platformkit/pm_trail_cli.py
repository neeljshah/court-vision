"""scripts.platformkit.pm_trail_cli -- CLI for PM paper-trade trail browsing.

Modes:
  --mode list   : paginated trade list (default); one row per trade, N lines for N rows
  --mode best   : top-N trades ranked by tier A>B>C, model_prob desc, clv_pct desc
  --mode detail : full JSON for one trade by bet_id

HONESTY CONTRACT (binding):
  * UNITS only -- no $ / dollar / roi / profit / pnl field emitted.
  * executed always False (paper channel only).
  * CLV proxy labelled is_proxy honestly; null CLV = INSUFFICIENT_DATA.
  * Stale-never-green: never marks data fresh when source is unavailable.
  * ASCII only.

Usage:
  python scripts/platformkit/pm_trail_cli.py --mode list [--venue kalshi] [--result win]
    [--tier A] [--offset 0] [--limit 25]
  python scripts/platformkit/pm_trail_cli.py --mode best [--top-n 20]
  python scripts/platformkit/pm_trail_cli.py --mode detail --bet-id <id>
  python scripts/platformkit/pm_trail_cli.py --mode detail --bet-id <id> [--ledger path]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# -- resolve repo root so imports work when invoked directly ---------------
_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.pm_trail_browse import (  # noqa: E402
    best_pm_trades,
    browse_pm_trail,
    trade_detail,
)

# ---------------------------------------------------------------------------
# Formatting helpers (ASCII only)
# ---------------------------------------------------------------------------

_COLS = ("bet_id", "ts", "sport", "matchup", "side", "venue",
         "tier", "stake_units", "status", "outcome", "clv_pct", "is_proxy")
_COL_W = (24, 16, 6, 30, 5, 12, 5, 10, 9, 7, 8, 8)


def _hdr() -> str:
    parts = []
    for col, w in zip(_COLS, _COL_W):
        parts.append(col[:w].ljust(w))
    return "  ".join(parts)


def _sep() -> str:
    return "  ".join("-" * w for w in _COL_W)


def _clv_str(trade: Dict[str, Any]) -> str:
    clv = trade.get("clv_pct")
    if clv is None:
        return "INSUF_DATA"
    return f"{clv:+.2f}%"


def _proxy_str(trade: Dict[str, Any]) -> str:
    return "proxy" if trade.get("clv_is_proxy") else "true"


def _fmt_row(trade: Dict[str, Any]) -> str:
    vals = [
        str(trade.get("bet_id") or "")[:24],
        str(trade.get("ts") or "")[:16],
        str(trade.get("sport") or "")[:6],
        str(trade.get("matchup") or "")[:30],
        str(trade.get("side") or "")[:5],
        str(trade.get("venue") or "")[:12],
        str(trade.get("tier") or "")[:5],
        str(trade.get("stake_units") or "")[:10],
        str(trade.get("status") or "")[:9],
        str(trade.get("outcome") or "")[:7],
        _clv_str(trade)[:8],
        _proxy_str(trade)[:8],
    ]
    parts = []
    for val, w in zip(vals, _COL_W):
        parts.append(val.ljust(w))
    return "  ".join(parts)


def _honest_footer(data: Dict[str, Any]) -> None:
    note = data.get("honest_note", "")
    if note:
        print()
        print("NOTE:", note)


# ---------------------------------------------------------------------------
# Mode handlers
# ---------------------------------------------------------------------------

def _run_list(args: argparse.Namespace) -> int:
    ledger = Path(args.ledger) if args.ledger else None
    result = browse_pm_trail(
        ledger_path=ledger,
        venue=args.venue or None,
        result=args.result or None,
        tier=args.tier or None,
        offset=args.offset,
        limit=args.limit,
    )
    trades: List[Dict[str, Any]] = result.get("trades", [])
    total = result.get("total_pm", len(trades))
    offset = result.get("offset", 0)
    limit = result.get("limit", len(trades))

    print(f"PM paper trail -- {len(trades)} of {total} trades "
          f"(offset={offset} limit={limit})")
    if args.venue:
        print(f"  filter venue={args.venue}")
    if args.result:
        print(f"  filter result={args.result}")
    if args.tier:
        print(f"  filter tier={args.tier}")
    print()
    print(_hdr())
    print(_sep())
    for trade in trades:
        print(_fmt_row(trade))
    if not trades:
        print("  (no trades match filters)")

    _honest_footer(result)
    return 0


def _run_best(args: argparse.Namespace) -> int:
    ledger = Path(args.ledger) if args.ledger else None
    result = best_pm_trades(ledger_path=ledger, top_n=args.top_n)
    trades: List[Dict[str, Any]] = result.get("trades", [])

    print(f"Best PM trades (top {args.top_n} by tier+model_prob+CLV) -- "
          f"{len(trades)} returned")
    print("  Rank order: tier A > B > C, then model_prob desc, then clv_pct desc")
    print()
    print(_hdr())
    print(_sep())
    for i, trade in enumerate(trades, 1):
        row = _fmt_row(trade)
        print(f"{i:3d}.  {row}")
    if not trades:
        print("  (no PM trades in ledger)")

    _honest_footer(result)
    return 0


def _run_detail(args: argparse.Namespace) -> int:
    if not args.bet_id:
        print("ERROR: --mode detail requires --bet-id <id>", file=sys.stderr)
        return 2
    ledger = Path(args.ledger) if args.ledger else None
    result = trade_detail(args.bet_id, ledger_path=ledger)
    status = result.get("status")
    if status == "not_found":
        print(f"Trade not found: bet_id={args.bet_id!r}")
        _honest_footer(result)
        return 1
    trade = result.get("trade") or {}

    # Emit full JSON (no $ fields by construction in _shape())
    out: Dict[str, Any] = {
        "status": status,
        "trade": trade,
    }
    # Annotate CLV proxy status explicitly in the detail output
    clv_note: str
    if trade.get("clv_pct") is None:
        clv_note = "INSUFFICIENT_DATA -- no closing line available"
    elif trade.get("clv_is_proxy"):
        clv_note = "proxy close (is_proxy=True); treat as estimate, not true CLV"
    else:
        clv_note = "true CLV (devigged closing line captured)"
    out["clv_note"] = clv_note
    out["honest_note"] = result.get("honest_note", "")

    print(json.dumps(out, indent=2, default=str))
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pm_trail_cli",
        description="Browse PM paper-trade trail (Kalshi/Polymarket). UNITS only, no $.",
    )
    p.add_argument(
        "--mode", choices=["list", "best", "detail"], default="list",
        help="list=paginated table  best=ranked top-N  detail=full JSON for one trade",
    )
    # list filters
    p.add_argument("--venue", help="kalshi | polymarket")
    p.add_argument("--result", help="win | loss | push | void | open | settled")
    p.add_argument("--tier", help="A | B | C")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--limit", type=int, default=25)
    # best options
    p.add_argument("--top-n", dest="top_n", type=int, default=20)
    # detail options
    p.add_argument("--bet-id", dest="bet_id", help="bet_id to look up (detail mode)")
    # shared
    p.add_argument("--ledger", help="override ledger path (default: data/frontend/clv_ledger.jsonl)")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.mode == "list":
        return _run_list(args)
    if args.mode == "best":
        return _run_best(args)
    if args.mode == "detail":
        return _run_detail(args)
    print(f"Unknown mode: {args.mode}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
