"""Focused contract coverage for shared leak-boundary guards."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.leak_boundary import assert_no_same_game_columns, embargo_indices


def test_same_game_and_team_identity_columns_are_rejected() -> None:
    with pytest.raises(ValueError, match="raw_same_game.*teamId"):
        assert_no_same_game_columns(["minutes_l5", "raw_same_game", "teamId"])


def test_embargo_removes_adjacent_prior_date_block_and_keeps_history() -> None:
    dates = pd.date_range("2024-01-01", periods=6, freq="D")

    result = embargo_indices(dates, [dates[4], dates[5]], blocks=1)

    assert np.array_equal(result, np.array([0, 1, 2]))


def test_zero_block_embargo_keeps_all_strictly_prior_rows() -> None:
    dates = pd.date_range("2024-01-01", periods=4, freq="D")

    assert np.array_equal(embargo_indices(dates, [dates[3]], blocks=0), np.array([0, 1, 2]))
