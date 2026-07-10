"""Per-file test for scripts.platformkit.interaction_factory.generator.

Covers: deterministic enumeration, closed-class blocklist (attr + pair),
registry validation (a bogus attr is dropped, never invented), and dedupe vs
the ledger (a tested candidate is never re-offered).

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/interaction_factory/test_generator.py -q
"""
from __future__ import annotations

import itertools

from scripts.platformkit.interaction_factory import generator as GEN

_NBA = "nba_shot_offense_x_offense"


def test_enumeration_is_deterministic_and_typed():
    a = GEN.enumerate_candidates(_NBA)
    b = GEN.enumerate_candidates(_NBA)
    assert [c.candidate_id for c in a] == [c.candidate_id for c in b]  # seedless, stable
    # self_cross over an 8-attr pool -> C(8,2)=28 unordered pairs.
    assert len(a) == 28
    assert all(c.attr_a < c.attr_b for c in a)  # i<j ordering
    assert all(c.sport == "basketball_nba" and c.atomic_unit == "player_game" for c in a)


def test_registry_validation_drops_bogus_attr(monkeypatch):
    # A typo'd pool attr must not survive resolve_pool (never invented).
    pool = GEN.resolve_pool("basketball_nba", {"attributes": ["zone_efg_rim", "not_a_real_attr"]})
    assert pool == ["zone_efg_rim"]


def test_blocklist_excludes_closed_class_attr_and_pair():
    # Global closed class: velo_decline_in_game (SP-fatigue) is refused anywhere.
    tpl = {"blocklist_attrs": [], "blocklist_pairs": []}
    assert GEN._blocked("velo_decline_in_game", "K_avoidance", tpl) is True
    # endQ1 x floor_quality closed interaction pair is refused as an unordered pair.
    assert GEN._blocked("floor_quality", "endQ1", tpl) is True
    # per-template blocklist honored too.
    tpl2 = {"blocklist_attrs": ["zone_efg_rim"], "blocklist_pairs": [["zone_efg_mid", "zone_efg_paint"]]}
    assert GEN._blocked("zone_efg_rim", "zone_efg_paint", tpl2) is True
    assert GEN._blocked("zone_efg_paint", "zone_efg_mid", tpl2) is True
    assert GEN._blocked("zone_efg_paint", "zone_efg_corner3", tpl2) is False


def test_blocklisted_attr_absent_from_real_enumeration():
    cands = GEN.enumerate_candidates("mlb_pa_attr_x_count_state")
    assert all("velo_decline_in_game" not in (c.attr_a, c.attr_b) for c in cands)


def test_next_batch_dedupes_vs_ledger_and_caps_k():
    full = GEN.enumerate_candidates(_NBA)
    first_id = full[0].candidate_id
    ledger = [{"template_id": _NBA, "candidate_id": first_id, "verdict": "NULL"}]
    batch = GEN.next_batch(_NBA, 5, ledger)
    assert len(batch) == 5
    assert first_id not in {c.candidate_id for c in batch}  # tested -> skipped


def test_not_testable_reenumerates_once_builder_lands():
    # A candidate graded NOT_TESTABLE (builder didn't exist yet / data was
    # unavailable) is NOT a terminal verdict -- it must re-offer once its
    # builder is registered, or it is skipped forever (the bug this guards).
    full = GEN.enumerate_candidates(_NBA)
    first_id = full[0].candidate_id
    ledger = [{"template_id": _NBA, "candidate_id": first_id, "verdict": "NOT_TESTABLE"}]
    assert first_id not in GEN.tested_ids(ledger, _NBA)
    batch = GEN.next_batch(_NBA, 5, ledger)
    assert first_id in {c.candidate_id for c in batch}


def test_terminal_verdicts_stay_deduped_forever():
    # Closed-class discipline: every non-NOT_TESTABLE verdict this ledger
    # actually writes (runner.py + replicate_*.py) must remain terminal.
    full = GEN.enumerate_candidates(_NBA)
    first_id = full[0].candidate_id
    terminal = [
        "NULL", "REJECT", "KILLED", "SHIP", "SURVIVES_PREREG_PROVISIONAL",
        "REPLICATED", "FAILED_REPLICATION_POWER_ANNOTATED", "REPLICATION_BLOCKED",
    ]
    for verdict in terminal:
        ledger = [{"template_id": _NBA, "candidate_id": first_id, "verdict": verdict}]
        assert first_id in GEN.tested_ids(ledger, _NBA), verdict


def test_cross_pairing_mlb_is_ordered_product():
    cands = GEN.enumerate_candidates("mlb_pa_batter_x_pitcher")
    # left {K_avoidance,BB_rate} x right {platoon_split,whiff_rate} = 4 ordered pairs.
    assert len(cands) == 4
    lefts = {c.attr_a for c in cands}
    assert lefts == {"K_avoidance", "BB_rate"}


def test_hypothesis_source_defaults_to_blind_and_is_overridable():
    # No template declares hypothesis_source -> every candidate defaults 'blind'
    # (additive field; measures knowledge-sourced vs blind survivor rates later).
    cands = GEN.enumerate_candidates(_NBA)
    assert cands and all(c.hypothesis_source == "blind" for c in cands)
    # A template that DOES declare it propagates to every candidate it enumerates.
    tpl_backup = dict(GEN.TEMPLATES[_NBA])
    GEN.TEMPLATES[_NBA]["hypothesis_source"] = "knowledge"
    try:
        cands2 = GEN.enumerate_candidates(_NBA)
        assert all(c.hypothesis_source == "knowledge" for c in cands2)
    finally:
        GEN.TEMPLATES[_NBA] = tpl_backup


def test_leaderboard_attrs_resolve_via_entity_pool():
    # registry-resolution check (not a template membership check -- no MLB
    # template names these attrs yet, see build report): an entity-wildcard
    # pool spec picks up the new leaderboard attrs the moment they enter the
    # registry, same "writes more on its own" property resolve_pool documents.
    batters = GEN.resolve_pool("mlb", {"entity": "batter"})
    assert {"swing_speed", "squared_up_rate", "blast_rate", "sword_rate"} <= set(batters)
    fielders = GEN.resolve_pool("mlb", {"entity": "fielder"})
    assert {"range_oaa", "difficult_play_conversion"} <= set(fielders)


def test_static_pool_serves_tennis_soccer_without_a_registry():
    # task-39b: tennis/soccer have no per-sport ATTRIBUTES registry wired into
    # this factory -- static_pool bypasses _registry(sport) entirely.
    tennis = GEN.resolve_pool("tennis", {"static_pool": "tennis_match_asof"})
    assert tennis == sorted(GEN.STATIC_POOLS["tennis_match_asof"])
    soccer = GEN.resolve_pool("soccer", {"static_pool": "soccer_match_asof"})
    assert soccer == sorted(GEN.STATIC_POOLS["soccer_match_asof"])
    # exclude seam still honored on a static pool.
    trimmed = GEN.resolve_pool("soccer", {"static_pool": "soccer_match_asof", "exclude": ["diff_shots_for_asof"]})
    assert "diff_shots_for_asof" not in trimmed


def test_tennis_soccer_templates_enumerate():
    # unlock lane (2026-07-10): avg_games_per_set_asof_diff / diff_xg_
    # supremacy_asof joined into STATIC_POOLS (builders_task39b.py) ->
    # 8-attr self-cross -> C(8,2)=28; 5-attr self-cross -> C(5,2)=10.
    tennis = GEN.enumerate_candidates("tennis_match_asof_self_cross")
    assert len(tennis) == 28
    assert all(c.sport == "tennis" for c in tennis)
    soccer = GEN.enumerate_candidates("soccer_match_asof_self_cross")
    assert len(soccer) == 10
    assert all(c.sport == "soccer" for c in soccer)


def test_archetype_wildcard_now_has_a_real_builder_declared():
    # mlb_pa_attr_x_archetype's feature_builder key exists (runner registers
    # it) -- generator itself doesn't import runner, just checks the name.
    assert GEN.TEMPLATES["mlb_pa_attr_x_archetype"]["feature_builder"] == "mlb_pa_archetype_asof"


def test_ingame_state_template_pool_now_wired():
    # nba_ingame_state_self_cross (M10 pool-unlock lane): the auto-discovery
    # seam (same as box_detail_asof/carryover_asof) is now REAL-wired --
    # attribute_registry.py's _INGAME_STATE_SPECS tags 5 quarter-shape asof
    # attrs family="ingame_state_asof" -> C(5,2)=10 self-cross pairs, no
    # longer the empty-pool state this test previously asserted.
    assert GEN.TEMPLATES["nba_ingame_state_self_cross"]["atomic_unit"] == "team_game_ingame_state"
    cands = GEN.enumerate_candidates("nba_ingame_state_self_cross")
    assert len(cands) == 10
    assert all(c.sport == "basketball_nba" and c.atomic_unit == "team_game_ingame_state" for c in cands)
    pool_attrs = {a for c in cands for a in (c.attr_a, c.attr_b)}
    assert pool_attrs == {
        "q1_margin_asof", "first_half_margin_asof", "second_half_margin_asof",
        "q4_margin_asof", "quarter_volatility_asof",
    }
