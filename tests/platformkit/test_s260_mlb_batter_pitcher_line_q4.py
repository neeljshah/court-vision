"""S260 evaluator capability limit check.

Run: python -m pytest tests/platformkit/test_s260_mlb_batter_pitcher_line_q4.py -q -p no:cacheprovider
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.walkforward import walk_forward


def _states() -> list[dict[str, object]]:
    start = datetime(2024, 1, 1, 12, 0, 0)
    return [
        {
            "game_id": "s260-{0}".format(index),
            "state_ts": (start + timedelta(days=index)).isoformat(),
            "features": {"player": "p{0}".format(index)},
            "feature_avail": {"player": (start + timedelta(days=index, seconds=-1)).isoformat()},
            "home": "S260_HOME",
            "away": "S260_AWAY",
            "outcome": index % 2,
        }
        for index in range(4)
    ]


def _empirical_callback(_train: list[dict], _test: dict, _inside: bool) -> list[float]:
    return [0.0, 1.0]


def test_shared_evaluators_reject_empirical_distribution_callback():
    """The current public route accepts only scalar binary predictions."""
    with pytest.raises(TypeError, match="not supported"):
        walk_forward(_states(), _empirical_callback)
    with pytest.raises(TypeError, match="not supported"):
        cpcv_evaluate(_states(), _empirical_callback, n_groups=2, n_test_groups=1)
