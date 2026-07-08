"""Per-file test for sport_config.py's soccer_intl wiring (new loader added
so relevance_gate can reach soccer_intl_* claim families -- see
soccer_intl_travel_gate.py).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_weighting/test_sport_config.py -q
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_weighting import sport_config as sc


def test_load_soccer_intl_derives_season_and_win(monkeypatch, tmp_path):
    fixture = pd.DataFrame({
        "date": pd.to_datetime(["2023-06-01", "2024-07-02", "2024-08-03"]),
        "home_team": ["A", "B", "C"], "away_team": ["X", "Y", "Z"],
        "home_score": [2.0, 1.0, 0.0], "away_score": [1.0, 1.0, 2.0],
    })
    path = tmp_path / "results.parquet"
    fixture.to_parquet(path)
    monkeypatch.setattr(sc, "REPO_ROOT", tmp_path.parent)
    (tmp_path.parent / "data" / "domains" / "soccer_intl").mkdir(parents=True, exist_ok=True)
    fixture.to_parquet(tmp_path.parent / "data" / "domains" / "soccer_intl" / "results.parquet")

    df = sc._load_soccer_intl()
    assert list(df["season"]) == ["2023", "2024", "2024"]
    assert list(df[sc.WIN_COL]) == [1.0, 0.5, 0.0]  # home win / draw / away win
    assert df["game_id"].is_unique


def test_soccer_intl_registered_in_style_and_loaders():
    assert sc.SEASON_STYLE["soccer_intl"] == "plain"
    assert sc.win_col("soccer_intl") == sc.WIN_COL
    assert "soccer_intl" in sc._LOADERS
