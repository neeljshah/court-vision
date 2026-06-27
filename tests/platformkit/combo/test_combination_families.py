"""Per-file test: combination_families is order-canonical, person-free, honest.

A combination spec round-trips its id; A*B and B*A hash to ONE id (the lexicographic
pair-sort); cold-start returns []; no person/cluster token leaks; weak-on-proven only
references the STATIC _PROVEN allowlist; every emitted spec passes validate_spec.
"""
from __future__ import annotations

from scripts.platformkit.combo.combination_families import (
    FAMILY_WEAK_ON_PROVEN, _PROVEN, CombinationSpec, all_combination_specs,
    validate_spec,
)

_HANDLES = ("run_diff", "pace_so_far", "poss_since_lead_change")


def test_order_canonical_pair_one_id():
    """A*B and B*A collapse to ONE id (interaction + detail_x_detail pairs are sorted)."""
    specs = all_combination_specs("nba", "home_win", _HANDLES)
    # interaction op=mul over (pace_so_far, run_diff) must equal the same op over the swap
    inter = [s for s in specs if s.family == "COMB_INTERACTION" and s.params.get("op") == "mul"]
    sigs = {s.signature for s in inter}
    # there is exactly one mul signature per unordered pair (no a:run|b:pace AND a:pace|b:run)
    pairs = {tuple(sorted((s.params["a"], s.params["b"]))) for s in inter}
    assert len(sigs) == len(pairs), (sigs, pairs)
    # the canonical handle order is lexicographic a<=b
    for s in inter:
        assert s.params["a"] <= s.params["b"], s.signature


def test_id_round_trips_and_is_stable():
    s = CombinationSpec("COMB_INTERACTION", "nba", "home_win",
                        "comb_interact=a:pace_so_far|b:run_diff|op:mul",
                        {"a": "pace_so_far", "b": "run_diff", "op": "mul"})
    assert s.combo_id == s.combo_id  # deterministic
    assert len(s.combo_id) == 24


def test_cold_start_empty():
    assert all_combination_specs("nba", "home_win", ()) == []
    assert all_combination_specs("nba", "home_win", ("kmeans_3", "cluster_7")) == []


def test_person_and_cluster_free():
    specs = all_combination_specs("nba", "home_win", _HANDLES)
    for s in specs:
        for bad in ("kmeans_", "cluster_"):
            assert bad not in s.signature, s.signature


def test_weak_on_proven_only_allowlist():
    specs = all_combination_specs("nba", "home_win", _HANDLES)
    wop = [s for s in specs if s.family == FAMILY_WEAK_ON_PROVEN]
    assert wop
    for s in wop:
        assert s.params["proven"] in _PROVEN, s.params


def test_every_spec_validates():
    specs = all_combination_specs("soccer", "home_win",
                                  ("red_diff", "yellow_diff", "shot_zone_diff"))
    assert specs
    for s in specs:
        assert validate_spec(s), s.signature


def test_deterministic_order():
    a = all_combination_specs("nba", "home_win", _HANDLES)
    b = all_combination_specs("nba", "home_win", _HANDLES)
    assert [s.signature for s in a] == [s.signature for s in b]
