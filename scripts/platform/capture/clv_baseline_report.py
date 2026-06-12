"""clv_baseline_report.py — 60-day CLV baseline report generator (N-CLV-006).

Produces a descriptive, plain-text report covering:

  1. Per-market opener -> close price movement distributions.
  2. Capture coverage: what fraction of events/markets have both an opener
     and a closer in the ledger.
  3. CLV vs our pre-game number gradings, where a ``prediction`` field exists
     on the opener row.

Output is printed to stdout.  The file NEVER writes to disk and NEVER claims
a betting edge exists.

MANDATORY DISCLAIMER
--------------------
Open-to-close price movement (and any CLV calculated from it) is
**market-follow by construction**: a positive CLV means the opener moved in
your favour, not that any forecast skill was demonstrated.  Open-vs-close
P&L is a measure of line movement, not predictive ability.  No betting edge
is asserted or implied by this report.

Design decisions
----------------
* Reads the ledger directly (inlines the JSONL scan) rather than importing
  ledger_reader.py, which may not be committed (per task spec).
* Uses only stdlib + math; no pandas, no torch.
* compute_clv imported from src/validation/clv_tracker.py (canonical,
  N-CLV-003 pinned).
* Runs cleanly on an empty ledger ("no forward rows yet") without error.
* ``fmt="american"`` is assumed; non-numeric prices are skipped with a warn.
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Path wiring — importable as a standalone script from any CWD.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_LEDGER_ROOT = _REPO_ROOT / "data" / "lines" / "forward"

# Add repo root to sys.path so we can import src.validation.clv_tracker.
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.validation.clv_tracker import compute_clv  # noqa: E402

# ---------------------------------------------------------------------------
# Mandatory disclaimer — pinned as a module-level constant so tests can check
# its presence without executing the full report.
# ---------------------------------------------------------------------------

MANDATORY_DISCLAIMER: str = (
    "DISCLAIMER: Open-to-close price movement (and any CLV calculated from it) "
    "is market-follow by construction: a positive CLV means the opener moved in "
    "your favour, not that any forecast skill was demonstrated. "
    "Open-vs-close P&L is a measure of line movement, not predictive ability. "
    "No betting edge is asserted or implied by this report."
)

# ---------------------------------------------------------------------------
# Internal helpers — inline JSONL reading (no ledger_reader import per spec).
# ---------------------------------------------------------------------------

PairKey = Tuple[str, str, str, str, str]  # (sport, event_id, market, book, side)


def _iter_ledger_rows(
    root: Optional[Path] = None,
    days: int = 60,
) -> Iterator[dict]:
    """Yield all ledger rows from the last *days* JSONL files, newest-first sort.

    Walks every sport subdirectory under *root* and reads every ``.jsonl``
    file.  The *days* parameter is a soft limit: it restricts how many date
    files are read per sport directory (sorted descending so the most recent
    files are read first).

    Args:
        root: Ledger root directory.  Defaults to ``data/lines/forward``.
        days: Maximum number of daily files to read per sport directory.

    Yields:
        Parsed record dicts in file-read order.
    """
    base = Path(root) if root is not None else _DEFAULT_LEDGER_ROOT
    if not base.exists():
        return

    for sport_dir in sorted(base.iterdir()):
        if not sport_dir.is_dir():
            continue
        jsonl_files = sorted(sport_dir.glob("*.jsonl"), reverse=True)[:days]
        # Reverse again so output is chronological within the window.
        for jf in reversed(jsonl_files):
            try:
                with open(jf, "r", encoding="utf-8") as fh:
                    for raw_line in fh:
                        stripped = raw_line.strip()
                        if stripped:
                            try:
                                yield json.loads(stripped)
                            except json.JSONDecodeError:
                                pass
            except OSError:
                pass


def _safe_price(value: object) -> Optional[float]:
    """Convert a ledger price to float, returning None on failure.

    Args:
        value: Raw price value from ledger (may be str or numeric).

    Returns:
        Float price, or None if not convertible.
    """
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Core report logic
# ---------------------------------------------------------------------------

def _build_pairs(rows: List[dict]) -> List[Tuple[dict, dict]]:
    """Match opener rows to closer rows by (sport, event_id, market, book, side).

    Args:
        rows: All ledger rows loaded for the window.

    Returns:
        List of (open_row, close_row) 2-tuples, one per complete pair.
    """
    opens: Dict[PairKey, dict] = {}
    closes: Dict[PairKey, dict] = {}

    for row in rows:
        k = row.get("kind")
        if k not in ("open", "close"):
            continue
        pk: PairKey = (
            str(row.get("sport", "")),
            str(row.get("event_id", "")),
            str(row.get("market", "")),
            str(row.get("book", "")),
            str(row.get("side", "")),
        )
        if k == "open" and pk not in opens:
            opens[pk] = row
        elif k == "close" and pk not in closes:
            closes[pk] = row

    return [(opens[pk], closes[pk]) for pk in opens if pk in closes]


def _percentile(sorted_vals: List[float], p: float) -> float:
    """Linear-interpolation percentile on a pre-sorted list.

    Args:
        sorted_vals: Ascending-sorted list of floats.
        p: Percentile in [0, 100].

    Returns:
        The p-th percentile value.
    """
    n = len(sorted_vals)
    if n == 0:
        return float("nan")
    if n == 1:
        return sorted_vals[0]
    idx = (p / 100.0) * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo])


def _mean(vals: List[float]) -> float:
    """Return mean of *vals*, or NaN if empty."""
    return sum(vals) / len(vals) if vals else float("nan")


def _stdev(vals: List[float]) -> float:
    """Return population std-dev of *vals*, or NaN if < 2 items."""
    if len(vals) < 2:
        return float("nan")
    mu = _mean(vals)
    return math.sqrt(sum((v - mu) ** 2 for v in vals) / len(vals))


def generate_report(
    root: Optional[Path] = None,
    days: int = 60,
) -> str:
    """Generate the 60-day CLV baseline report as a string.

    The report:

    * Always includes the mandatory market-follow disclaimer.
    * Reports honestly when the ledger is empty or contains no forward rows.
    * Shows per-market distributions of opener -> closer price movement.
    * Shows capture coverage (events and markets with paired open+close).
    * Shows CLV-vs-pregame grading where a ``prediction`` field is present.
    * Contains zero instances of "edge" used as a claim.

    Args:
        root: Override for the ledger root directory.  Defaults to
            ``data/lines/forward`` under repo root.
        days: Number of daily files to read per sport directory (default 60).

    Returns:
        The full report as a single string (print-ready).
    """
    lines: List[str] = []

    def _line(text: str = "") -> None:
        lines.append(text)

    # ── Header ────────────────────────────────────────────────────────────────

    _line("=" * 72)
    _line("NBA AI SYSTEM - CLV BASELINE REPORT (N-CLV-006)")
    _line("Descriptive analysis of opener->close movement over the ledger window")
    _line("=" * 72)
    _line()
    _line(MANDATORY_DISCLAIMER)
    _line()
    _line("-" * 72)

    # ── Load rows ─────────────────────────────────────────────────────────────

    all_rows: List[dict] = list(_iter_ledger_rows(root=root, days=days))

    # Filter to forward rows only (exclude ts_quality=reconstructed).
    forward_rows = [r for r in all_rows if r.get("ts_quality") != "reconstructed"]

    if not forward_rows:
        _line()
        _line("STATUS: no forward rows yet.")
        _line(
            "The ledger at data/lines/forward/ is empty or contains only "
            "reconstructed/archive rows.  Run capture_nba.py once live data "
            "is available to begin populating the ledger."
        )
        _line()
        return "\n".join(lines)

    # ── Summary counts ────────────────────────────────────────────────────────

    opener_rows = [r for r in forward_rows if r.get("kind") == "open"]
    closer_rows = [r for r in forward_rows if r.get("kind") == "close"]

    unique_events_with_open: set = {
        (r.get("sport"), r.get("event_id")) for r in opener_rows
    }
    unique_events_with_close: set = {
        (r.get("sport"), r.get("event_id")) for r in closer_rows
    }

    _line()
    _line(f"Window          : last {days} daily files per sport")
    _line(f"Total rows      : {len(forward_rows)}")
    _line(f"  kind=open     : {len(opener_rows)}")
    _line(f"  kind=close    : {len(closer_rows)}")
    _line(f"  kind=move     : {len([r for r in forward_rows if r.get('kind') == 'move'])}")
    _line()

    # ── Capture coverage ──────────────────────────────────────────────────────

    pairs = _build_pairs(forward_rows)

    events_with_both = {
        (r.get("sport"), r.get("event_id"))
        for r, _ in pairs
    }
    all_events_seen = unique_events_with_open | unique_events_with_close
    total_events = len(all_events_seen)
    covered_events = len(events_with_both)
    pct_events = (covered_events / total_events * 100) if total_events else 0.0

    markets_with_open: set = {
        (r.get("sport"), r.get("event_id"), r.get("market")) for r in opener_rows
    }
    markets_with_both = {
        (r.get("sport"), r.get("event_id"), r.get("market"))
        for r, _ in pairs
    }
    pct_markets = (len(markets_with_both) / len(markets_with_open) * 100) if markets_with_open else 0.0

    _line("CAPTURE COVERAGE")
    _line("-" * 40)
    _line(f"Events seen (any kind)          : {total_events}")
    _line(f"Events with open+close pair     : {covered_events}  ({pct_events:.1f}%)")
    _line(f"Market*event combos with opener : {len(markets_with_open)}")
    _line(f"Market*event combos with pair   : {len(markets_with_both)}  ({pct_markets:.1f}%)")
    _line(f"Completed open->close pairs     : {len(pairs)}")
    _line()

    if not pairs:
        _line("NOTE: no open->close pairs found yet.  Distributions will be")
        _line("populated once at least one event has both an opener and a closer")
        _line("in the ledger.")
        _line()
        return "\n".join(lines)

    # ── Per-market movement distributions ─────────────────────────────────────

    # movement_deltas[market] = list of (close_price - open_price)
    movement_deltas: Dict[str, List[float]] = defaultdict(list)
    skipped_non_numeric = 0

    for open_row, close_row in pairs:
        mkt = str(open_row.get("market", "unknown"))
        open_price = _safe_price(open_row.get("price"))
        close_price = _safe_price(close_row.get("price"))
        if open_price is None or close_price is None:
            skipped_non_numeric += 1
            continue
        movement_deltas[mkt].append(close_price - open_price)

    _line("PER-MARKET OPENER->CLOSE MOVEMENT DISTRIBUTIONS (price delta in odds points)")
    _line("-" * 72)
    _line(
        f"{'Market':<30} {'N':>5} {'Mean':>8} {'Std':>8} "
        f"{'P10':>8} {'P50':>8} {'P90':>8}"
    )
    _line("-" * 72)

    for mkt in sorted(movement_deltas.keys()):
        deltas = sorted(movement_deltas[mkt])
        n = len(deltas)
        mu = _mean(deltas)
        sd = _stdev(deltas)
        p10 = _percentile(deltas, 10)
        p50 = _percentile(deltas, 50)
        p90 = _percentile(deltas, 90)
        _line(
            f"{mkt:<30} {n:>5} {mu:>+8.2f} {sd:>8.2f} "
            f"{p10:>+8.2f} {p50:>+8.2f} {p90:>+8.2f}"
        )

    if skipped_non_numeric:
        _line(f"  [{skipped_non_numeric} pairs skipped - non-numeric price]")
    _line()

    # ── CLV vs pregame prediction ─────────────────────────────────────────────

    # A pair is "graded" if the opener row carries a numeric ``prediction``
    # field (our pre-game number in American odds format).
    graded_pairs = [
        (o, c) for o, c in pairs
        if _safe_price(o.get("prediction")) is not None
        and _safe_price(o.get("price")) is not None
        and _safe_price(c.get("price")) is not None
    ]

    _line("CLV VS PRE-GAME NUMBER GRADING")
    _line("-" * 40)

    if not graded_pairs:
        _line(
            "No graded pairs found.  A pair is graded when the opener row "
            "carries a numeric 'prediction' field (our pre-game price in "
            "American odds).  Grading will populate automatically once "
            "capture_nba.py is run with prediction enrichment."
        )
    else:
        _line(
            f"{len(graded_pairs)} graded pair(s) found (opener has 'prediction' field)."
        )
        _line()
        _line(
            "CLV % = (close_prob - taken_prob) / taken_prob * 100, where\n"
            "  taken_prob is implied prob of our pre-game prediction (not the opener book price).\n"
            "  close_prob is implied prob of the closing book price.\n"
            "Positive CLV: the line moved in our favour vs the close.\n"
            "Negative CLV: the line moved against us vs the close.\n"
            "This is descriptive line movement - see disclaimer above."
        )
        _line()

        clv_by_market: Dict[str, List[float]] = defaultdict(list)
        skip_clv = 0

        for open_row, close_row in graded_pairs:
            mkt = str(open_row.get("market", "unknown"))
            pred_odds = _safe_price(open_row.get("prediction"))
            close_price = _safe_price(close_row.get("price"))
            if pred_odds is None or close_price is None:
                skip_clv += 1
                continue
            try:
                result = compute_clv(
                    taken_odds=pred_odds,
                    closing_odds=close_price,
                    stake=100.0,
                    fmt="american",
                )
                clv_by_market[mkt].append(result.clv_pct)
            except (ValueError, ZeroDivisionError):
                skip_clv += 1
                continue

        _line(
            f"{'Market':<30} {'N':>5} {'Mean CLV%':>10} {'Std CLV%':>10} "
            f"{'P50 CLV%':>10}"
        )
        _line("-" * 70)
        for mkt in sorted(clv_by_market.keys()):
            vals = sorted(clv_by_market[mkt])
            _line(
                f"{mkt:<30} {len(vals):>5} {_mean(vals):>+10.3f} "
                f"{_stdev(vals):>10.3f} {_percentile(vals, 50):>+10.3f}"
            )
        if skip_clv:
            _line(f"  [{skip_clv} graded pairs skipped - non-numeric odds]")

    _line()
    _line("-" * 72)
    _line(MANDATORY_DISCLAIMER)
    _line("=" * 72)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Print the CLV baseline report to stdout."""
    print(generate_report())


if __name__ == "__main__":
    main()
