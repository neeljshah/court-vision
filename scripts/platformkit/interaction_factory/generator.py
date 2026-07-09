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
    # ---- NBA box-detail family -- AUTO-DISCOVERY demo ----------------------
    # Pool is `{"entity": "team", "family": "box_detail_asof"}`, not a named
    # attribute list: the moment a new team attribute is tagged
    # `"family": "box_detail_asof"` in the registry (see attribute_registry.py),
    # it enters this template's candidate space on its own, no template edit
    # needed (see resolve_pool). The 5 box-detail as-of attrs (fast_break_pts,
    # paint_pts, tov_pts, largest_lead, foul_trouble -- domains/basketball_nba/
    # boxdetail_asof.py) were entirely-dark espn_boxscores.parquet columns
    # per docs/research/utilization_matrix_2026_07_10.md's ranked backlog #1.
    "nba_boxdetail_self_cross": {
        "sport": "basketball_nba",
        "atomic_unit": "team_game",
        "outcome": "home_win",
        "baseline": "home_win ~ elo + attr_a_diff_asof + attr_b_diff_asof",
        "pairing": "self_cross",
        "left_pool": {"entity": "team", "family": "box_detail_asof"},
        "feature_builder": "nba_boxdetail_asof",   # not yet registered -> NOT_TESTABLE
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
    # ---- MLB bat-tracking family -- AUTO-DISCOVERY demo --------------------
    # Pool is `{"entity": "batter", "family": "bat_tracking"}`, not a named
    # attribute list: the moment a NEW batter attribute is tagged
    # `"family": "bat_tracking"` in the registry, it enters this template's
    # candidate space on its own, no template edit needed (see resolve_pool).
    "mlb_battrack_self_cross": {
        "sport": "mlb",
        "atomic_unit": "batter_season",
        "outcome": "next_season_contact_quality",
        "baseline": "next_season_contact_quality ~ attr_a + attr_b",
        "pairing": "self_cross",
        "left_pool": {"entity": "batter", "family": "bat_tracking"},
        "feature_builder": "mlb_battrack_asof",   # not yet registered -> NOT_TESTABLE
        # bat-tracking leaderboards only exist 2024+ (docstring in the
        # registry) -- a leak-free as-of frame needs >=2 prior-season
        # transitions per batter; deferred until that builder is worth it.
        "blocklist_attrs": [],
        "blocklist_pairs": [],
    },
    # ---- ENTITY-CLASS WILDCARD demo ----------------------------------------
    # `entity_classes` expands the single K_avoidance x BB_rate pair once per
    # MLB team-archetype slug (6 members from domains.mlb.atlas_playstyles) --
    # "does this batter interaction hold within a low-scoring-grinder team
    # vs. a power/run-scoring one", K = 1 pair * 6 members = 6 declared tests.
    "mlb_pa_attr_x_archetype": {
        "sport": "mlb",
        "atomic_unit": "plate_appearance",
        "outcome": "is_k",
        "baseline": "is_k ~ attr_a + attr_b, within team archetype",
        "pairing": "self_cross",
        "left_pool": {"attributes": ["K_avoidance", "BB_rate"]},
        "entity_classes": "mlb_team_archetype",
        "feature_builder": "mlb_pa_archetype_asof",   # not yet registered -> NOT_TESTABLE
        "blocklist_attrs": [],
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
    # ENTITY-CLASS WILDCARD: which class member this candidate is scoped to
    # (e.g. one MLB team-archetype slug), or None for a plain attr-pair
    # candidate. A template that declares `entity_classes` expands EVERY
    # (attr_a, attr_b) pair once per class member -- see ENTITY_CLASS_RESOLVERS
    # and enumerate_candidates below. Additive: absent on every pre-existing
    # candidate/ledger row (defaults None), never a migration.
    entity_class: Optional[str] = None


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
    property) -- this is the AUTO-DISCOVERY seam: a brand-new attribute family
    (e.g. the bat-tracking leaderboard attrs) needs no template edit, only a
    `family` tag on the registry entry (see below), to enter a future batch.

    Optional narrowing keys, either pool shape:
      `family`  -- ALLOWLIST seam, entity pools only: keep only attrs whose
                   registry entry has `"family" == pool_spec["family"]` (e.g.
                   `{"entity": "batter", "family": "bat_tracking"}`).
      `exclude` -- DENYLIST seam, either pool shape: attr names removed after
                   resolution (on top of the GLOBAL_BLOCKLIST_ATTRS closed-
                   class filter applied later in enumerate_candidates).

    Unknown pool shape -> [].
    """
    reg = _registry(sport)
    if "attributes" in pool_spec:
        names = [a for a in pool_spec["attributes"] if a in reg]
    elif "entity" in pool_spec:
        names = [n for n, s in reg.items() if s.get("entity") == pool_spec["entity"]]
        family = pool_spec.get("family")
        if family is not None:
            names = [n for n in names if reg[n].get("family") == family]
    else:
        names = []
    exclude = set(pool_spec.get("exclude") or [])
    return sorted(set(names) - exclude)


# --------------------------------------------------------------------------
# ENTITY-CLASS resolvers -- named, deterministic member lists for a WILDCARD
# template (task: quantify a candidate over a whole entity CLASS -- "any team
# archetype", "any player archetype" -- rather than only named attribute
# pairs). Each resolver is a zero-arg callable returning a sorted list of
# member slugs; it reads only python constants already declared elsewhere
# (real, shipped classifiers -- never live/refreshable data), so enumeration
# stays pure and data-free, matching this module's no-data-read contract. A
# template that declares `entity_classes: "<key>"` gets ONE candidate per
# (attr pair, member) -- the member count multiplies straight into K, exactly
# like any other declared-before-running enumeration.
def _mlb_team_archetype_members() -> List[str]:
    from domains.mlb.atlas_playstyles import _ARCHETYPES  # noqa: SLF001 -- reuse, not reinvent
    return sorted(slug for slug, *_rest in _ARCHETYPES)


def _nba_player_archetype_members() -> List[str]:
    from domains.basketball_nba.memory_atlas_archetypes import ARCHETYPES, _label_to_slug  # noqa: SLF001
    return sorted(_label_to_slug(a["label"]) for a in ARCHETYPES)


ENTITY_CLASS_RESOLVERS: Dict[str, Any] = {
    "mlb_team_archetype": _mlb_team_archetype_members,
    "nba_player_archetype": _nba_player_archetype_members,
}


def _blocked(a: str, b: str, tpl: Dict[str, Any]) -> bool:
    block_attrs = set(GLOBAL_BLOCKLIST_ATTRS) | set(tpl.get("blocklist_attrs") or [])
    if a in block_attrs or b in block_attrs:
        return True
    pair = frozenset({a, b})
    block_pairs = set(GLOBAL_BLOCKLIST_PAIRS) | {frozenset(p) for p in (tpl.get("blocklist_pairs") or [])}
    return pair in block_pairs


def _candidate_id(template_id: str, a: str, b: str, entity_class: Optional[str] = None) -> str:
    base = "%s::%s__x__%s" % (template_id, a, b)
    return base if entity_class is None else "%s::class=%s" % (base, entity_class)


def enumerate_candidates(template_id: str) -> List[Candidate]:
    """Deterministic, blocklist-filtered candidate list for one template.

    self_cross -> unordered i<j pairs of one pool (attr x attr, same entity);
    cross      -> ordered product of two distinct pools, a!=b. Ordering is the
    natural sorted-pool combinatorial order, so it is stable across runs.

    A template that declares `entity_classes: "<resolver key>"` expands every
    surviving (a, b) pair once per class member (sorted, deterministic) --
    K = n_pairs * n_members. A template with no `entity_classes` key behaves
    exactly as before (one candidate per pair, entity_class=None).
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
    class_key = tpl.get("entity_classes")
    members: List[Optional[str]] = ENTITY_CLASS_RESOLVERS[class_key]() if class_key else [None]
    out: List[Candidate] = []
    for a, b in pairs:
        if _blocked(a, b, tpl):
            continue
        for member in members:
            out.append(Candidate(
                candidate_id=_candidate_id(template_id, a, b, member),
                template_id=template_id, sport=sport, atomic_unit=tpl["atomic_unit"],
                outcome=tpl["outcome"], attr_a=a, attr_b=b,
                feature_builder=tpl["feature_builder"], hypothesis_source=hyp_source,
                entity_class=member,
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
    "ENTITY_CLASS_RESOLVERS", "resolve_pool", "enumerate_candidates", "tested_ids", "next_batch",
]
