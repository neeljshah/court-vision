"""Tests for the rest-asymmetry conditional-frequency producer.

A synthetic schedule with hand-counted cells proves the conditional counts and
frequencies, the mask floor, the contrast against the equal-rest baseline, the
devig, the game-cluster resampling and the interval shape. Two fixtures guard
the joins and masks that silently produced wrong numbers before: a THIN equal-
rest baseline must mask every contrast built on it, and an odds table that
fans out on the join key must fail loudly instead of double-counting games.

Run: python -m pytest scripts/platformkit/test_novel_rest_asymmetry.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.novel_rest_asymmetry import (
    CELLS, CONGESTION, MIN_GAMES_PER_CELL, contrast_panel, devig, frequency_panel,
    load_games, load_market, replicates, rest_cell,
)

# (rest_diff, n_games, n_home_wins, home_rest_days) -- hand-counted cells.
FIXTURE = [(2, 40, 30, 3), (0, 40, 20, 2), (0, 30, 15, 1), (-1, 10, 1, 1)]


def _schedule() -> pd.DataFrame:
    """Synthetic games.parquet: 120 games whose per-cell counts are known by construction."""
    rows = []
    for diff, total, wins, home_rest in FIXTURE:
        for i in range(total):
            away_rest = home_rest - diff
            rows.append({
                "game_id": "%+d-r%d-%03d" % (diff, home_rest, i),  # unique: two blocks share diff 0
                "date": "2026-01-%02d" % (1 + i % 28),
                "season": "2025-26",
                "home_team": "H%d" % (i % 5),
                "away_team": "A%d" % (i % 5),
                "home_win": 1.0 if i < wins else 0.0,
                "rest_days_home": float(home_rest),
                "rest_days_away": float(away_rest),
                "home_b2b": home_rest == 1,
                "away_b2b": away_rest == 1,
            })
    return pd.DataFrame(rows)


@pytest.fixture()
def games(tmp_path) -> pd.DataFrame:
    path = tmp_path / "games.parquet"
    frame = _schedule()
    frame.loc[0, "rest_days_home"] = np.nan  # a missing rest day must be dropped, not binned
    extra = frame.iloc[[1]].copy()
    extra["game_id"], extra["home_win"] = "no-label", np.nan  # a missing outcome is a SEPARATE reason
    pd.concat([frame, extra], ignore_index=True).to_parquet(path, index=False)
    return load_games(path)


def _thin_baseline(tmp_path) -> pd.DataFrame:
    """A schedule whose equal-rest baseline holds one game: every contrast on it is unusable."""
    rows = [{"game_id": "eq-0", "date": "2026-01-01", "season": "2025-26", "home_team": "H0",
             "away_team": "A0", "home_win": 0.0, "rest_days_home": 2.0, "rest_days_away": 2.0,
             "home_b2b": False, "away_b2b": False}]
    rows += [dict(rows[0], game_id="hi-%02d" % i, home_win=1.0, rest_days_home=4.0,
                  rest_days_away=2.0) for i in range(40)]
    path = tmp_path / "thin.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)
    return load_games(path)


def test_rest_cell_bins_and_clips():
    assert [rest_cell(d) for d in (-9, -2, -1, 0, 1, 2, 7)] == [
        CELLS[0], CELLS[0], CELLS[1], CELLS[2], CELLS[3], CELLS[4], CELLS[4]]


def test_devig_normalizes_a_moneyline_pair():
    probs = devig(np.array([-110.0, -200.0, 150.0]), np.array([-110.0, 170.0, -180.0]))
    assert probs[0] == pytest.approx(0.5)
    assert probs[1] == pytest.approx((200 / 300) / ((200 / 300) + (100 / 270)), rel=1e-9)
    assert np.all((probs > 0) & (probs < 1))


def test_load_games_separates_the_two_exclusion_reasons(games):
    assert len(games) == 119
    assert games.attrs["coverage"] == {"games_in_source": 121, "dropped_games_missing_outcome": 1,
                                       "dropped_games_missing_rest": 1}
    assert games["cell"].value_counts().to_dict() == {
        CELLS[2]: 70, CELLS[4]: 39, CELLS[1]: 10}
    equal = games.loc[games["rest_diff"].eq(0), "congestion"].value_counts().to_dict()
    assert equal == {CONGESTION[2]: 40, CONGESTION[0]: 30}


def test_conditional_counts_and_frequencies(games):
    cells = {row["cell"]: row for row in frequency_panel(games, CELLS, "cell")}
    equal, rested = cells[CELLS[2]], cells[CELLS[4]]
    assert (equal["n_games"], rested["n_games"]) == (70, 39)
    assert equal["home_win_frequency"] == pytest.approx(35 / 70, abs=1e-4)
    assert rested["home_win_frequency"] == pytest.approx(29 / 39, abs=1e-4)
    assert equal["masked"] is False and rested["masked"] is False


def test_mask_floor_keeps_the_count_and_drops_the_estimate(games):
    cells = {row["cell"]: row for row in frequency_panel(games, CELLS, "cell")}
    thin, empty = cells[CELLS[1]], cells[CELLS[0]]
    assert thin["n_games"] == 10 and thin["n_games"] < MIN_GAMES_PER_CELL
    assert thin["masked"] is True
    assert thin["home_win_frequency"] is None and thin["ci95"] == [None, None]
    assert thin["mask_reason"] == "fewer than %d games" % MIN_GAMES_PER_CELL
    assert empty["n_games"] == 0 and empty["mask_reason"] == "no games in this cell"


def test_interval_shape_brackets_the_point_estimate(games):
    for row in frequency_panel(games, CELLS, "cell"):
        low, high = row["ci95"]
        if row["masked"]:
            assert (low, high) == (None, None)
            continue
        assert isinstance(low, float) and isinstance(high, float)
        assert 0.0 <= low < high <= 1.0
        assert low <= row["home_win_frequency"] <= high


def test_contrast_is_paired_against_the_equal_cell(games):
    rows = {row["cell"]: row for row in contrast_panel(games)}
    assert CELLS[2] not in rows
    rested = rows[CELLS[4]]
    assert rested["delta_vs_equal"] == pytest.approx(29 / 39 - 35 / 70, abs=1e-4)
    low, high = rested["ci95"]
    assert low < rested["delta_vs_equal"] < high
    assert rested["excludes_zero"] is (low > 0 or high < 0)


def test_a_thin_equal_rest_baseline_masks_every_contrast(tmp_path):
    # Before the fix only the focal cell was checked against the floor, so this
    # one-game baseline published an unmasked difference of 1.0, CI [1.0, 1.0].
    frame = _thin_baseline(tmp_path)
    assert frame.loc[frame["rest_diff"].eq(0)].shape[0] == 1
    rows = contrast_panel(frame)
    assert len(rows) == len(CELLS) - 1
    for row in rows:
        assert row["masked"] is True
        assert row["delta_vs_equal"] is None and row["ci95"] == [None, None]
        assert row["excludes_zero"] is None
    assert {row["cell"]: row["n_games"] for row in rows}[CELLS[4]] == 40


def test_market_join_rejects_a_fanned_out_odds_table(tmp_path, games):
    duplicated = pd.DataFrame([
        {"date": "2026-01-01", "home_team": "H0", "away_team": "A0",
         "home_ml": -150.0, "away_ml": 130.0},
        {"date": "2026-01-01", "home_team": "H0", "away_team": "A0",
         "home_ml": -155.0, "away_ml": 135.0},
    ])
    path = tmp_path / "dup_odds.parquet"
    duplicated.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="duplicate game ids"):
        load_market(games, path)


def test_replicates_resample_whole_game_clusters():
    clusters = np.array(["g1", "g1", "g1", "g2", "g3"])
    draws = replicates(clusters, n_boot=25, seed=7)
    assert len(draws) == 25
    for idx in draws:
        counts = pd.Series(clusters[idx]).value_counts()
        assert counts.sum() == len(idx)
        # every drawn g1 arrives as its whole 3-row cluster
        assert counts.get("g1", 0) % 3 == 0


def test_market_join_attaches_a_devigged_forecast(tmp_path, games):
    odds = pd.DataFrame([
        {"date": "2026-01-01", "home_team": "H0", "away_team": "A0",
         "home_ml": -150.0, "away_ml": 130.0},
        {"date": "2026-01-02", "home_team": "H1", "away_team": "A1",
         "home_ml": np.nan, "away_ml": 130.0},
    ])
    path = tmp_path / "odds.parquet"
    odds.to_parquet(path, index=False)
    market = load_market(games, path)
    assert len(market) == len(games.loc[games["join_date"].eq("2026-01-01")
                                        & games["home_team"].eq("H0")])
    assert market["market_prob"].between(0.5, 0.7).all()
    assert market.attrs["duplicate_game_ids"] == 0
    assert not market["game_id"].duplicated().any()
