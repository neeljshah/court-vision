"""Tests for player style embeddings."""

import pandas as pd

from scripts.platformkit.player_embeddings import (
    EMBEDDING_COLUMNS,
    build_player_embeddings,
)


def _tracking() -> tuple[pd.DataFrame, dict[str, str]]:
    rows = []
    dates = {}
    for game_number in range(1, 8):
        game_id = "002000000%d" % game_number
        dates[game_id] = "2025-01-%02d" % (9 + game_number)
        for person_id in (10, 20):
            rows.append({
                "gameId": game_id, "personId": person_id, "minutes": 20 + game_number,
                "speed": 4 + person_id / 100 + game_number / 10,
                "touches": 30 + person_id / 10 + game_number,
                "passes": 20 + person_id / 10 + game_number,
                "distance": 1 + game_number / 10,
                "reboundChancesTotal": 4 + game_number,
                "secondaryAssists": game_number,
            })
    return pd.DataFrame(rows), dates


def test_embeddings_are_truncation_invariant_and_shifted() -> None:
    tracking, game_dates = _tracking()
    full = build_player_embeddings(tracking, game_dates)
    truncated = build_player_embeddings(tracking.iloc[:-4], game_dates)
    before_cutoff = full.gameDate < pd.Timestamp("2025-01-15")
    columns = ["personId", "gameId", *EMBEDDING_COLUMNS]
    pd.testing.assert_frame_equal(
        full.loc[before_cutoff, columns].reset_index(drop=True),
        truncated.loc[truncated.gameDate < pd.Timestamp("2025-01-15"), columns].reset_index(drop=True),
    )
    player = full.loc[full.personId == 10, list(EMBEDDING_COLUMNS)]
    assert player.iloc[0].isna().all()
    assert player.iloc[1].notna().all()

    changed_tracking = tracking.copy()
    changed_tracking.loc[changed_tracking.gameId == "0020000006", "touches"] = 9999
    changed = build_player_embeddings(changed_tracking, game_dates)
    target = full.gameId == "0020000006"
    pd.testing.assert_frame_equal(
        full.loc[target, list(EMBEDDING_COLUMNS)].reset_index(drop=True),
        changed.loc[target, list(EMBEDDING_COLUMNS)].reset_index(drop=True),
    )
