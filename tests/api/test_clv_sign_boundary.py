"""test_clv_sign_boundary.py -- Phase-7 honesty contract (TC).

CONTRACT UNDER TEST
-------------------
At the API boundary, CLV must mean BETTER-NUMBER-THAN-CLOSE:

  Positive CLV  <=>  we locked a more favourable number than the close.
    * OVER  bet: closing line HIGHER than our line  -> positive CLV
                 (we got the lower/easier over number).
    * UNDER bet: closing line LOWER than our line    -> positive CLV
                 (we got the higher/easier under number).

KNOWN BUG (do NOT re-endorse)
-----------------------------
Memory feedback_clv_sign_record_clv_backwards: a record_clv path has been
observed BACKWARDS. We therefore test the SIGN CONVENTION on the value the
boundary returns rather than blessing any one implementation. We exercise the
module-level src.prediction.betting_portfolio.record_clv (which execution_router
fronts) and assert the better-number-than-close sign. If the implementation is
backwards, this test FAILS loudly (not xfail) -- a backwards sign is a hard
honesty violation, not a tolerated gated quirk.

PROMOTION GUARD
---------------
test_clv_convention_documented re-checks the docstring still claims the correct
convention, so a future silent re-write that flips BOTH the code and the doc is
still caught by the numeric tests above.
"""
from __future__ import annotations

import json
import os
import tempfile

import pytest

bp = pytest.importorskip("src.prediction.betting_portfolio")


def _seed_bet(direction, line):
    """Write a single open bet to a temp bet log and point the module at it.

    Returns (bet_id, restore_fn). record_clv mutates the log in place.
    """
    bet_id = "clv-sign-test"
    bet = {
        "bet_id": bet_id,
        "player": "Test Player",
        "stat": "pts",
        "direction": direction,
        "line": line,
        "result": None,
    }
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump([bet], f)

    orig_log = getattr(bp, "_BET_LOG", None)
    orig_clv = getattr(bp, "_CLV_LOG", None)
    bp._BET_LOG = path
    bp._CLV_LOG = path + ".clv"

    def restore():
        for p in (path, path + ".clv"):
            try:
                os.remove(p)
            except OSError:
                pass
        if orig_log is not None:
            bp._BET_LOG = orig_log
        if orig_clv is not None:
            bp._CLV_LOG = orig_clv

    return bet_id, path, restore


def _read_clv(path, bet_id):
    with open(path, encoding="utf-8") as f:
        bets = json.load(f)
    for b in bets:
        if b["bet_id"] == bet_id:
            return b.get("clv")
    return None


# ---------------------------------------------------------------------------
# OVER: closing line ABOVE our line -> we got the easier number -> CLV > 0.
# ---------------------------------------------------------------------------

def test_over_clv_positive_when_close_higher():
    bet_id, path, restore = _seed_bet("over", 22.5)
    try:
        bp.record_clv(bet_id, closing_line=24.5)
        clv = _read_clv(path, bet_id)
        assert clv is not None, "record_clv did not write a clv value"
        assert clv > 0, (
            f"OVER 22.5 closing 24.5 must be POSITIVE CLV "
            f"(better-number-than-close); got {clv}. Sign is BACKWARDS."
        )
    finally:
        restore()


def test_over_clv_negative_when_close_lower():
    bet_id, path, restore = _seed_bet("over", 22.5)
    try:
        bp.record_clv(bet_id, closing_line=20.5)
        clv = _read_clv(path, bet_id)
        assert clv is not None
        assert clv < 0, (
            f"OVER 22.5 closing 20.5 must be NEGATIVE CLV (worse number); "
            f"got {clv}. Sign is BACKWARDS."
        )
    finally:
        restore()


# ---------------------------------------------------------------------------
# UNDER: closing line BELOW our line -> we got the easier number -> CLV > 0.
# ---------------------------------------------------------------------------

def test_under_clv_positive_when_close_lower():
    bet_id, path, restore = _seed_bet("under", 22.5)
    try:
        bp.record_clv(bet_id, closing_line=20.5)
        clv = _read_clv(path, bet_id)
        assert clv is not None
        assert clv > 0, (
            f"UNDER 22.5 closing 20.5 must be POSITIVE CLV "
            f"(better-number-than-close); got {clv}. Sign is BACKWARDS."
        )
    finally:
        restore()


def test_under_clv_negative_when_close_higher():
    bet_id, path, restore = _seed_bet("under", 22.5)
    try:
        bp.record_clv(bet_id, closing_line=24.5)
        clv = _read_clv(path, bet_id)
        assert clv is not None
        assert clv < 0, (
            f"UNDER 22.5 closing 24.5 must be NEGATIVE CLV (worse number); "
            f"got {clv}. Sign is BACKWARDS."
        )
    finally:
        restore()


# ---------------------------------------------------------------------------
# PROMOTION / DOC GUARD -- catches a silent re-write that flips code + doc.
# ---------------------------------------------------------------------------

def test_clv_convention_documented():
    doc = (bp.record_clv.__doc__ or "").lower()
    assert "better" in doc and "close" in doc, (
        "record_clv docstring no longer states the better-number-than-close "
        "convention -- re-verify the sign by hand before trusting it."
    )
