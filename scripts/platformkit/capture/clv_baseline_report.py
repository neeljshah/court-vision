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

import sys
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# Path wiring — importable as a standalone script from any CWD.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_LEDGER_ROOT = _REPO_ROOT / "data" / "lines" / "forward"

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Add capture dir so sibling bare-name imports work in all load modes.
_CAPTURE_DIR = Path(__file__).resolve().parent
if str(_CAPTURE_DIR) not in sys.path:
    sys.path.insert(0, str(_CAPTURE_DIR))

from clv_baseline_report_io import iter_ledger_rows, safe_price  # noqa: E402
from clv_baseline_report_compute import build_pairs  # noqa: E402
from clv_baseline_report_render import (  # noqa: E402
    render_clv_grading_section,
    render_distribution_table,
)

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

# Re-export original private-name aliases for any caller that imported them.
_iter_ledger_rows = iter_ledger_rows
_safe_price = safe_price
_build_pairs = build_pairs


# ---------------------------------------------------------------------------
# Core report logic
# ---------------------------------------------------------------------------

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
    all_rows: List[dict] = list(iter_ledger_rows(root=root, days=days))
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
    _line(
        f"  kind=move     : "
        f"{len([r for r in forward_rows if r.get('kind') == 'move'])}"
    )
    _line()

    # ── Capture coverage ──────────────────────────────────────────────────────
    pairs = build_pairs(forward_rows)

    events_with_both = {(r.get("sport"), r.get("event_id")) for r, _ in pairs}
    all_events_seen = unique_events_with_open | unique_events_with_close
    total_events = len(all_events_seen)
    covered_events = len(events_with_both)
    pct_events = (covered_events / total_events * 100) if total_events else 0.0

    markets_with_open: set = {
        (r.get("sport"), r.get("event_id"), r.get("market")) for r in opener_rows
    }
    markets_with_both = {
        (r.get("sport"), r.get("event_id"), r.get("market")) for r, _ in pairs
    }
    pct_markets = (
        len(markets_with_both) / len(markets_with_open) * 100
    ) if markets_with_open else 0.0

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
    dist_lines, _ = render_distribution_table(pairs)
    lines.extend(dist_lines)

    # ── CLV vs pregame prediction ─────────────────────────────────────────────
    lines.extend(render_clv_grading_section(pairs))

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
