"""Leak-contract tests for the foundry predictor construction (hermetic: no data reads)."""
from __future__ import annotations

import pytest

from scripts.platformkit.signals import foundry_run


@pytest.fixture(autouse=True)
def _injected_table():
    saved = dict(foundry_run._TABLES)
    foundry_run._TABLES.clear()
    foundry_run._TABLES["schedule_rest"] = {f"g{i}": float(i % 7 - 3) for i in range(80)}
    foundry_run._TABLES["schedule_rest"]["hi"] = 3.0
    foundry_run._TABLES["schedule_rest"]["lo"] = -3.0
    yield
    foundry_run._TABLES.clear()
    foundry_run._TABLES.update(saved)


def _train(n: int = 60) -> list[dict]:
    # outcome correlated with the signal: positive rest diff -> home win
    return [{"game_id": f"g{i}", "outcome": 1 if (i % 7 - 3) > 0 else 0} for i in range(n)]


def test_unredacted_test_view_raises():
    with pytest.raises(AssertionError, match="LEAK"):
        foundry_run.schedule_rest(_train(), {"game_id": "hi", "outcome": 1}, True)
    with pytest.raises(AssertionError, match="LEAK"):
        foundry_run.schedule_rest(_train(), {"game_id": "hi", "devig_close_prob": 0.5}, True)


def test_train_row_missing_outcome_raises():
    bad = _train()
    del bad[10]["outcome"]  # a redacted (test-style) view smuggled into train
    with pytest.raises(KeyError):
        foundry_run.schedule_rest(bad, {"game_id": "hi"}, True)


def test_valid_probability_and_signal_direction():
    p_hi = foundry_run.schedule_rest(_train(), {"game_id": "hi"}, True)
    p_lo = foundry_run.schedule_rest(_train(), {"game_id": "lo"}, True)
    assert 0.0 <= p_lo <= 1.0 and 0.0 <= p_hi <= 1.0
    assert p_hi > p_lo  # the logistic link actually uses the standardized signal


def test_missing_signal_falls_back_without_peeking():
    p = foundry_run.schedule_rest(_train(), {"game_id": "unknown-game"}, True)
    assert 0.0 <= p <= 1.0


def test_short_train_returns_base_rate():
    train = [{"game_id": f"g{i}", "outcome": 1} for i in range(5)]
    p = foundry_run.schedule_rest(train, {"game_id": "hi"}, True)
    assert p == pytest.approx(1.0 - 1e-4)
