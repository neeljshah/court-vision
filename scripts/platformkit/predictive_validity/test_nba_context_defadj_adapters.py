"""Per-file tests for nba_context_defadj_adapters -- SYNTHETIC boxscore
frame only (this worktree has no data/ dir).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/predictive_validity/test_nba_context_defadj_adapters.py -q

Acceptance: baseline-vs-candidate shape -- metric_asof/baseline_asof both
return {entity_id, value}; forward_outcome returns {entity_id, outcome,
n_forward}; the metric_asof computation is leak-free (excludes cutoff-or-
later rows both for the player's own history AND the opponent-strength
read it depends on).
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.predictive_validity import nba_context_defadj_adapters as A

CUTOFF = "2024-11-01"


def _row(gid, date, team, opp, pid, fgm, fga, fg3m, fg3a, ftm, fta, pts):
    return {"game_id": gid, "date": pd.Timestamp(date), "season": "2023-24", "team": team, "opp": opp,
            "player_id": pid, "player_name": f"P{pid}",
            "fgm": fgm, "fga": fga, "fg3m": fg3m, "fg3a": fg3a, "ftm": ftm, "fta": fta, "pts": pts}


def _box() -> pd.DataFrame:
    rows = []
    for i in range(10):
        date = pd.Timestamp("2024-09-01") + pd.Timedelta(days=i * 3)
        opp = "ZZZ" if i % 2 == 0 else "YYY"
        rows.append(_row(f"g{i}", date, "AAA", opp, 1, 5, 10, 0, 0, 2, 2, 12))
        if opp == "ZZZ":
            rows.append(_row(f"g{i}", date, "ZZZ", "AAA", 700, 7, 10, 0, 0, 1, 1, 15))
        else:
            rows.append(_row(f"g{i}", date, "YYY", "AAA", 750, 3, 10, 0, 0, 0, 0, 6))
    # future rows (>= CUTOFF) -- must NOT move the pre-cutoff metric/baseline
    for i in range(5):
        date = pd.Timestamp("2024-11-05") + pd.Timedelta(days=i * 3)
        rows.append(_row(f"f{i}", date, "AAA", "ZZZ", 1, 9, 9, 0, 0, 5, 5, 28))
        rows.append(_row(f"f{i}", date, "ZZZ", "AAA", 700, 1, 9, 0, 0, 0, 0, 2))
    return pd.DataFrame(rows)


def test_metric_and_baseline_asof_shape_and_leak_free():
    box = _box()
    m = A._defadj_ts_metric_asof(box, CUTOFF)
    b = A._min_forward_games  # just exercise the import path works
    assert set(m.columns) == {"entity_id", "value"}
    # future rows dated >= CUTOFF must never affect this pre-cutoff frame's
    # metric value -- recompute directly on the pre-cutoff slice only and
    # confirm they match bit-for-bit.
    pre_only = box[box["date"] < pd.Timestamp(CUTOFF)]
    m_direct = A._defadj_ts_metric_asof(pre_only, CUTOFF)
    pd.testing.assert_frame_equal(
        m.sort_values("entity_id").reset_index(drop=True),
        m_direct.sort_values("entity_id").reset_index(drop=True),
    )


def test_forward_outcome_and_baseline_columns_shape():
    from scripts.platformkit.predictive_validity.nba_adapters import (
        _forward_ts_outcome,
        _trailing_ts_baseline_asof,
    )
    box = _box()
    baseline = _trailing_ts_baseline_asof(box, CUTOFF)
    outcome = _forward_ts_outcome(box, CUTOFF, 20)
    assert set(baseline.columns) == {"entity_id", "value"}
    assert set(outcome.columns) == {"entity_id", "outcome", "n_forward"}


def test_defadj_ts_test_builds_a_valid_metric_test():
    box = _box()
    test = A.defadj_ts_test(box, forward_games=20)
    assert test.family == "nba_context_shooting_defadj"
    assert test.metric_name == "def_adj_ts_pct_asof"
    assert test.baseline_name == "trailing_ts_pct"
    assert test.caveat  # non-empty, declared caveat present
    m = test.metric_asof(CUTOFF)
    assert set(m.columns) == {"entity_id", "value"}
