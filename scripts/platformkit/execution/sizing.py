"""scripts.platformkit.execution.sizing -- tier-based paper stake sizing (team markets only).

PRE-REGISTERED 2026-07-15, BEFORE any forward measurement window, from
docs/research/execution-quality/EXECUTION_BACKLOG.md lever #2: Spearman(edge,
realized clv_pct) = +0.39 on moneyline (monotone across quintiles: median clv
+1.24 -> +1.42 -> +3.06 -> +8.66 -> +50), vs +0.056 on props (quintiles flat
~-7.5). This rule is registered before forward paper placements are measured
against it -- no post-hoc tuning on the same window it will be judged on. Any
future change needs a fresh pre-registration date + reason.

Team / moneyline markets scale with the placement tier (A/B/C, the pre-
registered floors from pm_trading.policy): A=2.0, B=1.5, C=1.0 units. Props /
any other non-team market ALWAYS get the flat base unit (1.0) regardless of
tier -- the ~0 prop rho means tier carries no sizing information there, so
scaling it would just load noise onto a projection bias (see
under_tilt_verdict.md). An unrecognized tier also falls back to the flat base.

PAPER / UNITS only. No $ figure anywhere. Never raises.
"""
from __future__ import annotations

import os
from typing import Optional

BASE_UNITS: float = 1.0

# team/moneyline tier -> units (pre-registered 2026-07-15).
_TIER_UNITS = {"A": 2.0, "B": 1.5, "C": BASE_UNITS}

# market_type strings treated as "team" markets eligible for tiered sizing.
# Everything else (props, unknown types) stays flat -- see module docstring.
_TEAM_MARKET_TYPES = frozenset({"moneyline", "team"})


def tier_sizing_enabled() -> bool:
    """CV_TIER_SIZING env toggle, default ON."""
    return os.environ.get("CV_TIER_SIZING", "1").strip().lower() not in ("0", "false", "off")


def stake_for(tier: Optional[str], market_type: str) -> float:
    """Units for one placement.

    Team/moneyline market_type: tiered (A=2.0, B=1.5, C=1.0). Any other
    market_type (props, unrecognized): flat BASE_UNITS regardless of tier.
    Unrecognized/None tier on a team market: flat BASE_UNITS. Never raises.
    """
    if str(market_type).strip().lower() not in _TEAM_MARKET_TYPES:
        return BASE_UNITS
    key = str(tier).strip().upper() if tier else None
    return _TIER_UNITS.get(key, BASE_UNITS)


def _demo() -> None:
    """Smallest runnable self-check (assert-based); not a test framework."""
    assert stake_for("A", "moneyline") == 2.0
    assert stake_for("B", "team") == 1.5
    assert stake_for("C", "moneyline") == 1.0
    assert stake_for(None, "moneyline") == 1.0
    assert stake_for("A", "prop") == 1.0       # props always flat, even tier A
    assert stake_for("Z", "moneyline") == 1.0  # unknown tier -> flat
    print("sizing self-check OK")


if __name__ == "__main__":
    _demo()


__all__ = ["BASE_UNITS", "stake_for", "tier_sizing_enabled"]
