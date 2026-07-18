"""Per-file tests for scripts.platformkit.predictive_validity.nba_adapters --
SYNTHETIC boxscore frame only (this worktree has no data/ dir).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/predictive_validity/test_nba_adapters.py -q
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.predictive_validity import nba_adapters as A

CUTOFF = "2024-01-01"


def _row(gid, date, pid, fgm, fga, fg3m, fg3a, ftm, fta, pts):
    return {"game_id": gid, "date": pd.Timestamp(date), "season": "2023-24",
            "player_id": pid, "player_name": f"P{pid}",
            "fgm": fgm, "fga": fga, "fg3m": fg3m, "fg3a": fg3a, "ftm": ftm, "fta": fta, "pts": pts}


def _box() -> pd.DataFrame:
    rows = [
        _row("g1", "2023-12-01", 1, 5, 10, 2, 5, 2, 2, 14),
        _row("g2", "2023-12-05", 1, 6, 10, 1, 4, 1, 1, 14),
        # future row (after CUTOFF) -- must NOT move any pre-cutoff aggregate
        _row("g3", "2024-01-15", 1, 9, 9, 5, 5, 5, 5, 28),
        _row("g4", "2023-12-10", 2, 3, 10, 1, 5, 2, 2, 9),
        _row("g5", "2024-01-20", 2, 8, 8, 4, 4, 4, 4, 24),
    ]
    return pd.DataFrame(rows)


def test_pre_cutoff_agg_ignores_future_rows():
    pre = A._pre_cutoff_agg(_box(), CUTOFF, season_only=False)
    p1 = pre[pre["player_id"] == 1].iloc[0]
    assert p1["games"] == 2  # g1+g2 only; g3 (2024-01-15) is AFTER cutoff
    assert p1["fga"] == 20 and p1["fgm"] == 11


def test_last_n_games_agg_ignores_future_rows():
    l1 = A._last_n_games_agg(_box(), CUTOFF, 10)
    p1 = l1[l1["player_id"] == 1].iloc[0]
    assert p1["games"] == 2  # future g3 excluded from the trailing window


def test_forward_n_games_excludes_pre_cutoff_rows():
    fwd = A._forward_n_games(_box(), CUTOFF, 20)
    p1 = fwd[fwd["player_id"] == 1].iloc[0]
    assert p1["n_forward"] == 1  # only g3 (2024-01-15) is >= cutoff
    p2 = fwd[fwd["player_id"] == 2].iloc[0]
    assert p2["n_forward"] == 1  # only g5


def test_pre_cutoff_agg_season_floor_excludes_prior_season():
    box = pd.concat(
        [_box(), pd.DataFrame([_row("g0", "2023-04-01", 1, 9, 9, 9, 9, 9, 9, 9)])],
        ignore_index=True,
    )
    pre = A._pre_cutoff_agg(box, CUTOFF, season_only=True)
    p1 = pre[pre["player_id"] == 1].iloc[0]
    assert p1["games"] == 2  # g0 (2023-04-01) is before the season's Aug-1 floor


def test_forward_outcome_adapters_leak_free_and_shaped():
    box = _box()
    ts = A._forward_ts_outcome(box, CUTOFF, 20)
    fg3 = A._forward_fg3_outcome(box, CUTOFF, 20)
    assert set(ts.columns) == {"entity_id", "outcome", "n_forward"}
    assert set(fg3.columns) == {"entity_id", "outcome", "n_forward"}
    # player 1's forward TS% comes only from g3 (2024-01-15): pts=28, fga=9, fta=5
    row = ts[ts["entity_id"] == 1].iloc[0]
    expected_ts = 28 / (2 * (9 + 0.44 * 5))
    assert abs(row["outcome"] - expected_ts) < 1e-9


def test_baseline_adapters_leak_free_and_shaped():
    box = _box()
    trailing = A._trailing_ts_baseline_asof(box, CUTOFF)
    season = A._season_ts_baseline_asof(box, CUTOFF)
    l10 = A._l10_ts_metric_asof(box, CUTOFF)
    for df in (trailing, season, l10):
        assert set(df.columns) == {"entity_id", "value"}
        assert 1 in set(df["entity_id"]) and 2 in set(df["entity_id"])
