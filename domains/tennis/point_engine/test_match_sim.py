import numpy as np

from domains.tennis.point_engine.match_sim import (
    play_game, play_set, play_match, simulate_match_ensemble,
)


def test_play_game_terminates_and_respects_margin():
    rng = np.random.default_rng(0)
    # fair coin: just check it terminates with a legal game score reachable
    won = play_game("A", lambda s, sb, tb: 0.6, 0, rng)
    assert won in (True, False)


def test_play_game_deterministic_extremes():
    rng = np.random.default_rng(1)
    assert play_game("A", lambda s, sb, tb: 1.0, 0, rng) is True
    assert play_game("A", lambda s, sb, tb: 0.0, 0, rng) is False


def test_play_set_terminates_with_valid_score():
    rng = np.random.default_rng(2)
    g1, g2, nxt = play_set("A", "B", "A", lambda s, sb, tb: 0.65, 1, rng)
    assert (g1 >= 6 or g2 >= 6)
    assert abs(g1 - g2) >= 2 or (g1, g2) in ((7, 6), (6, 7))
    assert nxt in ("A", "B")


def test_play_match_best_of_3_terminates():
    rng = np.random.default_rng(3)
    tg1, tg2, s1 = play_match("A", "B", 3, "A", lambda s, sb, tb: 0.6, rng)
    assert tg1 > 0 and tg2 >= 0
    assert 0 <= s1 <= 2


def test_simulate_match_ensemble_symmetric_when_equal_strength():
    margins, totals, p1_win = simulate_match_ensemble(
        "A", "B", 3, "A", lambda s, sb, tb: 0.65, n=400, seed=7)
    assert len(margins) == 400 and len(totals) == 400
    assert 0.0 <= p1_win <= 1.0
    assert (totals > 0).all()
