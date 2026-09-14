"""tests.platformkit.test_prop_game_model_matchup -- Q15c deliverable 2 checks.
No network.

(a) build_candidate_frame returns the same rows in the same order as the incumbent frame,
    plus the defender-matchup *_asof columns, on a synthetic fixture.
(b) load_matchup_columns drops DROPPED_CONSTANT_COL even though the real source table
    carries it (real data/domains/basketball_nba/defender_matchup_states.parquet, same
    local-file pattern as test_gate_b_tracking_ablation.py's own family test).
(c) promote_or_hold: PROMOTE only when both cuts are AHEAD and seed-stable; HOLD (with a
    reason per failing condition) on a BEHIND/UNDERPOWERED/seed-unstable cut.
(d) the constant-in-train guard blocks a constant defender-matchup family end to end
    (_run_cut) -> verdict_crps NOT_TESTED and seed_stability skipped, not a measured null.

Run: python -m pytest tests/platformkit/test_prop_game_model_matchup.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.proof_nba.prop_game_model_matchup import (
    DROPPED_CONSTANT_COL, _run_cut, build_candidate_frame, load_matchup_columns, promote_or_hold)


def _synthetic_incumbent_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "player_id": [1, 1, 2, 2],
        "season": ["2024-25", "2025-26", "2024-25", "2025-26"],
        "game_id": ["g1", "g2", "g3", "g4"],
        "date": pd.to_datetime(["2024-11-01", "2025-11-01", "2024-11-02", "2025-11-02"]),
    })


def _synthetic_dmatch() -> tuple:
    dmatch = pd.DataFrame({
        "player_id": [1, 2], "game_id": ["g2", "g4"],
        "def_test_asof": [0.4, 0.6], "def_n_prior": [3, 5],
    })
    return dmatch, ["def_test_asof", "def_n_prior"]


def test_candidate_frame_same_rows_same_order_plus_matchup_cols():
    df = _synthetic_incumbent_frame()
    dmatch, dm_cols = _synthetic_dmatch()
    df2, cols, matched_col = build_candidate_frame(df, dmatch, dm_cols)
    assert len(df2) == len(df)
    assert df2["player_id"].tolist() == df["player_id"].tolist()
    assert df2["game_id"].tolist() == df["game_id"].tolist()
    assert cols == dm_cols
    for c in dm_cols:
        assert c in df2.columns
    assert matched_col in df2.columns
    g2 = df2[df2["game_id"] == "g2"].iloc[0]
    assert g2["def_test_asof"] == 0.4
    g1 = df2[df2["game_id"] == "g1"].iloc[0]  # no matchup row for g1 -> NaN, not dropped
    assert pd.isna(g1["def_test_asof"])


def test_dropped_constant_column_absent_but_present_in_source():
    dmatch, dm_cols = load_matchup_columns()
    assert DROPPED_CONSTANT_COL not in dm_cols
    assert DROPPED_CONSTANT_COL not in dmatch.columns
    raw = pd.read_parquet("data/domains/basketball_nba/defender_matchup_states.parquet")
    assert DROPPED_CONSTANT_COL in raw.columns  # confirms it was deliberately dropped, not absent


def test_promote_requires_both_cuts_ahead_and_seed_stable():
    ahead_stable = {"status": "OK", "verdict_crps": "AHEAD", "seed_stability": {"seed_stable": True}}
    assert promote_or_hold(ahead_stable, ahead_stable)["verdict"] == "PROMOTE"

    behind = {"status": "OK", "verdict_crps": "BEHIND", "seed_stability": {"seed_stable": True}}
    out = promote_or_hold(ahead_stable, behind)
    assert out["verdict"] == "HOLD"
    assert any("verdict_crps=BEHIND" in r for r in out["reasons"])

    unstable = {"status": "OK", "verdict_crps": "AHEAD", "seed_stability": {"seed_stable": False}}
    out2 = promote_or_hold(ahead_stable, unstable)
    assert out2["verdict"] == "HOLD"
    assert any("seed_stable=False" in r for r in out2["reasons"])

    underpowered = {"status": "UNDERPOWERED_DATA"}
    out3 = promote_or_hold(underpowered, ahead_stable)
    assert out3["verdict"] == "HOLD"
    assert any("UNDERPOWERED_DATA" in r for r in out3["reasons"])


def test_guard_blocks_constant_defender_matchup_family():
    rng = np.random.default_rng(11)
    n_train, n_test = 220, 60
    champ_cols = ["f1"]
    dm_cols = ["dm1"]

    def _frame(n, start_gid):
        return pd.DataFrame({
            "f1": rng.normal(size=n),
            "opp_allowed_pts_10": rng.normal(size=n),
            "dm1": np.full(n, np.nan),  # constant (all-NaN) in TRAIN by construction
            "dm_matched": np.full(n, False),  # no defender_matchup row found -> join failed too
            "pts": rng.normal(loc=15, scale=4, size=n),
            "game_id": [f"g{start_gid + i}" for i in range(n)],
        })

    train_df, test_df = _frame(n_train, 0), _frame(n_test, n_train)
    split_meta = {"split": "synthetic_test"}
    result = _run_cut(champ_cols, dm_cols, "dm_matched", "pts", "TEST_CUT",
                       train_df, test_df, split_meta, weak=False)
    assert result["status"] == "OK"
    assert result["family_constant_in_train"]["all_constant"] is True
    assert result["verdict_crps"] == "NOT_TESTED"
    assert result["verdict_pinball"] == "NOT_TESTED"
    assert result["seed_stability"] is None  # guard skips the (expensive) stability refit too
