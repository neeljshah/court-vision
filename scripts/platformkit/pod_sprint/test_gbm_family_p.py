"""Tests for scripts.platformkit.pod_sprint.gbm_family_p (merge correctness; the GBM
fit itself is exercised by running the module's CLI directly -- see run() docstring)."""

import numpy as np
import pandas as pd

from scripts.platformkit.models import gbm_nba_ml as g
from scripts.platformkit.pod_sprint import gbm_family_p as fp


def _toy_box(n=30, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    teams = ["AAA", "BBB", "CCC", "DDD"]
    dates = pd.date_range("2025-10-01", periods=n, freq="2D")
    rows = []
    for i in range(n):
        h, a = rng.choice(teams, size=2, replace=False)
        rows.append({
            "date": dates[i], "home_abbr": h, "away_abbr": a,
            "home_pts": float(rng.integers(90, 130)), "away_pts": float(rng.integers(90, 130)),
            "home_fg_attempted": 85.0, "home_ft_attempted": 20.0, "home_oreb": 10.0, "home_tov": 13.0,
            "away_fg_attempted": 85.0, "away_ft_attempted": 20.0, "away_oreb": 10.0, "away_tov": 13.0,
        })
    return pd.DataFrame(rows)


def _toy_pb(box: pd.DataFrame, drop_last_n_dates: int = 5) -> pd.DataFrame:
    """Player box covering only most of box's date range -- exercises the missing-coverage
    fillna(0.0) path deliberately, like the real corpus's staleness gap."""
    cutoff = sorted(box["date"].unique())[-drop_last_n_dates]
    rows = []
    for i, r in enumerate(box.itertuples()):
        if r.date >= cutoff:
            continue
        for team in (r.home_abbr, r.away_abbr):
            for slot in range(2):
                rows.append({"game_id": f"G{i:04d}", "date": r.date, "team": team,
                             "opp": r.away_abbr if team == r.home_abbr else r.home_abbr,
                             "player_id": hash((team, slot)) % 1000,
                             "min": 24.0, "plus_minus": 2.0})
    return pd.DataFrame(rows)


def test_build_features_merge_shape(monkeypatch, tmp_path):
    box = _toy_box()
    pb = _toy_pb(box)
    pb_path = tmp_path / "player_boxscores.parquet"
    pb.to_parquet(pb_path)
    monkeypatch.setattr(fp, "_PLAYER_BOX", pb_path)

    merged = fp.build_features(box)
    assert set(fp.FAMILY_P_FEATURES) <= set(merged.columns)
    assert len(fp.FAMILY_P_FEATURES) == len(g._FEATURES) + 8
    assert not merged[fp._EXTRA_FEATURES].isna().any().any()   # left-join gaps filled to 0.0
    assert merged.attrs["n_missing_player_coverage"] > 0        # the dropped-dates path triggered
    assert len(merged) == len(box)
