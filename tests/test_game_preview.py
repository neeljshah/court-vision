"""Tests for src/intel/game_preview.py (+ its src/intel/matchup_report.py dep).

The game preview is a DESCRIPTIVE matchup assembler with a SEPARATE, clearly
labelled UNVALIDATED predictive-candidate surface. These tests verify:
  * game + roster resolution from games_lookup / season_games / prediction caches,
  * matchup-report assembly (team clash, scheme + player edges, key players),
  * the preview schema (top-5 edges, pace environment, keys-to-the-game),
  * and — load-bearing — that EVERY predictive candidate is flagged as an
    UNVALIDATED candidate, carries a gate spec, and is NOT applied to any model.

Synthetic-fixture tests are always runnable; real-data tests skip on a fresh
clone that lacks the atlas parquets / prediction caches.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.intel import game_preview as gp  # noqa: E402
from src.intel import matchup_report as mr  # noqa: E402
from src.intel import team_report as tr  # noqa: E402

_HAVE_REAL = (ROOT / "data" / "cache" / "atlas_team_offensive_scheme.parquet").exists()
_HAVE_LOOKUP = (ROOT / "data" / "cache" / "games_lookup.json").exists()


# ---------------------------------------------------------------------------
# Pure-helper tests (no data dependency)
# ---------------------------------------------------------------------------

def test_et_date_of_start_subtracts_to_eastern_evening():
    # 00:10 UTC tip == evening of the PREVIOUS calendar day in ET.
    assert gp._et_date_of_start("2026-05-31T00:10:00Z") == "2026-05-30"
    assert gp._et_date_of_start("2026-06-04T00:40:00Z") == "2026-06-03"


def test_et_date_of_start_handles_bad_input():
    assert gp._et_date_of_start("") is None
    assert gp._et_date_of_start("not-a-date") is None
    assert gp._et_date_of_start(None) is None


def test_stat_for_skill_mapping():
    assert gp._stat_for_skill("oreb_rate") == "reb"
    assert gp._stat_for_skill("catch_shoot_efg") == "fg3m"
    assert gp._stat_for_skill("ast_pts_created") == "ast"
    assert gp._stat_for_skill("unknown_metric") is None


def test_gate_spec_is_unvalidated_and_not_applied():
    g = gp._GATE_SPEC
    assert g["status"] == "UNVALIDATED_CANDIDATE"
    assert g["applied_to_model"] is False
    names = {gate["name"] for gate in g["required_gates"]}
    # the honest dual gate + shadow must all be present
    assert {"walk_forward", "single_split_production", "shadow"} <= names


# ---------------------------------------------------------------------------
# Synthetic-fixture tests (always runnable) — build a tiny 2-team atlas + roster
# ---------------------------------------------------------------------------

def _synthetic_atlases():
    """Two teams: AAA (strong, turnover-forcing) vs BBB (weak DREB, TO-prone)."""
    def osc(tri, pace, off, tov):
        return {
            "team_tricode": tri,
            "pace": json.dumps({"pace_pg": pace, "pace_identity":
                                "FAST" if pace > 100 else "SLOW"}),
            "shot_diet": json.dumps({"off_rtg": off, "efg_pct": 0.55,
                                     "ast_pct": 0.6, "tov_ratio": tov}),
            "tempo_spacing_cv": json.dumps({"team_transition_share_z": 0.6,
                                            "team_avg_spacing_z": 0.6}),
            "n": 245, "confidence": "high", "as_of": "2026-05-31",
        }

    def dsc(tri, drtg):
        return {
            "team_tricode": tri,
            "coverage_scheme": json.dumps({"dominant_tag": "DROP COVERAGE",
                                           "all_tags": ["DROP COVERAGE"]}),
            "scheme_axes": json.dumps({"drop_score": 0.4}),
            "ratings_context": json.dumps({"def_rtg": drtg}),
            "n": 245, "confidence": "high", "as_of": "2026-05-31",
        }

    def reb(tri, oreb, dreb):
        return {"team_tricode": tri, "oreb_pct_mean": oreb, "dreb_pct_mean": dreb,
                "reb_identity": "crash", "n": 245, "confidence": "high",
                "as_of": "2026-05-31"}

    def tof(tri, forced):
        return {"team_tricode": tri,
                "opp_tov": json.dumps({"opp_tov_pct_forced": forced}),
                "n": 245, "confidence": "high", "as_of": "2026-05-31"}

    # NOTE: team_report.build_league_context requires >=3 teams per metric to
    # rank, so include a neutral third team (CCC) in every section.
    return {
        "offensive_scheme": pd.DataFrame([osc("AAA", 102.0, 118.0, 11.0),
                                          osc("BBB", 101.0, 110.0, 16.0),
                                          osc("CCC", 99.0, 113.0, 13.0)]),
        "defensive_scheme": pd.DataFrame([dsc("AAA", 108.0), dsc("BBB", 116.0),
                                          dsc("CCC", 112.0)]),
        "rebounding_scheme": pd.DataFrame([reb("AAA", 0.30, 0.78),
                                           reb("BBB", 0.24, 0.70),
                                           reb("CCC", 0.27, 0.74)]),
        "turnover_forcing": pd.DataFrame([tof("AAA", 0.17), tof("BBB", 0.11),
                                          tof("CCC", 0.14)]),
    }


def test_matchup_report_structure_synthetic():
    atlases = _synthetic_atlases()
    ctx = tr.build_league_context(atlases)
    rep = mr.build_matchup_report("AAA", "BBB", team_ctx=ctx, atlases=atlases)
    assert rep["schema_version"] == mr.SCHEMA_VERSION
    assert rep["label"] == "BBB @ AAA"
    tc = rep["team_clash"]
    assert "pace_environment" in tc
    assert "rebounding_battle" in tc
    # AAA forces TOs & BBB is TO-prone -> a scheme edge AAA-attacks-BBB should fire
    tags = {(e["attacker"], e["tag"]) for e in rep["scheme_edges"]}
    assert ("AAA", "turnover_pressure") in tags
    # descriptive report carries NO predicted line / lift fields
    assert "predicted" not in json.dumps(rep).lower()


def test_scheme_edges_have_magnitude_and_provenance():
    atlases = _synthetic_atlases()
    ctx = tr.build_league_context(atlases)
    rep = mr.build_matchup_report("AAA", "BBB", team_ctx=ctx, atlases=atlases)
    assert rep["scheme_edges"], "expected at least one scheme edge"
    for e in rep["scheme_edges"]:
        assert "magnitude" in e and e["magnitude"] is not None
        assert "provenance" in e
        # edges are magnitude-sorted descending
    mags = [e["magnitude"] for e in rep["scheme_edges"]]
    assert mags == sorted(mags, reverse=True)


def test_game_preview_schema_synthetic():
    atlases = _synthetic_atlases()
    ctx = tr.build_league_context(atlases)
    # no rosters -> player edges empty, but the descriptive scheme surface builds
    p = gp.build_game_preview("AAA", "BBB", date_str="2026-05-30",
                              home_roster=[], away_roster=[],
                              team_ctx=ctx, atlases=atlases)
    assert p["schema_version"] == gp.SCHEMA_VERSION
    for key in ("matchup_report", "top_edges", "pace_environment",
                "keys_to_the_game", "predictive_candidates",
                "candidate_disclaimer", "completeness"):
        assert key in p, f"missing {key}"
    # top_edges is at most 5 and rank-stamped
    assert len(p["top_edges"]) <= 5
    for i, e in enumerate(p["top_edges"]):
        assert e["rank"] == i + 1
        assert e["edge_class"] in ("scheme", "player")
    # keys present for both teams
    assert set(p["keys_to_the_game"].keys()) == {"AAA", "BBB"}
    assert all(p["keys_to_the_game"][t] for t in ("AAA", "BBB"))
    # fully serializable
    json.dumps(p, default=str)


def test_every_candidate_is_unvalidated_and_gated():
    """Load-bearing honesty test: NO candidate may claim a validated lift."""
    atlases = _synthetic_atlases()
    ctx = tr.build_league_context(atlases)
    p = gp.build_game_preview("AAA", "BBB", date_str="2026-05-30",
                              home_roster=[], away_roster=[],
                              team_ctx=ctx, atlases=atlases)
    cands = p["predictive_candidates"]
    # a fast/slow pace OR a scheme lean should yield at least one candidate
    assert isinstance(cands, list)
    for c in cands:
        assert c["status"] == "UNVALIDATED_CANDIDATE"
        assert c["gate"]["applied_to_model"] is False
        names = {g["name"] for g in c["gate"]["required_gates"]}
        assert {"walk_forward", "single_split_production", "shadow"} <= names
    # disclaimer must explicitly say not applied + no claimed lift
    disc = p["candidate_disclaimer"].lower()
    assert "unvalidated" in disc
    assert "not applied" in disc
    assert "no" in disc and "lift" in disc


def test_pace_environment_classification():
    atlases = _synthetic_atlases()
    ctx = tr.build_league_context(atlases)
    p = gp.build_game_preview("AAA", "BBB", date_str="2026-05-30",
                              home_roster=[], away_roster=[],
                              team_ctx=ctx, atlases=atlases)
    pe = p["pace_environment"]
    assert pe["projected_pace"] is not None
    assert pe["pace_environment"] in ("fast", "average", "slow")
    # both teams ~101 pace -> midpoint ~101.5 boundary; assert it's a clean label
    assert "_note" in pe and "NOT a possession-model" in pe["_note"]


# ---------------------------------------------------------------------------
# Real-data tests (skipped on a fresh clone)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAVE_REAL, reason="atlas parquets not present")
def test_real_roster_resolution():
    # OKC should resolve a non-trivial roster from the prediction caches.
    okc = gp.resolve_roster("OKC")
    assert len(okc) >= 8
    assert all(isinstance(pid, int) for pid in okc)


@pytest.mark.skipif(not (_HAVE_REAL and _HAVE_LOOKUP),
                    reason="atlas/lookup not present")
def test_real_resolve_games_for_date():
    # The shipped games_lookup has an OKC/SAS game tipping 00:10Z on 2026-05-31
    # which maps to the 2026-05-30 ET slate.
    games = gp.resolve_games_for_date("2026-05-30")
    pairs = {(g["home"], g["away"]) for g in games}
    assert ("OKC", "SAS") in pairs


@pytest.mark.skipif(not _HAVE_REAL, reason="atlas parquets not present")
def test_real_full_preview_okc_sas():
    p = gp.build_game_preview("OKC", "SAS", date_str="2026-05-30")
    # descriptive surface populated
    assert p["matchup_report"]["completeness"]["rosters_supplied"] is True
    assert p["top_edges"], "expected ranked edges for a real matchup"
    assert p["pace_environment"]["projected_pace"] is not None
    # every candidate flagged for the gate
    for c in p["predictive_candidates"]:
        assert c["status"] == "UNVALIDATED_CANDIDATE"
        assert c["gate"]["applied_to_model"] is False
    # fully serializable (no numpy/NaN leakage)
    json.dumps(p, default=str)


@pytest.mark.skipif(not _HAVE_REAL, reason="atlas parquets not present")
def test_real_player_edges_reference_real_players():
    p = gp.build_game_preview("OKC", "SAS", date_str="2026-05-30")
    pedges = p["matchup_report"]["player_edges"]
    if pedges:  # roster-dependent; guard for data drift
        for e in pedges:
            assert e["player_name"]
            assert 0.0 <= e["opp_team_pctile"] <= 1.0
            assert e["player_percentile"] >= mr._STRONG_PCT
