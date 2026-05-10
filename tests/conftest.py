"""
tests/conftest.py — Shared pytest fixtures for the NBA AI System test suite.

Provides synthetic data fixtures usable across all Phase 2 test modules
without requiring real video files, a live database, or NBA API access.
"""

import os
from typing import Dict, Any

import numpy as np
import pytest


@pytest.fixture
def synthetic_crop_bgr() -> np.ndarray:
    """Return a synthetic 120x60 BGR uint8 image simulating a jersey crop.

    The image contains:
    - A solid green rectangle (simulating jersey fabric) at rows 20-80, cols 10-50.
    - White pixels (simulating jersey digit marks) at rows 30-60, cols 20-40.

    Returns
    -------
    np.ndarray
        Shape (120, 60, 3), dtype uint8, BGR channel order.
    """
    img: np.ndarray = np.zeros((120, 60, 3), dtype=np.uint8)
    # Jersey body — green fill
    img[20:80, 10:50] = (0, 180, 0)
    # Digit-like white marks
    img[30:60, 20:40] = (255, 255, 255)
    return img


@pytest.fixture
def mock_roster_dict() -> Dict[int, Dict[str, Any]]:
    """Return a minimal jersey-number-to-player mapping.

    Matches the shape returned by ``src.data.nba_stats.fetch_roster``:
    keys are int jersey numbers, values are dicts with ``player_id`` (int)
    and ``player_name`` (str).

    Returns
    -------
    Dict[int, Dict[str, Any]]
        Example roster with two well-known players.
    """
    return {
        23: {"player_id": 2544, "player_name": "LeBron James"},
        6: {"player_id": 1629029, "player_name": "Anthony Davis"},
    }


@pytest.fixture
def temp_db_url() -> str:
    """Return the DATABASE_URL environment variable for integration tests.

    Skips the test if the environment variable is not set, so the suite
    stays green in CI environments without a live PostgreSQL instance.

    Returns
    -------
    str
        A psycopg2-compatible connection string.

    Raises
    ------
    pytest.skip.Exception
        When DATABASE_URL is not set in the environment.
    """
    url: str | None = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping DB integration tests")
    return url


# ---------------------------------------------------------------------------
# Phase 16 — Tier-6 Models / Live Win Probability
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_possession_sequence():
    """Return 12 possession dicts simulating realistic in-game state.

    Each dict has home_pts, away_pts, time_remaining_s, spacing_index.
    Scores grow over time; time_remaining_s decrements from 2400 (full game).

    Returns
    -------
    list[dict]
        12-element list representing possession-by-possession game state.
    """
    possessions = []
    home_pts = 0
    away_pts = 0
    time_remaining = 2400.0
    spacing_values = [3.2, 3.5, 3.8, 3.1, 3.6, 3.9, 3.3, 3.7, 3.4, 3.8, 3.5, 3.6]
    for i in range(12):
        # Scores increment realistically (roughly 2-3 pts per possession)
        home_pts += 2 if i % 3 != 1 else 3
        away_pts += 2 if i % 4 != 2 else 3
        time_remaining -= 200.0
        possessions.append({
            "home_pts": home_pts,
            "away_pts": away_pts,
            "time_remaining_s": time_remaining,
            "spacing_index": spacing_values[i],
        })
    return possessions


@pytest.fixture
def sample_game_dict(sample_possession_sequence):
    """Return a minimal game dict consumed by live win probability features.

    Returns
    -------
    dict
        Game state with possessions list, team ratings, lineup net rating, outcome.
    """
    return {
        "possessions": sample_possession_sequence,
        "home_team": {"off_rtg": 112.0, "def_rtg": 108.0, "abbr": "LAL"},
        "away_team": {"off_rtg": 109.0, "def_rtg": 111.0, "abbr": "GSW"},
        "home_lineup_net_rtg": 3.5,
        "outcome": 1,  # home win
    }


@pytest.fixture
def mock_xgb_model():
    """Return a mock XGBoost-like model for fallback tests.

    The mock always predicts 0.6 regardless of input, allowing downstream
    tests to assert on fallback path behavior without a real model on disk.

    Returns
    -------
    _MockXGB
        Object with .predict(X) -> np.array([0.6]).
    """
    class _MockXGB:
        def predict(self, X):
            return np.array([0.6])

    return _MockXGB()
