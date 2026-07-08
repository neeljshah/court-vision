"""Smoke test for domains/tennis/serve_return_profiles.py -- tiny synthetic
match_stats + ATP/WTA matches frames, asserts the floor and formula reuse
(serve_pts_won own-line, return_won opponent-line) match asof_hold/asof_return.

Run: python -m pytest domains/tennis/test_serve_return_profiles.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.tennis.serve_return_profiles import build_profiles


def _synthetic(tmp_path):
    n = 22  # >= MIN_MATCHES=20
    rows = []
    for i in range(n):
        rows.append({
            "event_id": f"m{i}",
            "p1_ace": 5.0, "p1_df": 1.0, "p1_svpt": 60.0, "p1_1stIn": 40.0,
            "p1_1stWon": 30.0, "p1_2ndWon": 10.0, "p1_SvGms": 10.0,
            "p1_bpSaved": 3.0, "p1_bpFaced": 5.0,
            "p2_ace": 2.0, "p2_df": 2.0, "p2_svpt": 58.0, "p2_1stIn": 35.0,
            "p2_1stWon": 20.0, "p2_2ndWon": 8.0, "p2_SvGms": 10.0,
            "p2_bpSaved": 2.0, "p2_bpFaced": 6.0,
        })
    match_stats = pd.DataFrame(rows)
    matches = pd.DataFrame({
        "event_id": [f"m{i}" for i in range(n)],
        "date": pd.to_datetime(["2020-01-01"] * n),
        "surface": ["Hard"] * n,
        "p1_id": [1] * n, "p2_id": [2] * n,
        "p1_name": ["Alice"] * n, "p2_name": ["Bob"] * n,
    })
    ms_path = tmp_path / "match_stats.parquet"
    atp_path = tmp_path / "matches.parquet"
    wta_path = tmp_path / "wta_matches.parquet"
    match_stats.to_parquet(ms_path)
    matches.to_parquet(atp_path)
    matches.iloc[0:0].to_parquet(wta_path)  # empty WTA slice, same schema
    return ms_path, atp_path, wta_path


def test_floor_and_formula(tmp_path):
    ms_path, atp_path, wta_path = _synthetic(tmp_path)
    df = build_profiles(ms_path, atp_path, wta_path, min_matches=20)
    assert set(df["player_id"]) == {1, 2}
    alice = df[df["player_id"] == 1].iloc[0]
    # p1 serve_pts_won = (30+10)/60 = 0.6667
    assert alice["serve_strength"] == pytest.approx(40 / 60, abs=1e-6)
    # p1 return_won = 1 - (p2_1stWon+p2_2ndWon)/p2_svpt = 1 - 28/58
    assert alice["return_strength"] == pytest.approx(1 - 28 / 58, abs=1e-6)


def test_below_floor_excluded(tmp_path):
    ms_path, atp_path, wta_path = _synthetic(tmp_path)
    df = build_profiles(ms_path, atp_path, wta_path, min_matches=100)
    assert df.empty


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
