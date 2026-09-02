"""Regression test for the inline bridge source-retention cleanup."""
from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.platformkit import footage_bridge


def test_inline_tracking_moves_new_source_out_of_watched_stage(monkeypatch) -> None:
    """Inline tracking retains a new source in corpus instead of deleting it."""
    commands: list[str] = []

    def fake_ssh(command: str, timeout: int = 7200) -> subprocess.CompletedProcess:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(footage_bridge, "_ssh", fake_ssh)
    monkeypatch.setattr(footage_bridge.subprocess, "run",
                        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0))
    monkeypatch.setattr(footage_bridge, "tracking_rows", lambda game_id: 501)
    monkeypatch.setattr(footage_bridge, "grade", lambda game_id, sport: "passed")

    result = footage_bridge.push_and_track(
        Path("local_clip.mp4"), {"game_id": "g122_new", "sport": "tennis"})

    assert result.startswith("tracked rows=501")
    retention = commands[-1]
    remote = footage_bridge.REMOTE_STAGE + "/g122_new.mp4"
    assert "mv %s %s/" % (remote, footage_bridge.REMOTE_CORPUS) in retention
    assert "if [ -e %s/g122_new.mp4 ]" % footage_bridge.REMOTE_CORPUS in retention
    assert retention != "rm -f %s" % remote
