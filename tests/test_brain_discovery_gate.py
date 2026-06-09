"""P7.0 / V3a — tests for the discovery step-0 corpus-verification gate (RED-A §A1).

Proves the gate permits a cross-season GA only when >=2 labeled seasons each clear the n_min floor,
and otherwise blocks it to a single enumerated single-season-research pass.
"""
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from brain.discovery_gate import gate_discovery, per_season_counts, verify_corpus  # noqa: E402


def _df(counts_by_season, target=True):
    seasons = []
    for s, n in counts_by_season.items():
        seasons += [s] * n
    actual = [1.0] * len(seasons) if target else [None] * len(seasons)
    return pd.DataFrame({"season": seasons, "actual": actual})


def test_two_real_seasons_allow_ga():
    rep = gate_discovery("player_game", _df({"2024-25": 4000, "2025-26": 4000}))
    assert rep["power_class"] == "cross_season"
    assert rep["ga_allowed"] is True and rep["mode"] == "cross_season_GA"


def test_thin_second_season_blocks_ga():
    rep = gate_discovery("player_game", _df({"2024-25": 4000, "2025-26": 500}))
    assert rep["power_class"] == "single_season_effective"
    assert rep["ga_allowed"] is False
    assert "BLOCKED" in rep["recommendation"]


def test_mostly_unlabeled_one_season_blocks_ga():
    # 94%-style: a big blank-season block + one labeled season -> single season effective (RED-A §0)
    rep = gate_discovery("player_game", _df({"": 50000, "2025-26": 4000}))
    assert rep["labeled_seasons"] == 1
    assert rep["ga_allowed"] is False


def test_quarter_grain_imbalance_blocks_ga():
    # the 26186:1613 quarter imbalance RED-A flagged -> 1613 < 5000 floor
    rep = gate_discovery("quarter", _df({"2024-25": 26000, "2025-26": 1613}))
    assert rep["power_class"] == "single_season_effective"
    assert rep["ga_allowed"] is False


def test_target_col_filters_unrealized_rows():
    # rows with null target carry no cross-season signal and must not count toward n_min
    df = _df({"2024-25": 4000, "2025-26": 4000}, target=False)
    counts = per_season_counts(df, target_col="actual")
    assert counts == {} or all(v == 0 for v in counts.values())


def test_real_pregame_oof_smoke():
    """If the real corpus exists, the gate runs and returns a well-formed report (informational)."""
    p = os.path.join(ROOT, "data", "cache", "team_system", "pregame_oof.parquet")
    if not os.path.exists(p):
        p = os.path.join(ROOT, "data", "registry", "pregame_oof.parquet")
    if not os.path.exists(p):
        import pytest
        pytest.skip("pregame_oof.parquet not present in this environment")
    rep = verify_corpus(p, "player_game")
    assert set(rep) >= {"grain", "per_season", "power_class", "passes_n_min"}
    assert rep["power_class"] in {"cross_season", "single_season_effective"}
