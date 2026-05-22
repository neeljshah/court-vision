"""
test_prop_pergame.py -- Tests for per-game prop models (PRED-13).

Per-game training: each row is one game, features come only from prior
games, the target is that game's realised stat line. These tests pin the
leakage-free feature construction and the training contract.
"""

from __future__ import annotations

import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS,
    _ewma,
    build_pergame_dataset,
    feature_columns,
    train_pergame_models,
)


def _game(date: str, matchup: str, pts, reb, ast, minutes=30.0,
          fg3m=2, stl=1, blk=0, tov=2) -> dict:
    return {"GAME_DATE": date, "MATCHUP": matchup, "PTS": pts, "REB": reb,
            "AST": ast, "FG3M": fg3m, "STL": stl, "BLK": blk, "TOV": tov,
            "MIN": minutes}


def _write_gamelog(tmp_path, pid: str, games: list) -> None:
    (tmp_path / f"gamelog_{pid}_2024-25.json").write_text(
        json.dumps(games), encoding="utf-8")


# ── EWMA recency ──────────────────────────────────────────────────────────────

def test_ewma_weights_recent_games_more():
    """EWMA of an improving series is pulled toward the most recent value."""
    rising = [10.0, 12.0, 14.0, 16.0, 30.0]   # last game a spike
    assert _ewma(rising) > sum(rising) / len(rising)   # above the flat mean


def test_ewma_empty_is_zero():
    assert _ewma([]) == 0.0


# ── feature columns ───────────────────────────────────────────────────────────

def test_feature_columns_are_leakage_free():
    """Every feature is a prior-game form metric or game context — no target."""
    cols = feature_columns()
    assert "rest_days" in cols and "is_home" in cols
    assert all(not c.startswith("target_") for c in cols)
    # 5 form features x 8 stats + 3 context.
    assert len(cols) == 5 * 8 + 3


# ── dataset construction ──────────────────────────────────────────────────────

def test_dataset_emits_rows_with_prior_history(tmp_path):
    """Rows are emitted only once a player has min_prior prior played games."""
    games = [_game(f"Jan {d:02d}, 2025", "SAS vs. TOR", 10 + d, 5, 4)
             for d in range(1, 16)]
    _write_gamelog(tmp_path, "1", games)
    rows, cols = build_pergame_dataset(str(tmp_path), min_prior=6)
    # 15 games, first 6 are history -> 9 training rows.
    assert len(rows) == 9
    assert all("target_pts" in r and "date" in r for r in rows)
    assert all(c in rows[0] for c in cols)


def test_dnp_games_are_not_training_rows(tmp_path):
    """A game the player sat out (MIN=0) is not emitted as a training row."""
    games = [_game(f"Jan {d:02d}, 2025", "SAS @ TOR", 20, 6, 5) for d in range(1, 11)]
    games.append(_game("Jan 15, 2025", "SAS vs. TOR", 0, 0, 0, minutes=0.0))  # DNP
    games.append(_game("Jan 17, 2025", "SAS vs. TOR", 25, 7, 6))
    _write_gamelog(tmp_path, "2", games)
    rows, _ = build_pergame_dataset(str(tmp_path), min_prior=6)
    # No row should carry the DNP game's zero line as a target.
    assert all(not (r["target_pts"] == 0 and r["target_reb"] == 0) for r in rows)


def test_home_away_flag_parsed_from_matchup(tmp_path):
    """is_home is 1 for a 'vs.' matchup, 0 for an '@' matchup."""
    games = [_game(f"Jan {d:02d}, 2025", "SAS vs. TOR", 20, 6, 5) for d in range(1, 9)]
    games.append(_game("Jan 12, 2025", "SAS @ TOR", 18, 5, 4))   # away game
    _write_gamelog(tmp_path, "3", games)
    rows, _ = build_pergame_dataset(str(tmp_path), min_prior=6)
    assert rows[-1]["is_home"] == 0.0
    assert rows[0]["is_home"] == 1.0


def test_features_use_only_prior_games(tmp_path):
    """A row's rolling features reflect prior games, never the current one."""
    games = [_game(f"Jan {d:02d}, 2025", "SAS vs. TOR", 10, 5, 5) for d in range(1, 9)]
    games.append(_game("Jan 12, 2025", "SAS vs. TOR", 99, 5, 5))   # huge spike
    _write_gamelog(tmp_path, "4", games)
    rows, _ = build_pergame_dataset(str(tmp_path), min_prior=6)
    last = rows[-1]
    # The spike is the TARGET; the prior-form features must not include it.
    assert last["target_pts"] == 99.0
    assert last["l5_pts"] == 10.0          # all prior games scored 10


# ── training ──────────────────────────────────────────────────────────────────

def test_train_reports_honest_holdout(tmp_path):
    """Training yields a temporal-holdout R²/MAE per stat (not a 0.99 identity)."""
    import random
    rng = random.Random(0)
    # 40 players x 40 games — realistic noisy per-game lines.
    for pid in range(40):
        base = rng.uniform(8, 28)
        games = []
        for d in range(1, 41):
            pts = max(0, base + rng.gauss(0, 6))
            month, day = ("Jan", d) if d <= 28 else ("Feb", d - 28)
            games.append(_game(f"{month} {day:02d}, 2025",
                                "SAS vs. TOR" if d % 2 else "SAS @ TOR",
                                round(pts), rng.randint(2, 10), rng.randint(1, 9),
                                fg3m=rng.randint(0, 6), stl=rng.randint(0, 4),
                                blk=rng.randint(0, 3), tov=rng.randint(0, 5)))
        _write_gamelog(tmp_path, str(pid), games)

    metrics = train_pergame_models(
        gamelog_dir=str(tmp_path), model_dir=str(tmp_path), min_prior=6,
    )
    assert metrics["n_rows"] > 200
    for stat in STATS:
        m = metrics["stats"][stat]
        # Honest holdout — must NOT be a fake near-1.0 identity fit.
        assert -1.0 <= m["holdout_r2"] <= 0.95
        assert m["holdout_mae"] >= 0.0
        assert os.path.exists(tmp_path / f"props_pg_{stat}.json")


def test_train_insufficient_data_returns_status(tmp_path):
    """A near-empty gamelog dir returns a clean status, not a crash."""
    result = train_pergame_models(gamelog_dir=str(tmp_path), model_dir=str(tmp_path))
    assert result["status"] == "insufficient_data"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
