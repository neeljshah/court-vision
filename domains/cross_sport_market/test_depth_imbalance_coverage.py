"""Real-slice check for depth_imbalance_coverage.py: builds against the
actual data/cache/depth_history/ captures in this repo and asserts the two
zero-capture sports (nba, soccer) show up as explicit zero-coverage rows,
never silently dropped from the 8-sport universe.

Run: python -m pytest domains/cross_sport_market/test_depth_imbalance_coverage.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.cross_sport_market.depth_imbalance_coverage import (
    ALL_SPORTS,
    _summarize_sport,
    build,
)


def test_build_real_slice_has_all_8_sports_zero_rows_explicit(tmp_path) -> None:
    summary = build(out_path=tmp_path / "coverage.json")

    rows_by_sport = {r["sport"]: r for r in summary["rows"]}
    assert set(rows_by_sport) == set(ALL_SPORTS)
    assert summary["n_sports_total"] == 8

    # This session's real captures: nba + soccer have no depth_history dir.
    for zero_sport in ("nba", "soccer"):
        row = rows_by_sport[zero_sport]
        assert row["coverage"] == "zero"
        assert row["n_rows"] == 0
        assert row["mean_imbalance"] is None
        assert row["bid_heavy_rate"] is None

    # The other 6 sports have real captures -> present with positive n_rows.
    covered = [s for s in ALL_SPORTS if s not in ("nba", "soccer")]
    for sport in covered:
        row = rows_by_sport[sport]
        assert row["coverage"] == "present"
        assert row["n_rows"] > 0
        assert -1.0 <= row["mean_imbalance"] <= 1.0
        assert 0.0 <= row["bid_heavy_rate"] <= 1.0

    assert summary["n_sports_covered"] == len(covered)
    assert summary["n_sports_zero"] == 2
    assert summary["edge_claimed"] is False
    assert (tmp_path / "coverage.json").exists()


def test_summarize_sport_zero_row_frame(monkeypatch) -> None:
    monkeypatch.setattr(
        "domains.cross_sport_market.depth_imbalance_coverage._prep_sport",
        lambda sport: pd.DataFrame(),
    )
    row = _summarize_sport("nba")
    assert row == {
        "sport": "nba",
        "coverage": "zero",
        "n_rows": 0,
        "mean_imbalance": None,
        "bid_heavy_rate": None,
    }


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
