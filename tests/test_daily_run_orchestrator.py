"""Tests for scripts/daily_run.py — the cycle-54 daily ops orchestrator.

Note this file is NAMED test_daily_run_orchestrator.py (not test_daily_run.py)
because tests/test_daily_run.py already exists and covers the unrelated
scripts/daily_run.sh (backtest settlement pipeline). The two scripts share a
name in different extensions; the orchestrator is the new Python one.

We never let the orchestrator actually shell out to the sub-scripts — every
test that exercises the run loop monkey-patches subprocess.run / Popen. The
point of these tests is to lock in:

* the right argv lists are composed for every flag combination,
* --dry-run prints commands and does NOT call subprocess at all,
* the stdout parser correctly extracts the bet count from compare_to_lines
  output (real table + "no bets" + injuries-only-skipped cases).
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.daily_run as dr  # noqa: E402


# ---------------------------------------------------------------------------
# compose_*_cmd helpers — pure functions, no side effects to mock.
# ---------------------------------------------------------------------------

class TestComposeCommands(unittest.TestCase):

    def test_injury_cmd_basic(self):
        cmd = dr.compose_injury_cmd("2026-05-24", python_exe="python")
        self.assertEqual(cmd[0], "python")
        self.assertTrue(cmd[1].endswith("fetch_injury_report.py"))
        self.assertEqual(cmd[-2:], ["--date", "2026-05-24"])

    def test_slate_cmd_always_includes_save_and_injuries(self):
        cmd = dr.compose_slate_cmd("2026-05-24", top=None, python_exe="python")
        self.assertTrue(cmd[1].endswith("predict_slate.py"))
        self.assertIn("--save", cmd)
        self.assertIn("--injuries", cmd)
        self.assertIn("--date", cmd)
        # No --top because top=None
        self.assertNotIn("--top", cmd)

    def test_slate_cmd_with_top(self):
        cmd = dr.compose_slate_cmd("2026-05-24", top=5, python_exe="python")
        self.assertIn("--top", cmd)
        self.assertIn("5", cmd)

    def test_compare_cmd_minimal(self):
        cmd = dr.compose_compare_cmd("tonight.csv", python_exe="python")
        self.assertTrue(cmd[1].endswith("compare_to_lines.py"))
        self.assertIn("tonight.csv", cmd)
        self.assertIn("--injuries", cmd)
        self.assertNotIn("--kelly", cmd)
        self.assertNotIn("--bankroll", cmd)

    def test_compare_cmd_with_kelly_and_bankroll(self):
        cmd = dr.compose_compare_cmd("tonight.csv", kelly=True, bankroll=1000.0,
                                     python_exe="python")
        self.assertIn("--kelly", cmd)
        self.assertIn("--bankroll", cmd)
        self.assertIn("1000.0", cmd)


# ---------------------------------------------------------------------------
# --dry-run must NOT invoke subprocess at all.
# ---------------------------------------------------------------------------

class TestDryRun(unittest.TestCase):

    def test_dry_run_does_not_invoke_subprocess(self):
        with mock.patch("scripts.daily_run.subprocess.run") as mrun, \
             mock.patch("scripts.daily_run.subprocess.Popen") as mpopen:
            rc = dr.main(["--date", "2026-05-24", "--lines", "tonight.csv",
                          "--kelly", "--bankroll", "1000", "--dry-run"])
        self.assertEqual(rc, 0)
        mrun.assert_not_called()
        mpopen.assert_not_called()

    def test_dry_run_prints_three_commands(self):
        with mock.patch("scripts.daily_run.subprocess.run"), \
             mock.patch("scripts.daily_run.subprocess.Popen"), \
             mock.patch("builtins.print") as mprint:
            dr.main(["--date", "2026-05-24", "--lines", "tonight.csv", "--dry-run"])
        joined = "\n".join(
            " ".join(str(a) for a in call.args) for call in mprint.call_args_list
        )
        self.assertIn("fetch_injury_report.py", joined)
        self.assertIn("predict_slate.py", joined)
        self.assertIn("compare_to_lines.py", joined)
        self.assertIn("tonight.csv", joined)

    def test_dry_run_skip_injuries_omits_step_1(self):
        with mock.patch("scripts.daily_run.subprocess.run"), \
             mock.patch("scripts.daily_run.subprocess.Popen"), \
             mock.patch("builtins.print") as mprint:
            dr.main(["--date", "2026-05-24", "--skip-injuries", "--dry-run"])
        joined = "\n".join(
            " ".join(str(a) for a in call.args) for call in mprint.call_args_list
        )
        self.assertNotIn("fetch_injury_report.py", joined)
        self.assertIn("predict_slate.py", joined)
        self.assertIn("skipped", joined.lower())


# ---------------------------------------------------------------------------
# parse_bet_count — the only string-parsing logic in the orchestrator.
# ---------------------------------------------------------------------------

class TestBetParser(unittest.TestCase):

    def test_no_bets_message(self):
        s = "[done] no bets passed --min-edge filter\n"
        self.assertEqual(dr.parse_bet_count(s), 0)

    def test_empty_stdout(self):
        self.assertEqual(dr.parse_bet_count(""), 0)

    def test_real_table_three_bets(self):
        # Mirrors the actual compare_to_lines stdout format (cycle 51+53).
        stdout = (
            "  [injuries] loaded 12 unavailable player(s) from injuries_2026-05-24.json\n"
            "\n"
            "  player                 stat line   model edge    side   prob   odds   EV/$   Kelly%\n"
            "  ---------------------- ---- -----  ----- ------  -----  -----  -----  -------  -------\n"
            "  Nikola Jokic           REB  11.5  13.07  +1.57  OVER   0.671   -110  +0.2796     5.42%\n"
            "  LeBron James           PTS  24.5  26.10  +1.60  OVER   0.610   -110  +0.1645     2.10%\n"
            "  Stephen Curry          FG3M  4.5   5.20  +0.70  OVER   0.590   -110  +0.1265     1.10%\n"
            "\n"
            "  Total Kelly stake on positive-EV bets: $86.20 of $1000.00 bankroll\n"
        )
        self.assertEqual(dr.parse_bet_count(stdout), 3)

    def test_table_no_kelly_summary(self):
        stdout = (
            "  player                 stat line   model edge    side   prob   odds   EV/$   Kelly%\n"
            "  ---------------------- ---- -----  ----- ------  -----  -----  -----  -------  -------\n"
            "  Nikola Jokic           REB  11.5  13.07  +1.57  OVER   0.671   -110  +0.2796     5.42%\n"
        )
        self.assertEqual(dr.parse_bet_count(stdout), 1)

    def test_only_injury_skip_lines(self):
        # Every line was filtered by --injuries, so no table, no "no bets" line.
        stdout = (
            "  [injuries] loaded 12 unavailable player(s) from injuries_2026-05-24.json\n"
            "  [injuries] skipped 4 line(s) for OUT/DOUBTFUL players:\n"
            "    - Joel Embiid (OUT)\n"
            "    - Kawhi Leonard (OUT)\n"
        )
        self.assertEqual(dr.parse_bet_count(stdout), 0)


if __name__ == "__main__":
    sys.exit(unittest.main())
