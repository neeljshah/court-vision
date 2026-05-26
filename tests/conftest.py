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


# ---------------------------------------------------------------------------
# Phase 17 — Infrastructure / Drift / Auto-Retrain
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_model_metrics() -> dict:
    """Return synthetic model metrics used by test_model_validation_gate (plan 03).

    Returns
    -------
    dict
        Mapping of model name to {r2, mae} metrics.
    """
    return {
        "pts_model": {"r2": 0.47, "mae": 3.2},
        "reb_model": {"r2": 0.40, "mae": 1.1},
    }


@pytest.fixture(autouse=True)
def _clean_milestone_state(tmp_path, monkeypatch):
    """Redirect retrain_milestones.json to a temp path for every test.

    Prevents cross-test pollution when check_and_retrain persists milestone state.
    Applied automatically to all tests via autouse=True.
    """
    try:
        import src.pipeline.auto_retrain as ar_mod
        if hasattr(ar_mod, "_MILESTONE_STATE_PATH"):
            monkeypatch.setattr(
                ar_mod,
                "_MILESTONE_STATE_PATH",
                str(tmp_path / "retrain_milestones.json"),
            )
    except ImportError:
        pass


@pytest.fixture(autouse=True)
def _clean_alert_dedup_state(tmp_path, monkeypatch):
    """R26_S5 — pin the alert dedup sidecar to a per-test tmp path AND
    flush the in-process LRU before each test.

    Without this, the in-process dedup LRU (and the on-disk sidecar at
    ``data/cache/alerts/alert_dedup_state.json``) would carry state
    across tests — causing R21_N3 tests that fire repeated alerts to be
    silently suppressed by the R26_S5 layer.
    """
    try:
        import src.alerts.discord_webhook as dw_mod
        dedup_path = str(tmp_path / "alert_dedup_state.json")
        if hasattr(dw_mod, "_DEDUP_STATE_PATH"):
            monkeypatch.setattr(dw_mod, "_DEDUP_STATE_PATH", dedup_path)
        if hasattr(dw_mod, "flush_dedup"):
            dw_mod.flush_dedup(dedup_path)
    except ImportError:
        pass


@pytest.fixture
def mock_feature_importance() -> dict:
    """Return two feature-importance snapshots: baseline and drifted.

    Used by test_drift_alert_fires to supply synthetic importances without
    reading real model artifacts.

    Returns
    -------
    dict
        Keys "baseline" and "drifted", each a dict of feature -> importance float.
    """
    return {
        "baseline": {
            "fg_pct": 0.4,
            "usage": 0.3,
            "rest_days": 0.2,
            "def_rtg": 0.1,
        },
        "drifted": {
            "fg_pct": 0.05,
            "usage": 0.45,
            "rest_days": 0.35,
            "def_rtg": 0.15,
        },
    }


@pytest.fixture
def drift_log_path(tmp_path, monkeypatch) -> str:
    """Return a temp path for the feature drift log and monkeypatch the module constant.

    Patches src.pipeline.feature_drift_detector._DRIFT_LOG so that
    FeatureDriftDetector writes to a throwaway temp file during tests,
    never polluting data/models/.

    Returns
    -------
    str
        Absolute path to the temp drift log file (does not need to pre-exist).
    """
    log_path = str(tmp_path / "feature_drift_log.json")
    try:
        import src.pipeline.feature_drift_detector as fdd_mod
        if hasattr(fdd_mod, "_DRIFT_LOG"):
            monkeypatch.setattr(fdd_mod, "_DRIFT_LOG", log_path)
    except ImportError:
        pass  # Module not yet implemented — fixture still returns the path
    return log_path
