from pathlib import Path

import pytest

from domains.tennis.point_engine.corpus import SLAM_POINTS
from domains.tennis.point_engine.corpus_2026 import POINTS_2026
from domains.tennis.point_engine.market_join_2026 import attempt_join, append_ledger

_ODDS = (Path(__file__).resolve().parents[3] / "data" / "cache" / "inplay_odds"
         / "tennis_price_series.parquet")


@pytest.mark.skipif(not (SLAM_POINTS.exists() and POINTS_2026.exists() and _ODDS.exists()),
                     reason="fit corpus, 2026 test corpus, or kalshi tennis price series not on disk")
def test_attempt_join_is_honest_about_disjoint_populations():
    doc = attempt_join(n_sims=25)
    assert doc["edge_claimed"] is False
    assert doc["n_joined"] >= 0
    assert doc["verdict"] in ("NOT_TESTABLE", "UNDERPOWERED", "MODEL_SHARPER", "MARKET_SHARPER")
    if doc["verdict"] == "NOT_TESTABLE":
        assert "blocker" in doc and "DISJOINT" in doc["blocker"]
    n_rows = append_ledger(doc)
    assert n_rows == 1
