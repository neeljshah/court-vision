"""scripts.platformkit.bestbets.prop_tier -- EV-based tier assignment for prop bets.

Given a model probability for the over side and a decimal odds price, computes
EV via odds_shop.ev_vs_price and maps the result to a tier via pm_trading.policy.tier.

Design rails (binding):
  * PURE -- no IO, no network.  Same inputs -> same outputs.
  * Returns None (no bet) when decimal_odds is None / missing (UNAVAILABLE offseason)
    or when EV is below the proxy-adjusted floor.
  * Prop bets default to clv_is_proxy=True because in-play close prices for props
    are almost always synthetic/proxy; the caller may override when a true close
    is known.
  * UNITS only -- no $/dollar field. No edge claim.
  * <=300 LOC.  ASCII only.  Build only under scripts/platformkit/.
"""
from __future__ import annotations

from typing import Optional

try:  # package import (normal runtime)
    from scripts.platformkit.odds_shop import ev_vs_price
    from scripts.platformkit.pm_trading.policy import tier as _policy_tier
except ImportError:  # pragma: no cover  (flat-sibling hermetic import fallback)
    from odds_shop import ev_vs_price  # type: ignore
    from pm_trading.policy import tier as _policy_tier  # type: ignore


def tier_prop(
    p_over: float,
    decimal_odds: Optional[float],
    *,
    clv_is_proxy: bool = True,
) -> Optional[str]:
    """Assign an EV-based tier for a player-prop over bet.

    Parameters
    ----------
    p_over:
        Model probability of the stat going OVER the line (0 < p_over < 1).
    decimal_odds:
        Decimal (European) odds available at the best bettable price for the
        over side.  Pass None when odds are unavailable (e.g. NBA offseason) --
        returns None immediately with no fabricated price.
    clv_is_proxy:
        Whether the closing-line value will be graded against a proxy close
        (default True for props -- true in-play prop closes are rare).  When
        True the EV_PROXY_PENALTY from policy.py is added to every floor.

    Returns
    -------
    "A" / "B" / "C"  when EV clears the (proxy-adjusted) floor, else None.
    """
    if decimal_odds is None:
        return None

    try:
        p = float(p_over)
        o = float(decimal_odds)
    except (TypeError, ValueError):
        return None

    # decimal_odds must be strictly > 1.0 to be a valid bettable price.
    if o <= 1.0:
        return None

    ev = ev_vs_price(p, o)
    return _policy_tier(ev=ev, clv_is_proxy=clv_is_proxy)


__all__ = ["tier_prop"]
