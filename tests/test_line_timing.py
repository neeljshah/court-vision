"""
test_line_timing.py -- Tests for the closing-line predictor (16.7-01).

Acceptance criterion: line_timing implements a regression
(open_price, time_to_game, lineup_news, public_pct, sharp_pct, line_velocity)
-> predicted closing price, and evaluates on historical data with a logged MAE.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data import line_timing  # noqa: E402
from src.data.line_timing import (  # noqa: E402
    FEATURE_COLUMNS,
    build_training_data,
    evaluate,
    predict_closing_price,
    train,
)

_EXPECTED_FEATURES = {
    "open_price", "time_to_game", "lineup_news",
    "public_pct", "sharp_pct", "line_velocity",
}


def _make_rows(n: int = 240, seed: int = 11) -> list:
    """Synthetic rows where closing_price is a learnable function of features."""
    import random
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        open_price = rng.uniform(18.0, 32.0)
        ttg = rng.uniform(0.5, 24.0)
        lineup_news = rng.choice([0.0, 1.0])
        public_pct = rng.uniform(20.0, 80.0)
        sharp_pct = rng.uniform(20.0, 80.0)
        velocity = rng.uniform(-0.6, 0.6)
        # Closing drifts toward sharp money + velocity, away from public.
        closing = (
            open_price
            + 0.04 * (sharp_pct - 50.0)
            - 0.015 * (public_pct - 50.0)
            + 1.2 * velocity
            + 0.3 * lineup_news
            + rng.gauss(0, 0.25)
        )
        rows.append({
            "open_price": round(open_price, 2),
            "time_to_game": round(ttg, 2),
            "lineup_news": lineup_news,
            "public_pct": round(public_pct, 1),
            "sharp_pct": round(sharp_pct, 1),
            "line_velocity": round(velocity, 3),
            "closing_price": round(closing, 2),
        })
    return rows


@pytest.fixture(autouse=True)
def _clear_cache():
    line_timing.clear_cache()
    yield
    line_timing.clear_cache()


def test_feature_set_matches_spec():
    """The model consumes exactly the six features named in the task."""
    assert set(FEATURE_COLUMNS) == _EXPECTED_FEATURES


def test_train_produces_low_mae(tmp_path):
    """Training on a learnable dataset yields a small held-out MAE."""
    model_path = str(tmp_path / "line_timing.pkl")
    metrics = train(_make_rows(), model_path)
    # Signal dominates noise (gauss sigma 0.25) -> MAE should be well under 2 pts.
    assert metrics["mae"] < 2.0
    assert metrics["n_test"] > 0
    assert os.path.exists(model_path)


def test_evaluate_logs_mae(tmp_path, caplog):
    """evaluate() scores historical rows and emits a logged MAE."""
    model_path = str(tmp_path / "line_timing.pkl")
    rows = _make_rows()
    train(rows, model_path)

    import logging
    with caplog.at_level(logging.INFO, logger="src.data.line_timing"):
        result = evaluate(rows, model_path)
    assert result["mae"] is not None
    assert result["n"] == len(rows)
    assert any("MAE" in rec.message for rec in caplog.records)


def test_predict_closing_price_returns_float(tmp_path):
    """predict_closing_price returns a numeric closing-price estimate."""
    model_path = str(tmp_path / "line_timing.pkl")
    train(_make_rows(), model_path)

    pred = predict_closing_price(
        {"open_price": 25.0, "time_to_game": 3.0, "lineup_news": 0.0,
         "public_pct": 65.0, "sharp_pct": 40.0, "line_velocity": -0.3},
        model_path,
    )
    assert isinstance(pred, float)
    assert 10.0 < pred < 45.0


def test_train_raises_on_insufficient_rows(tmp_path):
    """Too few labelled rows raises rather than fitting noise."""
    with pytest.raises(ValueError, match="rows"):
        train(_make_rows(n=5), str(tmp_path / "m.pkl"))


def test_build_training_data_reads_history(tmp_path):
    """build_training_data loads labelled rows from the history JSON."""
    hist = tmp_path / "line_timing_history.json"
    rows = _make_rows(n=30)
    hist.write_text(json.dumps(rows), encoding="utf-8")
    loaded = build_training_data(str(hist))
    assert len(loaded) == 30


def test_build_training_data_missing_file_returns_empty(tmp_path):
    """An absent history file is a valid empty dataset, not an error."""
    assert build_training_data(str(tmp_path / "nope.json")) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
