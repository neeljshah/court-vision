"""
test_game_pace_fix.py -- Tests for the pace-model leakage fix (PRED-01).

The pace model's target was (home_season_pace + away_season_pace)/2 — identical
to the `pace_avg` feature, a 100% leakage that produced a fake R²=1.0. The fix
makes the target the realised box-score pace. These tests cover the new
_observed_game_pace() estimator.
"""

from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.game_models import _observed_game_pace  # noqa: E402


def _team(fga, oreb, tov, fta, minutes=240):
    return {"FGA": fga, "OREB": oreb, "TOV": tov, "FTA": fta, "MIN": minutes}


def test_regulation_game_pace_from_box_score():
    """Possessions = FGA − OREB + TOV + 0.44·FTA, averaged over both teams."""
    home = _team(fga=88, oreb=10, tov=14, fta=22)   # 88-10+14+9.68 = 101.68
    away = _team(fga=85, oreb=9,  tov=13, fta=20)   # 85-9+13+8.8   = 97.80
    pace = _observed_game_pace(home, away)
    assert pace == round((101.68 + 97.80) / 2, 2)   # 99.74


def test_overtime_game_normalised_to_per_48():
    """An OT game's raw possessions are scaled back to a per-48 pace."""
    home = _team(fga=88, oreb=10, tov=14, fta=22, minutes=265)  # 1 OT
    away = _team(fga=85, oreb=9,  tov=13, fta=20, minutes=265)
    reg = _observed_game_pace(_team(88, 10, 14, 22), _team(85, 9, 13, 20))
    ot  = _observed_game_pace(home, away)
    # Same box line over more minutes -> lower per-48 pace.
    assert ot < reg


def test_pace_is_not_the_season_average_identity():
    """The realised pace is computed from the box score, not a season prior.

    Two teams with identical season paces can still post very different
    realised game paces — which the old leaky target could never capture.
    """
    fast = _observed_game_pace(_team(95, 8, 16, 24), _team(94, 9, 15, 22))
    slow = _observed_game_pace(_team(78, 12, 9, 14), _team(76, 11, 10, 13))
    assert fast > slow
    assert abs(fast - slow) > 5.0   # genuine spread, not a constant


def test_missing_box_score_returns_sentinel():
    """Absent box-score stats return the −1.0 sentinel for caller fallback."""
    assert _observed_game_pace({}, {}) == -1.0


def test_minutes_reported_as_game_minutes():
    """A feed reporting MIN as 48 (game minutes) is handled like 240 (team)."""
    box = dict(fga=88, oreb=10, tov=14, fta=22)
    team_min = _observed_game_pace(_team(**box, minutes=240), _team(**box, minutes=240))
    game_min = _observed_game_pace(_team(**box, minutes=48), _team(**box, minutes=48))
    assert team_min == game_min


def test_pace_in_realistic_nba_range():
    """A typical NBA box score yields a pace in the realistic 90–110 range."""
    pace = _observed_game_pace(_team(87, 10, 13, 21), _team(86, 9, 14, 20))
    assert 90.0 <= pace <= 110.0


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
