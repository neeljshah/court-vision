"""Per-file test: python -m pytest scripts/platformkit/compose/test_dreb_challenger.py -q

Synthetic-frame checks (no parquet/pbp I/O):
  (a) leak guard   -- a team's FIRST game gets a NaN as-of feature (no prior games).
  (b) monotone     -- higher prior continuity -> higher current as-of feature.
  (c) verdict rule -- NULL fires when delta<=0; MATTERS_PROVISIONAL only when
                      delta>0 AND dm_p<0.05 AND delta_t80>0.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.compose.dreb_challenger import _verdict
from scripts.platformkit.compose.team_form import _asof_weighted_mean


def _per_game(rows):
    """rows: list of (game_id, team, date, v, w) -> the per-game frame
    _asof_dreb_feature builds before calling _asof_weighted_mean."""
    return pd.DataFrame(rows, columns=["game_id", "team", "date", "v", "w"])


def test_leak_guard_first_game_is_nan():
    df = _per_game([
        ("g1", "BOS", "2024-01-01", 5.0, 3),
        ("g2", "BOS", "2024-01-03", 8.0, 4),
    ])
    feat = _asof_weighted_mean(df, "v", "w")
    assert np.isnan(feat[("g1", "BOS")])          # no prior game -> NaN, never the current one
    assert feat[("g2", "BOS")] == 5.0              # only g1 is strictly prior


def test_monotone_higher_prior_continuity_higher_feature():
    low = _per_game([
        ("g1", "BOS", "2024-01-01", 3.0, 5),
        ("g2", "BOS", "2024-01-03", 3.0, 5),
        ("g3", "BOS", "2024-01-05", 3.0, 5),
    ])
    high = _per_game([
        ("g1", "BOS", "2024-01-01", 9.0, 5),
        ("g2", "BOS", "2024-01-03", 9.0, 5),
        ("g3", "BOS", "2024-01-05", 9.0, 5),
    ])
    f_low = _asof_weighted_mean(low, "v", "w")[("g3", "BOS")]
    f_high = _asof_weighted_mean(high, "v", "w")[("g3", "BOS")]
    assert f_high > f_low


def test_verdict_null_when_delta_non_positive():
    verdict, caveats = _verdict(delta=-0.001, dm_p=0.01, delta_t80=0.001)
    assert verdict == "NULL"
    assert caveats == []


def test_verdict_null_when_dm_p_not_significant():
    verdict, _ = _verdict(delta=0.002, dm_p=0.5, delta_t80=0.002)
    assert verdict == "NULL"


def test_verdict_matters_provisional_when_all_three_conditions_hold():
    verdict, caveats = _verdict(delta=0.002, dm_p=0.01, delta_t80=0.001)
    assert verdict == "MATTERS_PROVISIONAL"
    assert caveats


if __name__ == "__main__":  # pragma: no cover - smoke
    test_leak_guard_first_game_is_nan()
    test_monotone_higher_prior_continuity_higher_feature()
    test_verdict_null_when_delta_non_positive()
    test_verdict_null_when_dm_p_not_significant()
    test_verdict_matters_provisional_when_all_three_conditions_hold()
    print("all dreb_challenger tests passed")
