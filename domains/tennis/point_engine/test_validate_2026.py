import pytest

from domains.tennis.point_engine.corpus import SLAM_POINTS
from domains.tennis.point_engine.corpus_2026 import POINTS_2026
from domains.tennis.point_engine.validate_2026 import run, _ledger_rows, _match_mc_verdict


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
    match_mc_row = rows[1]
    assert match_mc_row["hypothesis"].endswith("_match_mc")
    # verdict is CI-gated: never a raw win when the bootstrap CI straddles zero,
    # and never an unqualified win off this single non-representative corpus
    assert match_mc_row["verdict"] in (
        "UNDERPOWERED", "MODEL_BEATS_CLIMATOLOGY_CRPS_PROVISIONAL", "CLIMATOLOGY_BEATS_MODEL_CRPS")
    if not b["model_beats_climatology_crps_significant"]:
        assert match_mc_row["verdict"] == "UNDERPOWERED"


def test_match_mc_verdict_is_ci_gated_not_point_estimate():
    sig_win = {"model_beats_climatology_crps": True, "model_beats_climatology_crps_significant": True}
    sig_lose = {"model_beats_climatology_crps": False, "model_beats_climatology_crps_significant": True}
    insig = {"model_beats_climatology_crps": True, "model_beats_climatology_crps_significant": False}
    assert _match_mc_verdict(sig_win) == "MODEL_BEATS_CLIMATOLOGY_CRPS_PROVISIONAL"
    assert _match_mc_verdict(sig_lose) == "CLIMATOLOGY_BEATS_MODEL_CRPS"
    assert _match_mc_verdict(insig) == "UNDERPOWERED"
