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
    # 2 mapping rows x 3 hypotheses, PLUS composed_candidates' chase_rate (batter)
    # x {edge_zone_rate, first_pitch_strike_rate} (pitcher) = 6 + 2 = 8.
    assert len(cands) == 8
    assert all(c.hypothesis_source == "knowledge" for c in cands)
    assert {"edge_zone_rate", "chase_rate", "first_pitch_strike_rate"} <= (
        {c.attr_a for c in cands} | {c.attr_b for c in cands})


def test_composed_candidates_cross_confirmed_batter_x_confirmed_pitcher_attrs(tmp_path):
    mlb = tmp_path / "mlb_ledger.jsonl"
    nba = tmp_path / "nba_ledger.jsonl"
    _write_ledger(mlb, [
        {"hypothesis": "contact_quality_persists_split_half", "verdict": "CONFIRMED_LOCAL"},
        {"hypothesis": "two_strike_chase_rate_rises", "verdict": "CONFIRMED_LOCAL"},
        {"hypothesis": "edge_zone_widens_with_two_strikes", "verdict": "CONFIRMED_LOCAL"},
        {"hypothesis": "spin_rate_deception", "verdict": "CONFIRMED_LOCAL"},
    ])
    _write_ledger(nba, [])
    cands = KI.composed_candidates({"mlb": mlb, "basketball_nba": nba})
    # 2 batter mechanism attrs (contact_quality, chase_rate) x 2 pitcher
    # mechanism attrs (edge_zone_rate, release_spin_rate) = 4 pairs.
    assert len(cands) == 4
    got = {(c.attr_a, c.attr_b) for c in cands}
    assert got == {
        ("contact_quality", "edge_zone_rate"), ("contact_quality", "release_spin_rate"),
        ("chase_rate", "edge_zone_rate"), ("chase_rate", "release_spin_rate"),
    }
    assert all(c.hypothesis_source == "knowledge" for c in cands)
    assert all(c.template_id == "mlb_pa_batter_x_pitcher" for c in cands)
    # never composes an attr with itself/its own entity side (no batter x batter).
    assert all(a != b for a, b in got)


def test_composed_candidates_needs_both_sides_confirmed(tmp_path):
    mlb = tmp_path / "mlb_ledger.jsonl"
    nba = tmp_path / "nba_ledger.jsonl"
    # only a batter-side mechanism confirmed -- no pitcher-side partner -> nothing to compose.
    _write_ledger(mlb, [{"hypothesis": "contact_quality_persists_split_half", "verdict": "CONFIRMED_LOCAL"}])
    _write_ledger(nba, [])
    assert KI.composed_candidates({"mlb": mlb, "basketball_nba": nba}) == []


def test_mechanism_attr_names_are_real_registry_members():
    # MECHANISM_ATTR must only ever name attrs that resolve in the MLB registry
    # -- never invent one (same discipline as KNOWN_MAPPINGS).
    reg = GEN._registry("mlb")  # noqa: SLF001 -- registry integrity check
    for hyp, m in KI.MECHANISM_ATTR.items():
        assert m["attr"] in reg, hyp
        assert reg[m["attr"]]["entity"] == m["entity"], hyp


def test_ingame_state_template_stays_unmapped_pending_registry_wiring():
    # M10 pool-unlock lane (this session): nba_ingame_state_self_cross now
    # exists in the grammar (generator.py) but KNOWN_MAPPINGS must not
    # reference it until a real attr lands with family="ingame_state_asof"
    # (never invent one, same discipline as every other row here). This is
    # the honest before/after of the session's pool probe for the 4
    # historic "in-match" exemplar hypotheses: still 0 mapped, 0 candidates.
    assert "nba_ingame_state_self_cross" not in {
        m["template_id"] for mappings in KI.KNOWN_MAPPINGS.values() for m in mappings}
    for hyp in ("q1_slow_start_persists_split_half", "transition_rate_split_half_persistence",
                "transition_rate_margin_relation", "called_strike_dispersion_exceeds_binomial_noise"):
        assert hyp not in KI.KNOWN_MAPPINGS
