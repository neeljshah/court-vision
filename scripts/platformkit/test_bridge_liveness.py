"""Focused tests for G94 bridge-supervisor liveness."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from scripts.platformkit import bridge_liveness, night_report


def _write_status(path, written_at: datetime) -> None:
    path.write_text(json.dumps({
        "written_at": written_at.isoformat(),
        "tracked_games": 0,
        "lanes": {"baseball": {"alive": True, "untracked": 1}},
    }), encoding="utf-8")


def test_assess_distinguishes_up_down_and_stale_unknown(tmp_path):
    now = datetime.now(timezone.utc)
    status = tmp_path / "status.json"
    pid_file = tmp_path / "supervisor.pid"
    pid_file.write_text(str(os.getpid()), encoding="ascii")

    _write_status(status, now)
    assert bridge_liveness.assess(status, pid_file, 60, now).state == "UP"

    payload = json.loads(status.read_text(encoding="utf-8"))
    payload["written_at"] = now.strftime("%Y-%m-%dT%H:%M:%S.") + "%06d7Z" % now.microsecond
    status.write_text(json.dumps(payload), encoding="utf-8")
    assert bridge_liveness.assess(status, pid_file, 60, now).state == "UP"

    pid_file.write_text("99999999", encoding="ascii")
    assert bridge_liveness.assess(status, pid_file, 60, now).state == "DOWN"

    pid_file.write_text(str(os.getpid()), encoding="ascii")
    _write_status(status, now - timedelta(seconds=61))
    stale = bridge_liveness.assess(status, pid_file, 60, now)
    assert stale.state == "UNKNOWN"
    assert "older than 60s" in stale.reason


def test_healthy_restart_is_a_noop_and_report_refuses_stale_status(tmp_path):
    now = datetime.now(timezone.utc)
    status = tmp_path / "status.json"
    pid_file = tmp_path / "supervisor.pid"
    pid_file.write_text(str(os.getpid()), encoding="ascii")
    _write_status(status, now)
    healthy = bridge_liveness.assess(status, pid_file, 60, now)
    called = []
    action, pid = bridge_liveness.restart_if_down(healthy, 3, lambda *args: called.append(args))
    assert (action, pid, called) == ("no-op", None, [])

    _write_status(status, now - timedelta(seconds=bridge_liveness.STATUS_MAX_AGE_SECONDS + 1))
    report = night_report.build_report(tmp_path / "tracking.jsonl", tmp_path / "bridge.jsonl", status)
    assert "unknown: status older than" in report
    assert "alive_lanes=baseball" not in report


def test_pid_is_alive_survives_a_dead_pid_on_windows():
    """A dead pid must answer False, not crash the checker.

    Windows raises SystemError rather than OSError from os.kill(pid, 0) when the
    pid is gone. Catching only OSError made the liveness check raise
    `SystemError: <class 'OSError'> returned a result with an exception set` --
    so the watchdog died precisely when the supervisor was down, which is the
    one moment it exists for. Reproduced against a real dead pid on 2026-09-02.
    """
    import os

    from scripts.platformkit.bridge_liveness import pid_is_alive

    assert pid_is_alive(999999) is False
    assert pid_is_alive(None) is False
    assert pid_is_alive(0) is False
    assert pid_is_alive(-1) is False
    assert pid_is_alive(os.getpid()) is True
