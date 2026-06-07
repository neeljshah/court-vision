"""Tests for src.intel.matchup_report — DESCRIPTIVE game matchup intelligence.

Covers the five spec deliverables:
  1. key individual matchups (offense player vs likely defender + projected edge)
  2. scheme vs scheme (directional edges)
  3. pace/style interaction (fast-vs-slow tempo battle + controller)
  4. strength-vs-weakness edges (player skill vs opposing team weakness)
  5. the deterministic "how this game projects to play" narrative
plus the HONESTY contract (descriptive only; no predicted line / claimed lift)
and roster auto-resolution.

Unit tests use controlled synthetic inputs (deterministic, fast, data-version
independent). Integration tests exercise real team dossiers but assert only
structural / sign properties that are stable across data refreshes.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("NBA_OFFLINE", "1")

from src.intel import matchup_report as mr  # noqa: E402


# --------------------------------------------------------------------------- #
# Synthetic dossier fixtures (shape mirrors player_report / team_report output)
# --------------------------------------------------------------------------- #
def _player(name, pid, position, archetype_label, tags,
            paint_share=None, three_share=None, drives=None,
            rim_rank=None, evt_rank=None, minutes=30.0):
    ranked = []
    if rim_rank is not None:
        ranked.append({"metric": "rim_protection", "percentile": rim_rank})
    if evt_rank is not None:
        ranked.append({"metric": "stl_block_rate", "percentile": evt_rank})
    return {
        "player_id": pid,
        "player_name": name,
        "archetype_role": {"data": {
            "position": position,
            "minutes_pg": minutes,
            "archetype": {"label": archetype_label, "tags": tags},
        }},
        "scoring": {"data": {
            "shot_distribution": {"pts_paint_share": paint_share,
                                  "pts_3pt_share": three_share},
            "creation": {"drives_per_game": drives},
        }},
        "defense": {"data": {"defensive_profile": {
            "rim_protection": {"blk_pg": None},
            "steal_block_rate": {"stl_pg": None},
        }}},
        "strengths_weaknesses": {"ranked": ranked, "strengths": []},
    }


def _team_dossier(tri, pace_identity, pace_pg, transition_z=0.0,
                  rim_pctile=0.5, three_pctile=0.5, dreb_pctile=0.5):
    """A minimal team dossier with the fields the matchup blocks read."""
    all_ranks = [
        {"metric": "paint_defense.rim_fg_pct_allowed", "label": "rim protection",
         "pctile": rim_pctile, "rank": 1, "n": 30},
        {"metric": "paint_defense.paint_fg_pct_allowed", "label": "paint defense",
         "pctile": rim_pctile, "rank": 1, "n": 30},
        {"metric": "three_pt_defense.opp_3p_pct_allowed", "label": "3pt% defense",
         "pctile": three_pctile, "rank": 1, "n": 30},
        {"metric": "rebounding_scheme.dreb_pct", "label": "defensive rebounding",
         "pctile": dreb_pctile, "rank": 1, "n": 30},
    ]
    return {
        "team_tricode": tri,
        "blocks": {
            "offensive_identity": {"data": {
                "pace_pg": pace_pg, "pace_identity": pace_identity,
                "transition_share_z": transition_z,
            }},
            "strengths_weaknesses": {"data": {"all_ranks": all_ranks,
                                              "strengths": [], "weaknesses": []}},
        },
        "completeness": {"coverage_pct": 100.0},
    }


# --------------------------------------------------------------------------- #
# (3) PACE / STYLE — fast vs slow flags a tempo battle
# --------------------------------------------------------------------------- #
def test_pace_battle_fast_vs_slow_flags_tempo_clash():
    fast = _team_dossier("FST", "FAST", 102.0)
    slow = _team_dossier("SLW", "SLOW", 96.5)
    out = mr._build_pace_battle(fast, slow, "FST", "SLW")
    assert out["tempo_battle"] is True
    assert out["tempo_controller"] == "contested"
    # narrative mentions running vs slowing it down
    assert "run" in out["note"] and "slow" in out["note"].lower()
    # projected possessions is the midpoint of the two paces
    assert out["projected_possessions_estimate"] == pytest.approx((102.0 + 96.5) / 2, abs=0.1)


def test_pace_battle_two_similar_teams_no_battle():
    a = _team_dossier("AAA", "MODERATE", 99.0)
    b = _team_dossier("BBB", "MODERATE", 99.4)
    out = mr._build_pace_battle(a, b, "AAA", "BBB")
    assert out["tempo_battle"] is False
    assert out["tempo_controller"] == "aligned"


def test_pace_battle_both_transition_heavy_note():
    a = _team_dossier("AAA", "FAST", 102.0, transition_z=0.8)
    b = _team_dossier("BBB", "FAST", 101.5, transition_z=0.9)
    out = mr._build_pace_battle(a, b, "AAA", "BBB")
    assert out["transition_note"] is not None
    assert "high-possession" in out["transition_note"]


# --------------------------------------------------------------------------- #
# (1) KEY INDIVIDUAL MATCHUPS — paint attacker vs weak/strong rim D
# --------------------------------------------------------------------------- #
def test_paint_heavy_player_vs_weak_paint_D_is_offense_edge():
    rim_attacker = _player("Paint Beast", 1, "Center", "Interior Scoring Big",
                           ["paint_scorer", "big", "high_usage"],
                           paint_share=0.62, drives=8)
    weak_paint_team = mr._team_def_context(_team_dossier("WPD", "MODERATE", 99,
                                                         rim_pctile=0.05))
    proj = mr._project_individual_edge(rim_attacker, None, weak_paint_team)
    assert proj["edge_score"] >= 1.0
    assert proj["edge_side"] == "offense"
    assert any("rim-attacker" in f and "advantage" in f for f in proj["factors"])


def test_paint_heavy_player_vs_elite_rim_D_is_defense_edge():
    rim_attacker = _player("Paint Beast", 1, "Center", "Interior Scoring Big",
                           ["paint_scorer", "big"], paint_share=0.62)
    strong_paint_team = mr._team_def_context(_team_dossier("SPD", "MODERATE", 99,
                                                           rim_pctile=0.95))
    proj = mr._project_individual_edge(rim_attacker, None, strong_paint_team)
    assert proj["edge_score"] <= -1.0
    assert proj["edge_side"] == "defense"


def test_shooter_vs_weak_3pt_D_is_offense_edge():
    shooter = _player("Sniper", 2, "Guard", "3&D Wing",
                      ["floor_spacer", "catch_and_shoot", "guard"], three_share=0.55)
    weak_three_team = mr._team_def_context(_team_dossier("W3D", "MODERATE", 99,
                                                        three_pctile=0.05))
    proj = mr._project_individual_edge(shooter, None, weak_three_team)
    assert proj["edge_score"] >= 1.0
    assert proj["edge_side"] == "offense"


def test_neutral_when_no_mismatch():
    role_guy = _player("Role Guy", 3, "Forward", "Role Player", [], minutes=18.0)
    avg_team = mr._team_def_context(_team_dossier("AVG", "MODERATE", 99,
                                                  rim_pctile=0.5, three_pctile=0.5))
    proj = mr._project_individual_edge(role_guy, None, avg_team)
    assert proj["edge_side"] == "neutral"
    assert proj["factors"] == ["no decisive scheme/skill mismatch identified"]


def test_likely_defender_pairs_by_position():
    guard = _player("Guard A", 10, "Guard", "Lead Guard", ["guard"])
    def_sigs = [
        mr._player_def_signature(_player("Opp Center", 20, "Center", "Big", ["big"])),
        mr._player_def_signature(_player("Opp Guard", 21, "Guard", "Guard", ["guard"])),
    ]
    defender = mr._pair_likely_defender(guard, def_sigs)
    assert defender is not None
    # nearest position to a guard should be the opposing guard, not the center
    assert defender["player_name"] == "Opp Guard"


# --------------------------------------------------------------------------- #
# _team_def_context derives the weak/strong flags correctly
# --------------------------------------------------------------------------- #
def test_team_def_context_flags_weak_dreb():
    ctx = mr._team_def_context(_team_dossier("X", "MODERATE", 99, dreb_pctile=0.10))
    assert ctx["dreb_weak"] is True
    ctx2 = mr._team_def_context(_team_dossier("Y", "MODERATE", 99, dreb_pctile=0.80))
    assert ctx2["dreb_weak"] is False


# --------------------------------------------------------------------------- #
# Integration tests — real dossiers, stable structural assertions only
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def shared_ctx():
    from src.intel import team_report as tr
    atlases = tr.load_team_atlases()
    if not atlases:
        pytest.skip("team atlases not available in this environment")
    return atlases, tr.build_league_context(atlases)


def test_full_report_has_all_spec_sections(shared_ctx):
    atlases, ctx = shared_ctx
    rep = mr.build_matchup_report("OKC", "SAS", atlases=atlases, team_ctx=ctx)
    for key in ("key_individual_matchups", "scheme_edges", "pace_style",
                "player_edges", "game_projection", "team_clash"):
        assert key in rep, f"missing section {key}"
    assert isinstance(rep["key_individual_matchups"], list)
    assert isinstance(rep["game_projection"], str) and len(rep["game_projection"]) > 0


def test_real_fast_vs_slow_flags_tempo_battle(shared_ctx):
    # ATL plays FAST, MIA plays SLOW in the current data -> tempo battle.
    atlases, ctx = shared_ctx
    rep = mr.build_matchup_report("ATL", "MIA", atlases=atlases, team_ctx=ctx)
    ps = rep["pace_style"]
    ids = {ps["home"]["pace_identity"], ps["away"]["pace_identity"]}
    if "FAST" in ids and "SLOW" in ids:
        assert ps["tempo_battle"] is True
        assert ps["tempo_controller"] == "contested"
    else:
        pytest.skip(f"ATL/MIA pace identities shifted in data: {ids}")


def test_individual_matchups_sorted_by_abs_edge(shared_ctx):
    atlases, ctx = shared_ctx
    rep = mr.build_matchup_report("OKC", "SAS", atlases=atlases, team_ctx=ctx)
    scores = [abs(m["edge_score"]) for m in rep["key_individual_matchups"]]
    assert scores == sorted(scores, reverse=True)
    for m in rep["key_individual_matchups"]:
        assert -3.0 <= m["edge_score"] <= 3.0
        assert m["edge_side"] in ("offense", "defense", "neutral")
        assert m["offense_player"]["team"] in ("OKC", "SAS")
        assert m["vs_team"] in ("OKC", "SAS")


def test_rosters_auto_resolved_when_not_supplied(shared_ctx):
    atlases, ctx = shared_ctx
    rep = mr.build_matchup_report("OKC", "SAS", atlases=atlases, team_ctx=ctx)
    comp = rep["completeness"]
    # either auto-resolved (gamelog/cache present) or honestly flagged as not
    assert "rosters_auto_resolved" in comp
    if comp["rosters_auto_resolved"]:
        assert comp["n_home_players"] > 0


# --------------------------------------------------------------------------- #
# HONESTY contract — descriptive only, no shipped predicted line / claimed lift
# --------------------------------------------------------------------------- #
def test_report_carries_no_predicted_line_or_lift(shared_ctx):
    atlases, ctx = shared_ctx
    rep = mr.build_matchup_report("OKC", "SAS", atlases=atlases, team_ctx=ctx)
    # the descriptive report must NOT silently ship a prediction/accuracy claim
    for banned in ("predicted_pts", "projection_value", "accuracy_lift",
                   "roi", "expected_value", "bet"):
        assert banned not in rep
    # the narrative must self-label as descriptive, not a validated bet
    assert "DESCRIPTIVE" in rep["game_projection"]
    assert "not a validated bet" in rep["game_projection"]


def test_predictive_candidates_are_gated_in_game_preview(shared_ctx):
    # any quantitative predictive lean lives in game_preview, flagged for the gate
    from src.intel import game_preview as gp
    atlases, ctx = shared_ctx
    prev = gp.build_game_preview("OKC", "SAS", atlases=atlases, team_ctx=ctx)
    assert "predictive_candidates" in prev
    for c in prev["predictive_candidates"]:
        assert c["status"] == "UNVALIDATED_CANDIDATE"
        assert c["gate"]["applied_to_model"] is False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
