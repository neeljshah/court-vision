"""Tests for scripts/live_run.py — the cycle-88h game-day orchestrator.

The orchestrator is a pure shell-out chain on top of the cycle-88a..g
sub-scripts (live_game_poll, predict_in_game, update_inactives,
update_confirmed_starters, poll_line_movement) plus cycle 60/61's
fetch_injury_espn + fetch_lineups. No production code is invoked here —
every test mocks subprocess and the tip-off fetcher.

What we lock in:
  1. compose_phase_commands returns the exact argv lists per phase.
  2. --dry-run prints every phase's plan and does NOT touch subprocess.
  3. Phase auto-detection from tip-off times (clock vs T-90 / T-30 / live).
  4. SIGINT shuts down the supervisor and terminates tracked children.
  5. Injury + lineups commands match the existing cycle-60/61 CLI shape.
"""
from __future__ import annotations

import io
import os
import signal
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.live_run as lr  # noqa: E402


# ---------------------------------------------------------------------------
# compose_phase_commands — pure functions.
# ---------------------------------------------------------------------------

class TestComposePhaseCommands(unittest.TestCase):

    DATE = "2026-05-24"

    def test_phase1_has_injury_lineups_lineposition(self):
        plan = lr.compose_phase_commands(1, self.DATE, python_exe="python")
        oneshot_paths = [c[1] for c in plan["oneshot"]]
        self.assertTrue(any(p.endswith("fetch_injury_espn.py") for p in oneshot_paths))
        self.assertTrue(any(p.endswith("fetch_lineups.py") for p in oneshot_paths))
        recurring_paths = [c[1] for c in plan["recurring"]]
        self.assertTrue(any(p.endswith("poll_line_movement.py") for p in recurring_paths))

    def test_phase1_no_line_poll_when_disabled(self):
        plan = lr.compose_phase_commands(1, self.DATE, line_poll=False,
                                          python_exe="python")
        self.assertEqual(plan["recurring"], [])
        # Refreshes still run.
        self.assertEqual(len(plan["oneshot"]), 2)

    def test_phase2_has_inactives_and_starters(self):
        plan = lr.compose_phase_commands(2, self.DATE, python_exe="python")
        oneshot_paths = [c[1] for c in plan["oneshot"]]
        self.assertTrue(any(p.endswith("update_inactives.py") for p in oneshot_paths))
        self.assertTrue(any(p.endswith("update_confirmed_starters.py")
                              for p in oneshot_paths))
        # Line poll still on in phase 2.
        recurring_paths = [c[1] for c in plan["recurring"]]
        self.assertTrue(any(p.endswith("poll_line_movement.py") for p in recurring_paths))

    def test_phase3_has_live_poll_and_line_poll(self):
        plan = lr.compose_phase_commands(3, self.DATE, python_exe="python")
        recurring_paths = [c[1] for c in plan["recurring"]]
        self.assertTrue(any(p.endswith("live_game_poll.py") for p in recurring_paths))
        self.assertTrue(any(p.endswith("poll_line_movement.py") for p in recurring_paths))
        # No precomputed predict_in_game (those fire per end-of-period).
        self.assertEqual(plan["oneshot"], [])

    def test_phase4_is_empty(self):
        plan = lr.compose_phase_commands(4, self.DATE, python_exe="python")
        self.assertEqual(plan["recurring"], [])
        self.assertEqual(plan["oneshot"], [])

    def test_unknown_phase_raises(self):
        with self.assertRaises(ValueError):
            lr.compose_phase_commands(99, self.DATE, python_exe="python")


# ---------------------------------------------------------------------------
# Cycle-60/61 contract — the injury/lineups commands match the existing CLIs.
# ---------------------------------------------------------------------------

class TestSubScriptContract(unittest.TestCase):

    def test_injury_cmd_uses_espn_and_date(self):
        cmd = lr.compose_injury_cmd("2026-05-24", python_exe="python")
        self.assertEqual(cmd[0], "python")
        self.assertTrue(cmd[1].endswith("fetch_injury_espn.py"))
        self.assertIn("--date", cmd)
        self.assertIn("2026-05-24", cmd)

    def test_lineups_cmd_uses_fetch_lineups_and_date(self):
        cmd = lr.compose_lineups_cmd("2026-05-24", python_exe="python")
        self.assertTrue(cmd[1].endswith("fetch_lineups.py"))
        self.assertIn("--date", cmd)
        self.assertIn("2026-05-24", cmd)

    def test_live_poll_cmd_passes_daemon_and_interval(self):
        cmd = lr.compose_live_poll_cmd("2026-05-24", interval_s=30,
                                         python_exe="python")
        self.assertTrue(cmd[1].endswith("live_game_poll.py"))
        self.assertIn("--daemon", cmd)
        self.assertIn("--interval", cmd)
        self.assertIn("30", cmd)

    def test_line_poll_cmd_passes_daemon_and_interval(self):
        cmd = lr.compose_line_poll_cmd("2026-05-24", interval_s=300,
                                         python_exe="python")
        self.assertTrue(cmd[1].endswith("poll_line_movement.py"))
        self.assertIn("--daemon", cmd)
        self.assertIn("--interval", cmd)
        self.assertIn("300", cmd)

    def test_predict_in_game_cmd_per_event(self):
        cmd = lr.compose_predict_in_game_cmd("0022400123", 2,
                                              python_exe="python")
        self.assertTrue(cmd[1].endswith("predict_in_game.py"))
        self.assertIn("--game-id", cmd)
        self.assertIn("0022400123", cmd)
        self.assertIn("--period", cmd)
        self.assertIn("2", cmd)


# ---------------------------------------------------------------------------
# --dry-run must NOT invoke subprocess at all and must print every phase.
# ---------------------------------------------------------------------------

class TestDryRun(unittest.TestCase):

    def test_dry_run_prints_every_phase_and_skips_subprocess(self):
        buf = io.StringIO()
        with mock.patch("scripts.live_run.subprocess.run") as mrun, \
                mock.patch("scripts.live_run.subprocess.Popen") as mpopen, \
                mock.patch("scripts.live_run._fetch_tipoffs", return_value=[]), \
                redirect_stdout(buf):
            rc = lr.main(["--date", "2026-05-24", "--dry-run"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        # All four phases referenced in the printed plan.
        for ph in (1, 2, 3, 4):
            self.assertIn(f"phase {ph}", out)
        # And all the cycle-88 sub-scripts appear at least once.
        for script in ("fetch_injury_espn.py", "fetch_lineups.py",
                         "update_inactives.py", "update_confirmed_starters.py",
                         "live_game_poll.py", "poll_line_movement.py",
                         "predict_in_game.py"):
            self.assertIn(script, out)
        # Critically: zero subprocess invocations.
        mrun.assert_not_called()
        mpopen.assert_not_called()

    def test_dry_run_no_line_poll_omits_poll_line_movement(self):
        buf = io.StringIO()
        with mock.patch("scripts.live_run.subprocess.run"), \
                mock.patch("scripts.live_run.subprocess.Popen"), \
                mock.patch("scripts.live_run._fetch_tipoffs", return_value=[]), \
                redirect_stdout(buf):
            rc = lr.main(["--date", "2026-05-24", "--dry-run", "--no-line-poll"])
        self.assertEqual(rc, 0)
        # poll_line_movement.py must not appear when --no-line-poll is set.
        self.assertNotIn("poll_line_movement.py", buf.getvalue())

    def test_dry_run_with_explicit_phase_only_prints_that_phase(self):
        buf = io.StringIO()
        with mock.patch("scripts.live_run.subprocess.run"), \
                mock.patch("scripts.live_run.subprocess.Popen"), \
                mock.patch("scripts.live_run._fetch_tipoffs", return_value=[]), \
                redirect_stdout(buf):
            rc = lr.main(["--date", "2026-05-24", "--dry-run", "--phase", "3"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("phase 3", out)
        self.assertNotIn("phase 1:", out)
        self.assertNotIn("phase 2:", out)
        self.assertNotIn("phase 4:", out)


# ---------------------------------------------------------------------------
# Phase auto-detection from tip-off time.
# ---------------------------------------------------------------------------

class TestPhaseAutoDetection(unittest.TestCase):

    def setUp(self):
        # Tip-off at 23:00 UTC (~7pm ET).
        self.tip = datetime(2026, 5, 24, 23, 0, tzinfo=timezone.utc)

    def test_phase1_when_more_than_30min_before_tip(self):
        now = self.tip - timedelta(minutes=60)
        self.assertEqual(lr.detect_phase(now, self.tip), 1)

    def test_phase1_at_T_minus_30_boundary(self):
        # Exactly T-30 should still resolve to phase 1 (we transition AT T-30).
        now = self.tip - timedelta(minutes=30)
        self.assertEqual(lr.detect_phase(now, self.tip), 1)

    def test_phase2_inside_pre_tip_window(self):
        now = self.tip - timedelta(minutes=15)
        self.assertEqual(lr.detect_phase(now, self.tip), 2)

    def test_phase3_after_tip_while_live(self):
        now = self.tip + timedelta(minutes=45)
        self.assertEqual(lr.detect_phase(now, self.tip, last_game_status="LIVE"), 3)

    def test_phase4_when_all_games_final(self):
        now = self.tip + timedelta(hours=4)
        self.assertEqual(lr.detect_phase(now, self.tip, last_game_status="FINAL"), 4)

    def test_phase1_when_no_tip_known(self):
        now = datetime(2026, 5, 24, 17, 0, tzinfo=timezone.utc)
        self.assertEqual(lr.detect_phase(now, None), 1)

    def test_first_tipoff_picks_min_from_mocked_slate(self):
        early = datetime(2026, 5, 24, 23, 0, tzinfo=timezone.utc)
        late  = datetime(2026, 5, 25, 2, 30, tzinfo=timezone.utc)
        with mock.patch("scripts.live_run._fetch_tipoffs",
                          return_value=[
                              {"tipoff_utc": late},
                              {"tipoff_utc": early},
                          ]):
            got = lr.first_tipoff("2026-05-24")
        self.assertEqual(got, early)

    def test_first_tipoff_none_when_no_games(self):
        with mock.patch("scripts.live_run._fetch_tipoffs", return_value=[]):
            self.assertIsNone(lr.first_tipoff("2026-05-24"))


# ---------------------------------------------------------------------------
# Supervisor: SIGINT / Ctrl-C terminates tracked children cleanly.
# ---------------------------------------------------------------------------

class _FakeProc:
    """Minimal Popen stand-in: tracks terminate/kill, supports poll()."""

    def __init__(self) -> None:
        self.terminated = False
        self.killed = False
        self._alive = True

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self.terminated = True
        self._alive = False

    def kill(self):
        self.killed = True
        self._alive = False


class TestSupervisorShutdown(unittest.TestCase):

    def test_shutdown_terminates_all_tracked_children(self):
        sup = lr._DaemonSupervisor()
        fake_a, fake_b = _FakeProc(), _FakeProc()
        sup._children.extend([fake_a, fake_b])

        sup.shutdown(signum=getattr(signal, "SIGINT", 2))
        self.assertTrue(fake_a.terminated)
        self.assertTrue(fake_b.terminated)
        self.assertTrue(sup._shutting_down)

    def test_shutdown_is_idempotent(self):
        sup = lr._DaemonSupervisor()
        fake = _FakeProc()
        sup._children.append(fake)
        sup.shutdown(signum=15)
        # Second call must not blow up and must not "re-terminate".
        fake.terminated = False
        sup.shutdown(signum=15)
        self.assertFalse(fake.terminated)

    def test_signal_handler_installs_and_triggers_shutdown(self):
        sup = lr._DaemonSupervisor()
        fake = _FakeProc()
        sup._children.append(fake)

        captured_handlers = {}

        def fake_signal(sig, handler):
            captured_handlers[sig] = handler

        with mock.patch("scripts.live_run.signal.signal", side_effect=fake_signal):
            lr.install_signal_handlers(sup)

        sigint = getattr(signal, "SIGINT", None)
        self.assertIsNotNone(sigint)
        self.assertIn(sigint, captured_handlers)
        # Fire the handler as if SIGINT arrived.
        with mock.patch("scripts.live_run.signal.signal"):
            captured_handlers[sigint](sigint, None)
        self.assertTrue(sup._shutting_down)
        self.assertTrue(fake.terminated)


# ---------------------------------------------------------------------------
# Argument errors return code 2.
# ---------------------------------------------------------------------------

class TestArgErrors(unittest.TestCase):

    def test_bad_date_returns_2(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = lr.main(["--date", "not-a-date", "--dry-run"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
