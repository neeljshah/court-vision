"""clv_baseline_report_render.py — Rendering helpers for clv_baseline_report (N-CLV-006).

Builds the per-market distribution table and the CLV-vs-pregame grading section
of the report.  Split from clv_baseline_report.py to stay within the 300
LOC/file rule.  Logic is identical — this is a verbatim move, not a rewrite.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Path wiring — ensure repo root is on sys.path for src.* imports.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_CAPTURE_DIR = Path(__file__).resolve().parent
if str(_CAPTURE_DIR) not in sys.path:
    sys.path.insert(0, str(_CAPTURE_DIR))

from src.validation.clv_tracker import compute_clv  # noqa: E402
from clv_baseline_report_io import safe_price  # noqa: E402
from clv_baseline_report_compute import mean, percentile, stdev  # noqa: E402


def render_distribution_table(
    pairs: List[Tuple[dict, dict]],
) -> Tuple[List[str], int]:
    """Build per-market opener->close movement distribution lines.

    Args:
        pairs: List of (open_row, close_row) 2-tuples.

    Returns:
        Tuple of (rendered_lines, skipped_non_numeric_count).
    """
    movement_deltas: Dict[str, List[float]] = defaultdict(list)
    skipped_non_numeric = 0

    for open_row, close_row in pairs:
        mkt = str(open_row.get("market", "unknown"))
        open_price = safe_price(open_row.get("price"))
        close_price = safe_price(close_row.get("price"))
        if open_price is None or close_price is None:
            skipped_non_numeric += 1
            continue
        movement_deltas[mkt].append(close_price - open_price)

    out: List[str] = []
    out.append(
        "PER-MARKET OPENER->CLOSE MOVEMENT DISTRIBUTIONS (price delta in odds points)"
    )
    out.append("-" * 72)
    out.append(
        f"{'Market':<30} {'N':>5} {'Mean':>8} {'Std':>8} "
        f"{'P10':>8} {'P50':>8} {'P90':>8}"
    )
    out.append("-" * 72)

    for mkt in sorted(movement_deltas.keys()):
        deltas = sorted(movement_deltas[mkt])
        n = len(deltas)
        mu = mean(deltas)
        sd = stdev(deltas)
        p10 = percentile(deltas, 10)
        p50 = percentile(deltas, 50)
        p90 = percentile(deltas, 90)
        out.append(
            f"{mkt:<30} {n:>5} {mu:>+8.2f} {sd:>8.2f} "
            f"{p10:>+8.2f} {p50:>+8.2f} {p90:>+8.2f}"
        )

    if skipped_non_numeric:
        out.append(f"  [{skipped_non_numeric} pairs skipped - non-numeric price]")
    out.append("")
    return out, skipped_non_numeric


def render_clv_grading_section(
    pairs: List[Tuple[dict, dict]],
) -> List[str]:
    """Build the CLV-vs-pregame grading section lines.

    Args:
        pairs: All completed open->close pairs (pre-filtered for forward rows).

    Returns:
        Lines for the grading section (including header, body, and trailing blank).
    """
    graded_pairs = [
        (o, c) for o, c in pairs
        if safe_price(o.get("prediction")) is not None
        and safe_price(o.get("price")) is not None
        and safe_price(c.get("price")) is not None
    ]

    out: List[str] = []
    out.append("CLV VS PRE-GAME NUMBER GRADING")
    out.append("-" * 40)

    if not graded_pairs:
        out.append(
            "No graded pairs found.  A pair is graded when the opener row "
            "carries a numeric 'prediction' field (our pre-game price in "
            "American odds).  Grading will populate automatically once "
            "capture_nba.py is run with prediction enrichment."
        )
        out.append("")
        return out

    out.append(
        f"{len(graded_pairs)} graded pair(s) found (opener has 'prediction' field)."
    )
    out.append("")
    out.append(
        "CLV % = (close_prob - taken_prob) / taken_prob * 100, where\n"
        "  taken_prob is implied prob of our pre-game prediction (not the opener book price).\n"
        "  close_prob is implied prob of the closing book price.\n"
        "Positive CLV: the line moved in our favour vs the close.\n"
        "Negative CLV: the line moved against us vs the close.\n"
        "This is descriptive line movement - see disclaimer above."
    )
    out.append("")

    clv_by_market: Dict[str, List[float]] = defaultdict(list)
    skip_clv = 0

    for open_row, close_row in graded_pairs:
        mkt = str(open_row.get("market", "unknown"))
        pred_odds = safe_price(open_row.get("prediction"))
        close_price_val = safe_price(close_row.get("price"))
        if pred_odds is None or close_price_val is None:
            skip_clv += 1
            continue
        try:
            result = compute_clv(
                taken_odds=pred_odds,
                closing_odds=close_price_val,
                stake=100.0,
                fmt="american",
            )
            clv_by_market[mkt].append(result.clv_pct)
        except (ValueError, ZeroDivisionError):
            skip_clv += 1
            continue

    out.append(
        f"{'Market':<30} {'N':>5} {'Mean CLV%':>10} {'Std CLV%':>10} "
        f"{'P50 CLV%':>10}"
    )
    out.append("-" * 70)
    for mkt in sorted(clv_by_market.keys()):
        vals = sorted(clv_by_market[mkt])
        out.append(
            f"{mkt:<30} {len(vals):>5} {mean(vals):>+10.3f} "
            f"{stdev(vals):>10.3f} {percentile(vals, 50):>+10.3f}"
        )
    if skip_clv:
        out.append(f"  [{skip_clv} graded pairs skipped - non-numeric odds]")
    out.append("")
    return out
