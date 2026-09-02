"""scripts.platformkit.paper -- honest PAPER bankroll + units P&L equity curve.

This package builds the everyday PAPER track record the user asked for: a starting
bankroll measured in UNITS (never dollars), the cumulative units P&L ("how much I
would have made") and daily P&L curve accumulated from GRADED paper bets, plus a
grading pass that settles the logged model predictions against real ESPN finals.

Binding honesty rails (mirror clv_ledger / grade_paper):
  * UNITS ONLY -- no dollar / pnl / roi / profit / bankroll($) field is ever written.
    BANNED_KEYS are stripped on every write path.
  * Real money stays DEFAULT-DENY; executed=False on every row; edge_claimed=False.
  * Nothing is fabricated: an ungraded / no-final bet stays open; pushes/voids are
    handled explicitly; CLV that is unproven is reported as INSUFFICIENT_DATA.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC/file; ASCII; no secrets.
"""
from __future__ import annotations

__all__ = ["bankroll", "pnl_series", "grade_predictions", "market_resolver",
           "finals_fetch"]
