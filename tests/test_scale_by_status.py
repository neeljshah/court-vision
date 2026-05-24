"""Cycle 66: tests for predict_player.apply_minutes_scaling + --scale-by-status."""
from __future__ import annotations

import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.predict_player as pp  # noqa: E402


def _preds():
    return {"pts": 28.4, "reb": 12.1, "ast": 9.8,
            "fg3m": 1.5, "stl": 0.8, "blk": 0.4, "tov": 3.1}


def test_starter_classification_no_scaling():
    """Starter factor is 1.0 — values are unchanged."""
    p = _preds()
    out = pp.apply_minutes_scaling(p, "starter")
    assert out == p
    # And it should NOT be the same dict object (pure function semantics).
    assert out is not p


def test_questionable_scales_to_75pct():
    out = pp.apply_minutes_scaling(_preds(), "questionable")
    # PTS 28.4 * 0.75 = 21.30
    assert out["pts"] == pytest.approx(21.30)
    assert out["reb"] == pytest.approx(9.08, abs=0.01)
    assert out["ast"] == pytest.approx(7.35)


def test_bench_scales_to_30pct():
    out = pp.apply_minutes_scaling(_preds(), "bench")
    # PTS 28.4 * 0.30 = 8.52
    assert out["pts"] == pytest.approx(8.52)
    assert out["fg3m"] == pytest.approx(0.45)


def test_no_game_zeros_predictions():
    out = pp.apply_minutes_scaling(_preds(), "no-game")
    assert all(v == 0.0 for v in out.values())


def test_unknown_classification_no_scaling():
    """Unknown lineup state → factor 1.0 (don't silently zero predictions)."""
    out = pp.apply_minutes_scaling(_preds(), "unknown")
    assert out == _preds()


def test_unrecognized_classification_defaults_to_one():
    """Defensive: if a future caller passes a typo'd classification,
    don't crash and don't silently scale to 0."""
    out = pp.apply_minutes_scaling(_preds(), "spaceship")
    assert out == _preds()


def test_scaling_propagates_through_empty_dict():
    assert pp.apply_minutes_scaling({}, "questionable") == {}
    assert pp.apply_minutes_scaling({}, "starter") == {}


def test_status_scale_table_matches_design():
    """Lock in the design values so future changes are explicit."""
    assert pp._STATUS_SCALE["starter"] == 1.00
    assert pp._STATUS_SCALE["questionable"] == 0.75
    assert pp._STATUS_SCALE["bench"] == 0.30
    assert pp._STATUS_SCALE["no-game"] == 0.00
    assert pp._STATUS_SCALE["unknown"] == 1.00


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
