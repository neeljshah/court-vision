"""Tests for the starter-rest-absorption conditional-frequency producer.

A synthetic schedule with hand-counted cells proves the rest arithmetic, the
dropped first start of a season, the home/away outcome and forecast flip, the
conditional counts and frequencies, the mask floor, the paired contrast, the
devig and the game-cluster resampling.

Run: python -m pytest scripts/platformkit/test_novel_starter_rest_absorption.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.novel_starter_rest_absorption import (
    BUCKETS, LOADS, MIN_PER_CELL, SLOTS, STANDARD_IDX, contrast_panel, devig, load_games,
    panel, replicates, rest_bucket, to_starts,
)

# (starter tag, calendar gap between that team's starts, games, home wins).
# The home starter works every game, so his rest is gap - 1. The away side alternates two
# starters, so each of them works every second game and rests 2 * gap - 1. A home win is
# game i for 1 <= i <= wins, which keeps game 0 -- always dropped for having no prior
# start -- a home loss, so the counted home wins are exactly the fourth entry.
FIXTURE = [("P3", 4, 40, 10), ("P4", 5, 40, 30), ("P5", 6, 32, 15), ("P7", 8, 6, 3)]
# bucket -> (counted starts, counted wins), hand-counted from FIXTURE.
COUNTED = {"3 or fewer": (39, 10), "4": (39, 30), "5": (31, 15), "6 or more": (115, 59)}
START = pd.Timestamp("2026-04-01")


def _row(event_id, date, home_sp, away_sp, home_win, seq=1, ml=(-110.0, -110.0)):
    return {"event_id": event_id, "date": date, "season": 2026, "home_team": "H", "away_team": "A",
            "home_runs": 1.0 if home_win else 0.0, "away_runs": 0.0 if home_win else 1.0,
            "target_home_win": float(home_win), "game_seq": seq, "home_sp_name": home_sp,
            "away_sp_name": away_sp, "ml_close_home_am": ml[0], "ml_close_away_am": ml[1]}


def _schedule() -> pd.DataFrame:
    """118 grouped games plus two edge games: one unpriced, one missing a home starter."""
    rows = []
    for tag, gap, total, wins in FIXTURE:
        for i in range(total):
            seq = 2 if tag == "P4" and i == total - 1 else 1
            rows.append(_row("%s-%03d" % (tag, i), START + pd.Timedelta(days=gap * i),
                             tag, "%s-a%d" % (tag, i % 2), 1 <= i <= wins, seq))
    rows.append(_row("UNPRICED-0", START, "X", "X-away", True, ml=(np.nan, -110.0)))
    rows.append(_row("NOSTARTER-0", START, None, "Y-away", True))
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def paths(tmp_path_factory):
    """Writes the synthetic games, pitchers and odds tables and returns their three paths."""
    directory = tmp_path_factory.mktemp("mlb")
    frame = _schedule()
    games, pitchers, odds = directory / "g.parquet", directory / "p.parquet", directory / "o.parquet"
    frame[["event_id", "date", "season", "home_team", "away_team", "home_runs", "away_runs",
           "target_home_win", "game_seq"]].to_parquet(games, index=False)
    frame[["event_id", "home_sp_name", "away_sp_name"]].to_parquet(pitchers, index=False)
    frame[["event_id", "ml_close_home_am", "ml_close_away_am"]].to_parquet(odds, index=False)
    return games, pitchers, odds


@pytest.fixture(scope="module")
def games(paths):
    return load_games(*paths)


@pytest.fixture(scope="module")
def starts(games):
    return to_starts(games)


@pytest.fixture(scope="module")
def bucket_cells(starts):
    return {row["cell"]: row for row in panel(starts, BUCKETS, "bucket")}


def test_rest_bucket_bins_and_clips():
    assert [rest_bucket(r) for r in (0, 3, 4, 5, 6, 40)] == [
        BUCKETS[0], BUCKETS[0], BUCKETS[1], BUCKETS[2], BUCKETS[3], BUCKETS[3]]


def test_devig_normalizes_a_moneyline_pair():
    probs = devig(np.array([-110.0, -200.0, 150.0]), np.array([-110.0, 170.0, -180.0]))
    assert probs[0] == pytest.approx(0.5)
    assert probs[1] == pytest.approx((200 / 300) / ((200 / 300) + (100 / 270)), rel=1e-9)
    assert np.all((probs > 0) & (probs < 1))


def test_load_games_drops_an_unpriced_game_and_labels_the_nightcap(games):
    assert games.attrs["n_scheduled"] == 120
    assert len(games) == 119
    assert "UNPRICED-0" not in set(games["event_id"])
    assert games["slot"].value_counts().to_dict() == {SLOTS[0]: 118, SLOTS[1]: 1}
    assert games["forecast"].round(6).eq(0.5).all()


def test_to_starts_drops_the_first_start_and_flips_the_away_side(starts):
    assert len(starts) == sum(count for count, _ in COUNTED.values())
    assert starts.attrs["dropped_missing_starter"] == 1
    assert starts.attrs["dropped_no_prior_start"] == 13
    assert starts["bucket"].value_counts().to_dict() == {k: v[0] for k, v in COUNTED.items()}
    assert (starts["rest_days"].min(), starts["rest_days"].max()) == (3, 15)
    # 58 counted home wins and 56 counted away wins, so the away flip must land exactly here
    assert starts["outcome"].sum() == pytest.approx(114.0)
    assert set(starts["load"]) == set(LOADS)


def test_conditional_counts_and_frequencies_are_hand_counted(bucket_cells):
    for label, (count, wins) in COUNTED.items():
        cell = bucket_cells[label]
        assert (cell["n_starts"], cell["masked"]) == (count, False)
        assert cell["win_frequency"] == pytest.approx(wins / count, abs=1e-4)
        # every game is priced at an even moneyline, so the forecast is 0.5 in every cell
        assert cell["mean_reference_forecast"] == pytest.approx(0.5, abs=1e-6)
        assert cell["gap_observed_minus_reference"] == pytest.approx(wins / count - 0.5, abs=1e-4)


def test_mask_floor_keeps_the_count_and_drops_the_estimate(starts):
    cells = {row["cell"]: row for row in panel(starts, BUCKETS, "bucket", floor=100)}
    thin, kept = cells[BUCKETS[2]], cells[BUCKETS[3]]
    assert thin["n_starts"] == COUNTED["5"][0] >= MIN_PER_CELL  # masked only by the raised floor
    assert thin["masked"] is True
    assert thin["win_frequency"] is None and thin["ci95"] == [None, None]
    assert thin["gap_ci95"] == [None, None] and thin["gap_excludes_zero"] is None
    assert thin["mask_reason"] == "fewer than 100 rows"
    assert kept["masked"] is False and kept["mask_reason"] is None


def test_an_empty_cell_keeps_its_zero_count(starts):
    trimmed = starts.loc[starts["bucket"].ne(BUCKETS[2])]
    empty = {row["cell"]: row for row in panel(trimmed, BUCKETS, "bucket")}[BUCKETS[2]]
    assert empty["n_starts"] == 0 and empty["masked"] is True
    assert empty["mask_reason"] == "no rows in this cell"
    assert empty["win_frequency"] is None and empty["ci95"] == [None, None]


def test_interval_shape_brackets_the_point_estimate(bucket_cells):
    for row in bucket_cells.values():
        low, high = row["ci95"]
        assert 0.0 <= low <= row["win_frequency"] <= high <= 1.0
        gap_low, gap_high = row["gap_ci95"]
        assert gap_low <= row["gap_observed_minus_reference"] <= gap_high
        assert row["gap_excludes_zero"] is (gap_low > 0 or gap_high < 0)


def test_contrast_is_paired_against_the_standard_bucket(starts):
    rows = {row["cell"]: row for row in contrast_panel(starts, BUCKETS, "bucket", STANDARD_IDX)}
    assert BUCKETS[STANDARD_IDX] not in rows
    short = rows[BUCKETS[0]]
    assert short["delta_vs_standard"] == pytest.approx(10 / 39 - 30 / 39, abs=1e-4)
    low, high = short["ci95"]
    assert low < short["delta_vs_standard"] < high
    assert short["excludes_zero"] is True  # a 51-point gap on 39 starts a side is not noise


def test_a_label_outside_the_declared_set_is_refused(starts):
    with pytest.raises(ValueError):
        panel(starts, ["4", "5"], "bucket")


def test_replicates_resample_whole_game_clusters():
    clusters = np.array(["g1", "g1", "g1", "g2", "g3"])
    draws = replicates(clusters, n_boot=25, seed=7)
    assert len(draws) == 25
    for idx in draws:
        counts = pd.Series(clusters[idx]).value_counts()
        assert counts.sum() == len(idx)
        # every drawn g1 arrives as its whole 3-row cluster
        assert counts.get("g1", 0) % 3 == 0
