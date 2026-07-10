import pytest

from domains.tennis.point_engine.corpus import SLAM_POINTS
from domains.tennis.point_engine.validate import run


@pytest.mark.skipif(not SLAM_POINTS.exists(), reason="slam_points.parquet not on disk")
def test_run_produces_honest_edge_claimed_false_doc():
    d = run(n_sims=25, max_matches=10)
    assert d["edge_claimed"] is False
    assert d["n_points_fit"] > 0 and d["n_points_test"] > 0
    a, b = d["panel_A_point_logloss"], d["panel_B_match_mc"]
    assert 0.0 < a["logloss_state_conditioned"] < 5.0
    assert 0.0 < a["logloss_naive_constant_rate"] < 5.0
    assert 0.0 <= b["model"]["brier_match_winner"] <= 1.0
    assert 0.0 <= b["naive_baseline"]["brier_match_winner"] <= 1.0
    assert "market_baseline" in d and "SKIPPED" in d["market_baseline"]
    for key in ("brier_vs_naive_ci", "crps_vs_climatology_ci"):
        ci = b[key]
        assert ci["ci_lo"] <= ci["mean_delta"] <= ci["ci_hi"]
        assert ci["n_boot"] > 0 and ci["n"] > 0
        assert isinstance(ci["significant"], bool)
        assert ci["significant"] == (ci["ci_lo"] > 0)
    assert b["model_beats_naive_brier_significant"] == b["brier_vs_naive_ci"]["significant"]
    assert b["model_beats_climatology_crps_significant"] == b["crps_vs_climatology_ci"]["significant"]
