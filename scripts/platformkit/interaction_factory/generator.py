"""scripts.platformkit.interaction_factory.generator -- TYPED candidate
enumeration + the factory's own template config.

A candidate is a pair of attributes drawn from the per-sport attribute registry
under a declared TYPE TEMPLATE (each names its atomic unit, outcome, baseline,
and the two pools it crosses). Enumeration is DETERMINISTIC and seedless: the
same registry + config always yields the same ordered candidate list, so a
resumed factory never re-tests a tested candidate and never depends on run order.

CLOSED CLASSES (memory: pregame team-season aggregates, SP-fatigue on this
corpus, endQ1 x floor_quality) are BLOCKLISTED here -- excluded from enumeration,
never silently tested.

Pure enumeration only -- no data read, no fit, no ledger write (runner.py owns
those). ASCII; stdlib + the registries.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------
# Closed classes -- blocklisted GLOBALLY across every template (from memory:
# these hypothesis classes are CLOSED, re-testing them is p-hacking the graveyard).
GLOBAL_BLOCKLIST_ATTRS = frozenset({
    "velo_decline_in_game",   # SP-fatigue on this corpus -- CLOSED (honest REJECT + NOT_TESTABLE)
})
# endQ1 x floor_quality (a closed interaction class); named as an unordered pair
# so it is refused even if both attrs are ever added to a registry.
GLOBAL_BLOCKLIST_PAIRS = frozenset({
    frozenset({"endQ1", "floor_quality"}),
})


# --------------------------------------------------------------------------
# TYPE TEMPLATES -- the factory's declared candidate grammar (pure DATA).
# `pairing`: "self_cross" (unordered i<j pairs within ONE pool -- attr x attr of
# the same entity) or "cross" (ordered product of two DISTINCT pools, a!=b).
# `feature_builder` names the runner builder that materializes the as-of frame;
# a template whose builder is not registered yields honest NOT_TESTABLE rows.
TEMPLATES: Dict[str, Dict[str, Any]] = {
    # ---- NBA (3) -------------------------------------------------------
    "nba_shot_offense_x_offense": {
        "sport": "basketball_nba",
        "atomic_unit": "player_game",
        "outcome": "efg",
        "baseline": "efg ~ attr_a + attr_b",
        "pairing": "self_cross",
        "left_pool": {"attributes": [
            "zone_efg_rim", "zone_efg_paint", "zone_efg_mid",
            "zone_efg_corner3", "zone_efg_above_break_3",
            "transition_efg", "halfcourt_efg", "late_clock_efg",
        ]},
        "feature_builder": "nba_player_offense_asof",
        "blocklist_attrs": [],
        "blocklist_pairs": [],
    },
    "nba_stint_lineup_x_lineup": {
        "sport": "basketball_nba",
        "atomic_unit": "stint",
        "outcome": "net_pts",
        "baseline": "net_pts ~ attr_a + attr_b",
        "pairing": "self_cross",
        "left_pool": {"attributes": ["synergy_residual", "continuity_s"]},
        "feature_builder": "nba_stint_lineup_asof",   # not yet registered -> NOT_TESTABLE
        "blocklist_attrs": [],
        "blocklist_pairs": [],
    },
    "nba_shot_attr_x_state": {
        "sport": "basketball_nba",
        "atomic_unit": "player_game",
        "outcome": "efg",
        "baseline": "efg ~ attr + state",
        "pairing": "cross",
        "left_pool": {"attributes": [
            "zone_efg_rim", "zone_efg_above_break_3", "transition_efg",
        ]},
        "right_pool": {"attributes": ["late_clock_efg", "clutch_efg"]},
        "feature_builder": "nba_offense_state_asof",   # not yet registered -> NOT_TESTABLE
        "blocklist_attrs": [],
        "blocklist_pairs": [],
    },
    # ---- MLB (2) -------------------------------------------------------
    "mlb_pa_batter_x_pitcher": {
        "sport": "mlb",
        "atomic_unit": "plate_appearance",
        "outcome": "is_k",
        "baseline": "is_k ~ batter_attr + pitcher_attr",
        "pairing": "cross",
        "left_pool": {"attributes": ["K_avoidance", "BB_rate"]},
        "right_pool": {"attributes": ["whiff_rate", "platoon_split"]},
        "feature_builder": "mlb_pa_asof",   # not yet registered -> NOT_TESTABLE
        "blocklist_attrs": [],
        "blocklist_pairs": [],
    },
    "mlb_pa_attr_x_count_state": {
        "sport": "mlb",
        "atomic_unit": "plate_appearance",
        "outcome": "is_k",
        "baseline": "is_k ~ attr + count_state",
        "pairing": "cross",
        "left_pool": {"attributes": ["K_avoidance", "whiff_rate"]},
        "right_pool": {"attributes": ["discipline_by_count", "mix_by_leverage"]},
        "feature_builder": "mlb_pa_count_state_asof",   # not yet registered -> NOT_TESTABLE
        "blocklist_attrs": ["velo_decline_in_game"],
        "blocklist_pairs": [],
    },
}


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    template_id: str
    sport: str
    atomic_unit: str
    outcome: str
    attr_a: str
    attr_b: str
    feature_builder: str
    # 'knowledge' (seeded from a domain mechanisms.md entry) | 'blind' (plain
    # combinatorial enumeration). Additive: a template that doesn't declare it
    # defaults to 'blind' -- see TEMPLATES.get(...) in enumerate_candidates.
    hypothesis_source: str = "blind"


def _registry(sport: str) -> Dict[str, Any]:
    """The per-sport ATTRIBUTES catalog -- imported lazily so enumerating one
    sport never forces the others' registries to import."""
    if sport == "basketball_nba":
        from domains.basketball_nba.profiles.attribute_registry import ATTRIBUTES
        return ATTRIBUTES
    if sport == "mlb":
        from domains.mlb.profiles.attribute_registry import ATTRIBUTES
        return ATTRIBUTES
    raise KeyError("no attribute registry for sport %r" % sport)


def resolve_pool(sport: str, pool_spec: Dict[str, Any]) -> List[str]:
    """Registry-valid attribute names for a pool spec, sorted (deterministic).

    `{"attributes": [...]}` -> the named attrs that EXIST in the registry (a
    typo drops out, it is never invented). `{"entity": "player"}` -> every
    registry attr for that entity, so a NEWLY-added registry attribute auto-
    enters the candidate space next enumeration (the "writes more on its own"
    property). Unknown pool shape -> [].
    """
    reg = _registry(sport)
    if "attributes" in pool_spec:
        names = [a for a in pool_spec["attributes"] if a in reg]
    elif "entity" in pool_spec:
        names = [n for n, s in reg.items() if s.get("entity") == pool_spec["entity"]]
    else:
        names = []
    return sorted(set(names))


def _blocked(a: str, b: str, tpl: Dict[str, Any]) -> bool:
    block_attrs = set(GLOBAL_BLOCKLIST_ATTRS) | set(tpl.get("blocklist_attrs") or [])
    if a in block_attrs or b in block_attrs:
        return True
    pair = frozenset({a, b})
    block_pairs = set(GLOBAL_BLOCKLIST_PAIRS) | {frozenset(p) for p in (tpl.get("blocklist_pairs") or [])}
    return pair in block_pairs


def _candidate_id(template_id: str, a: str, b: str) -> str:
    return "%s::%s__x__%s" % (template_id, a, b)


def enumerate_candidates(template_id: str) -> List[Candidate]:
    """Deterministic, blocklist-filtered candidate list for one template.

    self_cross -> unordered i<j pairs of one pool (attr x attr, same entity);
    cross      -> ordered product of two distinct pools, a!=b. Ordering is the
    natural sorted-pool combinatorial order, so it is stable across runs.
    """
    tpl = TEMPLATES[template_id]
    sport = tpl["sport"]
    left = resolve_pool(sport, tpl["left_pool"])
    pairing = tpl["pairing"]
    if pairing == "self_cross":
        pairs = itertools.combinations(left, 2)
    elif pairing == "cross":
        right = resolve_pool(sport, tpl["right_pool"])
        pairs = ((a, b) for a in left for b in right if a != b)
    else:
        raise ValueError("unknown pairing %r for %s" % (pairing, template_id))

    hyp_source = tpl.get("hypothesis_source", "blind")
    out: List[Candidate] = []
    for a, b in pairs:
        if _blocked(a, b, tpl):
            continue
        out.append(Candidate(
            candidate_id=_candidate_id(template_id, a, b),
            template_id=template_id, sport=sport, atomic_unit=tpl["atomic_unit"],
            outcome=tpl["outcome"], attr_a=a, attr_b=b,
            feature_builder=tpl["feature_builder"], hypothesis_source=hyp_source,
        ))
    return out


def tested_ids(ledger_rows: List[Dict[str, Any]], template_id: str) -> set:
    """candidate_ids already on record for this template (ANY verdict -- a
    tested candidate is never re-tested; see runner dedupe note)."""
    return {r.get("candidate_id") for r in ledger_rows if r.get("template_id") == template_id}


def next_batch(template_id: str, k: int, ledger_rows: Optional[List[Dict[str, Any]]] = None) -> List[Candidate]:
    """The next <=k untested candidates in deterministic order."""
    done = tested_ids(ledger_rows or [], template_id)
    remaining = [c for c in enumerate_candidates(template_id) if c.candidate_id not in done]
    return remaining[: max(0, int(k))]


__all__ = [
    "TEMPLATES", "GLOBAL_BLOCKLIST_ATTRS", "GLOBAL_BLOCKLIST_PAIRS", "Candidate",
    "resolve_pool", "enumerate_candidates", "tested_ids", "next_batch",
]
