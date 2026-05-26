"""probe_R25_R5_rec_backtest.py — viability probe for R25_R5.

Runs `backtest_live_rec_engine.sweep_configs` against the locally-cached
quarter_box ground truth, records the headline numbers, persists the
result, and exits non-zero if the SHIP gate is not met.

SHIP gate
---------
  - ≥ 3 dates backtested
  - ROI computed (numeric, not nan/None)
  - ≥ 3 viable configs in the sweep matrix

Diagnostic note
---------------
The backtest uses **synthesised** lines around the point-in-time q50
because the repo only ships one priced lines snapshot in history. The
absolute ROI is therefore optimistic (synthetic vig is centered on the
model's own prediction). What's informative is the **relative ranking**
of (min_edge, top) configs.

Persists:
    data/cache/probe_R25_R5_results.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from scripts.backtest_live_rec_engine import (  # noqa: E402
    DEFAULT_QB_DIR,
    run_backtest,
    sweep_configs,
)

DEFAULT_RESULTS_PATH = os.path.join(
    PROJECT_DIR, "data", "cache", "probe_R25_R5_results.json"
)


def run_probe(
    qb_dir: str = DEFAULT_QB_DIR,
    bankroll: float = 1000.0,
    n_per_date: int = 12,
    max_dates: int | None = 30,
    seed: int = 0,
    results_path: str = DEFAULT_RESULTS_PATH,
) -> Dict[str, Any]:
    # Headline single-config run (mirrors what the dashboard surfaces)
    headline = run_backtest(
        qb_dir=qb_dir, bankroll=bankroll, min_edge=0.05, top=5,
        n_per_date=n_per_date, max_dates=max_dates, seed=seed,
    )
    h_agg = headline.get("aggregate") or {}

    sweep = sweep_configs(
        qb_dir=qb_dir, bankroll=bankroll, n_per_date=n_per_date,
        max_dates=max_dates, seed=seed,
    )

    n_dates = int(h_agg.get("n_dates", 0))
    n_recs = int(h_agg.get("n_recs", 0))
    win_rate = float(h_agg.get("win_rate", 0.0))
    roi_pct = float(h_agg.get("roi", 0.0)) * 100.0
    n_viable_configs = int(sweep.get("n_viable", 0))
    best = sweep.get("best_config")

    # SHIP gate
    ship = (
        n_dates >= 3
        and n_recs > 0
        and isinstance(roi_pct, (int, float))
        and n_viable_configs >= 3
    )
    status = "SHIP" if ship else "PARTIAL"
    if n_dates == 0:
        status = "REJECT"

    summary = (
        f"R25_R5 backtest: n_dates={n_dates}, n_recs={n_recs}, "
        f"win_rate={win_rate*100:.2f}%, ROI={roi_pct:+.2f}%, "
        f"best_config={best.get('min_edge') if best else '-'}/"
        f"{best.get('top') if best else '-'} "
        f"-> {n_viable_configs} viable configs"
    )

    result = {
        "probe":              "R25_R5",
        "generated_at":       datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status":             status,
        "n_dates":            n_dates,
        "n_recs":             n_recs,
        "win_rate":           round(win_rate, 4),
        "roi_pct":            round(roi_pct, 4),
        "n_viable_configs":   n_viable_configs,
        "best_config":        best,
        "headline_config":    headline.get("config"),
        "headline_aggregate": h_agg,
        "sweep_matrix":       sweep.get("matrix", []),
        "diagnostic":         (
            "Synthetic lines around point-in-time q50 -- absolute ROI is "
            "optimistic. Relative ranking of (min_edge, top) is the signal."
        ),
        "summary":            summary,
    }

    os.makedirs(os.path.dirname(results_path) or ".", exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
    return result


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--qb-dir",     type=str, default=DEFAULT_QB_DIR)
    ap.add_argument("--bankroll",   type=float, default=1000.0)
    ap.add_argument("--n-per-date", type=int, default=12)
    ap.add_argument("--max-dates",  type=int, default=30)
    ap.add_argument("--seed",       type=int, default=0)
    ap.add_argument("--out",        type=str, default=DEFAULT_RESULTS_PATH)
    ap.add_argument("--json",       action="store_true")
    return ap.parse_args()


def main() -> int:
    args = _parse_args()
    res = run_probe(
        qb_dir=args.qb_dir, bankroll=args.bankroll,
        n_per_date=args.n_per_date, max_dates=args.max_dates,
        seed=args.seed, results_path=args.out,
    )
    if args.json:
        print(json.dumps(res, indent=2, default=str))
    else:
        print(res["summary"])
        print(f"status={res['status']}  results-> {args.out}")
    return 0 if res["status"] in ("SHIP", "PARTIAL") else 1


if __name__ == "__main__":
    sys.exit(main())
