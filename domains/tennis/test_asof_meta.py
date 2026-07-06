"""Per-file tests for domains.tennis.asof_meta -- leak discipline is the hill.

Run: python -m pytest domains/tennis/test_asof_meta.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domains.tennis.asof_meta import (
    OUT_COLS,
    _orient_raw,
    assert_no_future_leak,
    build_asof_meta,
)


def _fixture_matches() -> pd.DataFrame:
    # 4 chronological matches; players 1,2,3 recur so trailing minutes has signal.
    return pd.DataFrame({
        "event_id": ["e1", "e2", "e3", "e4"],
        "date": pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-03", "2023-01-04"]),
        "tour": ["atp"] * 4,
        "tourney_id": ["2023-100", "2023-100", "2023-100", "2023-100"],
        "round": ["R32", "R32", "R16", "R16"],
        "match_num": [1, 2, 1, 2],
        "p1_id": [1, 1, 1, 2],   # p1=min(winner,loser) per row
        "p2_id": [2, 3, 3, 3],
    })


def _fixture_raw() -> pd.DataFrame:
    # Raw sackmann orientation: winner_id/loser_id, NOT p1/p2 -- winner varies.
    return pd.DataFrame({
        "tourney_id": ["2023-100", "2023-100", "2023-100", "2023-100"],
        "match_num": ["1", "2", "1", "2"],
        "winner_id": ["1", "3", "3", "2"],   # match3: 3 beats 1; match4: 2 beats 3
        "loser_id": ["2", "1", "1", "3"],
        "winner_ht": ["185", "190", "190", "180"],
        "loser_ht": ["180", "185", "185", "190"],
        "winner_rank_points": ["1000", "1200", "1200", "800"],
        "loser_rank_points": ["900", "1000", "1000", "1200"],
        "winner_seed": ["1", "", "", "3"],
        "loser_seed": ["", "1", "1", ""],
        "draw_size": ["32", "32", "32", "32"],
        "minutes": ["90", "120", "150", "100"],
    })


def test_orient_raw_p1_is_min_id() -> None:
    """p1 must always be the smaller numeric id, regardless of who won."""
    out = _orient_raw(_fixture_raw())
    assert list(out["p1_id"]) == [1, 1, 1, 2]
    assert list(out["p2_id"]) == [2, 3, 3, 3]
    # match_num=2 (row idx1): winner=3 loser=1 -> p1=1(loser) so p1_ht comes from loser_ht=185
    assert out.loc[1, "p1_ht"] == 185.0
    assert out.loc[1, "p2_ht"] == 190.0


def test_build_asof_meta_schema_and_shape(tmp_path) -> None:
    matches = _fixture_matches()
    raw = _fixture_raw()
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    raw.to_csv(raw_dir / "atp_matches_2023.csv", index=False)
    out_path = tmp_path / "asof_meta.parquet"

    dest = build_asof_meta(raw_dir=str(raw_dir), matches=matches, out_path=str(out_path))
    result = pd.read_parquet(dest)

    assert list(result.columns) == OUT_COLS
    assert len(result) == 4


def test_pregame_facts_are_not_nan_when_present(tmp_path) -> None:
    """Height / rank_points / draw_size are pre-game facts -- populate on every row."""
    matches = _fixture_matches()
    raw = _fixture_raw()
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    raw.to_csv(raw_dir / "atp_matches_2023.csv", index=False)
    out_path = tmp_path / "asof_meta.parquet"

    dest = build_asof_meta(raw_dir=str(raw_dir), matches=matches, out_path=str(out_path))
    result = pd.read_parquet(dest)

    assert result["p1_ht"].notna().all()
    assert result["p2_ht"].notna().all()
    assert result["diff_rank_points"].notna().all()
    assert result["draw_size"].eq(32.0).all()


def test_own_row_minutes_never_leaks_into_own_asof(tmp_path) -> None:
    """The match's OWN minutes must never appear in that same row's asof value."""
    matches = _fixture_matches()
    raw = _fixture_raw()
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    raw.to_csv(raw_dir / "atp_matches_2023.csv", index=False)
    out_path = tmp_path / "asof_meta.parquet"

    dest = build_asof_meta(raw_dir=str(raw_dir), matches=matches, out_path=str(out_path))
    result = pd.read_parquet(dest)

    # Row 0 (e1): both players debut -> NaN prior minutes, n_prior=0.
    assert result.loc[0, "p1_n_prior"] == 0
    assert result.loc[0, "p2_n_prior"] == 0
    assert pd.isna(result.loc[0, "p1_minutes_prior_asof"])
    assert pd.isna(result.loc[0, "p2_minutes_prior_asof"])

    # Row 2 (e3): p1=1 played e1(90min)+e2(120min) prior -> mean 105, NOT influenced
    # by e3's own minutes (150).
    assert result.loc[2, "p1_n_prior"] == 2
    assert result.loc[2, "p1_minutes_prior_asof"] == pytest.approx(105.0)

    # Row 3 (e4): p1=2 played e1(90min) only prior; p2=3 played e2(120)+e3(150) prior
    # -> mean 135. Neither includes e4's own minutes (100).
    assert result.loc[3, "p1_minutes_prior_asof"] == pytest.approx(90.0)
    assert result.loc[3, "p2_minutes_prior_asof"] == pytest.approx(135.0)


def test_assert_no_future_leak_raises_on_planted_violation() -> None:
    """The leak assertion must actually fire when debut rows carry a non-NaN asof."""
    bad = pd.DataFrame({
        "p1_n_prior": [0, 1], "p2_n_prior": [0, 1],
        "p1_minutes_prior_asof": [77.0, 90.0],  # illegal: debut row has a value
        "p2_minutes_prior_asof": [np.nan, 100.0],
    })
    with pytest.raises(AssertionError):
        assert_no_future_leak(bad)


def test_truncation_invariance_first_three_rows_unchanged(tmp_path) -> None:
    """Dropping the tail row must not change the asof values already emitted earlier."""
    matches = _fixture_matches()
    raw = _fixture_raw()
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    raw.to_csv(raw_dir / "atp_matches_2023.csv", index=False)

    full = pd.read_parquet(
        build_asof_meta(raw_dir=str(raw_dir), matches=matches, out_path=str(tmp_path / "full.parquet"))
    )
    truncated = pd.read_parquet(
        build_asof_meta(
            raw_dir=str(raw_dir), matches=matches.iloc[:3].copy(),
            out_path=str(tmp_path / "trunc.parquet"),
        )
    )
    pd.testing.assert_frame_equal(
        full.iloc[:3].reset_index(drop=True), truncated.reset_index(drop=True)
    )


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
