"""Per-file test for scripts.platformkit.omni.replay_harness.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_replay_harness.py -q
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from scripts.platformkit.omni.replay_harness import (
    _build_state,
    _load_games_nba,
    replay,
)

_NBA_DATE = "2026-04-08"
_MLB_DATE = "2026-06-10"

_EXPECTED_COLS = [
    "sport", "date", "game_id", "market", "model_prob_or_value",
    "close_value_or_None", "realized", "brier_or_crps",
    "pipeline_version", "replayed_at",
]


def _has_nba_corpus() -> bool:
    try:
        df = _load_games_nba()
    except Exception:  # noqa: BLE001
        return False
    return (pd.to_datetime(df["date"]).dt.date == dt.date(2026, 4, 8)).any()


pytestmark = pytest.mark.skipif(not _has_nba_corpus(), reason="NBA games corpus unavailable")


def test_leak_free_state_matches_strictly_prior_games():
    """Rating state built via until=date must equal one built from games
    manually filtered to date < D -- proves no game ON/AFTER D enters the fit."""
    games = _load_games_nba()
    d = dt.date(2026, 4, 8)
    state_until = _build_state("nba", games, until=d)

    games2 = games.copy()
    games2["_d"] = pd.to_datetime(games2["date"]).dt.date
    prior_only = games2[games2["_d"] < d].drop(columns=["_d"])
    state_prior = _build_state("nba", prior_only, until=None)

    assert state_until.elo == state_prior.elo
    assert state_until.n_processed == state_prior.n_processed
    # Sanity: at least one game strictly on D was excluded from both fits.
    assert (games2["_d"] == d).sum() > 0


def test_replay_reproducible_nba():
    df1 = replay(_NBA_DATE, "nba", write=False)
    df2 = replay(_NBA_DATE, "nba", write=False)
    assert len(df1) > 0
    cols = [c for c in _EXPECTED_COLS if c != "replayed_at"]
    pd.testing.assert_frame_equal(
        df1[cols].reset_index(drop=True), df2[cols].reset_index(drop=True)
    )


def test_replay_graded_columns_and_write_nba(tmp_path):
    df = replay(_NBA_DATE, "nba", write=True, out_dir=tmp_path)
    assert list(df.columns) == _EXPECTED_COLS
    assert len(df) > 0
    assert df["brier_or_crps"].between(0.0, 1.0).all()
    assert df["realized"].isin([0.0, 1.0]).all()

    out_file = tmp_path / "nba" / f"{_NBA_DATE}.parquet"
    assert out_file.exists()
    on_disk = pd.read_parquet(out_file)
    assert list(on_disk.columns) == _EXPECTED_COLS
    assert len(on_disk) == len(df)


def test_replay_mlb_settled_games(tmp_path):
    df = replay(_MLB_DATE, "mlb", write=True, out_dir=tmp_path)
    assert list(df.columns) == _EXPECTED_COLS
    assert len(df) > 0
    assert df["realized"].isin([0.0, 1.0]).all()
    assert (tmp_path / "mlb" / f"{_MLB_DATE}.parquet").exists()


def test_unwired_sport_raises():
    with pytest.raises(ValueError):
        replay(_NBA_DATE, "soccer")
