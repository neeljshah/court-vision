"""
Tests for tracking/coordinate_writer.py and pipelines/run_pipeline.py.

TDD RED phase: Tests written before implementation.
Covers CoordinateWriter interface, batch buffering, parameterized SQL,
and run_pipeline orchestration wiring.
"""
import inspect
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# CoordinateWriter interface
# ---------------------------------------------------------------------------

class TestCoordinateWriterInterface:
    """CoordinateWriter must expose the expected public API."""

    def test_import(self):
        from tracking.coordinate_writer import CoordinateWriter
        assert CoordinateWriter is not None

    def test_instantiation(self):
        from tracking.coordinate_writer import CoordinateWriter
        cw = CoordinateWriter(game_id="test-game-id")
        assert cw is not None

    def test_stores_game_id(self):
        from tracking.coordinate_writer import CoordinateWriter
        cw = CoordinateWriter(game_id="abc-123")
        assert cw.game_id == "abc-123"

    def test_default_batch_size(self):
        from tracking.coordinate_writer import CoordinateWriter
        cw = CoordinateWriter(game_id="test")
        assert cw.batch_size == 500

    def test_custom_batch_size(self):
        from tracking.coordinate_writer import CoordinateWriter
        cw = CoordinateWriter(game_id="test", batch_size=100)
        assert cw.batch_size == 100

    def test_has_write_batch_method(self):
        from tracking.coordinate_writer import CoordinateWriter
        cw = CoordinateWriter(game_id="test")
        assert hasattr(cw, "write_batch")
        assert callable(cw.write_batch)

    def test_has_flush_method(self):
        from tracking.coordinate_writer import CoordinateWriter
        cw = CoordinateWriter(game_id="test")
        assert hasattr(cw, "flush")
        assert callable(cw.flush)

    def test_buffer_initially_empty(self):
        from tracking.coordinate_writer import CoordinateWriter
        cw = CoordinateWriter(game_id="test")
        assert hasattr(cw, "_buffer")
        assert cw._buffer == []


# ---------------------------------------------------------------------------
# CoordinateWriter buffering behaviour
# ---------------------------------------------------------------------------

class TestCoordinateWriterBuffering:
    """write_batch() buffers rows; flush triggers when batch_size is reached."""

    def _make_tracked_object(self, track_id=1, cx=100.0, cy=200.0):
        from tracking.tracker import TrackedObject
        return TrackedObject(
            track_id=track_id,
            object_type="player",
            cx=cx,
            cy=cy,
            bbox=(75.0, 170.0, 125.0, 230.0),
            confidence=0.9,
            frame_number=0,
            timestamp_ms=0.0,
            velocity_x=0.0,
            velocity_y=0.0,
            speed=0.0,
            direction_degrees=0.0,
        )

    @patch("tracking.coordinate_writer.get_connection")
    def test_write_batch_buffers_objects(self, mock_get_conn):
        """Objects below batch_size threshold are buffered, not immediately flushed."""
        from tracking.coordinate_writer import CoordinateWriter
        cw = CoordinateWriter(game_id="g1", batch_size=500)
        objs = [self._make_tracked_object(i) for i in range(10)]
        cw.write_batch(objs)
        assert len(cw._buffer) == 10
        mock_get_conn.assert_not_called()

    @patch("tracking.coordinate_writer.get_connection")
    def test_flush_clears_buffer(self, mock_get_conn):
        """flush() commits remaining buffer rows and clears the buffer."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value = mock_conn

        from tracking.coordinate_writer import CoordinateWriter
        cw = CoordinateWriter(game_id="g1", batch_size=500)
        cw._buffer = [self._make_tracked_object()]
        cw.flush()
        assert cw._buffer == []

    @patch("tracking.coordinate_writer.get_connection")
    def test_flush_on_empty_buffer_does_not_call_db(self, mock_get_conn):
        """flush() on empty buffer must not open a DB connection."""
        from tracking.coordinate_writer import CoordinateWriter
        cw = CoordinateWriter(game_id="g1")
        cw.flush()
        mock_get_conn.assert_not_called()

    @patch("tracking.coordinate_writer.get_connection")
    def test_write_batch_triggers_flush_when_full(self, mock_get_conn):
        """Buffer flushes automatically when it reaches batch_size."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value = mock_conn

        from tracking.coordinate_writer import CoordinateWriter
        cw = CoordinateWriter(game_id="g1", batch_size=3)
        objs = [self._make_tracked_object(i) for i in range(3)]
        cw.write_batch(objs)
        # Exactly 3 items added, batch_size is 3 — should flush
        mock_get_conn.assert_called_once()
        assert cw._buffer == []


# ---------------------------------------------------------------------------
# Parameterized SQL requirement
# ---------------------------------------------------------------------------

class TestCoordinateWriterSQL:
    """_flush_buffer() must use parameterized SQL (executemany with %s)."""

    def test_uses_parameterized_sql(self):
        from tracking.coordinate_writer import CoordinateWriter
        src = inspect.getsource(CoordinateWriter._flush_buffer)
        # Must use %s placeholders (parameterized), not string formatting
        assert "%s" in src or "executemany" in src

    def test_no_string_format_in_sql(self):
        """SQL must not be built with f-strings or % string formatting."""
        from tracking.coordinate_writer import CoordinateWriter
        src = inspect.getsource(CoordinateWriter._flush_buffer)
        # Ensure no f-string SQL injection patterns
        # (This test is heuristic — we verify executemany is used, not string concat)
        assert "executemany" in src

    def test_player_id_is_none_in_rows(self):
        """player_id must be NULL (None) in all Phase 1 writes."""
        from tracking.coordinate_writer import CoordinateWriter
        src = inspect.getsource(CoordinateWriter._flush_buffer)
        assert "None" in src or "null" in src.lower()

    def test_inserts_to_tracking_coordinates_table(self):
        from tracking.coordinate_writer import CoordinateWriter
        src = inspect.getsource(CoordinateWriter._flush_buffer)
        assert "tracking_coordinates" in src


# ---------------------------------------------------------------------------
# run_pipeline orchestration
# ---------------------------------------------------------------------------

class TestRunPipelineImport:
    """run_pipeline must import and have the correct signature."""

    def test_import(self):
        from pipelines.run_pipeline import run_pipeline
        assert run_pipeline is not None

    def test_accepts_video_path_and_game_id(self):
        from pipelines.run_pipeline import run_pipeline
        sig = inspect.signature(run_pipeline)
        params = list(sig.parameters.keys())
        assert "video_path" in params
        assert "game_id" in params

    def test_has_weights_path_param(self):
        from pipelines.run_pipeline import run_pipeline
        sig = inspect.signature(run_pipeline)
        assert "weights_path" in sig.parameters

    def test_has_conf_threshold_param(self):
        from pipelines.run_pipeline import run_pipeline
        sig = inspect.signature(run_pipeline)
        assert "conf_threshold" in sig.parameters


class TestRunPipelineWiring:
    """run_pipeline source must reference all four components."""

    def test_references_video_ingestor(self):
        from pipelines.run_pipeline import run_pipeline
        src = inspect.getsource(run_pipeline)
        assert "VideoIngestor" in src

    def test_references_object_tracker(self):
        from pipelines.run_pipeline import run_pipeline
        src = inspect.getsource(run_pipeline)
        assert "ObjectTracker" in src

    def test_references_coordinate_writer(self):
        from pipelines.run_pipeline import run_pipeline
        src = inspect.getsource(run_pipeline)
        assert "CoordinateWriter" in src

    def test_references_write_batch(self):
        from pipelines.run_pipeline import run_pipeline
        src = inspect.getsource(run_pipeline)
        assert "write_batch" in src

    def test_references_flush(self):
        from pipelines.run_pipeline import run_pipeline
        src = inspect.getsource(run_pipeline)
        assert "flush" in src

    def test_sets_tracker_fps(self):
        from pipelines.run_pipeline import run_pipeline
        src = inspect.getsource(run_pipeline)
        assert "set_fps" in src
