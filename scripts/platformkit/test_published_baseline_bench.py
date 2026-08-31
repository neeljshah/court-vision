"""Focused checks for the NFL published-baseline scoreboard."""
import pandas as pd
import pytest

from scripts.platformkit.published_baseline_bench import devig_moneyline, elo_probabilities


def _game(day, game_id, home_win):
    return {"gameday": day, "game_id": game_id, "home_team": "A", "away_team": "B", "home_win": home_win}


def test_elo_test_predictions_do_not_use_later_test_results():
    train = pd.DataFrame([_game("2022-09-01", "train", 1)])
    base = pd.DataFrame([_game("2023-09-01", "first", 0), _game("2023-09-08", "second", 1)])
    extended = pd.concat([base, pd.DataFrame([_game("2023-09-15", "future", 0)])], ignore_index=True)
    assert elo_probabilities(train, base).tolist() == elo_probabilities(train, extended)[:2].tolist()


def test_two_way_american_moneyline_devig_is_exact():
    home, away = devig_moneyline(-110, -110)
    assert home == pytest.approx(0.5)
    assert away == pytest.approx(0.5)
    home, away = devig_moneyline(-200, 150)
    assert home == pytest.approx(0.625)
    assert away == pytest.approx(0.375)
