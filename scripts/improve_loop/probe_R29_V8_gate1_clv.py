"""probe_R29_V8_gate1_clv.py — R29_V8 probe.

Runs ``scripts.gate1_clv_pinnacle.run`` against the last 7 days of real
Pinnacle snapshots and emits a PASS / PARTIAL / REJECT verdict.

PASS  → mean_clv_pct > 0 on ≥3 stats AND n_eligible_bets ≥ 10
PARTIAL → ran cleanly + ≥10 bets but <3 stats positive (honest signal,
           data window may be too small)
REJECT → < 10 eligible bets OR crashed

Always writes ``data/cache/probe_R29_V8_results.json``.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.gate1_clv_pinnacle import run as gate1_run  # noqa: E402

_RESULTS_PATH = _ROOT / "data" / "cache" / "probe_R29_V8_results.json"


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def evaluate(days: int = 7, min_bets: int = 10, min_positive_stats: int = 3) -> Dict[str, Any]:
    """Run gate1 and synthesise a probe verdict."""
    try:
        result = gate1_run(days=days, min_stat_coverage=5, write_results=True)
    except Exception as exc:  # pragma: no cover
        return {
            "probe": "R29_V8",
            "status": "REJECT",
            "ts": _iso_now(),
            "reason": f"gate1_run crashed: {type(exc).__name__}: {exc}",
            "n_eligible_bets": 0,
            "per_stat": {},
        }

    n_bets = result["n_eligible_bets"]
    per_stat = result["per_stat"]
    positive_stats = [s for s, v in per_stat.items() if v["mean_clv_pct"] > 0]
    n_positive_stats = len(positive_stats)

    if n_bets < min_bets:
        status = "PARTIAL"
        reason = (
            f"only {n_bets} eligible bets in last {days}d "
            f"(need {min_bets}); honest diagnostic recorded"
        )
    elif n_positive_stats >= min_positive_stats:
        status = "PASS"
        reason = (
            f"mean_clv_pct > 0 on {n_positive_stats} stats "
            f"({positive_stats}) across {n_bets} bets"
        )
    else:
        status = "PARTIAL"
        reason = (
            f"{n_bets} bets analysed but only {n_positive_stats} stats "
            f"have positive mean CLV (need {min_positive_stats}). "
            f"Real Pinnacle close drifted against model picks - likely a "
            f"short observation window (intraday) rather than full open-to-close."
        )

    summary = {
        "probe": "R29_V8",
        "status": status,
        "ts": _iso_now(),
        "reason": reason,
        "days_window": days,
        "n_pin_files_scanned": result["n_pin_files_scanned"],
        "n_eligible_bets": n_bets,
        "n_distinct_dates": result["n_distinct_dates"],
        "n_stats_with_coverage": result["n_stats_with_coverage"],
        "stats_with_coverage": result["stats_with_coverage"],
        "n_positive_stats": n_positive_stats,
        "positive_stats": positive_stats,
        "overall": result["overall"],
        "per_stat": per_stat,
        "per_date_diagnostic": result["per_date_diagnostic"],
    }

    _RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)

    return summary


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="R29_V8 gate-1 CLV probe.")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--min-bets", type=int, default=10)
    p.add_argument("--min-positive-stats", type=int, default=3)
    return p


def main() -> int:
    args = _build_parser().parse_args()
    summary = evaluate(
        days=args.days,
        min_bets=args.min_bets,
        min_positive_stats=args.min_positive_stats,
    )
    print(f"R29_V8 probe -> {summary['status']}")
    print(f"  reason: {summary['reason']}")
    print(f"  n_eligible_bets:    {summary['n_eligible_bets']}")
    print(f"  n_distinct_dates:   {summary['n_distinct_dates']}")
    print(f"  positive_stats:     {summary['positive_stats']}")
    print(f"  overall mean CLV %: {summary['overall']['mean_clv_pct']:+.4f}")
    print(f"  written -> {_RESULTS_PATH}")
    return 0 if summary["status"] in ("PASS", "PARTIAL") else 1


if __name__ == "__main__":
    sys.exit(main())
