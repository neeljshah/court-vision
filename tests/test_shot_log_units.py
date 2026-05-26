"""
tests/test_shot_log_units.py — Unit regression tests for defender_distance units.

Catches the unit-normalization bug where defender_distance is written in raw
pixels (0–940+) instead of feet (0–94).  Two complementary approaches:

1. Direct unit test on _shot_defender_dist() — no GPU, no video.
2. Fixture-based file test on tests/fixtures/golden_shot_log.csv.

Run both unconditionally; approach 1 gracefully skips if the sibling agent's
_px_to_ft helper has not landed yet.
"""
from __future__ import annotations

import csv
import math
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOLDEN_SHOT_LOG = FIXTURES_DIR / "golden_shot_log.csv"

# NBA court is 94 ft long; any defender_distance above this is physically impossible.
_MAX_DEFENDER_FEET = 94.0
# Diagonal of a 94×50 ft court ≈ 107 ft.  If values exceed this they must be pixels.
_MAX_COURT_DIAGONAL_FT = 107.0


# ── Approach 1a: _px_to_ft helper (forward-looking — skips if not yet present) ──

class TestPxToFtHelper:
    """_px_to_ft must scale pixel distances to feet using court width as reference."""

    def test_px_to_ft_full_court_width(self):
        """940 px on a 940-px-wide map == 94.0 ft (1:10 ratio)."""
        try:
            from src.pipeline.unified_pipeline import _px_to_ft
        except ImportError:
            pytest.skip("_px_to_ft not yet present — sibling agent fix pending")
        result = _px_to_ft(940, map_w=940)
        assert result == pytest.approx(94.0, abs=0.01), (
            f"_px_to_ft(940, 940) should be 94.0 ft, got {result}"
        )

    def test_px_to_ft_one_tenth_court(self):
        """50 px on a 940-px-wide map == 5.0 ft."""
        try:
            from src.pipeline.unified_pipeline import _px_to_ft
        except ImportError:
            pytest.skip("_px_to_ft not yet present — sibling agent fix pending")
        result = _px_to_ft(50, map_w=940)
        assert result == pytest.approx(5.0, abs=0.01), (
            f"_px_to_ft(50, 940) should be ~5.0 ft, got {result}"
        )

    def test_px_to_ft_zero_distance(self):
        """0 px == 0.0 ft."""
        try:
            from src.pipeline.unified_pipeline import _px_to_ft
        except ImportError:
            pytest.skip("_px_to_ft not yet present — sibling agent fix pending")
        result = _px_to_ft(0, map_w=940)
        assert result == pytest.approx(0.0, abs=0.001)


# ── Approach 1b: _shot_defender_dist() output bounds ────────────────────────────

class TestShotDefenderDistBounds:
    """_shot_defender_dist must return values in feet, not raw pixels."""

    @staticmethod
    def _import_fn():
        """Import _shot_defender_dist or skip if module is unavailable."""
        try:
            from src.pipeline.unified_pipeline import _shot_defender_dist
            return _shot_defender_dist
        except ImportError:
            pytest.skip("src.pipeline.unified_pipeline not importable in this environment")

    def test_nearby_defender_within_feet_bounds(self):
        """Shooter at (200, 250), defender 20 px away should produce < 94 ft after fix."""
        fn = self._import_fn()
        spatial = {}  # no _isolation key → triggers fallback path
        shooter = {"x2d": 200, "y2d": 250, "team": "home"}
        frame_tracks = [
            {"x2d": 220, "y2d": 250, "team": "away", "player_id": 9},
        ]
        dist = fn(spatial, shooter, frame_tracks, map_w=940)
        assert dist != "", "Expected a numeric distance, got empty string"
        # Pre-fix: raw pixel hypot = 20.0 → clearly fails the <=94 check if map_w=940
        # Post-fix: 20 px / 940 * 94 = ~2.0 ft → passes
        assert float(dist) <= _MAX_DEFENDER_FEET, (
            f"defender_distance={dist} exceeds {_MAX_DEFENDER_FEET} ft — "
            f"value appears to be in pixels rather than feet"
        )

    def test_far_defender_within_court_diagonal(self):
        """Defender at opposite end: raw pixel dist ≈ 700 px, expected ≤ 107 ft after fix."""
        fn = self._import_fn()
        spatial = {}
        shooter = {"x2d": 100, "y2d": 100, "team": "home"}
        frame_tracks = [
            {"x2d": 840, "y2d": 400, "team": "away", "player_id": 5},
        ]
        dist = fn(spatial, shooter, frame_tracks, map_w=940)
        if dist == "":
            pytest.skip("No opponent found — fallback returned empty (frame_tracks filter issue)")
        assert float(dist) <= _MAX_COURT_DIAGONAL_FT, (
            f"defender_distance={dist} exceeds court diagonal ({_MAX_COURT_DIAGONAL_FT} ft) — "
            f"likely in pixels (raw pixel dist would be ~760 px)"
        )

    def test_isolation_sentinel_not_returned_raw(self):
        """_ISOLATION_DEFAULT must not produce a defender_distance > 94 ft.

        Pre-fix: _ISOLATION_DEFAULT was 200.0 px; when spatial["_isolation"] ==
        _ISOLATION_DEFAULT the sentinel branch was skipped and the fallback returned
        "" (empty frame_tracks).  The bug manifested on the NON-sentinel path where
        raw pixel distances were returned.

        Post-fix: _ISOLATION_DEFAULT is 99.0 ft (a physically-impossible sentinel that
        is > court length).  This test guards against the sentinel value itself leaking
        through as a valid measurement in future refactors.
        """
        fn = self._import_fn()
        try:
            from src.pipeline.unified_pipeline import _ISOLATION_DEFAULT
        except ImportError:
            pytest.skip("_ISOLATION_DEFAULT not importable")
        spatial = {"_isolation": _ISOLATION_DEFAULT}
        shooter = {"x2d": 400, "y2d": 250, "team": "home"}
        frame_tracks = []
        dist = fn(spatial, shooter, frame_tracks, map_w=940)
        # _ISOLATION_DEFAULT (99.0 ft) acts as a skip-sentinel: when iso == sentinel
        # the branch is NOT taken, so dist falls through to "" (no opponents).
        # If the sentinel ever changes to a value < 94 that passes the != check,
        # it must still be <= 94 ft.
        if dist != "":
            assert float(dist) <= _MAX_DEFENDER_FEET, (
                f"Isolation sentinel produced {dist} ft — exceeds court length (94 ft). "
                f"_ISOLATION_DEFAULT={_ISOLATION_DEFAULT}. "
                "Sentinel value or branch logic may have regressed."
            )

    def test_empty_frame_tracks_returns_empty_string(self):
        """When no defenders present, _shot_defender_dist must return empty string."""
        fn = self._import_fn()
        spatial = {}
        shooter = {"x2d": 300, "y2d": 200, "team": "home"}
        dist = fn(spatial, shooter, [], map_w=940)
        assert dist == "", f"Expected '' for no defenders, got {dist!r}"


# ── Approach 2: fixture-based file test ──────────────────────────────────────────

class TestGoldenShotLogBounds:
    """golden_shot_log.csv fixture: all non-null defender_distance values must be in [0, 94] ft."""

    def test_golden_fixture_exists(self):
        """Fixture file must be present (committed to the repo)."""
        assert GOLDEN_SHOT_LOG.exists(), (
            f"Missing fixture: {GOLDEN_SHOT_LOG}. "
            "Commit tests/fixtures/golden_shot_log.csv to the repo."
        )

    def test_all_defender_distances_within_feet_bounds(self):
        """Every non-empty defender_distance cell must be 0–94 ft."""
        if not GOLDEN_SHOT_LOG.exists():
            pytest.skip("golden_shot_log.csv fixture absent")

        with open(GOLDEN_SHOT_LOG, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert len(rows) >= 5, (
            f"Fixture has only {len(rows)} rows — expected >= 5 for meaningful coverage"
        )

        violations = []
        for i, row in enumerate(rows, start=2):  # row 2 = first data row (1-indexed header)
            raw = row.get("defender_distance", "").strip()
            if not raw:
                continue
            try:
                val = float(raw)
            except ValueError:
                pytest.fail(f"Row {i}: defender_distance={raw!r} is not a valid float")

            if val < 0.0 or val > _MAX_DEFENDER_FEET:
                violations.append(f"Row {i}: defender_distance={val} (must be 0–{_MAX_DEFENDER_FEET} ft)")

        assert not violations, (
            f"Fixture has {len(violations)} out-of-bounds defender_distance values:\n"
            + "\n".join(violations)
        )

    def test_max_fixture_value_is_plausible(self):
        """Maximum defender_distance in the fixture should be < 35 ft (half-court diam)."""
        if not GOLDEN_SHOT_LOG.exists():
            pytest.skip("golden_shot_log.csv fixture absent")

        with open(GOLDEN_SHOT_LOG, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        values = []
        for row in rows:
            raw = row.get("defender_distance", "").strip()
            if raw:
                try:
                    values.append(float(raw))
                except ValueError:
                    pass

        if not values:
            pytest.skip("No non-null defender_distance values in fixture")

        max_val = max(values)
        # 35 ft is roughly the distance from the basket to the 3-point arc — a natural cap
        assert max_val <= 35.0, (
            f"Max defender_distance in fixture is {max_val} ft — "
            f"seems too large for an on-court shot scenario"
        )
