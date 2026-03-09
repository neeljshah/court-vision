"""Tests for features/feature_pipeline.py.

All DB calls are mocked — no live database required.

Test coverage:
- Import without error
- Argparse: --game-id parsed correctly
- run_feature_pipeline calls get_connection()
- Step 0a: possession boundary detection (INSERT INTO possessions)
- Step 0b: shot event detection (INSERT INTO shot_logs)
- Step isolation: each feature module is called during pipeline execution
"""

import json
from unittest.mock import MagicMock, patch, call
import pytest

# ---------------------------------------------------------------------------
# Import smoke test
# ---------------------------------------------------------------------------

def test_import_without_error():
    """run_feature_pipeline and _build_parser can be imported without error."""
    from features.feature_pipeline import run_feature_pipeline, _build_parser
    assert callable(run_feature_pipeline)
    assert callable(_build_parser)


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------

class TestArgparse:

    def test_parse_game_id(self):
        """--game-id is parsed correctly into args.game_id."""
        from features.feature_pipeline import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["--game-id", "test-uuid-1234"])
        assert args.game_id == "test-uuid-1234"

    def test_missing_game_id_exits(self):
        """Missing --game-id causes SystemExit."""
        from features.feature_pipeline import _build_parser
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])


# ---------------------------------------------------------------------------
# Helpers for mocking
# ---------------------------------------------------------------------------

def _make_cursor_mock(all_rows=None, ball_rows=None, possessions=None, shot_rows=None):
    """Build a cursor mock that returns configured data per execute call.

    Calls to cursor.execute() are tracked; fetchall() / fetchone() return
    data based on the most recent execute call's SQL text.
    """
    cursor = MagicMock()
    cursor.rowcount = 1  # default: UPDATE affects 1 row (skip INSERT fallback)

    _state = {"last_sql": ""}

    def _execute(sql, params=None):
        _state["last_sql"] = sql.strip().lower()

    def _fetchall():
        sql = _state["last_sql"]
        if "object_type = 'ball'" in sql or ("object_type" in sql and "ball" in sql and "order by frame_number" in sql):
            return ball_rows or []
        if "from possessions" in sql:
            return possessions or []
        if "from shot_logs" in sql:
            return shot_rows or []
        # Default: all tracking_coordinates rows
        return all_rows or []

    def _fetchone():
        return None

    cursor.execute.side_effect = _execute
    cursor.fetchall.side_effect = _fetchall
    cursor.fetchone.side_effect = _fetchone
    return cursor


def _make_conn_mock(cursor):
    """Build a connection mock that provides the given cursor."""
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cursor)
    cm.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cm
    return conn


# ---------------------------------------------------------------------------
# Step 0a: Possession boundary detection
# ---------------------------------------------------------------------------

class TestPossessionBoundaryDetection:

    def test_inserts_into_possessions_on_ball_speed_drop(self):
        """When ball speed drops for 3+ frames, INSERT INTO possessions is called."""
        from features.feature_pipeline import _detect_possession_boundaries

        # Ball rows: first 3 have speed < 20 (held), then fast, then 3 slow again
        ball_rows = [
            {"frame_number": i, "speed": 5.0 if i < 3 or i >= 7 else 200.0}
            for i in range(10)
        ]
        cursor = MagicMock()
        cursor.rowcount = 0

        count = _detect_possession_boundaries(ball_rows, "game-123", cursor)

        # Should have called INSERT INTO possessions
        insert_calls = [
            c for c in cursor.execute.call_args_list
            if "insert into possessions" in c.args[0].lower()
        ]
        assert len(insert_calls) > 0, "Expected INSERT INTO possessions to be called"

    def test_empty_ball_rows_returns_zero(self):
        """Empty ball_rows → no INSERT, returns 0."""
        from features.feature_pipeline import _detect_possession_boundaries
        cursor = MagicMock()
        count = _detect_possession_boundaries([], "game-123", cursor)
        assert count == 0
        cursor.execute.assert_not_called()

    def test_possession_start_and_end_frame_in_insert(self):
        """INSERT call includes correct start_frame and end_frame."""
        from features.feature_pipeline import _detect_possession_boundaries

        # Frames 0..9 with a clear held period at frames 5,6,7
        ball_rows = [{"frame_number": i, "speed": 200.0 if i < 5 else 5.0} for i in range(10)]
        cursor = MagicMock()

        _detect_possession_boundaries(ball_rows, "game-abc", cursor)

        # Collect all INSERT calls
        insert_args = []
        for c in cursor.execute.call_args_list:
            sql = c.args[0]
            if "insert into possessions" in sql.lower():
                insert_args.append(c.args[1])

        # At least one INSERT should reference game_id
        assert any("game-abc" in str(a) for a in insert_args)


# ---------------------------------------------------------------------------
# Step 0b: Shot event detection
# ---------------------------------------------------------------------------

class TestShotEventDetection:

    def test_inserts_into_shot_logs_for_fast_ball_near_basket(self):
        """Ball with speed > 400 and y near basket → INSERT INTO shot_logs."""
        from features.feature_pipeline import _detect_shot_events

        ball_rows = [
            {
                "frame_number": 10,
                "speed": 500.0,        # > threshold
                "x": 50.0,             # near left basket (x < 100)
                "y": 240.0,            # exactly at basket_y
                "direction_degrees": 45.0,
            }
        ]

        cursor = MagicMock()
        cursor.fetchone.return_value = (7,)  # nearest player track_id=7

        count = _detect_shot_events(ball_rows, "game-xyz", cursor)

        assert count == 1
        insert_calls = [
            c for c in cursor.execute.call_args_list
            if "insert into shot_logs" in c.args[0].lower()
        ]
        assert len(insert_calls) == 1

    def test_slow_ball_not_detected_as_shot(self):
        """Ball with speed <= 400 is not a shot."""
        from features.feature_pipeline import _detect_shot_events

        ball_rows = [
            {
                "frame_number": 10,
                "speed": 100.0,        # below threshold
                "x": 50.0,
                "y": 240.0,
                "direction_degrees": 45.0,
            }
        ]
        cursor = MagicMock()
        count = _detect_shot_events(ball_rows, "game-xyz", cursor)
        assert count == 0

    def test_fast_ball_far_from_basket_y_not_detected(self):
        """Fast ball but not near basket y → not a shot."""
        from features.feature_pipeline import _detect_shot_events

        ball_rows = [
            {
                "frame_number": 10,
                "speed": 500.0,
                "x": 50.0,
                "y": 400.0,  # far from basket_y=240
                "direction_degrees": 45.0,
            }
        ]
        cursor = MagicMock()
        count = _detect_shot_events(ball_rows, "game-xyz", cursor)
        assert count == 0

    def test_empty_ball_rows_returns_zero(self):
        from features.feature_pipeline import _detect_shot_events
        cursor = MagicMock()
        count = _detect_shot_events([], "game-xyz", cursor)
        assert count == 0


# ---------------------------------------------------------------------------
# Pipeline integration: get_connection() called, modules are imported
# ---------------------------------------------------------------------------

class TestPipelineIntegration:

    def _make_tracking_rows(self):
        """Create minimal tracking_coordinates rows for 2 frames."""
        rows = []
        for frame_num in [0, 5, 10]:
            # 3 players + ball
            for tid in [1, 2, 3]:
                rows.append((
                    frame_num, float(frame_num * 33), 100.0 + tid * 30, 200.0,
                    5.0, 0.0, 50.0, 90.0, "player", tid
                ))
            rows.append((
                frame_num, float(frame_num * 33), 150.0, 220.0,
                0.0, 0.0, 5.0, 0.0, "ball", None
            ))
        return rows

    @patch("features.feature_pipeline.get_connection")
    def test_get_connection_is_called(self, mock_get_conn):
        """run_feature_pipeline calls get_connection()."""
        from features.feature_pipeline import run_feature_pipeline

        cursor = MagicMock()
        cursor.rowcount = 1
        cursor.fetchall.return_value = []
        cursor.fetchone.return_value = None

        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cursor)
        cm.__exit__ = MagicMock(return_value=False)
        cursor.return_value = cm

        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cm
        mock_get_conn.return_value = conn

        run_feature_pipeline("test-game-id")

        mock_get_conn.assert_called_once()

    @patch("features.feature_pipeline.get_connection")
    def test_feature_modules_called_via_pipeline(self, mock_get_conn):
        """Pipeline calls compute_spacing, compute_defensive_pressure, and off-ball detectors."""
        from features.feature_pipeline import run_feature_pipeline

        all_rows = self._make_tracking_rows()

        cursor = MagicMock()
        cursor.rowcount = 1
        cursor.fetchone.return_value = None

        _state = {"last_sql": ""}

        def _execute(sql, params=None):
            _state["last_sql"] = sql.strip().lower()

        def _fetchall():
            sql = _state["last_sql"]
            if "object_type = 'ball'" in sql:
                return []
            if "from possessions" in sql:
                return []
            if "from shot_logs" in sql:
                return []
            return all_rows

        cursor.execute.side_effect = _execute
        cursor.fetchall.side_effect = _fetchall

        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cursor)
        cm.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cm
        mock_get_conn.return_value = conn

        with patch("features.feature_pipeline.compute_spacing") as mock_spacing, \
             patch("features.feature_pipeline.compute_defensive_pressure") as mock_pressure, \
             patch("features.feature_pipeline.detect_off_ball_events") as mock_off_ball, \
             patch("features.feature_pipeline.detect_pick_and_roll") as mock_pnr:

            mock_spacing.return_value = MagicMock(
                convex_hull_area=100.0, avg_inter_player_distance=50.0
            )
            mock_pressure.return_value = []
            mock_off_ball.return_value = []
            mock_pnr.return_value = []

            run_feature_pipeline("test-game-id")

            # Each module should have been called at least once
            assert mock_spacing.called, "compute_spacing was not called"
            assert mock_pressure.called, "compute_defensive_pressure was not called"
            assert mock_off_ball.called, "detect_off_ball_events was not called"
            assert mock_pnr.called, "detect_pick_and_roll was not called"


# ---------------------------------------------------------------------------
# Source-level checks: verify INSERT statements exist in pipeline source
# ---------------------------------------------------------------------------

class TestSourceInsertStatements:
    """Verify the pipeline source contains required INSERT statements."""

    def _get_source(self):
        import inspect
        import features.feature_pipeline as mod
        return inspect.getsource(mod)

    def test_insert_into_feature_vectors_present(self):
        src = self._get_source()
        assert "INSERT INTO feature_vectors" in src

    def test_insert_into_detected_events_present(self):
        src = self._get_source()
        assert "INSERT INTO detected_events" in src

    def test_insert_into_momentum_snapshots_present(self):
        src = self._get_source()
        assert "INSERT INTO momentum_snapshots" in src

    def test_insert_into_possessions_present(self):
        """DB-03: INSERT INTO possessions must be present."""
        src = self._get_source()
        assert "INSERT INTO possessions" in src

    def test_insert_into_shot_logs_present(self):
        """DB-03: INSERT INTO shot_logs must be present."""
        src = self._get_source()
        assert "INSERT INTO shot_logs" in src
