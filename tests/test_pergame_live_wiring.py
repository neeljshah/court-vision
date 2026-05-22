"""
test_pergame_live_wiring.py -- Tests for per-game models in the live path (PRED-16).

predict_props now prefers the honest per-game models (trained one-row-per-game
on real game logs) over the legacy season-average models, falling back
gracefully when a player's gamelog is unavailable.
"""

from __future__ import annotations

import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction import prop_pergame  # noqa: E402
from src.prediction.prop_pergame import (  # noqa: E402
    STATS,
    build_prediction_row,
    predict_player_pergame,
    train_pergame_models,
)


def _game(date: str, matchup: str, pts, reb, ast, minutes=30.0,
          fg3m=2, stl=1, blk=0, tov=2) -> dict:
    return {"GAME_DATE": date, "MATCHUP": matchup, "PTS": pts, "REB": reb,
            "AST": ast, "FG3M": fg3m, "STL": stl, "BLK": blk, "TOV": tov,
            "MIN": minutes}


def _seed_gamelogs(tmp_path, n_players: int = 30, n_games: int = 40) -> None:
    """Write synthetic gamelogs and clear the opponent-defence cache."""
    import random
    rng = random.Random(0)
    for pid in range(n_players):
        base = rng.uniform(8, 26)
        games = []
        for d in range(1, n_games + 1):
            month, day = ("Jan", d) if d <= 28 else ("Feb", d - 28)
            games.append(_game(f"{month} {day:02d}, 2025",
                                "SAS vs. TOR" if d % 2 else "SAS @ TOR",
                                max(0, round(base + rng.gauss(0, 6))),
                                rng.randint(2, 10), rng.randint(1, 9),
                                fg3m=rng.randint(0, 6), stl=rng.randint(0, 4),
                                blk=rng.randint(0, 3), tov=rng.randint(0, 5)))
        (tmp_path / f"gamelog_{pid}_2024-25.json").write_text(
            json.dumps(games), encoding="utf-8")
    prop_pergame._OPP_DEF_CACHE.clear()


def test_build_prediction_row_has_all_features(tmp_path):
    """The live feature row carries every column the models expect."""
    _seed_gamelogs(tmp_path)
    row = build_prediction_row(5, "TOR", "2024-25", gamelog_dir=str(tmp_path))
    assert row is not None
    from src.prediction.prop_pergame import feature_columns
    assert all(c in row for c in feature_columns())


def test_build_prediction_row_missing_gamelog_returns_none(tmp_path):
    """No gamelog for the player -> None (caller falls back)."""
    assert build_prediction_row(999, "TOR", "2024-25", gamelog_dir=str(tmp_path)) is None


def test_predict_player_pergame_end_to_end(tmp_path):
    """Train per-game models then predict a player's upcoming game."""
    _seed_gamelogs(tmp_path)
    metrics = train_pergame_models(gamelog_dir=str(tmp_path), model_dir=str(tmp_path))
    assert metrics["n_rows"] > 200

    preds = predict_player_pergame(
        7, "TOR", "2024-25", gamelog_dir=str(tmp_path), model_dir=str(tmp_path),
    )
    assert preds is not None
    assert set(preds.keys()) == set(STATS)
    assert all(v >= 0.0 for v in preds.values())


def test_predict_player_pergame_no_models_returns_none(tmp_path):
    """With gamelogs but no trained models, prediction returns None."""
    _seed_gamelogs(tmp_path)
    preds = predict_player_pergame(
        7, "TOR", "2024-25", gamelog_dir=str(tmp_path), model_dir=str(tmp_path),
    )
    assert preds is None   # no props_pg_*.json in this empty model dir


def test_opponent_defense_cache_reused(tmp_path):
    """The opponent-defence model is built once and process-cached."""
    _seed_gamelogs(tmp_path)
    build_prediction_row(1, "TOR", "2024-25", gamelog_dir=str(tmp_path))
    assert str(tmp_path) in prop_pergame._OPP_DEF_CACHE
    cached = prop_pergame._OPP_DEF_CACHE[str(tmp_path)]
    build_prediction_row(2, "TOR", "2024-25", gamelog_dir=str(tmp_path))
    # Same object — not rebuilt.
    assert prop_pergame._OPP_DEF_CACHE[str(tmp_path)] is cached


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
