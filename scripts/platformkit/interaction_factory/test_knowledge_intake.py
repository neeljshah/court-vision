"""Per-file test for scripts.platformkit.interaction_factory.knowledge_intake.

Covers: only a CONFIRMED_LOCAL hypothesis with a declared KNOWN_MAPPINGS entry
emits candidates; a NULL/NOT_TESTABLE verdict or an unmapped hypothesis emits
nothing (honest, not an error); emitted candidates carry
hypothesis_source='knowledge' and a candidate_id distinct from the same
attr-pair's blind id (no ledger collision if both ever run).

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/interaction_factory/test_knowledge_intake.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.interaction_factory import generator as GEN
from scripts.platformkit.interaction_factory import knowledge_intake as KI


def _write_ledger(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="ascii")


def test_confirmed_mapped_hypothesis_emits_candidates(tmp_path):
    mlb = tmp_path / "mlb_ledger.jsonl"
    nba = tmp_path / "nba_ledger.jsonl"
    _write_ledger(mlb, [{"hypothesis": "contact_quality_persists_split_half", "verdict": "CONFIRMED_LOCAL"}])
    _write_ledger(nba, [])
    cands = KI.knowledge_candidates({"mlb": mlb, "basketball_nba": nba})
    assert len(cands) == 2
    assert all(c.hypothesis_source == "knowledge" for c in cands)
    assert {c.attr_a for c in cands} == {"contact_quality"}
    assert {c.attr_b for c in cands} == {"whiff_rate", "platoon_split"}
    assert all(c.template_id == "mlb_pa_batter_x_pitcher" for c in cands)
    # deterministic id, distinct from the plain blind-enumeration id (no ledger collision).
    assert all(c.candidate_id.endswith("::src=knowledge") for c in cands)


def test_null_or_unmapped_hypothesis_emits_nothing(tmp_path):
    mlb = tmp_path / "mlb_ledger.jsonl"
    nba = tmp_path / "nba_ledger.jsonl"
    _write_ledger(mlb, [
        {"hypothesis": "contact_quality_persists_split_half", "verdict": "NULL_LOCAL"},  # not CONFIRMED
        {"hypothesis": "some_other_confirmed_thing", "verdict": "CONFIRMED_LOCAL"},       # no mapping declared
    ])
    _write_ledger(nba, [{"hypothesis": "b2b_rest_penalty", "verdict": "CONFIRMED_LOCAL"}])  # no mapping declared
    cands = KI.knowledge_candidates({"mlb": mlb, "basketball_nba": nba})
    assert cands == []


def test_mapped_attrs_are_real_registry_members():
    # KNOWN_MAPPINGS must only ever name attrs that actually resolve in the
    # target template's declared sport registry -- never invent one.
    for mappings in KI.KNOWN_MAPPINGS.values():
        for m in mappings:
            tpl = GEN.TEMPLATES[m["template_id"]]
            reg = GEN._registry(tpl["sport"])  # noqa: SLF001 -- registry integrity check
            assert m["attr_a"] in reg
            assert m["attr_b"] in reg


def test_fixwave_alpha_mlb_mappings_use_a_registered_builder(tmp_path):
    # edge_zone_widens_with_two_strikes / two_strike_chase_rate_rises /
    # first_pitch_strike_suppresses_bb (fix-wave-alpha, 2026-07-11) must map
    # onto mlb_pa_batter_x_pitcher (feature_builder mlb_pa_asof IS registered
    # in runner._BUILDERS) -- never mlb_pa_attr_x_count_state, whose builder
    # (mlb_pa_count_state_asof) is still unregistered and would silently
    # yield NOT_TESTABLE for every candidate.
    from scripts.platformkit.interaction_factory import runner as RUN
    for hyp in ("edge_zone_widens_with_two_strikes", "two_strike_chase_rate_rises",
                "first_pitch_strike_suppresses_bb"):
        mappings = KI.KNOWN_MAPPINGS[hyp]
        assert mappings, hyp
        for m in mappings:
            assert m["template_id"] == "mlb_pa_batter_x_pitcher"
            tpl = GEN.TEMPLATES[m["template_id"]]
            assert tpl["feature_builder"] in RUN._BUILDERS

    mlb = tmp_path / "mlb_ledger.jsonl"
    nba = tmp_path / "nba_ledger.jsonl"
    _write_ledger(mlb, [
        {"hypothesis": "edge_zone_widens_with_two_strikes", "verdict": "CONFIRMED_LOCAL"},
        {"hypothesis": "two_strike_chase_rate_rises", "verdict": "CONFIRMED_LOCAL"},
        {"hypothesis": "first_pitch_strike_suppresses_bb", "verdict": "CONFIRMED_LOCAL"},
    ])
    _write_ledger(nba, [])
    cands = KI.knowledge_candidates({"mlb": mlb, "basketball_nba": nba})
    assert len(cands) == 6  # 2 mapping rows x 3 hypotheses
    assert all(c.hypothesis_source == "knowledge" for c in cands)
    assert {"edge_zone_rate", "chase_rate", "first_pitch_strike_rate"} <= (
        {c.attr_a for c in cands} | {c.attr_b for c in cands})
