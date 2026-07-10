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
    # target template's declared pool -- never invent one. Two pool shapes:
    # registry-backed (basketball_nba/mlb, _registry(sport)) and static_pool
    # (tennis/soccer, GEN.STATIC_POOLS -- neither sport has a _registry()).
    for mappings in KI.KNOWN_MAPPINGS.values():
        for m in mappings:
            tpl = GEN.TEMPLATES[m["template_id"]]
            pool_spec = tpl["left_pool"]
            if "static_pool" in pool_spec:
                pool = set(GEN.STATIC_POOLS[pool_spec["static_pool"]])
                assert m["attr_a"] in pool
                assert m["attr_b"] in pool
            else:
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


def test_round1_3_2026_07_10_new_confirmed_mechanisms_stay_unmapped():
    # Tonight's first 3 research rounds (round-1 seed/wave-2/wave-3) added 13
    # new CONFIRMED_LOCAL hypotheses across the 4 real ledgers (wave-4's seed
    # yielded zero CONFIRMED). Fresh premise check, same discipline as
    # 39727abe: see the ROUND 1-3 CLASSIFICATION comment above KNOWN_MAPPINGS
    # for the per-hypothesis blocker. This locks in both halves of that claim
    # for the ones still unmapped: (1) each hypothesis really is
    # CONFIRMED_LOCAL on disk right now, not a stale premise, and (2) none of
    # them leaked into KNOWN_MAPPINGS.
    # UNLOCK LANE (2026-07-10, this session): boxdetail_ast_persistence_and_
    # margin (NBA) and dominance_margin_predicts_outcome_partial (tennis) are
    # now MAPPED (their STATIC_POOLS/template blockers closed this session)
    # -- removed from this unmapped list, asserted mapped separately below.
    new_confirmed = {
        "basketball_nba": [
            "defender_matchup_skill_predictive_validity",
            "starter_minutes_vs_margin__combined", "timeout_interrupts_opponent_run__combined",
        ],
        "mlb": [
            "compassionate_umpire_count_zone__combined", "mid_inning_pitching_change_interrupt__combined",
            "pinch_sub_platoon_targeting__combined",
        ],
        "soccer": [
            "block_depth_counterattack_share", "xg_rebound_cluster_calibration",
            "xg_supremacy_persistence", "substitution_timing_moderates_shift",
        ],
        "tennis": ["ball_cycle_serve_speed_kmh"],
    }
    for sport, hyps in new_confirmed.items():
        rows = KI._load_ledger(KI.LEDGERS[sport])
        confirmed = {r.get("hypothesis") for r in rows if r.get("verdict") == "CONFIRMED_LOCAL"}
        for h in hyps:
            assert h in confirmed, "%s/%s not CONFIRMED_LOCAL on disk -- classification is stale" % (sport, h)
            assert h not in KI.KNOWN_MAPPINGS, "%s/%s must stay unmapped -- named blocker not resolved" % (sport, h)
    # xg_supremacy_persistence (soccer, asserted CONFIRMED_LOCAL + unmapped
    # above) stays unmapped DELIBERATELY -- its STATIC_POOLS blocker is
    # closed (see the STATIC_POOLS assertion below), but its predictive-value
    # question is already a closed REJECT in data/frontend/reject_ledger.jsonl
    # (see the KNOWN_MAPPINGS comment on this hypothesis).

    # concretely verify the 3 named blockers instead of just asserting
    # absence-from-KNOWN_MAPPINGS (a real runnable check, not just enumeration).
    # UNLOCK LANE (2026-07-10, this session): all 3 named f94a0373 blockers
    # now RESOLVED. (1) NBA ast_asof: a real leak-free as-of assist-rate
    # column exists (asof_features.parquet's ast_rate_asof, registry family
    # "assist_asof") and now has its own cross template (nba_assist_x_
    # boxdetail_cross, generator.py) -- mapped below (builder registration in
    # runner._BUILDERS is separate, out-of-OWNS follow-on work). (2) tennis
    # avg_games_per_set_asof_diff (asof_setdetail.parquet) and (3) soccer
    # diff_xg_supremacy_asof (asof_xg_proxy.parquet) are now IN their
    # STATIC_POOLS (builders_task39b.py joins the extra parquet this session).
    assert "ast_rate_asof" in GEN._registry("basketball_nba")  # noqa: SLF001
    assert "avg_games_per_set_asof_diff" in GEN.STATIC_POOLS["tennis_match_asof"]
    assert "diff_xg_supremacy_asof" in GEN.STATIC_POOLS["soccer_match_asof"]
    assert "boxdetail_ast_persistence_and_margin" in KI.KNOWN_MAPPINGS
    assert "dominance_margin_predicts_outcome_partial" in KI.KNOWN_MAPPINGS

    # pool count proof: real ledgers, 16 before this session -> 20 after
    # (2 boxdetail_ast_persistence_and_margin rows + 2 dominance_margin_
    # predicts_outcome_partial rows, both real CONFIRMED_LOCAL on disk).
    cands = KI.knowledge_candidates()
    assert len(cands) == 20
    assert {c.sport for c in cands} == {"mlb", "basketball_nba", "tennis"}


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
