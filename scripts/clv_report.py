"""clv_report.py - tier2-7 (loop 5).

CLI front-end for src.betting.clv. Reads the pnl_ledger (cycle 8762cd94),
joins with the live prop-line snapshots (cycle 8d40558a), and prints the
CLV summary. Always (re)writes data/pnl_ledger_clv.csv as a side effect.

Usage
-----
    python scripts/clv_report.py
    python scripts/clv_report.py --range 7d
    python scripts/clv_report.py --range 30d --by stat
    python scripts/clv_report.py --range all --by book
    python scripts/clv_report.py --range 30d --by combined

Empty / missing inputs degrade gracefully:
    - missing pnl_ledger.csv  -> 0-row report, exit 0
    - missing data/lines/      -> every bet shows "no closing snapshot"
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.betting.clv import (  # noqa: E402
    DEFAULT_LINES_DIR,
    DEFAULT_OUT_PATH,
    DEFAULT_PNL_PATH,
    aggregate_clv,
    enrich_pnl_with_clv,
)


def _parse_range(rng: str) -> Optional[timedelta]:
    """'7d' -> 7 days; '30d' -> 30 days; 'all' / '' -> None (no filter)."""
    if not rng or rng.lower() == "all":
        return None
    if rng.endswith("d") and rng[:-1].isdigit():
        return timedelta(days=int(rng[:-1]))
    raise SystemExit(f"--range must be Nd or 'all' (got {rng!r})")


def _filter_by_range(rows: List[Dict], window: Optional[timedelta]) -> List[Dict]:
    """Keep only settled rows whose placed_at falls inside the lookback window.

    Open bets (status=='open') are dropped from CLV reporting because they
    have no realised P&L to correlate against - but they're still written
    to the enriched CSV so daemon scripts can re-read mid-game.
    """
    out: List[Dict] = []
    cutoff = datetime.now() - window if window else None
    for r in rows:
        status = (r.get("status", "") or "").lower()
        if status not in ("won", "lost", "push"):
            continue
        if cutoff is not None:
            try:
                t = datetime.fromisoformat(r.get("placed_at", ""))
            except (TypeError, ValueError):
                continue
            if t < cutoff:
                continue
        out.append(r)
    return out


def render_report(rows: List[Dict], by: str, range_label: str) -> str:
    """Render the human-readable text block. Caller prints it."""
    combined = aggregate_clv(rows, by="combined")
    n            = combined["n"]
    n_w          = combined["n_with_close"]
    missing      = combined["missing_close"]
    mean_pct     = combined["mean_clv_percent"] * 100.0
    beat_rate    = combined["beat_close_rate"] * 100.0
    corr         = combined["clv_vs_roi_corr"]
    cov          = (n_w / n * 100.0) if n else 0.0

    lines: List[str] = []
    lines.append(f"CLV Report - last {range_label}")
    lines.append(
        f"n_settled: {n}   n_with_close_line: {n_w} ({cov:.0f}%)   "
        f"missing_close: {missing}"
    )
    lines.append(
        f"mean_clv_percent: {mean_pct:+.1f}%   "
        f"beat_close_rate: {beat_rate:.1f}%"
    )

    if by in ("stat", "book", "side"):
        groups = aggregate_clv(rows, by=by)
        parts = []
        for k, s in groups.items():
            p_pct = s["mean_clv_percent"] * 100.0
            parts.append(f"{k} {p_pct:+.1f}% (n={s['n_with_close']})")
        if parts:
            lines.append(f"By {by}:  " + "   ".join(parts))

    if corr is not None:
        lines.append(
            f"Correlation: clv_percent vs realized_roi: "
            f"{corr:+.2f} (Pearson, {n_w} settled bets)"
        )
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="CLV report over the pnl_ledger.")
    ap.add_argument("--range", default="30d",
                    help="Lookback window: 7d|30d|all (default 30d)")
    ap.add_argument("--by", default="combined",
                    choices=["stat", "book", "side", "combined"],
                    help="Group breakdown column (default combined)")
    ap.add_argument("--pnl", default=DEFAULT_PNL_PATH,
                    help=f"Path to pnl_ledger.csv (default {DEFAULT_PNL_PATH})")
    ap.add_argument("--lines-dir", default=DEFAULT_LINES_DIR,
                    help=f"Lines snapshot dir (default {DEFAULT_LINES_DIR})")
    ap.add_argument("--out", default=DEFAULT_OUT_PATH,
                    help=f"Enriched output CSV (default {DEFAULT_OUT_PATH})")
    args = ap.parse_args(argv)

    window = _parse_range(args.range)
    enriched = enrich_pnl_with_clv(
        pnl_path=args.pnl, lines_dir=args.lines_dir, out_path=args.out,
    )
    if not enriched:
        print(f"CLV Report - last {args.range}")
        print("n_settled: 0   n_with_close_line: 0 (0%)   missing_close: 0")
        print("(no bets in ledger - place some via src.betting.pnl_ledger.place_bet)")
        return 0

    rows = _filter_by_range(enriched, window)
    print(render_report(rows, by=args.by, range_label=args.range))
    return 0


if __name__ == "__main__":
    # CV_CLV_LINE_SIGN_FIX (owner-flipped 2026-06-05): the line-based CLV sign in
    # src.betting.clv.compute_clv was inverted (reported beat_close for BOTH favorable
    # AND unfavorable line moves — GRADING_SETTLE_CLV_AUDIT B-1). The operator-facing
    # report should use the CORRECT sign by default. Set here (CLI entry only, NOT in
    # main()) so unit tests that call main()/compute_clv directly keep the gated
    # default-OFF byte-identical baseline; setdefault preserves the CV_CLV_LINE_SIGN_FIX=0
    # escape hatch. Training-label-safe: clv_label uses the separate price-based
    # clv_tracker path, not this one.
    os.environ.setdefault("CV_CLV_LINE_SIGN_FIX", "1")
    sys.exit(main())
