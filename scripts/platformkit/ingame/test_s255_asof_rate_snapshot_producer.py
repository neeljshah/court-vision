"""Focused tests for the strictly-prior S255 snapshot producer."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.platformkit.ingame.asof_rate_snapshot_producer import (
    PLAYER_RATES,
    TEAM_RATES,
    build_entity_snapshots,
    qualify_clusters,
)


def test_snapshots_are_strictly_prior_and_reject_a_future_source_row() -> None:
    player_rows = pd.DataFrame(
        {
            "player_id": [7, 7, 7],
            "game_date": ["2025-01-01", "2025-01-03", "2025-01-05"],
            "ft_rate_q50": [1.0, 3.0, 999.0],
            "ft_rate_spread": [0.1, 0.3, 99.9],
            "ft_n_prior": [1.0, 2.0, 3.0],
        }
    )
    team_rows = pd.DataFrame(
        {
            "team_id": [9, 9, 9],
            "game_date": ["2025-01-01", "2025-01-03", "2025-01-05"],
            **{column: [1.0, 3.0, 999.0] for column in TEAM_RATES},
        }
    )
    cutoff = pd.Timestamp("2025-01-05")
    player = build_entity_snapshots(player_rows, "player_id", PLAYER_RATES, cutoff)
    team = build_entity_snapshots(team_rows, "team_id", TEAM_RATES, cutoff)
    clusters = pd.DataFrame(
        {"game": ["g"], "cluster_id": ["c"], "game_date": [pd.Timestamp("2025-01-04")]}
    )
    qualification = qualify_clusters(clusters, player, team)

    assert qualification.loc[0, "qualifies"]
    assert qualification.loc[0, "player_snapshot_date"] == pd.Timestamp("2025-01-03")
    assert qualification.loc[0, "team_snapshot_date"] == pd.Timestamp("2025-01-03")
    assert qualification.loc[0, "player_snapshot_date"] < qualification.loc[0, "game_date"]
    assert qualification.loc[0, "team_snapshot_date"] < qualification.loc[0, "game_date"]
    assert player.loc[player["as_of_date"] == pd.Timestamp("2025-01-03"), "ft_rate_q50"].item() == 1.0
    assert (player["as_of_date"] <= cutoff).all()
    assert len(Path(__file__).with_name("asof_rate_snapshot_producer.py").read_text().splitlines()) <= 300
