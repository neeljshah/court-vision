"""scripts/ab_report.py — tier4-14 (loop 5).

A/B strategy report: per-strategy P&L table + pairwise Welch t-test.

Examples
--------
    python scripts/ab_report.py --range 30d
    python scripts/ab_report.py --range 30d --strategies pregame_only,endQ3_recommend
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.betting import ab_strategy as AB


def _table(summaries):
    cols = ["strategy", "n_bets", "n_settled", "won", "lost", "win_rate",
            "total_profit", "roi", "available"]
    widths = [22, 6, 8, 4, 4, 9, 12, 9, 10]
    print(" ".join(c.upper().rjust(w) for c, w in zip(cols, widths)))
    for s in summaries:
        vals = [
            s.get("strategy", ""),
            s.get("n_bets", 0),
            s.get("n_settled", 0),
            s.get("won", 0),
            s.get("lost", 0),
            f"{s.get('win_rate', 0):.4f}",
            f"{s.get('total_profit', 0):.2f}",
            f"{s.get('roi', 0):.4f}",
            f"{s.get('available', 0):.2f}",
        ]
        print(" ".join(str(v).rjust(w) for v, w in zip(vals, widths)))


def main() -> int:
    p = argparse.ArgumentParser(description="A/B strategy report")
    p.add_argument("--range", default=None, dest="range_",
                   help="e.g. 7d, 30d, or YYYY-MM-DD:YYYY-MM-DD")
    p.add_argument("--strategies", default=None,
                   help="comma-separated subset (default: all registered)")
    p.add_argument("--json", action="store_true",
                   help="machine-readable JSON output")
    args = p.parse_args()

    if args.strategies:
        names = [s.strip() for s in args.strategies.split(",") if s.strip()]
    else:
        names = [r["strategy"] for r in AB.list_strategies()]
    if not names:
        print("(no strategies registered — use scripts/ab_track.py --register)")
        return 1

    summaries = []
    for n in names:
        try:
            summaries.append(AB.strategy_summary(n, date_range=args.range_))
        except ValueError as e:
            print(f"# skip {n}: {e}", file=sys.stderr)

    if args.json:
        out = {"summaries": summaries, "comparisons": []}
    else:
        print(f"\n=== A/B strategy report (range={args.range_ or 'all'}) ===\n")
        _table(summaries)

    # Pairwise comparisons.
    pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            try:
                cmp = AB.ab_compare(names[i], names[j], date_range=args.range_)
            except ValueError as e:
                print(f"# cmp skip {names[i]}/{names[j]}: {e}", file=sys.stderr)
                continue
            pairs.append(cmp)

    if args.json:
        out["comparisons"] = pairs
        print(json.dumps(out, indent=2, default=str))
        return 0

    if pairs:
        print("\n--- pairwise (Welch's t on per-bet returns) ---")
        for c in pairs:
            print(
                f"  {c['strategy_a']} vs {c['strategy_b']}: "
                f"n=({c['n_a']},{c['n_b']}) "
                f"mean_ret=({c['mean_return_a']:+.4f},{c['mean_return_b']:+.4f}) "
                f"t={c['welch_t']} p={c['p_value']} "
                f"winner={c['winner']} confidence={c['confidence']}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
