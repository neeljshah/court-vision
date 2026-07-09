import numpy as np
import pandas as pd

from domains.soccer.chain_engine.shot_model import ShotModel, naive_baseline, MIN_CELL


def _synthetic_df():
    rows = []
    for i in range(MIN_CELL + 15):
        rows.append({"team": "X", "time_bucket": 0, "score_bucket": 1,
                     "had_shot": 1 if i % 3 else 0, "xg": 0.2 if i % 3 else np.nan,
                     "goal": False})
    for i in range(5):
        rows.append({"team": "X", "time_bucket": 3, "score_bucket": 2,
                     "had_shot": 0, "xg": np.nan, "goal": False})
    for i in range(10):
        rows.append({"team": "Y", "time_bucket": 1, "score_bucket": 0,
                     "had_shot": i % 2, "xg": 0.1 if i % 2 else np.nan, "goal": False})
    return pd.DataFrame(rows)


def test_full_cell_used_when_dense():
    m = ShotModel.fit(_synthetic_df())
    p = m.shot_prob("X", 0, 1)
    assert 0.0 < p < 1.0


def test_backoff_to_team_only_when_sparse():
    m = ShotModel.fit(_synthetic_df())
    p_sparse = m.shot_prob("X", 3, 2)
    assert abs(p_sparse - m._team_only["X"]) < 1e-9


def test_backoff_to_league_for_unseen_team():
    m = ShotModel.fit(_synthetic_df())
    p = m.shot_prob("unseen", 0, 1)
    assert 0.0 <= p <= 1.0


def test_sample_xg_returns_pool_value_or_fallback():
    m = ShotModel.fit(_synthetic_df())
    rng = np.random.default_rng(0)
    v = m.sample_xg(0, 1, rng)
    assert 0.0 <= v <= 1.0
    v2 = m.sample_xg(99, 99, rng)   # unseen cell -> global pool fallback
    assert 0.0 <= v2 <= 1.0


def test_naive_baseline_is_per_team_constant():
    base = naive_baseline(_synthetic_df())
    assert "X" in base and "Y" in base and "__global__" in base
