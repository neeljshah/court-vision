"""stake_units_normalize.py -- Dollar-to-display-units normalizer.

The paper_autobet runner sizes bets via Kelly math (kelly_fraction * bankroll),
which produces a raw dollar amount (e.g. $382.32).  That value is then recorded
as ``stake_units`` by clv_ledger.record_bet, so the /api/paper/trail endpoint
renders "382.32u" instead of a meaningful unit count.

This module provides a single pure function ``normalize`` that converts a dollar
stake to a display-unit count by dividing by the configured unit_size and
clamping to a realistic 0-10 band.  It has NO side-effects and NO network calls.

Ownership: BACKEND lane -- scripts/platformkit/pm_trading/ only.
Contract:
  * Returns a bare float (no $ string, no rounding artefacts beyond 6 d.p.).
  * Output is always in [0.0, UNIT_BAND_MAX].
  * Zero input -> 0.0 (no bet, no units).
  * unit_size <= 0 raises ValueError (callers must configure a sensible base).

The BE-D workstream owns the call-site edit in paper_autobet.py to pipe the
normalized value into record_bet; this module is BE-C (pure normalizer only).
"""
from __future__ import annotations

__all__ = ["normalize", "DEFAULT_UNIT_SIZE", "UNIT_BAND_MAX"]

# Default unit base matches AutoBetConfig.unit_stake ($100 flat unit).
DEFAULT_UNIT_SIZE: float = 100.0

# Realistic per-bet ceiling: 10 units is a very large position for paper trading.
UNIT_BAND_MAX: float = 10.0


def normalize(
    dollar_stake: float,
    unit_size: float = DEFAULT_UNIT_SIZE,
    band_max: float = UNIT_BAND_MAX,
) -> float:
    """Convert a dollar stake to display units, clamped to [0, band_max].

    Parameters
    ----------
    dollar_stake:
        Raw dollar amount returned by size_stake() or policy.stake_units().
        Must be >= 0.
    unit_size:
        The base dollar value of one unit (e.g. 100.0 for a $100 flat unit).
        Must be > 0.
    band_max:
        Upper clamp on the returned unit count.  Default 10.0.

    Returns
    -------
    float
        Units in [0.0, band_max], rounded to 6 decimal places.
        This is a bare float -- never a formatted $ string.

    Examples
    --------
    >>> normalize(382.32, unit_size=100)
    3.8232
    >>> normalize(5000.0, unit_size=100)   # clamped
    10.0
    >>> normalize(0.0)
    0.0
    """
    if unit_size <= 0.0:
        raise ValueError(
            "unit_size must be > 0, got %r" % (unit_size,)
        )
    if dollar_stake < 0.0:
        raise ValueError(
            "dollar_stake must be >= 0, got %r" % (dollar_stake,)
        )
    if dollar_stake == 0.0:
        return 0.0
    raw = float(dollar_stake) / float(unit_size)
    clamped = min(raw, float(band_max))
    return round(clamped, 6)
