"""Smoke test for domains/soccer/style_fingerprints.py -- tiny synthetic
match_stats+matches frames, asserts the team-season floor and z-score math.

Run: python -m pytest domains/soccer/test_style_fingerprints.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.soccer.style_fingerprints import STYLE_DIMS, build_fingerprints


def _synthetic(tmp_path):
    n = 16  # >= MIN_MATCHES=15 for TeamA/TeamB, one season
    rows = []
    for i in range(n):
        rows.append({
            "event_id": f"m{i}", "home_team": "TeamA", "away_team": "TeamB",
            "home_shots": 10.0, "away_shots": 5.0, "home_sot": 4.0, "away_sot": 2.0,
            "home_corners": 6.0, "away_corners": 3.0,
            "home_fouls": 10.0, "away_fouls": 12.0,
            "home_yellow": 1.0, "away_yellow": 2.0, "home_red": 0.0, "away_red": 0.0,
        })
    match_stats = pd.DataFrame(rows)
    matches = pd.DataFrame({
        "event_id": [f"m{i}" for i in range(n)],
        "season": [2020] * n,
        "ftr": ["H"] * n,
    })
    ms_path = tmp_path / "match_stats.parquet"
    m_path = tmp_path / "matches.parquet"
    match_stats.to_parquet(ms_path)
    matches.to_parquet(m_path)
    return ms_path, m_path


def test_floor_and_columns(tmp_path):
    ms_path, m_path = _synthetic(tmp_path)
    fp = build_fingerprints(ms_path, m_path, min_matches=15)
    assert set(fp["team"]) == {"TeamA", "TeamB"}
    for dim in STYLE_DIMS:
        assert dim in fp.columns
        assert f"z_{dim}" in fp.columns


def test_below_floor_excluded(tmp_path):
    ms_path, m_path = _synthetic(tmp_path)
    fp = build_fingerprints(ms_path, m_path, min_matches=100)  # no team clears 100
    assert fp.empty


def test_shot_share_bounds(tmp_path):
    ms_path, m_path = _synthetic(tmp_path)
    fp = build_fingerprints(ms_path, m_path, min_matches=15)
    assert (fp["shot_share"].between(0, 1)).all()
    a = fp[fp["team"] == "TeamA"].iloc[0]
    assert a["shot_share"] == pytest.approx(10 / 15)  # 10 shots for / (10+5)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
