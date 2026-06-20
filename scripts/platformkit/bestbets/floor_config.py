"""scripts.platformkit.bestbets.floor_config -- per-sport no-bet floor config table.

BB-Q5 (P1): lets each sport override the global EV tier floors without touching
the human-gated frontend/exec_decision.py.

Design contract:
  * Read exec_decision.TIER_FLOORS as the default fallback (read-only import;
    this module NEVER mutates that dict).
  * A sport-keyed override table holds calibration-threshold adjustments per sport.
    Floors are EV thresholds (probability-space, per 1 unit staked), not $.
  * get_floors(sport) returns the per-sport override dict when the sport is known,
    otherwise returns a COPY of TIER_FLOORS so callers always get a mutable dict
    without aliasing the global.
  * Unknown sport is not an error -- it silently falls back to the global default.
  * UNITS not $. No dollar / ROI / PnL field. No edge claim. ASCII only.
  * <=300 LOC; pure (no IO, no network, no global state mutation on import).

Override rationale per sport:
  NBA -- default floors; most liquid market with tight closes.
  tennis -- proxy closes are near-universal (no real-time close for props),
    raise all floors by 0.01 on top of the global default.
  soccer -- similar proxy-close exposure; raise by 0.01.
  mlb -- pitcher-blind model; stronger divergence needed; raise by 0.02.
  nfl -- very liquid market; default floors.

These overrides encode calibration discipline, not claimed edge.
"""
from __future__ import annotations

from typing import Dict

# Read the global defaults -- import is READ-ONLY; we never assign to TIER_FLOORS.
from frontend.exec_decision import TIER_FLOORS as _TIER_FLOORS_DEFAULT

# ---------------------------------------------------------------------------
# Per-sport floor override table.
# Keys are canonical sport slugs (lowercase).  Values are complete tier-floor
# dicts (all three tiers must be present).  These are EV thresholds, not $.
# ---------------------------------------------------------------------------
_SPORT_OVERRIDES: Dict[str, Dict[str, float]] = {
    # NBA: liquid market, true closes frequent; global defaults are appropriate.
    "nba": {
        "A": _TIER_FLOORS_DEFAULT["A"],        # 0.08
        "B": _TIER_FLOORS_DEFAULT["B"],        # 0.04
        "C": _TIER_FLOORS_DEFAULT["C"],        # 0.02
    },
    # tennis: props almost always settle against a proxy close; +0.01 penalty.
    "tennis": {
        "A": _TIER_FLOORS_DEFAULT["A"] + 0.01,   # 0.09
        "B": _TIER_FLOORS_DEFAULT["B"] + 0.01,   # 0.05
        "C": _TIER_FLOORS_DEFAULT["C"] + 0.01,   # 0.03
    },
    # soccer: frequent proxy closes, especially for player props; +0.01.
    "soccer": {
        "A": _TIER_FLOORS_DEFAULT["A"] + 0.01,   # 0.09
        "B": _TIER_FLOORS_DEFAULT["B"] + 0.01,   # 0.05
        "C": _TIER_FLOORS_DEFAULT["C"] + 0.01,   # 0.03
    },
    # mlb: pitcher-blind model needs a wider measured divergence to bet; +0.02.
    "mlb": {
        "A": _TIER_FLOORS_DEFAULT["A"] + 0.02,   # 0.10
        "B": _TIER_FLOORS_DEFAULT["B"] + 0.02,   # 0.06
        "C": _TIER_FLOORS_DEFAULT["C"] + 0.02,   # 0.04
    },
    # nfl: liquid market; global defaults (explicit entry for discoverability).
    "nfl": {
        "A": _TIER_FLOORS_DEFAULT["A"],        # 0.08
        "B": _TIER_FLOORS_DEFAULT["B"],        # 0.04
        "C": _TIER_FLOORS_DEFAULT["C"],        # 0.02
    },
}

# Sorted canonical sport names (stable order for inspection / tests).
KNOWN_SPORTS = tuple(sorted(_SPORT_OVERRIDES))


def get_floors(sport: str) -> Dict[str, float]:
    """Return the tier EV floors for *sport*, or the global default fallback.

    Parameters
    ----------
    sport:
        Canonical sport slug (case-insensitive: "NBA", "nba", and "Nba" all
        map to the NBA entry).  Unknown slugs return the global default.

    Returns
    -------
    Dict[str, float]
        A NEW dict with keys "A", "B", "C" mapping to EV threshold floats.
        All values are calibration thresholds (EV per 1 unit, not $).
        The returned dict is independent of _TIER_FLOORS_DEFAULT and
        _SPORT_OVERRIDES -- mutating it is safe.

    Notes
    -----
    - Unknown sport is NOT an error: it returns the TIER_FLOORS fallback.
    - This function never mutates TIER_FLOORS or _SPORT_OVERRIDES.
    """
    key = str(sport).lower().strip()
    if key in _SPORT_OVERRIDES:
        src = _SPORT_OVERRIDES[key]
    else:
        src = _TIER_FLOORS_DEFAULT
    # Always return a fresh copy -- no aliasing.
    return dict(src)


def is_known_sport(sport: str) -> bool:
    """Return True when *sport* has an explicit override entry."""
    return str(sport).lower().strip() in _SPORT_OVERRIDES


__all__ = [
    "KNOWN_SPORTS",
    "get_floors",
    "is_known_sport",
]
