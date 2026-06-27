"""Per-file test: fusion_families -- spec honesty, id stability, allowlist enforcement."""
from __future__ import annotations

import pytest

from scripts.platformkit.improve.fusion.fusion_families import (
    FAMILIES, FusionSpec, all_fusion_specs, validate_spec,
)


def test_every_spec_validates_and_is_calibration_only():
    specs = all_fusion_specs("nba", "win_prob")
    assert specs, "proven bases should produce a non-empty fusion surface"
    for s in specs:
        assert validate_spec(s) is s
        assert s.vs_close == "UNPROVEN"
        assert "$" not in s.signature and "roi" not in s.signature.lower()
        assert s.family in FAMILIES


def test_same_idea_same_id_distinct_config_distinct_id():
    a = FusionSpec("FAMILY_STACK_OOF", "nba", "win_prob",
                   "stack_oof=bases:ingame_prior|meta:ridge", {"bases": "ingame_prior"})
    b = FusionSpec("FAMILY_STACK_OOF", "nba", "win_prob",
                   "stack_oof=bases:ingame_prior|meta:ridge", {"bases": "ingame_prior"})
    c = FusionSpec("FAMILY_STACK_OOF", "nba", "win_prob",
                   "stack_oof=bases:ingame_prior|meta:nnls", {"bases": "ingame_prior"})
    assert a.fusion_id == b.fusion_id      # same idea -> same id
    assert a.fusion_id != c.fusion_id      # distinct config -> distinct id


def test_base_outside_static_allowlist_rejected():
    bad = FusionSpec("FAMILY_STACK_OOF", "nba", "win_prob",
                     "stack_oof=bases:made_up|meta:ridge", {"bases": "made_up"})
    with pytest.raises(ValueError):
        validate_spec(bad)


def test_dollar_token_rejected():
    bad = FusionSpec("FAMILY_RESID_BOOST", "nba", "win_prob",
                     "resid_boost=base:ingame_prior|learner:roi", {"bases": "ingame_prior"})
    with pytest.raises(ValueError):
        validate_spec(bad)


def test_empty_base_list_yields_no_specs():
    assert all_fusion_specs("nba", "win_prob", bases=()) == []
    assert all_fusion_specs("nba", "win_prob", bases=("not_proven",)) == []


def test_all_four_families_present_and_ids_unique():
    specs = all_fusion_specs("nba", "win_prob")
    fams = {s.family for s in specs}
    assert fams == set(FAMILIES)
    ids = [s.fusion_id for s in specs]
    assert len(ids) == len(set(ids)), "spec ids must be unique"
