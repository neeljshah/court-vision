import pytest

from domains.tennis.point_engine.corpus import SLAM_POINTS
from domains.tennis.point_engine.corpus_2026 import POINTS_2026
from domains.tennis.point_engine.validate_2026 import run, _ledger_rows


@pytest.mark.skipif(not (SLAM_POINTS.exists() and POINTS_2026.exists()),
                     reason="fit or 2026 test corpus not on disk")
def test_run_produces_honest_2026_drift_doc():
    d = run(n_sims=25, max_matches=10)
    assert d["edge_claimed"] is False
    assert d["population"] == "mcp_charted_nonrepresentative"
    assert d["n_points_test_2026"] > 0 and d["n_matches_test_2026"] > 0
    a, b = d["panel_A_point_logloss"], d["panel_B_match_mc"]
    assert 0.0 < a["logloss_state_conditioned"] < 5.0
    assert 0.0 <= b["model"]["brier_match_winner"] <= 1.0
    rows = _ledger_rows(d)
    assert len(rows) == 2
    assert all(r["edge_claimed"] is False for r in rows)
