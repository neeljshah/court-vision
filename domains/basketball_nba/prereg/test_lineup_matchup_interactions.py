"""Per-file test for lineup_matchup_interactions -- verdict rules on synthetic
fits (no disk/network), the as-of continuity leak guard (game-2 continuity
uses only game-1 seconds), and the overlap_s weight floor.

Run: python -m pytest domains/basketball_nba/prereg/test_lineup_matchup_interactions.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.prereg.lineup_matchup_interactions import (
    ALPHA, CONTROL_COL, _row, build_continuity_table, build_lineup_talent,
    build_segment_features, fit_wls_cluster,
)

_XCOL = "x1_spacing_diff"


def _fit(effect: float, p: float, n: int = 500) -> dict:
    return {"effect": effect, "p": p, "n": n, "term": _XCOL}


# --- _row verdict rules -----------------------------------------------------

def test_alpha_is_bonferroni_k3():
    assert abs(ALPHA - 0.05 / 3) < 1e-12


def test_primary_declaration_survives():
    row = _row("H1_spacing_diff", "2025_26", "raw", _fit(0.01, 1e-6), None)
    assert row["verdict"] == "SURVIVES_PREREG"
    assert row["edge_claimed"] is False
    assert row["alpha_fwer"] == ALPHA


def test_primary_declaration_null_above_bonferroni():
    """p=0.02 clears a plain 0.05 bar but not the K=3 Bonferroni ~0.0167 one."""
    row = _row("H1_spacing_diff", "2025_26", "raw", _fit(0.01, 0.02), None)
    assert row["verdict"] == "NULL"


def test_replication_same_sign_and_significant():
    row = _row("H1_spacing_diff", "2024_25", "raw", _fit(0.01, 1e-6), None, sign_ref=1)
    assert row["verdict"] == "REPLICATED"


def test_replication_wrong_sign_fails():
    row = _row("H1_spacing_diff", "2024_25", "raw", _fit(-0.01, 1e-6), None, sign_ref=1)
    assert row["verdict"] == "FAILED_REPLICATION"


def test_replication_not_significant_fails():
    row = _row("H1_spacing_diff", "2024_25", "raw", _fit(0.01, 0.5), None, sign_ref=1)
    assert row["verdict"] == "FAILED_REPLICATION"


def test_n_zero_is_not_testable_not_a_failed_replication():
    row = _row("H1_spacing_diff", "2023_24", "raw", _fit(0.01, 1e-6, n=0), None, sign_ref=1)
    assert row["verdict"] == "NOT_TESTABLE"


# --- as-of continuity leak guard -------------------------------------------

def test_continuity_leak_guard_game2_uses_only_game1_seconds():
    stints_df = pd.DataFrame([
        {"team_id": 1, "lineup_key": "a,b,c", "game_id": "g1", "n_on_court": 5, "elapsed_s": 100.0},
        {"team_id": 1, "lineup_key": "a,b,c", "game_id": "g2", "n_on_court": 5, "elapsed_s": 150.0},
        {"team_id": 1, "lineup_key": "a,b,c", "game_id": "g3", "n_on_court": 5, "elapsed_s": 200.0},
    ])
    games_df = pd.DataFrame([
        {"game_id": "g1", "date": pd.Timestamp("2024-01-01")},
        {"game_id": "g2", "date": pd.Timestamp("2024-01-03")},
        {"game_id": "g3", "date": pd.Timestamp("2024-01-05")},
    ])
    cont = build_continuity_table(stints_df, games_df).set_index("game_id")["continuity_s"]
    assert cont["g1"] == 0.0            # first-ever appearance: no prior minutes
    assert cont["g2"] == 100.0          # only game-1's seconds, not game-2's own
    assert cont["g3"] == 250.0          # game-1 + game-2, strictly before game-3


def test_talent_sum_requires_all_five_players():
    stints_df = pd.DataFrame([
        {"team_id": 1, "lineup_key": "1,2,3,4,5", "n_on_court": 5},
    ])
    on_off_complete = pd.DataFrame([
        {"player_id": pid, "team_id": 1, "net_rating_on_per48": 1.0} for pid in range(1, 6)
    ])
    full = build_lineup_talent(stints_df, on_off_complete)
    assert full.loc[0, "talent_sum"] == 5.0

    on_off_missing = on_off_complete.iloc[:4]  # player 5 absent
    missing = build_lineup_talent(stints_df, on_off_missing)
    assert pd.isna(missing.loc[0, "talent_sum"])


# --- overlap_s weight floor --------------------------------------------------

def test_overlap_floor_drops_short_segments():
    matchups_df = pd.DataFrame([
        {"game_id": "g1", "team_id_a": 1, "team_id_b": 2, "lineup_key_a": "a,b,c",
         "lineup_key_b": "x,y,z", "overlap_s": 10.0, "pts_a": 1.0, "pts_b": 1.0},   # below floor
        {"game_id": "g1", "team_id_a": 1, "team_id_b": 2, "lineup_key_a": "a,b,c",
         "lineup_key_b": "x,y,z", "overlap_s": 50.0, "pts_a": 2.0, "pts_b": 1.0},   # above floor
    ])
    empty_spacing = pd.DataFrame(columns=["team_id", "lineup_key", "n_shots", "spacing_mean_dist"])
    empty_talent = pd.DataFrame(columns=["team_id", "lineup_key", "talent_sum"])
    empty_cont = pd.DataFrame(columns=["team_id", "lineup_key", "game_id", "continuity_s"])
    out = build_segment_features(matchups_df, empty_spacing, empty_talent, empty_cont, min_overlap_s=30.0)
    assert len(out) == 1
    assert out.iloc[0]["overlap_s"] == 50.0


# --- fit_wls_cluster sanity --------------------------------------------------

def test_fit_wls_cluster_recovers_linear_signal():
    df = pd.DataFrame({
        "y": [0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 1.0, 3.0, 5.0, 7.0],
        "x1_spacing_diff": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 0.5, 1.5, 2.5, 3.5],
        "overlap_s": [40.0] * 10,
        "game_id": [f"g{i}" for i in range(10)],
    })
    fit = fit_wls_cluster(df, "x1_spacing_diff")
    assert fit["n"] == 10
    assert fit["effect"] > 1.5  # true slope is ~2.0
    assert fit["p"] < 0.05


def test_fit_wls_cluster_n_zero_all_missing():
    df = pd.DataFrame({"y": [None], "x1_spacing_diff": [None], "overlap_s": [None], "game_id": ["g1"]})
    fit = fit_wls_cluster(df, "x1_spacing_diff")
    assert fit["n"] == 0 and fit["effect"] is None and fit["p"] is None


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
