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
from datetime import datetime


def _dt(s: str) -> datetime:
    """Parse an NBA gamelog date string for tests."""
    return datetime.strptime(s, "%b %d, %Y")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS,
    _RestTravel,
    _ewma,
    build_opponent_defense,
    build_pergame_dataset,
    build_rest_travel,
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
    """Every feature is a prior-game form metric, game context, or opponent
    defence — never the target."""
    cols = feature_columns()
    assert "rest_days" in cols and "is_home" in cols
    assert all(not c.startswith("target_") for c in cols)
    assert all(f"opp_def_{s}" in cols for s in STATS)
    # 5 form x 8 stats + 3 context + 7 opp_def + 4 rest/travel + 9 playtype + 12 bbref.
    assert len(cols) == 5 * 8 + 3 + 7 + 4 + 9 + 12


def test_feature_columns_include_rest_travel():
    """feature_columns() includes the 4 new rest/travel schedule features."""
    cols = feature_columns()
    for name in ("is_b2b", "is_b3b", "miles_traveled", "altitude_ft"):
        assert name in cols, f"Missing rest/travel feature: {name}"


def test_build_rest_travel_neutral_defaults_for_unknown_key():
    """_RestTravel returns neutral defaults for any (date, team) not in the parquet."""
    rt = build_rest_travel()   # parquet absent in test env -> empty lookup
    from datetime import datetime
    feats = rt.features("XXX", datetime(2025, 1, 15))
    assert feats["is_b2b"] == 0.0
    assert feats["is_b3b"] == 0.0
    assert feats["miles_traveled"] == 0.0
    assert feats["altitude_ft"] == 0.0


def test_build_pergame_dataset_has_rest_travel_columns(tmp_path):
    """build_pergame_dataset() includes all 4 rest/travel columns in every row
    even when no rest_travel.parquet exists (neutral defaults applied)."""
    import math
    games = [_game(f"Jan {d:02d}, 2025", "SAS vs. TOR", 10 + d, 5, 4)
             for d in range(1, 16)]
    (tmp_path / "gamelog_10_2024-25.json").write_text(
        json.dumps(games), encoding="utf-8")
    rows, cols = build_pergame_dataset(str(tmp_path), min_prior=6)
    assert len(rows) > 0
    for name in ("is_b2b", "is_b3b", "miles_traveled", "altitude_ft"):
        assert name in cols, f"feature_columns() missing {name}"
        for row in rows:
            assert name in row, f"Row missing key {name}"
            assert math.isfinite(row[name]), f"{name} is not finite in row"


def test_opponent_defense_is_to_date_only(tmp_path):
    """Opponent-defence factors use only games before the query date — no leak."""
    # SAS allows big lines early, small lines late.
    sas_games = ([_game(f"Jan {d:02d}, 2025", "TOR @ SAS", 40, 12, 10) for d in range(1, 9)]
                 + [_game(f"Feb {d:02d}, 2025", "TOR @ SAS", 4, 1, 1) for d in range(1, 9)])
    (tmp_path / "gamelog_99_2024-25.json").write_text(json.dumps(sas_games), encoding="utf-8")
    # A control opponent (DEN) with steady lines so the league baseline is stable.
    den_games = ([_game(f"Jan {d:02d}, 2025", "TOR @ DEN", 20, 6, 5) for d in range(9, 17)]
                 + [_game(f"Feb {d:02d}, 2025", "TOR @ DEN", 20, 6, 5) for d in range(9, 17)])
    (tmp_path / "gamelog_100_2024-25.json").write_text(json.dumps(den_games), encoding="utf-8")

    oppdef = build_opponent_defense(str(tmp_path))
    early = oppdef.factors("SAS", _dt("Jan 20, 2025"))   # only SAS's big lines seen
    late = oppdef.factors("SAS", _dt("Feb 20, 2025"))    # big + small lines seen
    # Early query sees only the inflated lines -> a higher allowed factor.
    assert early["opp_def_pts"] > late["opp_def_pts"]


def test_opponent_defense_neutral_without_history(tmp_path):
    """An unknown opponent / no prior games yields a neutral 1.0 factor."""
    oppdef = build_opponent_defense(str(tmp_path))
    factors = oppdef.factors("XXX", _dt("Jan 01, 2025"))
    assert all(v == 1.0 for v in factors.values())


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
