"""Per-file tests for market_coverage.sample_book -- sim-result -> SampleBook.

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && \
  C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
  scripts/platformkit/market_coverage/tests/test_sample_book.py -q

Uses a FAKE sim result (no GPU) to test the flattening + period synthesis. The real
run_nba_sim path is exercised by the coverage smoke when torch/caches are present.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import numpy as np  # noqa: E402

from scripts.platformkit.market_coverage import sample_book as SB  # noqa: E402


class _FakeRes:
    def __init__(self, n=2000):
        rng = np.random.default_rng(0)
        self.home, self.away = "NYK", "SAS"
        self.home_total = 110 + rng.normal(0, 6, n)
        self.away_total = 106 + rng.normal(0, 6, n)
        self.players = {
            1: {"name": "Star A", "team": "NYK",
                "samples": {"pts": 25 + rng.normal(0, 4, n), "reb": 7 + rng.normal(0, 2, n),
                            "ast": 5 + rng.normal(0, 2, n)}},
            2: {"name": "Big C", "team": "SAS",
                "samples": {"pts": 20 + rng.normal(0, 4, n), "reb": 9 + rng.normal(0, 2, n),
                            "ast": 3 + rng.normal(0, 2, n)}},
        }


def test_book_from_sim_columns_and_membership():
    book, name_to_pid, team_pids = SB.book_from_sim(_FakeRes())
    assert "home_score" in book.cols and "away_score" in book.cols
    assert "1|pts" in book.cols and "2|reb" in book.cols
    assert name_to_pid["star a"] == 1
    assert team_pids["home"] == [1] and team_pids["away"] == [2]
    # columns are coherent rows from the SAME matrix.
    assert book.samples.shape[0] == 2000
    assert book.joint_quality == "simulated"


def test_period_columns_synthesized():
    book, _, _ = SB.book_from_sim(_FakeRes())
    book2 = SB.add_period_columns(book)
    for side in ("home", "away"):
        for q in ("q1", "q2", "q3", "q4"):
            assert f"{side}_{q}" in book2.cols
        for h in ("h1", "h2"):
            assert f"{side}_{h}" in book2.cols
    # quarter scores sum to roughly the full-game score (approx synthesis).
    full = book2.col("home_score").mean()
    qsum = sum(book2.col(f"home_q{q}").mean() for q in (1, 2, 3, 4))
    assert abs(qsum - full) / full < 0.05
    # original book is unchanged (new SampleBook returned).
    assert "home_q1" not in book.cols


def test_median_line():
    book, _, _ = SB.book_from_sim(_FakeRes())
    m = SB.median_line(book, "1|pts")
    assert 20 < m < 30
