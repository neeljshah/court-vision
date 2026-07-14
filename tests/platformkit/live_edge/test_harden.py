"""Per-file test: B4-HARDEN's DM-clustered scorer + 2-corpora gate, on
synthetic data (no real ledger touched). Run:
cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_harden.py -q
"""
import numpy as np
import pandas as pd

from scripts.platformkit.live_edge.replay import harden as hd


def test_dm_test_clustered_detects_a_real_improvement():
    # 40 games, each with 20 possessions; conditioned prediction is exactly
    # right (true active mean), baseline is off by a constant -> conditioned
    # must win with p<0.05 across the game clusters.
    rng = np.random.default_rng(0)
    game_ids, actual = [], []
    for g in range(40):
        for _ in range(20):
            game_ids.append(f"g{g}")
            actual.append(rng.normal(1.0, 0.3))
    actual = np.array(actual)
    game_ids = np.array(game_ids)
    dm = hd.dm_test_clustered(actual, baseline_pred=0.5, conditioned_pred=1.0, game_ids=game_ids)
    assert dm["n_games"] == 40
    assert dm["mean_diff"] > 0
    assert dm["p_value"] < 0.05
    assert hd.dm_verdict(dm) == "IMPROVES"


def test_dm_test_clustered_null_when_no_real_difference():
    rng = np.random.default_rng(1)
    game_ids, actual = [], []
    for g in range(40):
        for _ in range(20):
            game_ids.append(f"g{g}")
            actual.append(rng.normal(1.0, 0.3))
    actual = np.array(actual)
    game_ids = np.array(game_ids)
    # baseline and "conditioned" are the same predictor -> zero loss diff always
    dm = hd.dm_test_clustered(actual, baseline_pred=1.0, conditioned_pred=1.0, game_ids=game_ids)
    assert dm["mean_diff"] == 0.0
    assert hd.dm_verdict(dm) == "INSUFFICIENT_DATA"  # zero-variance cluster means, no p-value


def test_dm_verdict_insufficient_data_below_min_games():
    dm = {"n_games": 3, "p_value": 0.001, "mean_diff": 1.0}
    assert hd.dm_verdict(dm, min_games=10) == "INSUFFICIENT_DATA"


def test_dm_verdict_worse_direction():
    dm = {"n_games": 20, "p_value": 0.01, "mean_diff": -1.0}
    assert hd.dm_verdict(dm) == "WORSE"


def test_split_trailing_corpora_is_disjoint_and_date_ordered():
    dates = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"])
    df = pd.DataFrame({"game_date": dates.repeat(5), "val": range(20)})
    corpus_a, corpus_b = hd.split_trailing_corpora(df)
    assert len(corpus_a) + len(corpus_b) == len(df)
    assert corpus_a["game_date"].max() < corpus_b["game_date"].min()


def test_split_trailing_corpora_empty_when_single_date():
    df = pd.DataFrame({"game_date": pd.to_datetime(["2026-01-01"] * 5), "val": range(5)})
    corpus_a, corpus_b = hd.split_trailing_corpora(df)
    assert len(corpus_a) == 0 and len(corpus_b) == 0


def test_validate_one_corpus_insufficient_data_below_floor():
    df = pd.DataFrame({"points": [1.0] * 5, "game_id": [f"g{i}" for i in range(5)]})
    mask = pd.Series(True, index=df.index)
    result = hd.validate_one_corpus(df, mask, "points", baseline_val=1.0, delta=0.1)
    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert result["n_active"] == 5


def test_combine_two_corpora_requires_both_improve():
    improves = {"verdict": "IMPROVES"}
    null = {"verdict": "NULL"}
    worse = {"verdict": "WORSE"}
    insuff = {"verdict": "INSUFFICIENT_DATA"}
    assert hd.combine_two_corpora(improves, improves) == "IMPROVES_BOTH_CORPORA"
    assert hd.combine_two_corpora(improves, null) == "IMPROVES_SINGLE_CORPUS"
    assert hd.combine_two_corpora(null, improves) == "IMPROVES_SINGLE_CORPUS"
    assert hd.combine_two_corpora(worse, improves) == "WORSE"
    assert hd.combine_two_corpora(insuff, null) == "INSUFFICIENT_DATA"
    assert hd.combine_two_corpora(null, null) == "NULL"


def test_classify_claim_grains_and_skips():
    from scripts.platformkit.live_edge.replay import run_full_ledger as rfl
    import json
    team = pd.Series({"topic": "situation.full_grid_team",
                       "scope_json": json.dumps({"context": {"cell": {"blowout_flag": False}},
                                                 "entity_type": "team", "entity_ids": ["ABC"]}),
                       "effect_json": json.dumps({"delta": 0.1, "stat": "points_per_possession"})})
    player = pd.Series({"topic": "player_cell.player_margin",
                         "scope_json": json.dumps({"context": {"cell": {"margin_bucket": "tied"}},
                                                   "entity_type": "player", "entity_ids": ["99"]}),
                         "effect_json": json.dumps({"delta": 0.05, "stat": "x", "baseline_rate": 0.2})})
    synergy = pd.Series({"topic": "synergy.with_without_teammate",
                          "scope_json": json.dumps({"context": "with_without_teammate",
                                                    "entity_type": "player_pair", "entity_ids": [1, 2]}),
                          "effect_json": json.dumps({"delta": 2.0, "stat": "pts"})})
    assert rfl.classify_claim(team)["grain"] == "team"
    assert rfl.classify_claim(player)["grain"] == "player"
    c = rfl.classify_claim(synergy)
    assert c["grain"] is None and c["reason"] == "wrong_grain_pairwise_teammate_not_cell"


def test_layer_gate_bonferroni_and_majority_class():
    from scripts.platformkit.live_edge.replay import run_full_ledger as rfl
    import json
    # 3 both-corpora rows; only the first passes Bonferroni; it is majority-class.
    results = pd.DataFrame({
        "claim_id": ["a", "b", "c"],
        "verdict": ["IMPROVES_BOTH_CORPORA", "IMPROVES_BOTH_CORPORA", "NULL"],
        "p_value_a": [1e-9, 0.04, 0.5], "p_value_b": [1e-9, 0.04, 0.5],
    })
    # pad to 1000 tests so alpha_bonf = 5e-5; row a passes, row b does not
    pad = pd.DataFrame({"claim_id": [f"z{i}" for i in range(997)],
                         "verdict": ["NULL"] * 997, "p_value_a": [0.5] * 997, "p_value_b": [0.5] * 997})
    results = pd.concat([results, pad], ignore_index=True)
    claims = pd.DataFrame({"claim_id": ["a", "b"],
                            "effect_json": [json.dumps({"n_a": 950, "n_b": 50}),   # 5% complement -> majority-class
                                            json.dumps({"n_a": 500, "n_b": 500})]})  # 50% -> balanced
    both = rfl.layer_gate(results, claims)
    assert set(both["claim_id"]) == {"a", "b"}
    row_a = both[both["claim_id"] == "a"].iloc[0]
    row_b = both[both["claim_id"] == "b"].iloc[0]
    assert bool(row_a["bonferroni_pass"]) and bool(row_a["majority_class"])
    assert not bool(row_b["bonferroni_pass"])
    defensible = both[both["bonferroni_pass"] & ~both["majority_class"]]
    assert len(defensible) == 0  # a passes Bonferroni but is majority-class -> killed


def test_attach_dates_real_box_rate_smoke():
    box = pd.DataFrame({
        "game_id": ["001", "001", "002", "002"],
        "date": pd.to_datetime(["2026-01-01"] * 2 + ["2026-01-02"] * 2),
        "team": ["A", "B", "A", "B"], "is_home": [1.0, 0.0, 1.0, 0.0],
    })
    df = pd.DataFrame({"game_id": ["001", "002"], "points": [1.0, 2.0]})
    out = hd.attach_dates(df, box_source=box)
    assert list(out["game_date"]) == list(pd.to_datetime(["2026-01-01", "2026-01-02"]))
