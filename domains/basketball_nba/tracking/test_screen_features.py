"""Focused tests for NBA screen-candidate feature assembly."""
from __future__ import annotations

import pandas as pd
import pytest

from domains.basketball_nba.tracking.screen_features import (
    court_zone,
    game_features,
    screen_handler_concentration,
    screen_location_mix,
    screen_rate,
)

BLOCK_LEN = 12
BLOCK_STRIDE = 20
# (screener_x, screener_y, expected_zone)
SCREENS = [
    (25.0, 25.0, "top"),
    (28.0, 22.0, "top"),
    (25.0, 40.0, "wing"),
    (8.0, 45.0, "corner"),
]


def _tracks(handler_ids: list[str]) -> pd.DataFrame:
    """N engineered screens: one stationary screener parked by the handler."""
    rows = []
    for block, ((sx, sy, _), handler) in enumerate(zip(SCREENS, handler_ids)):
        for offset in range(BLOCK_LEN):
            frame = block * BLOCK_STRIDE + offset
            rows.extend([
                {"game_id": "g1", "frame": frame, "player_id": handler, "team_id": "A",
                 "x": sx - 3.0, "y": sy, "has_possession": True},
                {"game_id": "g1", "frame": frame, "player_id": "scr%d" % block,
                 "team_id": "A", "x": sx, "y": sy, "has_possession": False},
                {"game_id": "g1", "frame": frame, "player_id": "def%d" % block,
                 "team_id": "B", "x": sx + 1.0, "y": sy, "has_possession": False},
            ])
    return pd.DataFrame(rows)


def _write(tmp_path, handler_ids: list[str]):
    path = tmp_path / "tracking.csv"
    _tracks(handler_ids).to_csv(path, index=False)
    return path


def test_court_zone_uses_the_94x50_convention() -> None:
    assert court_zone(25.0, 25.0) == "top"
    assert court_zone(25.0, 40.0) == "wing"
    assert court_zone(8.0, 45.0) == "corner"
    # Folded about half-court: the far basket mirrors the near one.
    assert court_zone(94.0 - 8.0, 5.0) == "corner"


def test_rate_is_exact_per_minute() -> None:
    events = pd.DataFrame({"handler_id": ["h"] * 4})
    assert screen_rate(events, n_frames=1800, fps=30.0) == 4.0
    with pytest.raises(ValueError):
        screen_rate(events, n_frames=0, fps=30.0)


def test_four_engineered_screens_give_exact_rate_and_zone_mix(tmp_path) -> None:
    features = game_features(_write(tmp_path, ["h1"] * 4))
    assert len(features) == 1
    row = features.iloc[0]
    assert row["screen_candidate_count"] == 4
    # 4 screens across a 72-frame span at 30 fps == 0.04 minutes.
    assert row["screen_rate_per_min"] == pytest.approx(100.0)
    assert row["screen_zone_share_top"] == pytest.approx(0.5)
    assert row["screen_zone_share_wing"] == pytest.approx(0.25)
    assert row["screen_zone_share_corner"] == pytest.approx(0.25)


def test_concentration_is_one_for_a_single_handler_and_lower_when_split(tmp_path) -> None:
    solo = game_features(_write(tmp_path, ["h1"] * 4))
    assert solo.iloc[0]["screen_handler_hhi"] == pytest.approx(1.0)

    split = game_features(_write(tmp_path, ["h1", "h1", "h2", "h2"]))
    assert split.iloc[0]["screen_candidate_count"] == 4
    assert split.iloc[0]["screen_handler_hhi"] == pytest.approx(0.5)
    assert split.iloc[0]["screen_handler_hhi"] < solo.iloc[0]["screen_handler_hhi"]


def test_empty_events_are_zeroed_not_guessed() -> None:
    empty = pd.DataFrame(columns=["game_id", "frame", "handler_id", "screener_id", "x", "y"])
    assert screen_handler_concentration(empty) == 0.0
    assert screen_location_mix(empty) == {"top": 0.0, "wing": 0.0, "corner": 0.0}
