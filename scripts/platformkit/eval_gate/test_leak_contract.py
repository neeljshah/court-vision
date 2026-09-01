"""Regression coverage for eval-gate leak failures, including python -O."""
from __future__ import annotations

import subprocess
import sys

import pytest

from scripts.platformkit.eval_gate.schema import validate_golden
from scripts.platformkit.eval_gate.walkforward import LeakError, assert_vintage, walk_forward


def _state(game_id: str = "g0") -> dict:
    return {
        "game_id": game_id,
        "season": "2024-25",
        "sport": "nba",
        "regime": "pregame",
        "game_date": "2025-03-07",
        "state_ts": "2025-03-07T19:00:00",
        "features": {"x": 0.5},
        "feature_avail": {"x": "2025-03-06T00:00:00"},
        "devig_close_prob": 0.5,
        "truth_wp": 0.5,
        "outcome": 1,
        "home": "A",
        "away": "B",
    }


def _golden_states() -> list[dict]:
    regimes = ("pregame", "q4", "blowout", "foul_trouble")
    states = []
    for i in range(90):
        state = _state(f"g{i}")
        state["regime"] = regimes[i % len(regimes)]
        state["state_ts"] = f"2025-03-07T{(i % 24):02d}:00:00"
        state["feature_avail"] = {"x": "2025-03-06T00:00:00"}
        states.append(state)
    return states


def test_predictor_cannot_read_outcome():
    with pytest.raises(KeyError):
        walk_forward([_state()], lambda train, test, select_inside: float(test["outcome"]))


def test_space_separated_same_day_later_availability_leaks():
    state = _state()
    state["feature_avail"] = {"x": "2025-03-07 23:59:59"}
    with pytest.raises(LeakError):
        assert_vintage(state)


def test_date_only_availability_leaks():
    state = _state()
    state["feature_avail"] = {"x": "2025-03-07"}
    with pytest.raises(LeakError):
        assert_vintage(state)


def test_mixed_aware_and_naive_timestamps_leak():
    state = _state()
    state["feature_avail"] = {"x": "2025-03-07T20:00:00+00:00"}
    with pytest.raises(LeakError):
        assert_vintage(state)


def test_undeclared_feature_leaks_from_schema():
    states = _golden_states()
    states[0]["features"]["undeclared"] = 0.1
    with pytest.raises(LeakError):
        validate_golden(states)


def test_leak_guard_survives_optimized_python():
    code = (
        "from scripts.platformkit.eval_gate.schema import validate_golden; "
        "s={'game_id':'g','season':'2024-25','sport':'nba','regime':'pregame',"
        "'game_date':'2025-03-07','state_ts':'2025-03-07T19:00:00',"
        "'features':{'x':0.5},'feature_avail':{'x':'2025-03-07'},"
        "'devig_close_prob':0.5,'truth_wp':0.5,'outcome':1}; "
        "validate_golden([s] * 90)"
    )
    result = subprocess.run(
        [sys.executable, "-O", "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode != 0
    assert "LEAK" in result.stderr
