"""Per-file test for domains/mlb/ingest_bullpen_relief_chains.py.

Runs build() against the REAL on-disk player_gamelogs.parquet (no mocking)
and checks the invariants the heuristic depends on: every relief row is
genuinely NOT its team's game-high-IP pitcher that game, rest_days/is_b2b
agree row-for-row, and appearances_last_3d never goes negative.

Run: python -m pytest domains/mlb/test_ingest_bullpen_relief_chains.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.mlb.ingest_bullpen_relief_chains import _KEEP_COLS, _SRC, build


@pytest.fixture(scope="module")
def out_df() -> pd.DataFrame:
    if not _SRC.exists():
        pytest.skip(f"source parquet not present in this checkout: {_SRC}")
    return build()


def test_columns_present(out_df: pd.DataFrame) -> None:
    assert list(out_df.columns) == _KEEP_COLS


def test_relief_rows_are_never_their_teams_game_high_ip_pitcher(out_df: pd.DataFrame) -> None:
    raw = pd.read_parquet(_SRC)
    pitchers = raw[raw["is_pitcher"] == True]  # noqa: E712
    max_ip = pitchers.groupby(["game_pk", "team"])["inningsPitched"].transform("max")
    starters = set(
        zip(
            pitchers.loc[pitchers["inningsPitched"] == max_ip, "game_pk"],
            pitchers.loc[pitchers["inningsPitched"] == max_ip, "team"],
            pitchers.loc[pitchers["inningsPitched"] == max_ip, "player_id"],
        )
    )
    relief_keys = set(zip(out_df["game_pk"], out_df["team"], out_df["player_id"]))
    # a relief row's (game_pk, team, player_id) must not ALSO be recorded as
    # that team's sole game-high-IP starter for a DIFFERENT reason (ties are
    # a disclosed edge case, so this only checks the common, non-tied case)
    single_starter_games = pitchers.groupby(["game_pk", "team"])["inningsPitched"].apply(
        lambda s: (s == s.max()).sum() == 1
    )
    clean_games = set(single_starter_games[single_starter_games].index)
    offending = {k for k in relief_keys if (k[0], k[1]) in clean_games} & starters
    assert not offending


def test_is_b2b_agrees_with_rest_days(out_df: pd.DataFrame) -> None:
    known = out_df.dropna(subset=["rest_days"])
    assert (known["is_b2b"] == (known["rest_days"] <= 1).astype(float)).all()


def test_appearances_last_3d_never_negative(out_df: pd.DataFrame) -> None:
    assert (out_df["appearances_last_3d"].dropna() >= 0).all()


def test_nonempty_and_smaller_than_raw_pitcher_rows(out_df: pd.DataFrame) -> None:
    raw = pd.read_parquet(_SRC)
    n_pitcher_rows = int((raw["is_pitcher"] == True).sum())  # noqa: E712
    assert 0 < len(out_df) < n_pitcher_rows


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
