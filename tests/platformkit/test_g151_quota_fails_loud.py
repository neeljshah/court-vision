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
