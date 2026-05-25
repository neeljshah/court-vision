"""pnl_report.py — print realised P&L summary from the ledger.

Usage:
    python scripts/pnl_report.py                # lifetime
    python scripts/pnl_report.py --range 30d    # last 30 days
    python scripts/pnl_report.py --range 7d --by stat
    python scripts/pnl_report.py --by book
    python scripts/pnl_report.py --open         # also list open bets
"""
from __future__ import annotations

import argparse
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.betting.pnl_ledger import (  # noqa: E402
    pnl_summary, pnl_group_by, open_bets,
)


def _print_summary(s: dict) -> None:
    print("  ------------------------------------------------")
    print(f"  n_bets              {s['n_bets']:>10d}")
    print(f"  n_settled           {s['n_settled']:>10d}   (won {s['won']} / lost {s['lost']} / push {s['push']})")
    print(f"  n_open              {s['n_open']:>10d}")
    print(f"  win_rate            {s['win_rate']:>10.4f}")
    print(f"  push_rate           {s['push_rate']:>10.4f}")
    print(f"  total_staked        ${s['total_staked']:>9.2f}")
    print(f"  total_profit        ${s['total_profit']:>+9.2f}")
    print(f"  ROI                 {s['roi']:>+10.4f}")
    print(f"  avg_stake           ${s['avg_stake']:>9.2f}")
    print(f"  sharpe (per-bet)    {s['sharpe']:>10.4f}")
    print(f"  current_bankroll    ${s['current_bankroll']:>9.2f}")
    print("  ------------------------------------------------")


def _print_group(field: str, rows: list) -> None:
    if not rows:
        print(f"  no settled bets to group by {field}")
        return
    print(f"\n  by {field}:")
    print(f"    {field:<14s} {'n':>4s} {'W-L-P':>10s} {'win%':>7s} "
          f"{'staked':>10s} {'profit':>10s} {'roi':>8s}")
    print(f"    {'-'*14} {'-'*4} {'-'*10} {'-'*7} {'-'*10} {'-'*10} {'-'*8}")
    for r in rows:
        wlp = f"{r['won']}-{r['lost']}-{r['push']}"
        print(f"    {str(r[field])[:14]:<14s} {r['n']:>4d} {wlp:>10s} "
              f"{r['win_rate']*100:>6.1f}% ${r['staked']:>8.2f} "
              f"${r['profit']:>+8.2f} {r['roi']:>+7.2%}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--range", dest="dr", default=None,
                    help="7d | 30d | 90d | YYYY-MM-DD:YYYY-MM-DD")
    ap.add_argument("--by", choices=["stat", "book", "side", "player"], default=None)
    ap.add_argument("--filter-stat", default=None)
    ap.add_argument("--filter-book", default=None)
    ap.add_argument("--filter-side", default=None, choices=["OVER", "UNDER"])
    ap.add_argument("--open", action="store_true", help="Also list open bets.")
    args = ap.parse_args()

    filt = {}
    if args.filter_stat: filt["stat"] = args.filter_stat
    if args.filter_book: filt["book"] = args.filter_book
    if args.filter_side: filt["side"] = args.filter_side

    label = args.dr or "lifetime"
    if filt:
        label += " " + ",".join(f"{k}={v}" for k, v in filt.items())
    print(f"\n  P&L summary [{label}]")
    _print_summary(pnl_summary(date_range=args.dr, filter_by=filt or None))

    if args.by:
        _print_group(args.by, pnl_group_by(args.by, date_range=args.dr))

    if args.open:
        ob = open_bets()
        print(f"\n  open bets ({len(ob)}):")
        if ob:
            for b in ob:
                print(f"    {b['bet_id'][:8]}  {b['player']:<22s} "
                      f"{b['stat'].upper():4s} {b['side']:5s} {b['line']:>5s} "
                      f"@ {int(b['american_odds']):+d}  stake ${float(b['stake']):.2f}  "
                      f"({b['book']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
