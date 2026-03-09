"""Tests for tracking/seed_historical.py — RED phase (written before implementation)."""

import inspect
import pathlib
import sys
import unittest
from unittest.mock import MagicMock, patch, call


class TestSeedHistoricalStructure(unittest.TestCase):
    """Verify seed_historical module and function structure without a live DB."""

    def test_module_is_importable(self):
        """seed_historical must be importable without a DATABASE_URL set."""
        # Ensure DATABASE_URL is absent so the module doesn't auto-connect on import
        import importlib
        with patch.dict("os.environ", {}, clear=False):
            import tracking.seed_historical  # noqa: F401
        self.assertIn("seed_historical", dir(
            __import__("tracking.seed_historical", fromlist=["seed_historical"])
        ))

    def test_seed_historical_function_exists(self):
        """seed_historical() must be a callable function."""
        from tracking.seed_historical import seed_historical
        self.assertTrue(callable(seed_historical))

    def test_references_seed_games_sql(self):
        """seed_historical() source must reference seed_games.sql."""
        from tracking.seed_historical import seed_historical
        src = inspect.getsource(seed_historical)
        self.assertIn("seed_games.sql", src)

    def test_references_seed_players_sql(self):
        """seed_historical() source must reference seed_players.sql."""
        from tracking.seed_historical import seed_historical
        src = inspect.getsource(seed_historical)
        self.assertIn("seed_players.sql", src)

    def test_references_tracking_coordinates_note(self):
        """seed_historical() must print a note about tracking_coordinates."""
        from tracking.seed_historical import seed_historical
        src = inspect.getsource(seed_historical)
        self.assertIn("tracking_coordinates", src)

    def test_handles_missing_database_url_without_crashing(self):
        """seed_historical() must catch EnvironmentError and exit cleanly (not raise)."""
        from tracking import seed_historical as mod
        # Patch get_connection to raise EnvironmentError (no DATABASE_URL)
        with patch("tracking.seed_historical.get_connection",
                   side_effect=EnvironmentError("DATABASE_URL not set")):
            try:
                with self.assertRaises(SystemExit) as ctx:
                    mod.seed_historical()
                self.assertEqual(ctx.exception.code, 1)
            except SystemExit as e:
                self.assertEqual(e.code, 1)

    def test_executes_both_sql_files(self):
        """seed_historical() must execute seed_games.sql and seed_players.sql."""
        from tracking import seed_historical as mod

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        # COUNT queries return (N,) tuples
        mock_cursor.fetchone.return_value = (42,)

        with patch("tracking.seed_historical.get_connection", return_value=mock_conn):
            mod.seed_historical()

        # cursor.execute must have been called at least twice (for the two SQL files)
        execute_calls = mock_cursor.execute.call_count
        self.assertGreaterEqual(execute_calls, 2,
                                f"Expected at least 2 execute() calls, got {execute_calls}")

    def test_commits_after_seeding(self):
        """seed_historical() must commit the transaction."""
        from tracking import seed_historical as mod

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (10,)

        with patch("tracking.seed_historical.get_connection", return_value=mock_conn):
            mod.seed_historical()

        mock_conn.commit.assert_called()

    def test_prints_row_counts(self, capsys=None):
        """seed_historical() must print the counts of games and players rows."""
        from tracking import seed_historical as mod
        import io
        from contextlib import redirect_stdout

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (40,)

        buf = io.StringIO()
        with patch("tracking.seed_historical.get_connection", return_value=mock_conn):
            with redirect_stdout(buf):
                mod.seed_historical()

        output = buf.getvalue()
        # Should print some numeric count info
        self.assertIn("40", output)

    def test_main_guard_calls_seed_historical(self):
        """The __main__ guard must call seed_historical()."""
        src = pathlib.Path("tracking/seed_historical.py").read_text(encoding="utf-8")
        self.assertIn('if __name__ == "__main__"', src)
        self.assertIn("seed_historical()", src)


if __name__ == "__main__":
    unittest.main()
