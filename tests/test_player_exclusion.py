"""
test_player_exclusion.py — Wave 0 stubs for per-player exclusion list contract.

All tests are xfail(strict=False) — they define the contract that
src/prediction/prop_cv_split.filter_excluded_players (Plan 02) must satisfy.
"""
import numpy as np
import pandas as pd
import pytest


def _make_player_df(n_players: int = 10, rows_per_player: int = 20) -> pd.DataFrame:
    """Synthetic DataFrame with player_id 1..n_players and pts column."""
    rng = np.random.default_rng(7)
    player_ids = list(range(1, n_players + 1)) * rows_per_player
    pts = rng.normal(20, 5, len(player_ids))
    return pd.DataFrame({"player_id": player_ids, "pts": pts})


@pytest.mark.xfail(strict=False, reason="impl pending Plan 02")
def test_excluded_players_not_in_train_set() -> None:
    """filter_excluded_players removes all rows whose player_id is in EXCLUDE."""
    prop_cv_split = pytest.importorskip("src.prediction.prop_cv_split")
    filter_excluded_players = prop_cv_split.filter_excluded_players

    df = _make_player_df(n_players=10, rows_per_player=20)
    EXCLUDE = [3, 7]
    result = filter_excluded_players(df, EXCLUDE)

    remaining_players = set(result["player_id"].unique())
    for pid in EXCLUDE:
        assert pid not in remaining_players, (
            f"Player {pid} should have been excluded but is still present"
        )


@pytest.mark.xfail(strict=False, reason="impl pending Plan 02")
def test_exclusion_empty_list_is_noop() -> None:
    """filter_excluded_players with an empty exclude list returns the full DataFrame."""
    prop_cv_split = pytest.importorskip("src.prediction.prop_cv_split")
    filter_excluded_players = prop_cv_split.filter_excluded_players

    df = _make_player_df(n_players=10, rows_per_player=20)
    result = filter_excluded_players(df, [])

    assert len(result) == len(df), (
        f"Empty exclusion list should be a no-op: "
        f"expected {len(df)} rows, got {len(result)}"
    )
