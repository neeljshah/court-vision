"""settle_bet.py — settle an open bet by id, or auto-settle a whole date.

Manual settle:
    python scripts/settle_bet.py --bet-id abc-123 --actual 31

Auto-settle every open bet placed on a given date by looking up the player's
realised stat from the cached gamelog JSON in data/nba/:
    python scripts/settle_bet.py --auto --date 2026-05-24

Void a bet (returns stake, status=voided):
    python scripts/settle_bet.py --bet-id abc-123 --void
"""
from __future__ import annotations

import argparse
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.betting.pnl_ledger import (  # noqa: E402
    settle_bet, void_bet, auto_settle_date, current_bankroll,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bet-id", default=None)
    ap.add_argument("--actual", type=float, default=None,
                    help="Realised stat value (e.g. 31 for 31 points).")
    ap.add_argument("--void", action="store_true", help="Mark bet voided, refund stake.")
    ap.add_argument("--auto", action="store_true",
                    help="Auto-settle every open bet placed on --date using cached gamelogs.")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD for --auto.")
    args = ap.parse_args()

    if args.auto:
        if not args.date:
            ap.error("--auto requires --date YYYY-MM-DD")
        results = auto_settle_date(args.date)
        if not results:
            print(f"  no open bets placed on {args.date}")
            return 0
        for r in results:
            if "skipped" in r:
                print(f"  {r['bet_id'][:8]}  SKIP   ({r['skipped']})")
            else:
                print(f"  {r['bet_id'][:8]}  {r['status'].upper():5s}  "
                      f"actual={r['actual']:>5.1f}  pnl={r['profit_loss']:+8.2f}  "
                      f"bankroll=${r['bankroll_after']:.2f}")
        return 0

    if not args.bet_id:
        ap.error("--bet-id is required unless --auto is set")

    if args.void:
        out = void_bet(args.bet_id)
        print(f"  {args.bet_id}  VOIDED   pnl=0.00  bankroll=${out['bankroll_after']:.2f}")
        return 0

    if args.actual is None:
        ap.error("--actual is required unless --void or --auto is set")

    out = settle_bet(args.bet_id, args.actual)
    print(f"  {args.bet_id}  {out['status'].upper():5s}  "
          f"actual={args.actual:>5.1f}  pnl={out['profit_loss']:+8.2f}  "
          f"bankroll=${out['bankroll_after']:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
