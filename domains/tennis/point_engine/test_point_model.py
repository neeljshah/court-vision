import pandas as pd

from domains.tennis.point_engine.point_model import PointModel, naive_baseline, MIN_CELL


def _synthetic_df():
    rows = []
    # server "A": strong on score_bucket 0 (many samples), weak elsewhere (few samples)
    for i in range(MIN_CELL + 20):
        rows.append({"server_id": "A", "score_bucket": 0, "set_bucket": 0,
                     "server_won": 1 if i % 10 else 0})   # ~0.9 win rate
    for i in range(5):
        rows.append({"server_id": "A", "score_bucket": 5, "set_bucket": 0, "server_won": 0})
    # server "B": moderate global rate, no dense cells at all
    for i in range(10):
        rows.append({"server_id": "B", "score_bucket": 2, "set_bucket": 1,
                     "server_won": i % 2})
    return pd.DataFrame(rows)


def test_full_cell_used_when_dense():
    m = PointModel.fit(_synthetic_df())
    p = m.prob("A", 0, 0)
    assert p > 0.7   # dense cell reflects the ~0.9 empirical rate (Laplace-shrunk a bit)


def test_backoff_to_server_only_when_sparse():
    m = PointModel.fit(_synthetic_df())
    p_sparse = m.prob("A", 5, 0)          # only 5 obs at this cell -> below MIN_CELL
    p_server_only = m._server_only["A"]
    assert abs(p_sparse - p_server_only) < 1e-9


def test_backoff_to_league_for_unseen_server():
    m = PointModel.fit(_synthetic_df())
    p = m.prob("unseen_player", 0, 0)
    assert 0.0 <= p <= 1.0


def test_naive_baseline_is_per_server_constant():
    base = naive_baseline(_synthetic_df())
    assert "A" in base and "B" in base
    assert 0.0 <= base["A"] <= 1.0
