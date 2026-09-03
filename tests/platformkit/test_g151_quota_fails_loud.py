"""G151 regression coverage for quota-write failures at both live call sites."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.platformkit import footage_bridge, track_daemon


def test_ledger_probe_failure_prevents_a_silent_append(monkeypatch, tmp_path) -> None:
    """A failed ledger probe raises before an entry can be treated as recorded."""
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(track_daemon, "LEDGER", ledger)
    monkeypatch.setattr(track_daemon, "_write_probe",
                        lambda *_args: (_ for _ in ()).throw(
                            RuntimeError("ledger write probe failed: quota exceeded")))

    with pytest.raises(RuntimeError, match="quota exceeded"):
        track_daemon._record({"game_id": "g151", "sport": "tennis"})

    assert not ledger.exists()


def test_staged_upload_reports_probe_failure_and_stranded_part(monkeypatch, tmp_path) -> None:
    """A pod write failure is loud and says whether its .part still exists."""
    calls: list[str] = []

    def fake_ssh(command: str, timeout: int = 7200) -> subprocess.CompletedProcess:
        calls.append(command)
        if command.startswith("test -e "):
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(footage_bridge, "_ssh", fake_ssh)
    monkeypatch.setattr(footage_bridge, "_pod_write_probe",
                        lambda: (_ for _ in ()).throw(
                            RuntimeError("Disk quota exceeded")))
    monkeypatch.setattr(footage_bridge.subprocess, "run",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            AssertionError("scp must not run after a failed write probe")))

    with pytest.raises(RuntimeError, match="stranded .part remains"):
        footage_bridge.push_staged(
            tmp_path / "clip.mp4", {"game_id": "g151", "sport": "tennis"})

    assert any(command.startswith("test -e ") for command in calls)


def test_ledger_failure_does_not_kill_the_daemon_or_strand_the_source(
        monkeypatch, tmp_path, capsys) -> None:
    """A persistent append failure must be loud, not fatal.

    The regression this guards is the one the adversarial review caught the same
    day the guard landed: `_record` raises inside `_finish`, which runs inside
    `tick`, which the main loop calls with no exception handler. `retain` sits
    BELOW the append, so a raise both killed the daemon and left the source in
    STAGE -- and the keeper's 60-second restart then re-claimed and re-tracked
    the same game, adding disk pressure to the full volume on every cycle.
    """
    monkeypatch.setattr(track_daemon, "_write_probe",
                        lambda *_args: (_ for _ in ()).throw(
                            RuntimeError("ledger write probe failed: quota exceeded")))

    assert track_daemon._record_loudly({"game_id": "g151b", "sport": "tennis"}) is False
    printed = capsys.readouterr().out
    assert "LEDGER APPEND FAILED" in printed
    assert "g151b" in printed
    assert "quota exceeded" in printed
