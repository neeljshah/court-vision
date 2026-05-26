"""tests/test_daemon_watchdog.py — R19_L3 unit tests for the daemon watchdog.

The tests exercise the watchdog WITHOUT touching the live RunPod daemons:
ps + subprocess + Discord post_alert are all injected so the test suite is
fully hermetic and runs in <1s.

Ship gate: stale heartbeat → restart triggered (and Discord alert fired).
"""
from __future__ import annotations

import json
import os
import sys
import time
import unittest
from typing import Any, Dict, List
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts import daemon_watchdog as dw  # noqa: E402


def _make_daemon(tmp_dir: str, name: str = "stale_daemon",
                 expected_interval: int = 30) -> Dict[str, Any]:
    return {
        "name": name,
        "command": f"python -u scripts/{name}.py",
        "expected_interval_sec": expected_interval,
        "heartbeat_file": os.path.join(tmp_dir, f"{name}.txt"),
        "restart_cmd": f"echo RESTARTED-{name}",
        "process_match": f"{name}.py",
    }


def _touch_old(path: str, age_sec: float) -> None:
    """Create file and back-date its mtime by ``age_sec`` seconds."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("2026-05-26T00:00:00Z\n")
    past = time.time() - age_sec
    os.utime(path, (past, past))


class HeartbeatFreshnessTests(unittest.TestCase):
    def test_missing_heartbeat_is_stale(self):
        d = _make_daemon("/nonexistent_dir", "ghost_daemon")
        status = dw.check_daemon(d, ps_runner=lambda: "")
        self.assertTrue(status["heartbeat_stale"])
        self.assertTrue(status["dead"])
        self.assertIn("heartbeat_missing", status["reason"])

    def test_fresh_heartbeat_and_live_process_is_ok(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = _make_daemon(tmp, "alive_daemon", expected_interval=30)
            with open(d["heartbeat_file"], "w") as fh:
                fh.write("now\n")
            # ps says the process is alive.
            ps = lambda: f"  1234 python -u scripts/alive_daemon.py --interval-sec 30\n"
            status = dw.check_daemon(d, ps_runner=ps)
            self.assertFalse(status["heartbeat_stale"])
            self.assertTrue(status["process_alive"])
            self.assertFalse(status["dead"])

    def test_stale_heartbeat_flags_dead_even_if_process_alive(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = _make_daemon(tmp, "wedged_daemon", expected_interval=30)
            _touch_old(d["heartbeat_file"], age_sec=600)  # 10 min old, limit=90s
            ps = lambda: f"  4321 python -u scripts/wedged_daemon.py\n"
            status = dw.check_daemon(d, ps_runner=ps)
            self.assertTrue(status["heartbeat_stale"])
            self.assertTrue(status["process_alive"])  # wedged but still in ps
            self.assertTrue(status["dead"])


class RateLimiterTests(unittest.TestCase):
    def test_allows_up_to_max_then_blocks(self):
        rl = dw.RestartRateLimiter(max_per_hour=3)
        self.assertTrue(rl.allow("a", now=1000))
        self.assertTrue(rl.allow("a", now=1001))
        self.assertTrue(rl.allow("a", now=1002))
        self.assertFalse(rl.allow("a", now=1003))  # 4th in same window → blocked

    def test_window_rolls_over(self):
        rl = dw.RestartRateLimiter(max_per_hour=2)
        self.assertTrue(rl.allow("b", now=0))
        self.assertTrue(rl.allow("b", now=10))
        self.assertFalse(rl.allow("b", now=20))
        # 1 hour + 1s later — both old timestamps evicted.
        self.assertTrue(rl.allow("b", now=3601))

    def test_different_daemons_independent(self):
        rl = dw.RestartRateLimiter(max_per_hour=1)
        self.assertTrue(rl.allow("x", now=100))
        self.assertTrue(rl.allow("y", now=100))   # different bucket
        self.assertFalse(rl.allow("x", now=101))  # x is full


class SweepRestartTests(unittest.TestCase):
    """The headline test: stale heartbeat → restart triggered + Discord fired."""

    def test_sweep_restarts_dead_daemon_and_fires_discord(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            hb_dir = os.path.join(tmp, "hbs")
            os.makedirs(hb_dir, exist_ok=True)
            d = _make_daemon(hb_dir, "stale_demo", expected_interval=10)
            _touch_old(d["heartbeat_file"], age_sec=600)  # very stale
            registry = [d]
            limiter = dw.RestartRateLimiter(max_per_hour=3)
            shell_calls: List[str] = []
            discord_calls: List[Dict[str, Any]] = []

            def fake_shell(cmd: str):
                shell_calls.append(cmd)
                return mock.Mock(returncode=0, stdout="ok", stderr="")

            def fake_post(**kwargs):
                discord_calls.append(kwargs)
                return True

            summary = dw.sweep(
                registry, limiter,
                restart_log_path=os.path.join(tmp, "restarts.md"),
                ps_runner=lambda: "",  # process is gone
                shell_runner=fake_shell,
                post_alert_fn=fake_post,
            )

            # Headline assertions: restart triggered + Discord alert fired.
            self.assertIn("stale_demo", summary["dead"])
            self.assertEqual(len(summary["restarted"]), 1)
            self.assertTrue(summary["restarted"][0]["restart_ok"])
            self.assertTrue(summary["restarted"][0]["discord_fired"])
            self.assertEqual(len(shell_calls), 1)
            self.assertIn("RESTARTED-stale_demo", shell_calls[0])
            self.assertEqual(len(discord_calls), 1)
            self.assertEqual(discord_calls[0]["severity"], "WARN")
            self.assertEqual(discord_calls[0]["source"], "daemon_watchdog")

            # Restart log written.
            self.assertTrue(os.path.exists(os.path.join(tmp, "restarts.md")))
            with open(os.path.join(tmp, "restarts.md"), "r", encoding="utf-8") as fh:
                contents = fh.read()
            self.assertIn("stale_demo", contents)

    def test_sweep_skips_healthy_daemon(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = _make_daemon(tmp, "healthy", expected_interval=30)
            with open(d["heartbeat_file"], "w") as fh:
                fh.write("fresh\n")
            limiter = dw.RestartRateLimiter()
            shell_calls: List[str] = []
            discord_calls: List[Dict[str, Any]] = []
            summary = dw.sweep(
                [d], limiter,
                restart_log_path=os.path.join(tmp, "restarts.md"),
                ps_runner=lambda: " 1 python scripts/healthy.py\n",
                shell_runner=lambda c: shell_calls.append(c) or mock.Mock(returncode=0),
                post_alert_fn=lambda **k: discord_calls.append(k) or True,
            )
            self.assertEqual(summary["dead"], [])
            self.assertEqual(len(summary["restarted"]), 0)
            self.assertEqual(shell_calls, [])
            self.assertEqual(discord_calls, [])

    def test_rate_limit_blocks_fourth_restart(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = _make_daemon(tmp, "flapper", expected_interval=10)
            _touch_old(d["heartbeat_file"], age_sec=900)
            limiter = dw.RestartRateLimiter(max_per_hour=2)
            # Pre-load the bucket so the next sweep tick is over the limit.
            limiter.allow("flapper", now=time.time())
            limiter.allow("flapper", now=time.time())
            summary = dw.sweep(
                [d], limiter,
                restart_log_path=os.path.join(tmp, "restarts.md"),
                ps_runner=lambda: "",
                shell_runner=lambda c: mock.Mock(returncode=0),
                post_alert_fn=lambda **k: True,
            )
            self.assertIn("flapper", summary["rate_limited"])
            self.assertEqual(len(summary["restarted"]), 0)


class RegistryLoaderTests(unittest.TestCase):
    def test_loads_real_registry(self):
        path = os.path.join(_ROOT, "scripts", "daemon_registry.json")
        if not os.path.exists(path):
            self.skipTest("registry not present in this checkout")
        registry = dw.load_registry(path)
        self.assertGreaterEqual(len(registry), 10)
        for d in registry:
            self.assertIn("name", d)
            self.assertIn("restart_cmd", d)
            self.assertIn("heartbeat_file", d)
            self.assertIn("expected_interval_sec", d)


class HeartbeatHelperTests(unittest.TestCase):
    def test_write_heartbeat_creates_file(self):
        import tempfile
        from src.monitor.daemon_heartbeat import write_heartbeat
        with tempfile.TemporaryDirectory() as tmp:
            ok = write_heartbeat("unit_test_daemon", hb_dir=tmp)
            self.assertTrue(ok)
            hb_path = os.path.join(tmp, "unit_test_daemon.txt")
            self.assertTrue(os.path.exists(hb_path))
            with open(hb_path, "r", encoding="utf-8") as fh:
                contents = fh.read().strip()
            # ISO-8601 timestamp.
            self.assertRegex(contents, r"^20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


if __name__ == "__main__":
    unittest.main()
