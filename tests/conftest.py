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
