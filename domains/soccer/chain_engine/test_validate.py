import pytest

from domains.soccer.chain_engine.corpus import MATCH_META
from domains.soccer.chain_engine.validate import run


@pytest.mark.skipif(not MATCH_META.exists(), reason="match_meta.parquet not on disk")
def test_run_produces_honest_edge_claimed_false_doc():
    d = run(n_sims=15, max_matches=4)
    assert d["edge_claimed"] is False
    assert set(d["results"].keys()) == {"A", "B"}
    for tag in ("A", "B"):
        r = d["results"][tag]
        a, b = r["panel_A_possession_logloss"], r["panel_B_match_mc"]
        assert 0.0 < a["logloss_state_conditioned"] < 5.0
        assert 0.0 < a["logloss_naive_constant_rate"] < 5.0
        assert 0.0 <= b["model"]["brier_home_win"] <= 1.0
        assert 0.0 <= b["naive_baseline"]["brier_home_win"] <= 1.0
    assert "market_baseline" in d and "SKIPPED" in d["market_baseline"]
