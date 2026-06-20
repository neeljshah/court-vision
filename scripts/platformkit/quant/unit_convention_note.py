"""scripts.platformkit.quant.unit_convention_note -- shared honest clarifier for unit conventions.

PURPOSE:
  Two stake-unit conventions coexist in this system and must NEVER be silently
  conflated:

  1. Kelly-style stake_units -- the quant/risk and pm_trail surfaces expose a
     field named ``stake_units`` that is computed as flat_unit + quarter_kelly_units.
     This is a FRACTIONAL Kelly position size (e.g. 0.25x bankroll) expressed in
     UNITS, not dollars.  A bet may carry stake_units up to ~373 units when the
     Kelly formula sizes aggressively; the raw number reflects sizing math, NOT the
     display unit on the board.

  2. Flat-1.0 display unit -- the bestbets board labels every bet as exactly
     1.0 unit (one flat unit per bet) for display/comparison purposes.  This is the
     number shown next to the ``honest_note`` on the board.  It is NOT the same as
     the Kelly-sized stake_units in the quant ledger.

INVARIANTS (honesty rails):
  * UNITS only -- no $/dollar/roi/pnl/profit/bankroll/stake_dollars field.
  * No retracted number (no +18.38%, 0.119, +54%, 78.11, 8.94, 54.57).
  * No fabricated edge or P&L claim.
  * Deterministic -- same inputs always produce the same output.
  * Never raises.
  * Calibration, not edge.

Build invariants: additive; <=300 LOC; ASCII only.
"""
from __future__ import annotations

from typing import Any, Dict

__all__ = [
    "UNIT_CONVENTION_NOTE",
    "unit_convention_note",
    "attach_note",
]

# ---------------------------------------------------------------------------
# Canonical note text
# ---------------------------------------------------------------------------

UNIT_CONVENTION_NOTE: str = (
    "UNIT CONVENTION: Two sizing conventions coexist -- "
    "(1) Kelly-style stake_units: fractional Kelly position size in UNITS "
    "(flat_unit + quarter_kelly_units); may be large (e.g. up to ~373 units) "
    "when Kelly math sizes aggressively; reflects calibrated model confidence, "
    "NOT the flat-1.0 display unit on the board; "
    "(2) Flat-1.0 display unit: the bestbets board honest_note shows 1.0 unit "
    "per bet for uniform comparison, irrespective of Kelly sizing. "
    "UNITS only -- no monetary value anywhere. Calibration, not edge."
)


def unit_convention_note(*, surface: str = "quant") -> Dict[str, Any]:
    """Return the shared honest unit-convention clarifier.

    Parameters
    ----------
    surface : str
        Informational label for the caller surface (e.g. 'quant', 'pm_trail',
        'risk', 'bestbets').  Does not change the note text; carried for
        provenance only.

    Returns
    -------
    dict with keys:
      note          -- the canonical human-readable clarifier string.
      kelly_units   -- description of the Kelly-style stake_units convention.
      flat_unit     -- description of the flat-1.0 display unit convention.
      surface       -- the caller surface label (provenance only).
      units         -- always "units" (never dollars).
      edge_claimed  -- always False (calibration, not edge).

    Never raises.  Deterministic.
    """
    return {
        "note": UNIT_CONVENTION_NOTE,
        "kelly_units": (
            "stake_units = flat_unit + quarter_kelly_units; "
            "fractional Kelly position size in UNITS; "
            "reflects calibrated model confidence; NOT the flat-1.0 board display"
        ),
        "flat_unit": (
            "bestbets board honest_note: 1.0 unit per bet (flat) for display; "
            "irrespective of Kelly sizing; uniform comparison baseline"
        ),
        "surface": str(surface),
        "units": "units",
        "edge_claimed": False,
    }


def attach_note(payload: Dict[str, Any], *, surface: str = "quant") -> Dict[str, Any]:
    """Attach the unit-convention note to an existing payload dict (copy).

    Returns a NEW dict (the original is not mutated) with
    ``unit_convention_note`` injected as a nested key.  Safe to call on any
    quant/risk/pm_trail response before returning it to a client.

    Parameters
    ----------
    payload : dict
        Any dict (quant response, risk view, paper-trail row, etc.).
    surface : str
        Passed through to unit_convention_note(); informational only.

    Returns
    -------
    A copy of ``payload`` with the key ``unit_convention_note`` added.
    Never raises.
    """
    try:
        result = dict(payload)
        result["unit_convention_note"] = unit_convention_note(surface=surface)
        return result
    except Exception:  # noqa: BLE001
        # If anything goes wrong, return the original rather than raising.
        return dict(payload) if isinstance(payload, dict) else {}
