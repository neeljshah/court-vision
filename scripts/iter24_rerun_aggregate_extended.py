"""iter-24: re-run aggregate_oos_backtest with the EXTENDED OOS pool
(canonical + reisneriv net-new + benashkar 2025-26).

We monkey-patch the production module's CSV_PATH so we do not touch
the iter-9 source script. Report writes to a new file so the canonical
honest_aggregate_oos_backtest.md is untouched.
"""
from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import scripts.aggregate_oos_backtest as agg  # noqa: E402

EXT_CSV = os.path.join(
    PROJECT_DIR, "data", "external", "historical_lines", "extended_oos_canonical.csv"
)
EXT_REPORT = os.path.join(
    PROJECT_DIR, "vault", "Reports", "iter24_extended_aggregate_oos_backtest.md"
)

agg.CSV_PATH = EXT_CSV
agg.REPORT_PATH = EXT_REPORT

if __name__ == "__main__":
    result = agg.run()
    tot = result["totals"]
    print("\n  EXTENDED AGGREGATE OOS (canonical + reisneriv + benashkar):")
    print(f"    n_pred={tot['n_pred']}  n_bets={tot['n_bets']}  "
          f"hit={tot['hit_rate']*100:.2f}%  ROI={tot['roi_pct']:+.2f}%  "
          f"PnL=${tot['pnl_dollars']:+,.0f}")
    agg.save_report(result)
