"""MICRO-FIX LANE kappa -- word-boundary regression tests for the edge/
calibration keyword guards in resolver_registry.py. Naive substring checks
false-fired on innocent words: "ledger" contains "edge" (wrongly refused),
"receipt" contains "ece" (wrongly routed to calibration_number). Guard must
still refuse all GENUINE edge language.

Run: python -m pytest scripts/platformkit/answers/test_edge_calibration_guards.py -q
"""
from __future__ import annotations

import pytest

from scripts.platformkit.answers import resolver_registry as R


# ---------------------------------------------------------------------------
# Previously false-firing innocent words -- must NOT trigger the guard
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("query", [
    "show me the validation ledger",
    "append to the mechanism ledger",
    "what does the knowledge ledger say",
])
def test_ledger_is_not_edge_language(query):
    assert R.is_edge_language(query) is None
    assert R.classify(query) != "edge_language"


@pytest.mark.parametrize("query", [
    "where is the receipt for this",
    "give me the verbatim receipt",
])
def test_receipt_is_not_calibration(query):
    assert R.classify(query) != "calibration_number"


# ---------------------------------------------------------------------------
# Genuine edge language -- must still refuse
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("query", [
    "what edge do we have here",
    "what is our ROI",
    "do we beat the market",
    "do we beat the close",
    "what is the profit",
    "is this positive ev",
    "is this a +EV bet",
    "what is our bankroll",
    "win rate over market",
    "18.38 percent edge",
])
def test_genuine_edge_language_still_refused(query):
    assert R.is_edge_language(query) is not None
    assert R.classify(query) == "edge_language"


# ---------------------------------------------------------------------------
# Genuine calibration language -- must still route (incl. the deliberate
# "calibrat*" stem match for calibration/calibrated/calibrating)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("query", [
    "what is the brier score",
    "what is the ECE here",
    "what is our calibration score",
    "is this calibrated well",
    "how is the model calibrating",
])
def test_genuine_calibration_language_still_routes(query):
    assert R.classify(query) == "calibration_number"
