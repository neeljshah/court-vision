"""sell.entitlements -- plan->feature map and feature access gating.

Defines the three product tiers (free / pro / enterprise) and the allowed(plan,
feature)->bool predicate that every access check calls. No I/O, no secrets, no
dollar-edge claim. Pure policy data + a tolerant accessor.

Plans:

    free        NBA predictions only; paper-trail read (CLV history). Honest
                calibration + CLV cadence. Read-only; no export; no stream.

    pro         All-sport predictions (NBA + MLB + soccer + tennis); full CLV
                report export; SSE streaming endpoint; bulk slate download.

    enterprise  Everything in pro PLUS the evidence pack (OOS calibration audit,
                walk-forward transcript, governance run artifacts, methodology PDF).

Feature names are lowercase snake_case ASCII strings; unknown features are
always DENIED to fail-closed on typos.

INVARIANTS: <=300 LOC; ASCII only; no secrets; no $-edge field; no I/O.
"""
from __future__ import annotations

from typing import Dict, FrozenSet

# --------------------------------------------------------------------------- #
# Canonical feature registry                                                   #
# --------------------------------------------------------------------------- #

#: All known feature identifiers. Any feature NOT in this set -> DENIED.
KNOWN_FEATURES: FrozenSet[str] = frozenset({
    # Data access -- which sports are covered
    "sport_nba",
    "sport_mlb",
    "sport_soccer",
    "sport_tennis",
    # Paper-trail read
    "paper_trail_read",      # CLV history read access
    # Report exports
    "clv_report_export",     # full CLV ledger export (CSV / JSON)
    # Delivery modes
    "stream_sse",            # server-sent events streaming endpoint
    "bulk_slate_download",   # full slate parquet/JSON bulk download
    # Evidence pack (enterprise only)
    "evidence_pack",         # OOS calibration audit + WF transcript + governance artifacts
    "methodology_pdf",       # methodology document
    "governance_artifacts",  # run_governance.py output snapshots
    # Live edge view (pro + enterprise; NOT free)
    "live_edges",            # GET /sell/v1/edges/{sport} deep model-vs-market view
    # Paper placement via the sell API (pro + enterprise; NOT free)
    "paper_place",           # POST /sell/v1/paper/place manual paper-trade endpoint
})


# --------------------------------------------------------------------------- #
# Plan definitions                                                             #
# --------------------------------------------------------------------------- #

#: Per-plan feature sets. The plan name is the key; value is frozenset of
#: allowed feature identifiers. Built bottom-up so enterprise >= pro >= free.

_FREE_FEATURES: FrozenSet[str] = frozenset({
    "sport_nba",
    "paper_trail_read",
})

_PRO_FEATURES: FrozenSet[str] = _FREE_FEATURES | frozenset({
    "sport_mlb",
    "sport_soccer",
    "sport_tennis",
    "clv_report_export",
    "stream_sse",
    "bulk_slate_download",
    "live_edges",
    "paper_place",
})

_ENTERPRISE_FEATURES: FrozenSet[str] = _PRO_FEATURES | frozenset({
    "evidence_pack",
    "methodology_pdf",
    "governance_artifacts",
})

#: Canonical plan map. Keys are the canonical plan names (lowercase).
PLAN_FEATURES: Dict[str, FrozenSet[str]] = {
    "free": _FREE_FEATURES,
    "pro": _PRO_FEATURES,
    "enterprise": _ENTERPRISE_FEATURES,
}

#: Ordered tier list (lowest to highest) for UI / display purposes.
PLAN_TIERS = ("free", "pro", "enterprise")

#: The product makes no dollar-edge claims. Reflected on the entitlements map.
EDGE_CLAIMED: bool = False


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #

def allowed(plan: str, feature: str) -> bool:
    """Return True iff *feature* is allowed on *plan*.

    Fails CLOSED: an unknown plan OR an unknown feature both return False.
    This is the single predicate every access check in the sell layer calls.

    Args:
        plan:    One of "free", "pro", "enterprise" (case-insensitive).
        feature: A KNOWN_FEATURES member (lowercase snake_case).

    Returns:
        True iff the plan grants this feature. False on any unknown input.
    """
    plan_key = plan.lower() if isinstance(plan, str) else ""
    feature_key = feature.lower() if isinstance(feature, str) else ""
    if plan_key not in PLAN_FEATURES:
        return False
    if feature_key not in KNOWN_FEATURES:
        return False
    return feature_key in PLAN_FEATURES[plan_key]


def plan_features(plan: str) -> FrozenSet[str]:
    """Return the feature set for *plan*, or empty frozenset for unknown plan."""
    plan_key = plan.lower() if isinstance(plan, str) else ""
    return PLAN_FEATURES.get(plan_key, frozenset())


def feature_min_plan(feature: str) -> str:
    """Return the lowest plan tier that grants *feature*, or 'enterprise' if none.

    Useful for error messages: "this feature requires plan X or higher."
    Returns empty string if *feature* is not a known feature at all.
    """
    feature_key = feature.lower() if isinstance(feature, str) else ""
    if feature_key not in KNOWN_FEATURES:
        return ""
    for tier in PLAN_TIERS:
        if feature_key in PLAN_FEATURES[tier]:
            return tier
    return "enterprise"


__all__ = [
    "KNOWN_FEATURES",
    "PLAN_FEATURES",
    "PLAN_TIERS",
    "EDGE_CLAIMED",
    "allowed",
    "plan_features",
    "feature_min_plan",
]
