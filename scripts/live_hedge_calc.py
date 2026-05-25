"""live_hedge_calc.py -- tier2-6 (loop 5). Mid-game hedge CLI.

Quick lock-in calculator for a placed bet whose line has moved live.

    python scripts/live_hedge_calc.py --stake 100 --open-odds -110 --live-odds +130
    python scripts/live_hedge_calc.py --stake 100 --open-odds -110 --live-odds +130 --live-prob 0.42
    python scripts/live_hedge_calc.py --stake 50  --open-odds +150 --live-odds -120 --partial 0.5

The math is in src/betting/live_hedge.py -- this script only formats output.
"""
from __future__ import annotations

import argparse
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.betting.live_hedge import (  # noqa: E402
    equal_profit_hedge,
    optimal_hedge_given_live_prob,
    partial_hedge,
    payout,
    recommend,
)


def _fmt_american(odds: float) -> str:
    """+130, -110, etc. Always with sign so the operator can't misread."""
    o = float(odds)
    return f"{int(o):+d}" if o == int(o) else f"{o:+.2f}"


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Mid-game hedge calculator -- pure math, no books.")
    ap.add_argument("--stake", type=float, required=True,
                    help="Original stake in dollars.")
    ap.add_argument("--open-odds", type=float, required=True,
                    help="American odds when the original bet was placed.")
    ap.add_argument("--live-odds", type=float, required=True,
                    help="American odds available NOW on the opposite side.")
    ap.add_argument("--live-prob", type=float, default=None,
                    help="Operator's live win-prob for the ORIGINAL side "
                         "(0-1). When supplied, prints the EV-optimal hedge "
                         "and a recommendation.")
    ap.add_argument("--partial", type=float, default=None,
                    help="Fraction of equal-profit hedge (0-1). Prints the "
                         "win/lose profit branches for that partial size.")
    return ap


def format_report(stake: float, open_odds: float, live_odds: float,
                  live_prob: float = None, partial: float = None) -> str:
    """Build the multi-line report. Pure str output for testability."""
    lines = []
    open_profit = payout(open_odds, stake)
    lines.append(f"Original bet: ${stake:.2f} at {_fmt_american(open_odds)} "
                 f"-> potential profit ${open_profit:.2f}")
    lines.append(f"Live opposite: {_fmt_american(live_odds)}")

    eq = equal_profit_hedge(stake, open_odds, live_odds)
    lines.append(
        f"Equal-profit hedge: stake ${eq['hedge_stake']:.2f} -> "
        f"guaranteed profit ${eq['guaranteed_profit']:.2f} regardless")

    if partial is not None:
        ph = partial_hedge(stake, open_odds, live_odds, partial)
        lines.append(
            f"Partial hedge ({partial*100:.0f}% of equal-profit): "
            f"stake ${ph['hedge_stake']:.2f}  "
            f"win-branch profit ${ph['win_profit']:.2f}  "
            f"lose-branch profit ${ph['lose_profit']:.2f}")

    if live_prob is not None:
        opt = optimal_hedge_given_live_prob(stake, open_odds, live_odds,
                                            live_prob)
        lines.append(
            f"Optimal hedge (live_prob {live_prob:.2f}): "
            f"stake ${opt['hedge_stake']:.2f} -> "
            f"expected profit ${opt['expected_profit']:.2f}")

    rec = recommend(stake, open_odds, live_odds, live_prob)
    verdict = rec["verdict"]
    # Note when the lock-in is a guaranteed loss so the operator can decide
    # whether to override -- consistent with "no negative-EV hedges by default".
    if eq["guaranteed_profit"] < 0 and verdict == "hold":
        verdict += "  (equal-profit hedge would lock a loss; let it ride)"
    lines.append(f"Recommendation: {verdict}")
    return "\n".join(lines)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    print(format_report(args.stake, args.open_odds, args.live_odds,
                        live_prob=args.live_prob, partial=args.partial))
    return 0


if __name__ == "__main__":
    sys.exit(main())
