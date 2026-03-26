"""
defensive_scheme_classifier.py — M40: Classify opponent's defensive scheme.

Output: scheme enum: ZONE / MAN / SWITCH_HEAVY / DROP / HEDGE / ICE
Method: Rule-based on synergy play type defense + matchup data.
        Paint touch rate < 15% → likely zone.
        High switch rate from matchup data → switch.

Public API
----------
    classify_defensive_scheme(team_abbrev, season) -> str
    get_scheme_adjustments(scheme)                 -> dict
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")

log = logging.getLogger(__name__)

# Scheme labels
SCHEME_MAN         = "MAN"
SCHEME_ZONE        = "ZONE"
SCHEME_SWITCH      = "SWITCH_HEAVY"
SCHEME_DROP        = "DROP"
SCHEME_HEDGE       = "HEDGE"
SCHEME_ICE         = "ICE"

# FG% adjustment by scheme for various play types
_SCHEME_ADJUSTMENTS = {
    SCHEME_MAN:    {"spot_up": 1.0, "isolation": 1.0, "pick_roll": 1.0, "post": 1.0},
    SCHEME_ZONE:   {"spot_up": 0.97, "isolation": 1.03, "pick_roll": 0.98, "post": 1.02},
    SCHEME_SWITCH: {"spot_up": 1.02, "isolation": 0.97, "pick_roll": 1.04, "post": 1.05},
    SCHEME_DROP:   {"spot_up": 1.0, "isolation": 1.0, "pick_roll": 1.05, "post": 1.0},
    SCHEME_HEDGE:  {"spot_up": 1.0, "isolation": 1.0, "pick_roll": 0.96, "post": 1.01},
    SCHEME_ICE:    {"spot_up": 1.0, "isolation": 1.0, "pick_roll": 0.97, "post": 1.0},
}

# Teams known for specific schemes (updated 2024-25 — rough approximations)
_TEAM_SCHEME_HINTS = {
    "MEM": SCHEME_DROP,
    "DEN": SCHEME_DROP,
    "MIA": SCHEME_ZONE,
    "GS":  SCHEME_SWITCH, "GSW": SCHEME_SWITCH,
    "BOS": SCHEME_SWITCH,
    "HOU": SCHEME_ICE,
    "LAC": SCHEME_HEDGE,
    "OKC": SCHEME_DROP,
    "MIN": SCHEME_SWITCH,
    "CLE": SCHEME_DROP,
}

_SCHEME_CACHE: dict[str, str] = {}


def classify_defensive_scheme(team_abbrev: str, season: str = "2024-25") -> str:
    """
    Classify the defensive scheme for a team.

    Uses:
    1. Synergy defensive play type data (ppp allowed by play type)
    2. Matchup data (switch frequency proxy)
    3. Team hints as fallback

    Returns:
        One of: ZONE, MAN, SWITCH_HEAVY, DROP, HEDGE, ICE
    """
    cache_key = f"{team_abbrev}_{season}"
    if cache_key in _SCHEME_CACHE:
        return _SCHEME_CACHE[cache_key]

    scheme = _classify_from_synergy(team_abbrev, season)
    if scheme is None:
        scheme = _TEAM_SCHEME_HINTS.get(team_abbrev, SCHEME_MAN)

    _SCHEME_CACHE[cache_key] = scheme
    log.debug("Defensive scheme %s → %s", team_abbrev, scheme)
    return scheme


def _classify_from_synergy(team_abbrev: str, season: str) -> Optional[str]:
    """
    Attempt to classify scheme from synergy defensive data.
    Returns None if insufficient data.
    """
    import glob
    syn_files = glob.glob(os.path.join(_NBA_CACHE, f"synergy_defensive_{season}.json"))
    if not syn_files:
        return None

    try:
        data = json.load(open(syn_files[0]))
        if not isinstance(data, list):
            return None

        # Filter to this team's defensive data
        team_data = [
            r for r in data
            if r.get("team_abbreviation", "").upper() == team_abbrev.upper()
        ]
        if not team_data:
            return None

        # Build play type → ppp map
        ppp_by_type: dict[str, float] = {}
        for r in team_data:
            pt  = r.get("play_type", "")
            ppp = float(r.get("ppp", 1.0) or 1.0)
            if pt:
                ppp_by_type[pt] = ppp

        # Rule-based classification
        pr_ppp      = ppp_by_type.get("PRBallHandler", 1.0)
        iso_ppp     = ppp_by_type.get("Isolation", 1.0)
        spotup_ppp  = ppp_by_type.get("SpotUp", 1.0)
        post_ppp    = ppp_by_type.get("Postup", 1.0)

        # DROP coverage: good at perimeter, vulnerable to P&R pull-ups
        if pr_ppp > 1.05 and spotup_ppp < 0.95:
            return SCHEME_DROP

        # SWITCH: bad at post (bigger defenders on PGs), good at spot-up
        if post_ppp > 1.08 and iso_ppp < 0.95:
            return SCHEME_SWITCH

        # ZONE: good at isolation, bad at spot-up
        if iso_ppp < 0.95 and spotup_ppp > 1.05:
            return SCHEME_ZONE

        # HEDGE: best at eliminating ball-handler, vulnerable to pocket passes
        if pr_ppp < 0.90:
            return SCHEME_HEDGE

        return SCHEME_MAN

    except Exception as e:
        log.debug("Synergy scheme classification failed: %s", e)
        return None


def get_scheme_adjustments(scheme: str) -> dict:
    """
    Return FG% adjustment factors for various play types under this scheme.
    Values > 1.0 mean player gets easier looks.
    """
    return _SCHEME_ADJUSTMENTS.get(scheme, _SCHEME_ADJUSTMENTS[SCHEME_MAN]).copy()
