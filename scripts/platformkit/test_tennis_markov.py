"""Focused checks for the tennis Markov backbone."""
import math

from scripts.platformkit.tennis_markov import (
    calibrate_from_history,
    game_win_prob,
    match_win_prob,
    set_win_prob,
    win_prob,
)


def test_symmetric_players_are_fifty_fifty_at_symmetric_states():
    assert math.isclose(game_win_prob(0.5), 0.5, abs_tol=1e-12)
    assert math.isclose(set_win_prob(0.5, 0.5), 0.5, abs_tol=1e-12)
    assert math.isclose(match_win_prob(0.5, 0.5), 0.5, abs_tol=1e-12)
    for state in (
        (0, 0, 0, 0, 0, 0, "A"),
        (0, 0, 3, 3, 3, 3, "B"),
        (1, 1, 5, 5, 2, 2, "A"),
        (1, 1, 6, 6, 6, 6, "B"),
    ):
        assert math.isclose(win_prob(state, 0.5, 0.5), 0.5, abs_tol=1e-12)


def test_omalley_game_formula_is_independently_reproduced():
    p, q = 0.65, 0.35
    expected = p**4 * (1 + 4 * q + 10 * q**2)
    expected += 20 * p**3 * q**3 * (p**2 / (p**2 + q**2))
    assert abs(game_win_prob(p) - expected) < 1e-6
    assert 0.0 < game_win_prob(0.60) < 1.0


def test_leading_state_is_never_worse_than_trailing_state():
    leading = win_prob((0, 0, 4, 2, 0, 0, "A"), 0.65, 0.60)
    trailing = win_prob((0, 0, 2, 4, 0, 0, "A"), 0.65, 0.60)
    point_leading = win_prob((0, 0, 3, 3, 3, 2, "B"), 0.65, 0.60)
    point_trailing = win_prob((0, 0, 3, 3, 2, 3, "B"), 0.65, 0.60)
    assert leading >= trailing
    assert point_leading >= point_trailing


def test_history_calibration_skips_without_local_data():
    result = calibrate_from_history([])
    assert result["status"] == "skipped"
    assert "research-use" in result["note"]


def test_history_calibration_uses_both_sides_service_points():
    result = calibrate_from_history([
        {"w_svpt": 10, "w_1stWon": 4, "w_2ndWon": 2,
         "l_svpt": 10, "l_1stWon": 3, "l_2ndWon": 1},
    ])
    assert result["status"] == "ok"
    assert result["n_service_points"] == 20
    assert math.isclose(result["p_serve_prior"], 0.5)
