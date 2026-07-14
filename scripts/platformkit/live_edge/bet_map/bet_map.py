"""scripts.platformkit.live_edge.bet_map.bet_map -- extend claim_impact's
observable -> market-family fan-out to the FULL biddable surface (Track B3).

claim_impact.py (imported, never edited) already builds a tier-1/tier-2-only
index over 9 native observables and ~12 market families. That leaves most of
the 78k-row ledger (screened/proposed/rejected claims, and topics its fixed
vocabulary never learned -- tails.*, player_cell.*, situation.*, synergy.*,
opponent.opp_def_tercile.*) as structurally "unmapped" even though they DO
inform real market shapes once mined. This module:

  1. adds the missing market-shape vocabulary books actually offer (mainline
     moneyline, quarter/half period lines, minutes props, race-to-X, team/
     game alt lines, first-basket exotics, team SGP legs) that claim_impact's
     FAMILIES_BY_OBSERVABLE never listed;
  2. adds a fallback topic->observable vocabulary (same fixed-vocab-fallback
     shape as claim_impact._TOPIC_VOCAB) for the ledger topics claim_impact's
     vocab misses;
  3. maps EVERY ledger claim (all lifecycles, not just tier-1/2 -- this is a
     mining-target index, not a trusted-signal index) to every market family
     its observable can inform.

INVARIANTS: pandas + stdlib only. <=300 LOC. ASCII stdout. Never writes
data/registry/. Structural fan-out only -- no effect size, no $/edge claim.
"""
from __future__ import annotations

import re

import pandas as pd

from scripts.platformkit.omni import claim_impact as ci
from scripts.platformkit.omni import claims_ledger as cl

# Market shapes claim_impact already uses (kept here only for reference/tests
# -- the source of truth for these stays claim_impact.FAMILIES_BY_OBSERVABLE).
EXISTING_FAMILIES = sorted({f for fams in ci.FAMILIES_BY_OBSERVABLE.values() for f in fams})

# NEW biddable shapes (Kalshi/Polymarket in-game contracts + standard book
# props) that no existing claim_impact family covers.
NEW_MARKET_FAMILIES = [
    "moneyline",              # mainline ML / win-market
    "props.min",               # player minutes prop
    "period.team_total",       # quarter/half team total lines
    "period.spread",           # quarter/half spread lines
    "period.game_total",       # quarter/half game total lines
    "race_to_x",                # race-to-N-points/threes contracts
    "alt_lines.team",           # team alt spread/total
    "alt_lines.game",           # game alt total
    "sgp.team_legs",             # team-leg same-game-parlay components
    "exotics.first_basket",       # first-basket-ish exotics
]

ALL_MARKET_SHAPES = sorted(set(EXISTING_FAMILIES) | set(NEW_MARKET_FAMILIES))

# Observables that claim_impact's vocab does not resolve, keyed the same way
# as claim_impact.FAMILIES_BY_OBSERVABLE (structural "can move", not effect
# size). One entry per ledger topic family found in the current corpus
# (STATE.md: situation-grid, player-grid, synergy, tails, opp-tercile).
EXTRA_FAMILIES_BY_OBSERVABLE = {
    "tail_risk": ["props.pts", "props.reb", "props.ast", "props.threes",
                    "alt_lines.player", "sgp.player_legs", "race_to_x"],
    "player_context": ["props.pts", "props.reb", "props.ast", "props.threes",
                         "props.min", "ingame.player_surface",
                         "sgp.player_legs", "period.team_total"],
    "team_situation": ["team_total", "spread", "game_total", "moneyline",
                         "period.team_total", "period.spread",
                         "ingame.team", "alt_lines.team", "sgp.team_legs"],
}

# Ordered (regex, observable) pairs, same fallback shape as
# claim_impact._TOPIC_VOCAB -- checked ONLY after claim_impact.resolve_observable
# comes back "unmapped", never overriding what it already knows. Note:
# opponent.opp_def_tercile.* and most synergy.* topics already resolve via
# claim_impact's own vocab (shot_quality / possession_outcome substrings) --
# not repeated here. The synergy line below is a safety net for a future
# synergy subtype that misses those substrings; verified empirically
# unreachable against the current 78k-row ledger (2026-07-14).
_EXTRA_TOPIC_VOCAB = [
    (r"^tails\.", "tail_risk"),
    (r"^player_cell\.", "player_context"),
    (r"^situation\.", "team_situation"),
    (r"^synergy\.", "team_situation"),
]


def resolve_observable_full(topic: str) -> str:
    """claim_impact.resolve_observable first (native + its own fallback
    vocab); if still 'unmapped', try the extra vocab above; else 'unmapped'."""
    obs = ci.resolve_observable(topic)
    if obs != "unmapped":
        return obs
    t = (topic or "").lower()
    for pat, extra_obs in _EXTRA_TOPIC_VOCAB:
        if re.search(pat, t):
            return extra_obs
    return "unmapped"


def families_for_observable(observable: str) -> list[str]:
    """Market families an observable can inform -- claim_impact's map first,
    falling back to the extra map above."""
    if observable in ci.FAMILIES_BY_OBSERVABLE:
        return ci.FAMILIES_BY_OBSERVABLE[observable]
    return EXTRA_FAMILIES_BY_OBSERVABLE.get(observable, [])


def bet_fanout(sport: str | None = None, lifecycle: str | None = None,
               base_dir=None) -> pd.DataFrame:
    """EVERY ledger claim (any lifecycle -- this is a mining-target index,
    not claim_impact's trusted tier-1/2 index) exploded over every market
    family its observable can inform. Columns match claim_impact's index
    shape (claim_id, sport, entity_ids, observable, market_family) plus
    lifecycle so callers can slice trusted-vs-candidate."""
    claims = cl.query(sport=sport, lifecycle=lifecycle, base_dir=base_dir)
    rows = []
    for _, r in claims.iterrows():
        observable = resolve_observable_full(r["topic"])
        families = families_for_observable(observable)
        base_row = {
            "claim_id": r["claim_id"], "lifecycle": r["lifecycle"],
            "sport": r["sport"], "entity_ids": r["entity_ids_flat"],
            "topic": r["topic"], "observable": observable,
        }
        if not families:
            rows.append({**base_row, "market_family": ""})
        else:
            for fam in families:
                rows.append({**base_row, "market_family": fam})
    cols = ["claim_id", "lifecycle", "sport", "entity_ids", "topic",
            "observable", "market_family"]
    return pd.DataFrame(rows, columns=cols)


__all__ = ["resolve_observable_full", "families_for_observable", "bet_fanout",
           "ALL_MARKET_SHAPES", "NEW_MARKET_FAMILIES", "EXTRA_FAMILIES_BY_OBSERVABLE"]
