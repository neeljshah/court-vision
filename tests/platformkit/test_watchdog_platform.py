"""tests/platformkit/test_watchdog_platform.py

Unit tests for the --platform flag added to scripts/daemon_watchdog.py.

Verifies:
  - --platform win  -> _pick_restart_cmd selects restart_cmd_win
  - --platform posix -> _pick_restart_cmd selects restart_cmd
  - --platform auto + sys.platform='win32'  -> selects restart_cmd_win
  - --platform auto + sys.platform='linux'  -> selects restart_cmd
  - fallback: missing restart_cmd_win -> falls back to restart_cmd on win
  - fallback: missing restart_cmd     -> falls back to restart_cmd_win on posix
  - sweep() passes platform to restart_daemon and calls the right cmd
  - main() parses --platform and passes it to sweep

No real processes are spawned, no ports are bound, no filesystem side-effects
beyond a tempdir for the restart log.
"""
from __future__ import annotations

import sys
import types
import tempfile
import os

import pytest

# ---------------------------------------------------------------------------
# Import the module under test (stdlib-only, so this is always safe).
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from scripts.daemon_watchdog import (  # noqa: E402
    _pick_restart_cmd,
    restart_daemon,
    sweep,
    RestartRateLimiter,
    PLATFORM_AUTO,
    PLATFORM_WIN,
    PLATFORM_POSIX,
)

# ---------------------------------------------------------------------------
# Fake registry rows
# ---------------------------------------------------------------------------

FAKE_DAEMON = {
    "name": "test_daemon",
    "expected_interval_sec": 60,
    "heartbeat_file": "data/cache/daemon_heartbeats/test_daemon.txt",
    "restart_cmd": "nohup python test_daemon.py &",
    "restart_cmd_win": "start \"\" /b cmd /c \"python test_daemon.py\"",
    "process_match": "test_daemon.py",
    "heartbeat_optional": True,
}

FAKE_DAEMON_NO_WIN = {
    "name": "posix_only_daemon",
    "expected_interval_sec": 60,
    "heartbeat_file": "data/cache/daemon_heartbeats/posix_only.txt",
    "restart_cmd": "nohup python posix_only.py &",
    "process_match": "posix_only.py",
    "heartbeat_optional": True,
}

FAKE_DAEMON_NO_POSIX = {
    "name": "win_only_daemon",
    "expected_interval_sec": 60,
    "heartbeat_file": "data/cache/daemon_heartbeats/win_only.txt",
    "restart_cmd_win": "start \"\" /b cmd /c \"python win_only.py\"",
    "process_match": "win_only.py",
    "heartbeat_optional": True,
}


# ===========================================================================
# _pick_restart_cmd tests
# ===========================================================================

class TestPickRestartCmd:
    def test_explicit_win_selects_win_cmd(self):
        cmd = _pick_restart_cmd(FAKE_DAEMON, platform=PLATFORM_WIN)
        assert cmd == FAKE_DAEMON["restart_cmd_win"]

    def test_explicit_posix_selects_posix_cmd(self):
        cmd = _pick_restart_cmd(FAKE_DAEMON, platform=PLATFORM_POSIX)
        assert cmd == FAKE_DAEMON["restart_cmd"]

    def test_auto_on_win32_selects_win_cmd(self):
        cmd = _pick_restart_cmd(FAKE_DAEMON, platform=PLATFORM_AUTO,
                                _sys_platform="win32")
        assert cmd == FAKE_DAEMON["restart_cmd_win"]

    def test_auto_on_cygwin_selects_win_cmd(self):
        cmd = _pick_restart_cmd(FAKE_DAEMON, platform=PLATFORM_AUTO,
                                _sys_platform="cygwin")
        assert cmd == FAKE_DAEMON["restart_cmd_win"]

    def test_auto_on_linux_selects_posix_cmd(self):
        cmd = _pick_restart_cmd(FAKE_DAEMON, platform=PLATFORM_AUTO,
                                _sys_platform="linux")
        assert cmd == FAKE_DAEMON["restart_cmd"]

    def test_auto_on_darwin_selects_posix_cmd(self):
        cmd = _pick_restart_cmd(FAKE_DAEMON, platform=PLATFORM_AUTO,
                                _sys_platform="darwin")
        assert cmd == FAKE_DAEMON["restart_cmd"]

    def test_fallback_win_missing_uses_posix(self):
        """No restart_cmd_win -> fall back to restart_cmd even on win."""
        cmd = _pick_restart_cmd(FAKE_DAEMON_NO_WIN, platform=PLATFORM_WIN)
        assert cmd == FAKE_DAEMON_NO_WIN["restart_cmd"]

    def test_fallback_posix_missing_uses_win(self):
        """No restart_cmd -> fall back to restart_cmd_win even on posix."""
        cmd = _pick_restart_cmd(FAKE_DAEMON_NO_POSIX, platform=PLATFORM_POSIX)
        assert cmd == FAKE_DAEMON_NO_POSIX["restart_cmd_win"]

    def test_neither_cmd_returns_none(self):
        empty = {"name": "empty"}
        cmd = _pick_restart_cmd(empty, platform=PLATFORM_WIN)
        assert cmd is None


# ===========================================================================
# restart_daemon tests (fake shell_runner, no real subprocess)
# ===========================================================================

class TestRestartDaemonPlatform:
    def _make_runner(self, captured: list):
        """Return a fake shell_runner that records calls."""
        class FakeResult:
            returncode = 0
            stderr = ""

        def runner(cmd: str) -> FakeResult:
            captured.append(cmd)
            return FakeResult()

        return runner

    def test_restart_daemon_uses_win_cmd_on_platform_win(self):
        captured: list = []
        ok, rc = restart_daemon(
            FAKE_DAEMON,
            platform=PLATFORM_WIN,
            shell_runner=self._make_runner(captured),
        )
        assert ok is True
        assert rc == 0
        assert captured == [FAKE_DAEMON["restart_cmd_win"]]

    def test_restart_daemon_uses_posix_cmd_on_platform_posix(self):
        captured: list = []
        ok, rc = restart_daemon(
            FAKE_DAEMON,
            platform=PLATFORM_POSIX,
            shell_runner=self._make_runner(captured),
        )
        assert ok is True
        assert rc == 0
        assert captured == [FAKE_DAEMON["restart_cmd"]]

    def test_dry_run_does_not_call_runner(self):
        captured: list = []
        ok, rc = restart_daemon(
            FAKE_DAEMON,
            platform=PLATFORM_WIN,
            dry_run=True,
            shell_runner=self._make_runner(captured),
        )
        assert ok is True
        assert captured == []  # runner not called in dry-run

    def test_no_cmd_returns_false(self):
        empty = {"name": "empty", "heartbeat_optional": True}
        ok, rc = restart_daemon(empty, platform=PLATFORM_WIN)
        assert ok is False
        assert rc is None


# ===========================================================================
# sweep() tests: platform forwarded to restart_daemon
# ===========================================================================

class TestSweepPlatform:
    """sweep() should forward platform to restart_daemon."""

    def _dead_registry(self):
        """Registry with one daemon that is definitely dead (heartbeat missing,
        not optional)."""
        return [{
            "name": "dead_daemon",
            "expected_interval_sec": 60,
            "heartbeat_file": "/nonexistent/path/that/cannot/exist/hb.txt",
            "restart_cmd": "posix_launch_cmd",
            "restart_cmd_win": "win_launch_cmd",
            "process_match": "__no_such_process_9z8y7x__",
            "heartbeat_optional": False,
        }]

    def test_sweep_win_uses_win_cmd(self, tmp_path):
        registry = self._dead_registry()
        limiter = RestartRateLimiter(max_per_hour=10)
        called_with: list = []

        class FakeResult:
            returncode = 0
            stderr = ""

        def fake_runner(cmd):
            called_with.append(cmd)
            return FakeResult()

        # ps_runner that says process is NOT alive (empty output)
        ps_runner = lambda: ""

        restart_log = str(tmp_path / "restarts.md")
        summary = sweep(
            registry, limiter,
            platform=PLATFORM_WIN,
            shell_runner=fake_runner,
            ps_runner=ps_runner,
            restart_log_path=restart_log,
            post_alert_fn=lambda **_kw: True,
        )
        assert len(summary["restarted"]) == 1
        assert called_with == ["win_launch_cmd"]

    def test_sweep_posix_uses_posix_cmd(self, tmp_path):
        registry = self._dead_registry()
        limiter = RestartRateLimiter(max_per_hour=10)
        called_with: list = []

        class FakeResult:
            returncode = 0
            stderr = ""

        def fake_runner(cmd):
            called_with.append(cmd)
            return FakeResult()

        ps_runner = lambda: ""

        restart_log = str(tmp_path / "restarts.md")
        summary = sweep(
            registry, limiter,
            platform=PLATFORM_POSIX,
            shell_runner=fake_runner,
            ps_runner=ps_runner,
            restart_log_path=restart_log,
            post_alert_fn=lambda **_kw: True,
        )
        assert len(summary["restarted"]) == 1
        assert called_with == ["posix_launch_cmd"]


# ===========================================================================
# main() parses --platform
# ===========================================================================

class TestMainPlatformArg:
    """main() should accept --platform without error and propagate the value."""

    def test_main_accepts_platform_win(self, tmp_path, monkeypatch):
        """--platform win + --once + --dry-run on a minimal fake registry."""
        import json
        registry_data = {
            "_comment": "test",
            "daemons": [FAKE_DAEMON],
        }
        reg_path = str(tmp_path / "registry.json")
        with open(reg_path, "w") as fh:
            json.dump(registry_data, fh)

        restart_log = str(tmp_path / "restarts.md")

        from scripts.daemon_watchdog import main
        rc = main([
            "--registry", reg_path,
            "--once",
            "--dry-run",
            "--platform", "win",
            "--restart-log", restart_log,
            "--log-level", "WARNING",
        ])
        assert rc == 0

    def test_main_accepts_platform_posix(self, tmp_path):
        import json
        registry_data = {"_comment": "test", "daemons": [FAKE_DAEMON]}
        reg_path = str(tmp_path / "registry.json")
        with open(reg_path, "w") as fh:
            json.dump(registry_data, fh)
        restart_log = str(tmp_path / "restarts.md")

        from scripts.daemon_watchdog import main
        rc = main([
            "--registry", reg_path,
            "--once",
            "--dry-run",
            "--platform", "posix",
            "--restart-log", restart_log,
            "--log-level", "WARNING",
        ])
        assert rc == 0

    def test_main_accepts_platform_auto(self, tmp_path):
        import json
        registry_data = {"_comment": "test", "daemons": [FAKE_DAEMON]}
        reg_path = str(tmp_path / "registry.json")
        with open(reg_path, "w") as fh:
            json.dump(registry_data, fh)
        restart_log = str(tmp_path / "restarts.md")

        from scripts.daemon_watchdog import main
        rc = main([
            "--registry", reg_path,
            "--once",
            "--dry-run",
            "--platform", "auto",
            "--restart-log", restart_log,
            "--log-level", "WARNING",
        ])
        assert rc == 0

    def test_main_rejects_invalid_platform(self, tmp_path, capsys):
        import json
        registry_data = {"_comment": "test", "daemons": [FAKE_DAEMON]}
        reg_path = str(tmp_path / "registry.json")
        with open(reg_path, "w") as fh:
            json.dump(registry_data, fh)

        from scripts.daemon_watchdog import main
        with pytest.raises(SystemExit) as exc_info:
            main([
                "--registry", reg_path,
                "--once",
                "--platform", "invalid_value",
                "--log-level", "WARNING",
            ])
        assert exc_info.value.code != 0
