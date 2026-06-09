"""lib_betting_validation.py — canonical betting-data validation helpers.

Centralises the safe_odds() guard so all betting consumers use identical
validation logic.  Import via:

    from scripts.lib_betting_validation import safe_odds

Bug 10: over_odds=-1 (and similar corrupt sentinels) was found to inflate
ROI from realistic values to +64%.  safe_odds() must be applied to every
odds column right after loading a lines DataFrame.
"""

from __future__ import annotations

import math


def safe_odds(v) -> float:
    """Return valid American odds, defaulting to -110 for corrupt/missing values.

    American odds must be <= -100 (negative) or >= 100 (positive).
    Values in (-99, 99) are corrupt data entries (e.g. the known -1 sentinel
    that inflated ROI by +64% in the Bug 10 incident).

    Handles: numeric strings, NaN/None, integer 0, the -1 sentinel.

    Args:
        v: Any odds value (int, float, str, None, NaN).

    Returns:
        A valid American-odds float, or -110.0 if the input is corrupt/missing.
    """
    try:
        f = float(v)
        # NaN or explicit zero are missing-data sentinels
        if math.isnan(f) or f == 0:
            return -110.0
        # Reject values that aren't valid American odds:
        # valid range is <= -100 or >= +100; anything in (-99, 99) is corrupt.
        if -99 < f < 100:
            return -110.0
        return f
    except Exception:
        return -110.0
