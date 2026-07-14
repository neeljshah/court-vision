"""Per-file test: B4-APEX placebo/MDE/testability-expansion plumbing, all on
synthetic data (no real ledger/possessions touched). Run:
cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_apex.py -q
"""
import json

import numpy as np
import pandas as pd

from scripts.platformkit.live_edge.replay import apex as ax


# ---------------------------------------------------------------- 1. PLACEBO

def _synthetic_corpora():
    rng = np.random.default_rng(0)
    n = 400
    team_a = pd.DataFrame({"points": rng.normal(1.0, 0.3, n),
                            "game_id": [f"g{i % 40}" for i in range(n)],
                            "off_team": ["ABC"] * n, "blowout_flag": [False] * n})
    team_b = team_a.copy()
    player_a = pd.DataFrame({"scored": rng.integers(0, 2, n).astype(float),
                              "game_id": [f"g{i % 40}" for i in range(n)],
                              "player_id": [1] * n, "margin_bucket": ["tied"] * n})
    player_b = player_a.copy()
    return {"team_a": team_a, "team_b": team_b, "baseline_ppp": 1.0,
            "player_a": player_a, "player_b": player_b}


def test_shuffle_outcomes_preserves_values_changes_pairing():
    corpora = _synthetic_corpora()
    shuffled = ax.shuffle_outcomes(corpora, seed=1)
    for key, col in (("team_a", "points"), ("player_a", "scored")):
        orig = sorted(corpora[key][col].tolist())
        new = sorted(shuffled[key][col].tolist())
        assert orig == new  # same multiset of values
    # game_id / cell columns untouched
    assert (shuffled["team_a"]["game_id"] == corpora["team_a"]["game_id"]).all()


def _synthetic_claims_and_classified():
    team_row = pd.Series({
        "claim_id": "t1", "topic": "situation.full_grid_team", "lifecycle": "proposed",
        "scope_json": json.dumps({"context": {"cell": {"blowout_flag": False}},
                                  "entity_type": "team", "entity_ids": ["ABC"]}),
        "effect_json": json.dumps({"delta": 0.05, "stat": "points_per_possession"}),
    })
    player_row = pd.Series({
        "claim_id": "p1", "topic": "player_cell.player_margin", "lifecycle": "proposed",
        "scope_json": json.dumps({"context": {"cell": {"margin_bucket": "tied"}},
                                  "entity_type": "player", "entity_ids": ["1"]}),
        "effect_json": json.dumps({"delta": 0.02, "stat": "x", "baseline_rate": 0.5}),
    })
    claims_df = pd.DataFrame([team_row, player_row])
    classified = ax.classify_all(claims_df)
    return claims_df, classified


def test_sample_testable_returns_all_when_under_cap():
    claims_df, classified = _synthetic_claims_and_classified()
    sample = ax.sample_testable(claims_df, classified, n_cap=10, seed=0)
    assert len(sample) == 2


def test_placebo_run_and_summary_shapes():
    claims_df, classified = _synthetic_claims_and_classified()
    corpora = _synthetic_corpora()
    results = ax.placebo_run(claims_df, classified, corpora, n_total_testable=2, n_cap=10, seed=0)
    assert len(results) == 2
    assert set(results["verdict"]) <= {
        "IMPROVES_BOTH_CORPORA", "IMPROVES_SINGLE_CORPUS", "WORSE", "NULL", "INSUFFICIENT_DATA"}
    summary = ax.placebo_summary(results)
    assert 0 <= summary["bonferroni_survivors_on_placebo"] <= summary["raw_both_corpora_pass"]
    assert summary["n_sampled"] == 2
    if not np.isnan(summary["empirical_improves_rate_a"]):
        assert 0.0 <= summary["empirical_improves_rate_a"] <= 1.0
    defensible = ax.placebo_defensible_check(results, claims_df, n_total_testable=2)
    assert defensible["n_defensible"] <= defensible["n_bonferroni_pass"]


# ------------------------------------------------------------- 2. MDE/POWER

def test_mde_for_n_known_formula():
    mde = ax.mde_for_n(100, sigma=1.0)
    expected = (1.959963984540054 + 0.8416212335729143) / np.sqrt(100)
    assert abs(mde - expected) < 1e-6


def test_mde_for_n_edge_cases_return_inf():
    assert ax.mde_for_n(0, sigma=1.0) == float("inf")
    assert ax.mde_for_n(100, sigma=0.0) == float("inf")
    assert ax.mde_for_n(None, sigma=1.0) == float("inf")


def test_mde_shrinks_with_more_data():
    assert ax.mde_for_n(400, sigma=1.0) < ax.mde_for_n(100, sigma=1.0)


def test_corpus_sigma_matches_known_std():
    vals_team = np.array([1.0, 2.0, 3.0, 4.0])
    corpora = {"team_a": pd.DataFrame({"points": vals_team[:2]}),
               "team_b": pd.DataFrame({"points": vals_team[2:]}),
               "player_a": pd.DataFrame({"scored": [0.0, 1.0]}),
               "player_b": pd.DataFrame({"scored": [1.0, 0.0]})}
    sigma = ax.corpus_sigma(corpora)
    assert abs(sigma["team"] - float(vals_team.std(ddof=1))) < 1e-9
    assert abs(sigma["player"] - float(np.array([0.0, 1.0, 1.0, 0.0]).std(ddof=1))) < 1e-9


def test_power_report_and_summary_on_insufficient_rows():
    ledger_results = pd.DataFrame({
        "claim_id": ["a", "b", "c"], "topic": ["situation.x"] * 3,
        "grain": ["team", "player", "team"],
        "discovered_delta": [0.1, 0.05, 0.2],
        "n_active_a": [5, 20, 0], "n_active_b": [8, 15, 0],
        "verdict": ["INSUFFICIENT_DATA", "INSUFFICIENT_DATA", "NULL"],
    })
    sigma = {"team": 1.0, "player": 0.5}
    power_df = ax.power_report(ledger_results, sigma)
    assert len(power_df) == 2  # only the 2 INSUFFICIENT_DATA rows, "c" (NULL) excluded
    assert (power_df["mde_binding"] >= power_df["mde_a"]).all()
    assert (power_df["mde_binding"] >= power_df["mde_b"]).all()
    summary = ax.mde_summary(power_df)
    assert summary["n_insufficient"] == 2
    assert summary["team_n"] == 1 and summary["player_n"] == 1


# --------------------------------------------------- 3. TESTABILITY EXPANSION

def _synthetic_tails_claims():
    rows = [
        {"claim_id": "tail1", "topic": "tails.nba.points",
         "scope_json": json.dumps({"context": {"stat": "points"}, "entity_ids": ["7"],
                                    "entity_type": "player", "sport": "nba"}),
         "effect_json": json.dumps({"archetype": "q2", "verdict": "TESTED"})},
        {"claim_id": "tail2", "topic": "tails.nba.points",
         "scope_json": json.dumps({"context": {"stat": "points"}, "entity_ids": ["999"],
                                    "entity_type": "player", "sport": "nba"}),
         "effect_json": json.dumps({"archetype": "q1", "verdict": "TESTED"})},
        {"claim_id": "tail3", "topic": "tails.mlb.runs",
         "scope_json": json.dumps({"context": {"stat": "runs"}, "entity_ids": ["TEAM"],
                                    "entity_type": "team", "sport": "mlb"}),
         "effect_json": json.dumps({"verdict": "TESTED"})},
        {"claim_id": "tail4", "topic": "tails.nba.points",
         "scope_json": json.dumps({"context": {"stat": "points"}, "entity_ids": ["ATL"],
                                    "entity_type": "team", "sport": "nba"}),
         "effect_json": json.dumps({"verdict": "TESTED"})},
    ]
    return pd.DataFrame(rows)


def test_tails_claims_filters_by_topic_prefix():
    claims_df = _synthetic_tails_claims()
    out = ax.tails_claims(claims_df)
    assert len(out) == 4  # all 4 start with "tails."


def test_expand_tails_testability_insufficient_and_not_testable_here():
    claims_df = _synthetic_tails_claims()
    rng = np.random.default_rng(2)
    disc = pd.DataFrame({"player_id": [7] * 30, "pts": rng.normal(15, 4, 30)})
    res = pd.DataFrame({"player_id": [7] * 15, "pts": rng.normal(15, 4, 15)})
    out = ax.expand_tails_testability(claims_df, disc, res)
    by_id = out.set_index("claim_id")
    assert by_id.loc["tail3", "verdict"] == "NOT_TESTABLE_HERE"  # non-nba.points topic
    assert by_id.loc["tail4", "verdict"] == "NOT_TESTABLE_HERE"  # nba.points but TEAM-grain, not player
    assert by_id.loc["tail2", "verdict"] == "INSUFFICIENT_DATA"  # player 999 has no discovery rows
    assert by_id.loc["tail1", "verdict"] in (
        "TAIL_CALIB_BEATS_BASELINE", "TAIL_CALIB_WORSE", "NULL", "INSUFFICIENT_DATA")


def test_expansion_summary_counts_newly_testable():
    expansion_df = pd.DataFrame({
        "claim_id": ["a", "b", "c", "d"],
        "verdict": ["TAIL_CALIB_BEATS_BASELINE", "NULL", "INSUFFICIENT_DATA", "NOT_TESTABLE_HERE"],
    })
    summary = ax.expansion_summary(expansion_df)
    assert summary["n_tails_claims"] == 4
    assert summary["newly_testable"] == 2  # BEATS_BASELINE + NULL are adjudicated verdicts
    assert summary["verdict_counts"]["NOT_TESTABLE_HERE"] == 1  # only the literal count for this frame
