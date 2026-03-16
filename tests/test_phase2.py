"""
tests/test_phase2.py — Phase 2 Tracking Improvements test suite.

Tests for:
  - jersey_ocr.py (OCR reader, preprocessing, color clustering)
  - player_identity.py (JerseyVotingBuffer, run_ocr_annotation_pass)
  - nba_stats.py (fetch_roster)

Run with:
    conda run -n basketball_ai pytest tests/test_phase2.py -v
"""

from __future__ import annotations

import os
import sys
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _solid_bgr(h: int, w: int, color=(128, 64, 32)) -> np.ndarray:
    """Return a solid-color BGR crop of given size."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = color
    return img


def _white_number_crop(h: int = 80, w: int = 50) -> np.ndarray:
    """Return a white-on-dark crop that looks like a jersey number."""
    crop = np.zeros((h, w, 3), dtype=np.uint8)
    crop[20:60, 10:40] = (200, 200, 200)  # light rectangle in jersey area
    return crop


# ─────────────────────────────────────────────────────────────────────────────
# Task 1 tests — jersey_ocr.py
# ─────────────────────────────────────────────────────────────────────────────

class TestOCRReaderInit:
    """test_ocr_reader_init: get_reader() is a singleton."""

    def test_get_reader_returns_same_object(self):
        from src.tracking.jersey_ocr import get_reader
        r1 = get_reader()
        r2 = get_reader()
        assert r1 is r2, "get_reader() must return the same singleton object"

    def test_get_reader_has_readtext(self):
        from src.tracking.jersey_ocr import get_reader
        r = get_reader()
        assert hasattr(r, "readtext"), "Reader must expose readtext()"


class TestJerseyNumberExtraction:
    """test_jersey_number_extraction: read_jersey_number() contract."""

    def test_returns_int_or_none_on_small_crop(self):
        from src.tracking.jersey_ocr import read_jersey_number
        crop = _solid_bgr(10, 10)
        result = read_jersey_number(crop)
        assert result is None or isinstance(result, int)

    def test_returns_int_or_none_on_normal_crop(self):
        from src.tracking.jersey_ocr import read_jersey_number
        crop = _solid_bgr(120, 60)
        result = read_jersey_number(crop)
        assert result is None or isinstance(result, int)

    def test_never_raises(self):
        from src.tracking.jersey_ocr import read_jersey_number
        for size in [(1, 1), (5, 5), (100, 60), (200, 100)]:
            crop = _solid_bgr(*size)
            try:
                result = read_jersey_number(crop)
                assert result is None or (isinstance(result, int) and 0 <= result <= 99)
            except Exception as exc:
                pytest.fail(f"read_jersey_number raised on {size} crop: {exc}")

    def test_result_in_range_0_to_99_when_int(self):
        from src.tracking.jersey_ocr import read_jersey_number
        crop = _white_number_crop()
        result = read_jersey_number(crop)
        if result is not None:
            assert 0 <= result <= 99, f"Expected 0-99, got {result}"

    def test_preprocess_small_returns_valid_array(self):
        from src.tracking.jersey_ocr import preprocess_crop
        crop = _solid_bgr(10, 10)
        out = preprocess_crop(crop)
        assert out.ndim == 2, "preprocess_crop must return a 2D array"
        assert out.dtype == np.uint8

    def test_preprocess_normal_returns_min_height(self):
        from src.tracking.jersey_ocr import preprocess_crop
        crop = _solid_bgr(120, 60)
        out = preprocess_crop(crop)
        assert out.shape[0] >= 64, f"Expected height >= 64, got {out.shape[0]}"
        assert out.ndim == 2


class TestKMeansColorDescriptor:
    """test_kmeans_color_descriptor: dominant_hsv_cluster() contract."""

    def test_shape_is_3_float32(self):
        from src.tracking.jersey_ocr import dominant_hsv_cluster
        crop = _solid_bgr(80, 50, color=(50, 150, 200))
        result = dominant_hsv_cluster(crop)
        assert result.shape == (3,), f"Expected (3,), got {result.shape}"
        assert result.dtype == np.float32, f"Expected float32, got {result.dtype}"

    def test_small_crop_fallback_no_crash(self):
        """Crops smaller than _MIN_CROP_PIXELS must not crash."""
        from src.tracking.jersey_ocr import dominant_hsv_cluster
        crop = _solid_bgr(10, 10, color=(100, 100, 100))
        result = dominant_hsv_cluster(crop)
        assert result.shape == (3,)
        assert result.dtype == np.float32

    def test_large_crop_returns_valid_hsv(self):
        from src.tracking.jersey_ocr import dominant_hsv_cluster
        crop = _solid_bgr(200, 100, color=(0, 0, 255))  # red in BGR
        result = dominant_hsv_cluster(crop)
        assert result.shape == (3,)
        # HSV H channel should be 0-180 in OpenCV, S and V 0-255
        assert 0 <= result[0] <= 180
        assert 0 <= result[1] <= 255
        assert 0 <= result[2] <= 255

    def test_empty_like_crop_does_not_raise(self):
        from src.tracking.jersey_ocr import dominant_hsv_cluster
        crop = _solid_bgr(5, 5)
        try:
            result = dominant_hsv_cluster(crop)
            assert result.shape == (3,)
        except Exception as exc:
            pytest.fail(f"dominant_hsv_cluster raised on tiny crop: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Task 2 tests — player_identity.py
# ─────────────────────────────────────────────────────────────────────────────

class TestVotingBuffer:
    """test_voting_buffer: JerseyVotingBuffer behaviour."""

    def test_confirms_after_three_identical(self):
        from src.tracking.player_identity import JerseyVotingBuffer
        buf = JerseyVotingBuffer(confirm_threshold=3)
        buf.record(slot=0, number=23)
        buf.record(slot=0, number=23)
        assert buf.get_confirmed(0) is None, "Should not confirm after 2 reads"
        buf.record(slot=0, number=23)
        assert buf.get_confirmed(0) == 23, "Should confirm after 3 identical reads"

    def test_none_breaks_streak(self):
        from src.tracking.player_identity import JerseyVotingBuffer
        buf = JerseyVotingBuffer(confirm_threshold=3)
        buf.record(slot=1, number=10)
        buf.record(slot=1, number=None)
        buf.record(slot=1, number=10)
        # streak was broken; deque has [10, None, 10] — not all same
        assert buf.get_confirmed(1) is None

    def test_reset_slot_clears_confirmed(self):
        from src.tracking.player_identity import JerseyVotingBuffer
        buf = JerseyVotingBuffer(confirm_threshold=3)
        for _ in range(3):
            buf.record(slot=5, number=7)
        assert buf.get_confirmed(5) == 7
        buf.reset_slot(5)
        assert buf.get_confirmed(5) is None

    def test_reset_nonexistent_slot_does_not_raise(self):
        from src.tracking.player_identity import JerseyVotingBuffer
        buf = JerseyVotingBuffer()
        buf.reset_slot(99)  # should not raise

    def test_all_confirmed_returns_dict(self):
        from src.tracking.player_identity import JerseyVotingBuffer
        buf = JerseyVotingBuffer(confirm_threshold=3)
        for _ in range(3):
            buf.record(slot=0, number=5)
        result = buf.all_confirmed()
        assert isinstance(result, dict)
        assert result[0] == 5

    def test_different_numbers_do_not_confirm(self):
        from src.tracking.player_identity import JerseyVotingBuffer
        buf = JerseyVotingBuffer(confirm_threshold=3)
        buf.record(slot=2, number=3)
        buf.record(slot=2, number=4)
        buf.record(slot=2, number=3)
        assert buf.get_confirmed(2) is None

    def test_module_constants_exported(self):
        import src.tracking.player_identity as pi
        assert hasattr(pi, "CONFIRM_THRESHOLD")
        assert hasattr(pi, "SAMPLE_EVERY_N")
        assert isinstance(pi.CONFIRM_THRESHOLD, int)
        assert isinstance(pi.SAMPLE_EVERY_N, int)


# ─────────────────────────────────────────────────────────────────────────────
# Task 2 tests — fetch_roster in nba_stats.py
# ─────────────────────────────────────────────────────────────────────────────

class TestRosterLookup:
    """test_roster_lookup: fetch_roster() contract using mock to avoid API calls."""

    def test_returns_dict_keyed_by_int(self, monkeypatch):
        """fetch_roster with mocked API returns dict keyed by int jersey num."""
        import src.data.nba_stats as nba_stats

        fake_roster = [
            {"PLAYER_ID": 1001, "PLAYER": "LeBron James", "NUM": "23"},
            {"PLAYER_ID": 1002, "PLAYER": "Anthony Davis", "NUM": "3"},
            {"PLAYER_ID": 1003, "PLAYER": "Staff Member", "NUM": ""},  # no number
        ]

        class MockRosterEndpoint:
            def get_normalized_dict(self):
                return {"CommonTeamRoster": fake_roster}

        def mock_common_roster(*args, **kwargs):
            return MockRosterEndpoint()

        # Patch time.sleep so tests run fast
        monkeypatch.setattr("time.sleep", lambda _: None)

        # Patch the CommonTeamRoster import inside fetch_roster
        import unittest.mock as mock
        with mock.patch.dict("sys.modules", {}):
            # We need to patch nba_api.stats.endpoints.CommonTeamRoster
            mock_module = mock.MagicMock()
            mock_module.CommonTeamRoster = mock_common_roster
            monkeypatch.setattr(
                "builtins.__import__",
                _make_import_patcher(mock_module),
                raising=False,
            )

            # Use a temp cache dir so we don't hit disk
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                orig_cache = nba_stats._NBA_CACHE
                nba_stats._NBA_CACHE = tmpdir
                try:
                    result = nba_stats.fetch_roster(team_id=1610612747, season="2024-25")
                finally:
                    nba_stats._NBA_CACHE = orig_cache

        assert isinstance(result, dict), "fetch_roster must return a dict"
        # Keys must be ints
        for k in result:
            assert isinstance(k, int), f"Keys must be int, got {type(k)}"
        # Values must have player_id and player_name
        for v in result.values():
            assert "player_id" in v
            assert "player_name" in v

    def test_non_numeric_num_does_not_raise(self, monkeypatch):
        """fetch_roster must not raise when NUM is empty or non-numeric."""
        import src.data.nba_stats as nba_stats

        fake_roster = [
            {"PLAYER_ID": 9001, "PLAYER": "No Number Guy", "NUM": ""},
            {"PLAYER_ID": 9002, "PLAYER": "Staff", "NUM": "N/A"},
        ]

        class MockRosterEndpoint:
            def get_normalized_dict(self):
                return {"CommonTeamRoster": fake_roster}

        import unittest.mock as mock
        mock_module = mock.MagicMock()
        mock_module.CommonTeamRoster = lambda *a, **kw: MockRosterEndpoint()
        monkeypatch.setattr("time.sleep", lambda _: None)

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_cache = nba_stats._NBA_CACHE
            nba_stats._NBA_CACHE = tmpdir
            try:
                with mock.patch.dict("sys.modules", {}):
                    monkeypatch.setattr(
                        "builtins.__import__",
                        _make_import_patcher(mock_module),
                        raising=False,
                    )
                    result = nba_stats.fetch_roster(team_id=1610612747)
            finally:
                nba_stats._NBA_CACHE = orig_cache

        # All entries had no valid number — should return empty dict (not raise)
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_fetch_roster_is_importable(self):
        """fetch_roster must be importable from nba_stats."""
        from src.data.nba_stats import fetch_roster
        assert callable(fetch_roster)


# ─────────────────────────────────────────────────────────────────────────────
# Task 02-03 tests — referee filtering (REQ-08)
# ─────────────────────────────────────────────────────────────────────────────

_SPATIAL_COLS = [
    "team_spacing",
    "nearest_opponent",
    "nearest_teammate",
    "paint_count_own",
    "paint_count_opp",
]


def _make_tracking_df(include_referee: bool = True) -> "pd.DataFrame":
    """Build a minimal tracking DataFrame for spatial feature testing."""
    import pandas as pd
    rows = []
    # Team 0 — 5 players
    for i in range(5):
        rows.append({
            "frame": 1,
            "player_id": i,
            "team": "green",
            "x_position": float(100 + i * 30),
            "y_position": float(200 + i * 20),
            "velocity": 1.0,
            "ball_possession": int(i == 0),
            "event": "none",
            "team_spacing": 50000.0,
            "nearest_opponent": 80.0,
            "nearest_teammate": 40.0,
            "paint_count_own": 1,
            "paint_count_opp": 2,
        })
    # Team 1 — 5 players
    for i in range(5):
        rows.append({
            "frame": 1,
            "player_id": 10 + i,
            "team": "white",
            "x_position": float(500 + i * 30),
            "y_position": float(300 + i * 20),
            "velocity": 1.5,
            "ball_possession": 0,
            "event": "none",
            "team_spacing": 45000.0,
            "nearest_opponent": 90.0,
            "nearest_teammate": 35.0,
            "paint_count_own": 2,
            "paint_count_opp": 1,
        })
    if include_referee:
        rows.append({
            "frame": 1,
            "player_id": 20,
            "team": "referee",
            "x_position": 300.0,
            "y_position": 250.0,
            "velocity": 0.5,
            "ball_possession": 0,
            "event": "none",
            "team_spacing": 99999.0,
            "nearest_opponent": 15.0,
            "nearest_teammate": 12.0,
            "paint_count_own": 5,
            "paint_count_opp": 5,
        })
    return pd.DataFrame(rows)


class TestRefereeExcludedFromSpacing:
    """REQ-08: Referee rows must have NaN spatial columns after compute_spatial_features()."""

    def test_referee_excluded_from_spacing(self):
        """
        compute_spatial_features() must:
          1. Keep referee rows in the output DataFrame.
          2. Set all spatial columns to NaN for referee rows.
          3. Leave non-referee spatial values unchanged.
        """
        import pandas as pd
        from src.features.feature_engineering import compute_spatial_features

        df = _make_tracking_df(include_referee=True)
        result = compute_spatial_features(df)

        ref_rows = result[result["team"] == "referee"]
        assert len(ref_rows) == 1, "Referee row must remain in output"

        for col in _SPATIAL_COLS:
            if col in result.columns:
                val = ref_rows.iloc[0][col]
                assert pd.isna(val), (
                    f"Expected referee {col} to be NaN, got {val!r}"
                )

        non_ref = result[result["team"] != "referee"]
        assert len(non_ref) == 10, "Must still have 10 player rows"
        for col in _SPATIAL_COLS:
            if col in result.columns:
                assert non_ref[col].notna().all(), (
                    f"Non-referee {col} should not be NaN after filtering"
                )

    def test_compute_spatial_features_importable(self):
        """compute_spatial_features must be importable as a public function."""
        from src.features.feature_engineering import compute_spatial_features
        assert callable(compute_spatial_features)

    def test_no_referee_no_change(self):
        """When no referee rows present, spatial columns are unchanged."""
        import pandas as pd
        from src.features.feature_engineering import compute_spatial_features

        df = _make_tracking_df(include_referee=False)
        result = compute_spatial_features(df)

        assert len(result) == 10
        for col in _SPATIAL_COLS:
            if col in result.columns and col in df.columns:
                pd.testing.assert_series_equal(
                    result[col].reset_index(drop=True),
                    df[col].reset_index(drop=True),
                    check_names=False,
                )


class TestRefereeExcludedFromPressure:
    """REQ-08: shot_quality.run() output must contain no referee rows."""

    def _make_features_csv(self, tmp_path: str, referee_shoots: bool = True) -> str:
        import pandas as pd
        rows = [
            {
                "frame": 10, "timestamp": 0.33, "player_id": 0,
                "team": "green", "x_position": 200.0, "y_position": 300.0,
                "event": "shot", "court_zone": "paint",
                "handler_isolation": 120.0, "team_spacing": 50000.0, "possession_run": 30,
            },
            {
                "frame": 11, "timestamp": 0.37, "player_id": 1,
                "team": "white", "x_position": 400.0, "y_position": 300.0,
                "event": "none", "court_zone": "3pt_arc",
                "handler_isolation": 60.0, "team_spacing": 40000.0, "possession_run": 10,
            },
        ]
        if referee_shoots:
            rows.append({
                "frame": 12, "timestamp": 0.40, "player_id": 20,
                "team": "referee", "x_position": 300.0, "y_position": 250.0,
                "event": "shot", "court_zone": "paint",
                "handler_isolation": 10.0, "team_spacing": 0.0, "possession_run": 5,
            })
        df = pd.DataFrame(rows)
        path = os.path.join(tmp_path, "features.csv")
        df.to_csv(path, index=False)
        return path

    def test_referee_excluded_from_pressure(self, tmp_path):
        """shot_quality.run() output must contain no rows where team == 'referee'."""
        from src.analytics.shot_quality import run as shot_quality_run
        import pandas as pd

        csv_path = self._make_features_csv(str(tmp_path), referee_shoots=True)
        result = shot_quality_run(input_path=csv_path, output_dir=str(tmp_path))

        assert not result.empty, "Should have at least one shot row"
        if "team" in result.columns:
            referee_shots = result[result["team"] == "referee"]
            assert len(referee_shots) == 0, (
                f"Expected 0 referee rows in shot_quality output, got {len(referee_shots)}"
            )

    def test_non_referee_shots_unchanged(self, tmp_path):
        """Non-referee shot rows must remain in output."""
        from src.analytics.shot_quality import run as shot_quality_run

        csv_path = self._make_features_csv(str(tmp_path), referee_shoots=True)
        result = shot_quality_run(input_path=csv_path, output_dir=str(tmp_path))

        player_shots = result[result["team"] != "referee"] if "team" in result.columns else result
        assert len(player_shots) >= 1, "Non-referee shots must be present"
        assert "shot_quality" in result.columns
        assert result["shot_quality"].notna().all()


def _make_import_patcher(mock_endpoints_module):
    """
    Returns a patched __import__ that intercepts
    nba_api.stats.endpoints imports and returns our mock.
    """
    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def patched_import(name, *args, **kwargs):
        if name == "nba_api.stats.endpoints":
            return mock_endpoints_module
        return real_import(name, *args, **kwargs)

    return patched_import
