"""Cycle 65: tests for --auto-lineups / --auto-lines in scripts/daily_run.py.

The cycle-54 daily_run.py tests live in test_daily_run_orchestrator.py and
lock down the original injuries→slate→compare composition. This file
covers the new cycle-65 helpers (compose_lineups_cmd, compose_dk_props_cmd)
and the wiring that activates them.

All tests mock subprocess.run and never let the orchestrator actually
shell out — same discipline as the cycle-54 tests.
"""
from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.daily_run as dr  # noqa: E402


class TestNewComposeHelpers(unittest.TestCase):
    """compose_lineups_cmd + compose_dk_props_cmd are pure — no mocks needed."""

    def test_lineups_cmd_basic(self):
        cmd = dr.compose_lineups_cmd("2026-05-24", python_exe="python")
        # Must call fetch_lineups.py with --date
        self.assertEqual(cmd[0], "python")
        self.assertTrue(cmd[1].endswith(os.path.join("scripts", "fetch_lineups.py")))
        self.assertIn("--date", cmd)
        self.assertIn("2026-05-24", cmd)

    def test_dk_props_cmd_defaults_to_draftkings(self):
        cmd = dr.compose_dk_props_cmd("2026-05-24", python_exe="python")
        self.assertTrue(cmd[1].endswith(os.path.join("scripts", "fetch_dk_props.py")))
        # Default books list is just draftkings
        self.assertIn("--book", cmd)
        self.assertIn("draftkings", cmd)
        self.assertEqual(cmd.count("--book"), 1)

    def test_dk_props_cmd_multi_book(self):
        cmd = dr.compose_dk_props_cmd("2026-05-24",
                                        books=["draftkings", "fanduel"],
                                        python_exe="python")
        # One --book per book name
        self.assertEqual(cmd.count("--book"), 2)
        self.assertIn("draftkings", cmd)
        self.assertIn("fanduel", cmd)

    def test_slate_cmd_with_lineups_adds_flag(self):
        cmd = dr.compose_slate_cmd("2026-05-24", with_lineups=True,
                                     python_exe="python")
        self.assertIn("--lineups", cmd)
        self.assertIn("--injuries", cmd)
        self.assertIn("--save", cmd)

    def test_slate_cmd_without_lineups_omits_flag(self):
        cmd = dr.compose_slate_cmd("2026-05-24", with_lineups=False,
                                     python_exe="python")
        self.assertNotIn("--lineups", cmd)
        self.assertIn("--injuries", cmd)

    def test_compare_cmd_with_lineups_adds_flag(self):
        cmd = dr.compose_compare_cmd("/x/lines.csv", kelly=True,
                                       bankroll=1000.0, with_lineups=True,
                                       python_exe="python")
        self.assertIn("--lineups", cmd)
        self.assertIn("--injuries", cmd)
        self.assertIn("--kelly", cmd)
        self.assertIn("--bankroll", cmd)
        self.assertIn("1000.0", cmd)


class TestDryRunWithAutoFlags(unittest.TestCase):
    """--dry-run + --auto-* should print the new step lines and skip subprocess."""

    def _run_dry(self, argv):
        buf = io.StringIO()
        with mock.patch("scripts.daily_run.subprocess.run") as mock_run, \
             redirect_stdout(buf):
            try:
                rc = dr.main(argv)
            except SystemExit as e:
                rc = e.code
        # Hard invariant: dry-run never actually invokes subprocess.
        self.assertEqual(mock_run.call_count, 0)
        return rc, buf.getvalue()

    def test_dry_run_auto_lineups_prints_step_1b(self):
        rc, out = self._run_dry(["--dry-run", "--auto-lineups", "--date", "2026-05-24"])
        self.assertEqual(rc, 0)
        self.assertIn("[1b]", out)
        self.assertIn("fetch_lineups.py", out)
        # slate command should also carry --lineups in dry-run print
        self.assertIn("--lineups", out)

    def test_dry_run_auto_lines_prints_step_1c_and_uses_lines_path(self):
        rc, out = self._run_dry(["--dry-run", "--auto-lines", "--date", "2026-05-24"])
        self.assertEqual(rc, 0)
        self.assertIn("[1c]", out)
        self.assertIn("fetch_dk_props.py", out)
        # compare_to_lines step should appear and reference data/lines/<date>.csv
        self.assertIn("compare_to_lines.py", out)
        self.assertIn(os.path.join("data", "lines", "2026-05-24.csv"), out)

    def test_dry_run_neither_auto_flag_skips_new_steps(self):
        rc, out = self._run_dry(["--dry-run", "--date", "2026-05-24"])
        self.assertEqual(rc, 0)
        self.assertNotIn("[1b]", out)
        self.assertNotIn("[1c]", out)
        # No --lineups in any composed command
        self.assertNotIn("--lineups", out)

    def test_dry_run_explicit_lines_overrides_auto(self):
        """When --lines /path is given AND --auto-lines, auto-lines path wins
        per cycle-65 semantics (auto-lines is opinionated about where it puts the file)."""
        rc, out = self._run_dry(["--dry-run", "--auto-lines",
                                  "--lines", "/explicit/path.csv",
                                  "--date", "2026-05-24"])
        self.assertEqual(rc, 0)
        # The auto-lines path should be the one passed to compare_to_lines.
        self.assertIn(os.path.join("data", "lines", "2026-05-24.csv"), out)
        # Explicit path should NOT appear.
        self.assertNotIn("/explicit/path.csv", out)


class TestSettleMode(unittest.TestCase):
    """Cycle 71: --settle is a separate post-game mode."""

    def _run_dry(self, argv):
        buf = io.StringIO()
        with mock.patch("scripts.daily_run.subprocess.run") as mock_run, \
             redirect_stdout(buf):
            try:
                rc = dr.main(argv)
            except SystemExit as e:
                rc = e.code
        self.assertEqual(mock_run.call_count, 0)
        return rc, buf.getvalue()

    def test_settle_dry_run_omits_slate_and_compare_steps(self):
        rc, out = self._run_dry(["--dry-run", "--settle", "--date", "2026-05-24"])
        self.assertEqual(rc, 0)
        # Settle plan header replaces normal plan header.
        self.assertIn("SETTLE plan", out)
        # Only the two settle steps appear, not slate / compare.
        self.assertIn("[A]", out)
        self.assertIn("fetch_actuals.py", out)
        self.assertIn("[B]", out)
        self.assertIn("settle_bets.py", out)
        # Normal-flow markers must NOT appear.
        self.assertNotIn("predict_slate.py", out)
        self.assertNotIn("compare_to_lines.py", out)

    def test_compose_actuals_cmd_basic(self):
        cmd = dr.compose_actuals_cmd("2026-05-24", python_exe="python")
        self.assertEqual(cmd[0], "python")
        self.assertTrue(cmd[1].endswith(os.path.join("scripts", "fetch_actuals.py")))
        self.assertIn("--date", cmd)
        self.assertIn("2026-05-24", cmd)

    def test_compose_settle_cmd_points_at_canonical_paths(self):
        cmd = dr.compose_settle_cmd("2026-05-24", project_dir="/proj",
                                      python_exe="python")
        # Args: python, settle_bets.py, bet_log_path, actuals_path
        self.assertEqual(len(cmd), 4)
        self.assertTrue(cmd[1].endswith(os.path.join("scripts", "settle_bets.py")))
        # Both paths follow the canonical data/bets and data/actuals layout.
        self.assertIn(os.path.join("data", "bets", "2026-05-24.csv"), cmd[2])
        self.assertIn(os.path.join("data", "actuals", "2026-05-24.csv"), cmd[3])


class TestReportFlag(unittest.TestCase):
    """Cycle 74: --report runs nightly_report.py at end of either mode."""

    def _run_dry(self, argv):
        buf = io.StringIO()
        with mock.patch("scripts.daily_run.subprocess.run") as mock_run, \
             redirect_stdout(buf):
            try:
                rc = dr.main(argv)
            except SystemExit as e:
                rc = e.code
        self.assertEqual(mock_run.call_count, 0)
        return rc, buf.getvalue()

    def test_compose_report_cmd_basic(self):
        cmd = dr.compose_report_cmd("2026-05-24", python_exe="python")
        self.assertEqual(cmd[0], "python")
        self.assertTrue(cmd[1].endswith(os.path.join("scripts", "nightly_report.py")))
        self.assertIn("--date", cmd)
        self.assertIn("2026-05-24", cmd)

    def test_report_flag_adds_step_4_in_morning_mode(self):
        rc, out = self._run_dry(["--dry-run", "--report", "--date", "2026-05-24"])
        self.assertEqual(rc, 0)
        self.assertIn("[4] nightly_report", out)
        self.assertIn("nightly_report.py", out)

    def test_report_flag_adds_step_C_in_settle_mode(self):
        rc, out = self._run_dry(["--dry-run", "--settle", "--report",
                                  "--date", "2026-05-24"])
        self.assertEqual(rc, 0)
        self.assertIn("[C] nightly_report", out)
        # And the settle plan body is still there.
        self.assertIn("[A] fetch_actuals", out)
        self.assertIn("[B] settle_bets", out)

    def test_no_report_flag_omits_step_4(self):
        rc, out = self._run_dry(["--dry-run", "--date", "2026-05-24"])
        self.assertEqual(rc, 0)
        self.assertNotIn("[4]", out)
        self.assertNotIn("nightly_report.py", out)


if __name__ == "__main__":
    unittest.main()
