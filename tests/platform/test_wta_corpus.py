"""tests/platform/test_wta_corpus.py — hermetic tests for domains/tennis/wta_corpus.py.

All tests use synthetic WTA-shaped DataFrames; NO real CSVs or parquet files are
loaded.  Verifies:
  1. build_wta_corpus/_transform_wta: schema contract, tour="wta", outcome-blind p1/p2.
  2. validate_wta_elo: returns correct keys, valid metric ranges, Platt recal column.
  3. No-future-leak / truncation-invariance on a WTA-shaped synthetic df.
  4. load_wta_corpus round-trips correctly (written + re-read = same data).
  5. Dedup: duplicate event_ids are disambiguated.
"""
from __future__ import annotations

import datetime as dt
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Module under test
# ---------------------------------------------------------------------------

from domains.tennis.wta_corpus import (
    _transform_wta,
    validate_wta_elo,
    load_wta_corpus,
    TRAIN_YEAR_MAX,
)
from domains.tennis.elo_core import BASE_RATING, replay, _expected, _k
from domains.tennis.elo_walkforward import walk_forward_elo


# ---------------------------------------------------------------------------
# Synthetic-data helpers
# ---------------------------------------------------------------------------

def _raw_wta_row(
    tourney_date: str,
    winner_id: int,
    loser_id: int,
    surface: str = "Hard",
    tourney_id: str = "wta-t1",
    tourney_name: str = "WTA Test",
    tourney_level: str = "A",
    round_: str = "R32",
    match_num: int = 1,
    score: str = "6-3 6-4",
    best_of: int = 3,
    minutes: float = 85.0,
    winner_rank: float = 10.0,
    loser_rank: float = 20.0,
) -> dict:
    """Return a raw Sackmann-format WTA match row dict."""
    return {
        "tourney_date": tourney_date,
        "tourney_id": tourney_id,
        "tourney_name": tourney_name,
        "tourney_level": tourney_level,
        "surface": surface,
        "round": round_,
        "match_num": str(match_num),
        "best_of": str(best_of),
        "winner_id": str(winner_id),
        "loser_id": str(loser_id),
        "winner_name": f"WPlayer{winner_id}",
        "loser_name":  f"WPlayer{loser_id}",
        "winner_rank": str(winner_rank),
        "loser_rank":  str(loser_rank),
        "score": score,
        "minutes": str(minutes),
        "_tour": "wta",
    }


def _make_raw_wta(n: int = 30, seed: int = 7) -> pd.DataFrame:
    """Return a synthetic raw WTA DataFrame with n matches (2019-2025)."""
    rng = np.random.default_rng(seed)
    player_ids = [300_001 + i for i in range(8)]
    rows = []
    years = list(range(2019, 2026))
    for k in range(n):
        yr = years[k % len(years)]
        base = dt.date(yr, 1, 1)
        day_offset = int(rng.integers(0, 340))
        d = base + dt.timedelta(days=day_offset)
        p1, p2 = rng.choice(player_ids, size=2, replace=False)
        rows.append(_raw_wta_row(
            tourney_date=d.strftime("%Y%m%d"),
            winner_id=int(p1),
            loser_id=int(p2),
            surface=["Hard", "Clay", "Grass"][k % 3],
            match_num=k + 1,
        ))
    return pd.DataFrame(rows)


def _make_wta_df(n: int = 50, seed: int = 42) -> pd.DataFrame:
    """Return a TRANSFORMED (schema-contract) WTA DataFrame via _transform_wta."""
    raw = _make_raw_wta(n=n, seed=seed)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "wta_matches.parquet"
        return _transform_wta(raw, out)


# ---------------------------------------------------------------------------
# 1. Schema contract and basic correctness
# ---------------------------------------------------------------------------

class TestTransformWta:
    def test_required_columns_present(self):
        from domains.tennis.ingest_sackmann import MATCHES_REQUIRED_COLS
        df = _make_wta_df()
        for col in MATCHES_REQUIRED_COLS:
            assert col in df.columns, f"Missing required column: {col}"

    def test_tour_is_wta(self):
        df = _make_wta_df()
        assert (df["tour"] == "wta").all(), "All rows must have tour='wta'"

    def test_winner_is_1_or_2(self):
        df = _make_wta_df()
        assert df["winner"].isin([1, 2]).all(), "winner column must be 1 or 2"

    def test_p1_id_leq_p2_id(self):
        """p1 is assigned as min(winner_id, loser_id) — outcome-blind."""
        df = _make_wta_df()
        # Both are Int64; compare as integers
        p1 = df["p1_id"].astype(int)
        p2 = df["p2_id"].astype(int)
        assert (p1 <= p2).all(), "p1_id must be <= p2_id (outcome-blind orientation)"

    def test_event_id_unique(self):
        df = _make_wta_df()
        assert df["event_id"].is_unique, "event_id must be unique after dedup"

    def test_best_of_dtype(self):
        df = _make_wta_df()
        assert df["best_of"].dtype == np.dtype("int8")

    def test_surface_normalised(self):
        df = _make_wta_df()
        known = {"Hard", "Clay", "Grass", "Carpet", "Unknown"}
        assert df["surface"].isin(known).all()

    def test_retirement_flag_is_bool(self):
        df = _make_wta_df()
        assert df["retirement"].dtype == bool or df["retirement"].dtype == np.dtype("bool")

    def test_no_nan_player_ids(self):
        df = _make_wta_df()
        assert not df["p1_id"].isna().any(), "p1_id must not be NaN"
        assert not df["p2_id"].isna().any(), "p2_id must not be NaN"

    def test_walkover_row_has_retirement_false(self):
        """A 'W/O' score should set retirement=True via _retirement_flag."""
        raw = pd.DataFrame([_raw_wta_row("20230601", 300001, 300002, score="W/O")])
        with tempfile.TemporaryDirectory() as tmp:
            df = _transform_wta(raw, Path(tmp) / "wta_matches.parquet")
        assert df["retirement"].iloc[0] is True or bool(df["retirement"].iloc[0]) is True

    def test_date_column_is_date(self):
        df = _make_wta_df()
        sample = df["date"].dropna().iloc[0]
        assert isinstance(sample, dt.date), f"date column should be dt.date, got {type(sample)}"


# ---------------------------------------------------------------------------
# 2. validate_wta_elo: metric keys, ranges, Platt recal
# ---------------------------------------------------------------------------

class TestValidateWtaElo:
    @pytest.fixture(scope="class")
    def wta_df(self):
        return _make_wta_df(n=120, seed=99)

    def test_returns_all_expected_keys(self, wta_df):
        metrics = validate_wta_elo(wta_df, train_year_max=2021, blend=0.3)
        expected = {
            "n_total", "n_test", "year_min", "year_max",
            "brier_raw", "logloss_raw", "ece_raw",
            "brier_recal", "logloss_recal", "ece_recal",
            "brier_delta", "ece_delta",
        }
        assert expected.issubset(set(metrics.keys()))

    def test_brier_raw_in_valid_range(self, wta_df):
        metrics = validate_wta_elo(wta_df, train_year_max=2021)
        assert 0.0 <= metrics["brier_raw"] <= 1.0, (
            f"brier_raw out of range: {metrics['brier_raw']}"
        )

    def test_logloss_positive(self, wta_df):
        metrics = validate_wta_elo(wta_df, train_year_max=2021)
        assert metrics["logloss_raw"] > 0.0

    def test_ece_non_negative(self, wta_df):
        metrics = validate_wta_elo(wta_df, train_year_max=2021)
        assert metrics["ece_raw"] >= 0.0

    def test_n_total_matches_input(self, wta_df):
        metrics = validate_wta_elo(wta_df, train_year_max=2021)
        assert metrics["n_total"] == len(wta_df)

    def test_n_test_positive(self, wta_df):
        metrics = validate_wta_elo(wta_df, train_year_max=2021)
        assert metrics["n_test"] > 0

    def test_brier_delta_is_recal_minus_raw(self, wta_df):
        metrics = validate_wta_elo(wta_df, train_year_max=2021)
        assert abs(metrics["brier_delta"] - (metrics["brier_recal"] - metrics["brier_raw"])) < 1e-12

    def test_ece_delta_is_recal_minus_raw(self, wta_df):
        metrics = validate_wta_elo(wta_df, train_year_max=2021)
        assert abs(metrics["ece_delta"] - (metrics["ece_recal"] - metrics["ece_raw"])) < 1e-12

    def test_recal_brier_finite(self, wta_df):
        metrics = validate_wta_elo(wta_df, train_year_max=2021)
        assert math.isfinite(metrics["brier_recal"])

    def test_year_range_consistent(self, wta_df):
        metrics = validate_wta_elo(wta_df, train_year_max=2021)
        assert metrics["year_min"] <= metrics["year_max"]


# ---------------------------------------------------------------------------
# 3. No-future-leak / truncation-invariance (WTA-shaped synthetic df)
# ---------------------------------------------------------------------------

class TestTruncationInvarianceWta:
    """Assert the core leak-free property on a WTA-shaped corpus.

    elo_state_asof(full_df, D) must equal replay(df[df.date < D]).
    """

    def _make_simple_wta(self) -> pd.DataFrame:
        rows = [
            {"date": dt.date(2022, 1, 10), "p1_id": 300001, "p2_id": 300002,
             "winner": 1, "surface": "Hard", "score": "6-4 6-3",
             "tour": "wta", "tourney_id": "w1", "round": "R32", "match_num": 1},
            {"date": dt.date(2022, 3, 15), "p1_id": 300003, "p2_id": 300002,
             "winner": 2, "surface": "Clay", "score": "3-6 6-4 6-2",
             "tour": "wta", "tourney_id": "w2", "round": "R32", "match_num": 1},
            {"date": dt.date(2022, 6,  1), "p1_id": 300001, "p2_id": 300003,
             "winner": 1, "surface": "Grass", "score": "7-5 6-3",
             "tour": "wta", "tourney_id": "w3", "round": "QF", "match_num": 1},
            {"date": dt.date(2023, 2, 20), "p1_id": 300002, "p2_id": 300003,
             "winner": 1, "surface": "Hard", "score": "6-2 6-1",
             "tour": "wta", "tourney_id": "w4", "round": "SF", "match_num": 1},
        ]
        return pd.DataFrame(rows)

    def _states_equal(self, a, b) -> None:
        assert a.ratings == b.ratings, f"ratings differ: {a.ratings} vs {b.ratings}"
        assert a.surface == b.surface, "surface ratings differ"
        assert a.counts == b.counts, "counts differ"
        assert a.n_processed == b.n_processed

    def test_truncation_invariance_mid_corpus(self):
        from domains.tennis.elo_core import replay
        from domains.tennis.elo_walkforward import elo_state_asof
        df = self._make_simple_wta()
        cut = dt.date(2023, 1, 1)
        state_a = elo_state_asof(df, cut)
        dates = pd.to_datetime(df["date"]).dt.date
        state_b = replay(df[dates < cut].copy())
        self._states_equal(state_a, state_b)

    def test_no_future_data_in_first_wta_prediction(self):
        """The first WTA match must use only BASE_RATING — no data precedes it."""
        df = self._make_simple_wta()
        result = walk_forward_elo(df)
        first = result.iloc[0]
        assert first["p1_elo"] == BASE_RATING, "First WTA match p1 must start at BASE_RATING"
        assert first["p2_elo"] == BASE_RATING, "First WTA match p2 must start at BASE_RATING"

    def test_win_prob_strictly_between_0_and_1(self):
        df = self._make_simple_wta()
        result = walk_forward_elo(df)
        wp = result["win_prob_p1"]
        assert (wp > 0.0).all()
        assert (wp < 1.0).all()

    def test_truncation_no_future_leak_assertion(self):
        """Explicit no-future-leak: for each row i, Elo was built from rows 0..i-1 only."""
        df = self._make_simple_wta().reset_index(drop=True)
        result = walk_forward_elo(df)

        for i in range(len(result)):
            row = result.iloc[i]
            row_date = pd.to_datetime(row["date"]).date()
            dates_col = pd.to_datetime(df["date"]).dt.date
            prior_df = df[dates_col < row_date].copy()
            from domains.tennis.elo_core import replay, BASE_RATING as BR
            if len(prior_df) == 0:
                # No prior data: both players must be at BASE_RATING
                assert row["p1_elo"] == BR, f"Row {i}: p1_elo should be BASE_RATING"
                assert row["p2_elo"] == BR, f"Row {i}: p2_elo should be BASE_RATING"
            else:
                state = replay(prior_df)
                p1 = int(row["p1_id"])
                p2 = int(row["p2_id"])
                exp_p1 = state.ratings.get(p1, BR)
                exp_p2 = state.ratings.get(p2, BR)
                assert abs(row["p1_elo"] - exp_p1) < 1e-10, (
                    f"Row {i}: p1_elo={row['p1_elo']} != expected {exp_p1} (future leak?)"
                )
                assert abs(row["p2_elo"] - exp_p2) < 1e-10, (
                    f"Row {i}: p2_elo={row['p2_elo']} != expected {exp_p2} (future leak?)"
                )


# ---------------------------------------------------------------------------
# 4. load_wta_corpus round-trips correctly
# ---------------------------------------------------------------------------

class TestLoadWtaCorpus:
    def test_round_trip_schema(self):
        from domains.tennis.ingest_sackmann import MATCHES_REQUIRED_COLS
        df_orig = _make_wta_df(n=40)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "wta_matches.parquet"
            # Write it out via _transform_wta
            raw = _make_raw_wta(n=40)
            _transform_wta(raw, p)
            df_loaded = load_wta_corpus(p)
        for col in MATCHES_REQUIRED_COLS:
            assert col in df_loaded.columns, f"Missing column after round-trip: {col}"

    def test_round_trip_row_count(self):
        raw = _make_raw_wta(n=20)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "wta_matches.parquet"
            df_orig = _transform_wta(raw, p)
            df_loaded = load_wta_corpus(p)
        assert len(df_orig) == len(df_loaded), (
            f"Row count changed on round-trip: {len(df_orig)} → {len(df_loaded)}"
        )

    def test_round_trip_tour_wta(self):
        raw = _make_raw_wta(n=15)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "wta_matches.parquet"
            _transform_wta(raw, p)
            df = load_wta_corpus(p)
        assert (df["tour"] == "wta").all()


# ---------------------------------------------------------------------------
# 5. Dedup: duplicate event_ids are disambiguated
# ---------------------------------------------------------------------------

class TestEventIdDedup:
    def test_dedup_produces_unique_event_ids(self):
        """Two rows with identical (date, tourney_id, p1_id, p2_id, match_num) get unique ids."""
        raw = pd.DataFrame([
            _raw_wta_row("20230101", 300001, 300002, match_num=1),
            _raw_wta_row("20230101", 300001, 300002, match_num=1),  # duplicate
        ])
        with tempfile.TemporaryDirectory() as tmp:
            df = _transform_wta(raw, Path(tmp) / "wta_matches.parquet")
        assert df["event_id"].is_unique, f"Duplicate event_ids remain: {df['event_id'].tolist()}"


# ---------------------------------------------------------------------------
# 6. Isolation: WTA corpus does NOT touch ATP matches.parquet
# ---------------------------------------------------------------------------

class TestATPIsolation:
    def test_transform_does_not_write_atp_parquet(self):
        """_transform_wta writes ONLY to the out_path we give it."""
        raw = _make_raw_wta(n=10)
        with tempfile.TemporaryDirectory() as tmp:
            wta_path = Path(tmp) / "wta_matches.parquet"
            atp_path = Path(tmp) / "matches.parquet"  # ATP sentinel
            _transform_wta(raw, wta_path)
            assert wta_path.exists(), "wta_matches.parquet should have been written"
            assert not atp_path.exists(), "matches.parquet (ATP) must NOT be touched"


# ---------------------------------------------------------------------------
# Needed imports at module level
# ---------------------------------------------------------------------------

import math  # noqa: E402 — used in TestValidateWtaElo
