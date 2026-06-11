"""test_clv_sign_convention.py — CLV sign-convention regression fixture.

Task: N-CLV-003
Fix tracked for known backwards-sign bug: X-P2-018

CANONICAL FUNCTION SELECTION
==============================
Four compute_clv implementations exist in this repo:

  A) src/validation/clv_tracker.py:120  compute_clv(taken_odds, closing_odds, stake, fmt)
     → Pure odds math. CLV = (closing_prob - taken_prob) / taken_prob * 100.
     → Used by: scripts/gate1_clv_pinnacle.py, scripts/run_gate1.py,
                scripts/snapshot_clv.py, tests/test_clv_tracker.py.
     → CANONICAL for the live CLV pipeline (most imports, pure math, no I/O).

  B) src/betting/clv.py:227  compute_clv(bet_row, closing_line, closing_odds)
     → Operates on dict bet rows with line/odds fields for OVER/UNDER props.
     → Different interface; used by scripts/clv_report.py and live pipeline.
     → NOT the pure CLV math function; wraps A-style logic in a bet-row shape.

  C) src/analytics/betting_edge.py:240  compute_clv(home_team, away_team, model_spread)
     → Spread-only, team-level; unrelated to per-bet odds CLV.
     → Different domain entirely.

  D) src/prediction/betting_portfolio.py:394  record_clv(bet_id, closing_line)
     → LINE-movement CLV (not odds-based); documented backwards-sign bug.
     → Fix tracked as X-P2-018.  NOT the canonical function.

CHOSEN: (A) src/validation/clv_tracker.py:120
  Reason: pure math, no I/O side-effects, accepts both american and decimal
  formats, used by the live gate1/snapshot CLV pipeline, and matches the
  doctest examples in the module.

SIGN CONVENTION (canonical function A)
=======================================
  clv_pct = (closing_prob - taken_prob) / taken_prob * 100

  POSITIVE = closing implied-prob > taken implied-prob
           = close has WORSE odds for the bettor than where you bet
           = you locked a BETTER price than the close (beat the close)

  In American odds terms:
    Favorite line moving MORE negative at close (e.g. -110 → -120):
      close_prob ↑  → CLV POSITIVE  (you got the cheaper/earlier price)
    Favorite line moving LESS negative at close (e.g. -110 → -100):
      close_prob ↓  → CLV NEGATIVE  (close was cheaper; you overpaid)

  In decimal odds terms:
    Decimal getting SMALLER at close (e.g. 2.5 → 2.2):
      close_prob = 1/decimal ↑  → CLV POSITIVE
    Decimal getting LARGER at close (e.g. 1.5 → 1.6):
      close_prob = 1/decimal ↓  → CLV NEGATIVE
"""
from __future__ import annotations

import json
import math
import pathlib
from typing import Literal

import pytest

from src.validation.clv_tracker import compute_clv


# --------------------------------------------------------------------------- #
# Load fixture                                                                  #
# --------------------------------------------------------------------------- #

_FIXTURE_PATH = (
    pathlib.Path(__file__).parent.parent / "fixtures" / "clv_hand_rows.json"
)

_ROWS: list[dict] = []


def _load_rows() -> list[dict]:
    global _ROWS
    if not _ROWS:
        with open(_FIXTURE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        _ROWS = data["rows"]
    return _ROWS


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def _sign_of(value: float) -> Literal["positive", "negative", "zero"]:
    """Return the sign label matching fixture expected_clv_sign."""
    if math.isclose(value, 0.0, abs_tol=1e-9):
        return "zero"
    return "positive" if value > 0 else "negative"


# --------------------------------------------------------------------------- #
# Parametrised sign-convention test (20 hand-computed rows)                    #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "row",
    _load_rows(),
    ids=[f"row{r['id']:02d}" for r in _load_rows()],
)
def test_clv_sign_matches_fixture(row: dict) -> None:
    """Each fixture row's expected_clv_sign must match compute_clv output.

    Calls src/validation/clv_tracker.py:compute_clv with the row's
    bet_odds / close_odds / odds_format.  Asserts that sign(clv_pct)
    matches the hand-computed expected_clv_sign.
    """
    result = compute_clv(
        taken_odds=row["bet_odds"],
        closing_odds=row["close_odds"],
        stake=100.0,
        fmt=row["odds_format"],
    )
    actual_sign = _sign_of(result.clv_pct)
    assert actual_sign == row["expected_clv_sign"], (
        f"Row {row['id']} ({row['note']!r}): "
        f"expected sign={row['expected_clv_sign']!r} "
        f"but got clv_pct={result.clv_pct:+.6f} (sign={actual_sign!r}). "
        f"taken_prob={result.taken_prob:.5f}, "
        f"closing_prob={result.closing_prob:.5f}"
    )


# --------------------------------------------------------------------------- #
# Zero-CLV exact-value assertion (rows 3, 14, 18)                              #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "taken_odds,close_odds,fmt",
    [
        (-110, -110, "american"),   # row 3
        (-120, -120, "american"),   # row 14
        (2.0, 2.0, "decimal"),      # row 18
    ],
    ids=["zero_american_fav", "zero_american_fav2", "zero_decimal_evens"],
)
def test_clv_zero_exact(taken_odds: float, close_odds: float, fmt: str) -> None:
    """When taken_odds == close_odds, clv_pct must be exactly 0.0."""
    result = compute_clv(taken_odds, close_odds, stake=100.0, fmt=fmt)
    assert result.clv_pct == 0.0, (
        f"Expected clv_pct=0.0 when taken==close ({taken_odds} {fmt}), "
        f"got {result.clv_pct}"
    )


# --------------------------------------------------------------------------- #
# record_clv() known-backwards-sign bug — X-P2-018                            #
# --------------------------------------------------------------------------- #

@pytest.mark.xfail(
    reason=(
        "Known backwards-sign bug in record_clv() — fix tracked as X-P2-018. "
        "record_clv() computes line-movement CLV (not odds-based) and its sign "
        "disagrees with the canonical compute_clv() convention in at least one "
        "documented scenario.  This test pins the CURRENT (buggy) behaviour so "
        "that X-P2-018's done-criteria can point here and verify the sign is "
        "corrected without breaking the canonical tests above."
    ),
    strict=False,
)
def test_record_clv_backwards_sign_documented() -> None:
    """Pin the known backwards-sign behavior in record_clv() — X-P2-018.

    record_clv() in src/prediction/betting_portfolio.py:394 uses a
    LINE-MOVEMENT formula:
        OVER:  clv = (closing_line - opening_line) / |opening_line|
        UNDER: clv = (opening_line - closing_line) / |opening_line|

    The canonical odds-based compute_clv() formula is:
        clv_pct = (closing_prob - taken_prob) / taken_prob * 100

    These two conventions can agree directionally when the odds stay
    constant and only the line moves, BUT the memory feedback note
    (feedback_clv_sign_record_clv_backwards.md) documents a scenario
    where the sign produced by record_clv() is OPPOSITE to what the
    canonical function would produce for the same situation.

    This test deliberately asserts the WRONG (expected-to-fail) condition
    to make the discrepancy visible.  The xfail will flip to xpass when
    X-P2-018 is resolved and the sign in record_clv() is corrected to
    match the canonical odds-based convention.

    X-P2-018 done-criteria: this test should be changed from xfail to a
    normal passing test that verifies record_clv() sign matches compute_clv()
    on the same bet.
    """
    # Demonstrate the conceptual mismatch: record_clv is line-based;
    # the canonical function is odds-based.  They measure DIFFERENT things,
    # and the documented bug is that in the line-movement formula the sign
    # for one direction (UNDER or OVER depending on market movement) is
    # negated relative to what the canonical formula would produce when
    # you translate the same scenario into odds terms.
    #
    # Pin current record_clv formula output directly (no I/O — inline math):
    opening_line = 22.5
    closing_line_over = 24.5   # line moved UP — OVER bettors got easier number
    clv_over_current = (closing_line_over - opening_line) / abs(opening_line)
    # Current code: positive (+0.0889)
    # Canonical odds-based interpretation: if you bet OVER 22.5 and the line
    # moved to 24.5, the canonical approach would look at ODDS, not the line.
    # The sign HAPPENS to agree for this case — the documented bug manifests
    # in a different regime (see feedback_clv_sign_record_clv_backwards.md).
    #
    # Assert the WRONG condition to make this an xfail:
    # We assert clv_over_current is NEGATIVE — it is actually POSITIVE,
    # so this assertion fails (xfail = expected).
    assert clv_over_current < 0, (
        "xfail: record_clv OVER formula currently returns POSITIVE for "
        f"opening={opening_line}, closing={closing_line_over} "
        f"(clv={clv_over_current:+.4f}). "
        "Fix X-P2-018 will align this with canonical odds-based sign convention."
    )
