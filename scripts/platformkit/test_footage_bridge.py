"""Focused tests for the local-download / pod-track footage bridge."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.platformkit import footage_bridge


def test_thin_tracking_output_is_not_reported_as_tracked(monkeypatch, tmp_path):
    """A 103-row CSV is non-empty and useless; only the row count may pass it."""
    commands: list[str] = []

    def fake_ssh(command, timeout=7200):
        commands.append(command)
        if command.startswith("wc -l"):
            return subprocess.CompletedProcess(command, 0, stdout="103\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="done", stderr="")

    monkeypatch.setattr(footage_bridge, "_ssh", fake_ssh)
    monkeypatch.setattr(footage_bridge.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))

    status = footage_bridge.push_and_track(
        tmp_path / "kbo_01.mp4", {"game_id": "kbo_01", "sport": "kbo"})

    assert status.startswith("thin rows=103")
    # The video must be staged privately, never in data/footage where the pod
    # track_staged loop would delete it mid-transfer.
    assert any("data/footage_bridge/kbo_01.mp4" in c for c in commands)
    assert not any("/data/footage/kbo_01" in c for c in commands)
    # And the remote copy is always reclaimed.
    assert any(c.startswith("rm -f") for c in commands)


def test_remote_copy_deleted_even_when_tracking_raises(monkeypatch, tmp_path):
    removed: list[str] = []

    def fake_ssh(command, timeout=7200):
        if command.startswith("rm -f"):
            removed.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command.startswith("wc -l"):
            return subprocess.CompletedProcess(command, 0, stdout="0\n", stderr="")
        if "adapter_run" in command:
            raise RuntimeError("tracking exploded")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(footage_bridge, "_ssh", fake_ssh)
    monkeypatch.setattr(footage_bridge.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))

    try:
        footage_bridge.push_and_track(tmp_path / "npb_02.mp4",
                                      {"game_id": "npb_02", "sport": "npb"})
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected the tracking failure to propagate")
    assert removed, "pod disk must be reclaimed even when tracking raises"


def test_download_resolves_mkv_fallback_and_skips_fragments(monkeypatch, tmp_path):
    """yt-dlp falls back to .mkv; fragment files are not real artifacts."""
    monkeypatch.setattr(footage_bridge, "LOCAL_STAGE", tmp_path)
    monkeypatch.setattr(footage_bridge, "COOKIES", tmp_path / "absent.txt")

    def fake_run(command, **kwargs):
        (tmp_path / "g1.mp4-Frag511").write_bytes(b"x" * 999)
        (tmp_path / "g1.mkv").write_bytes(b"video")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(footage_bridge.subprocess, "run", fake_run)

    produced = footage_bridge.download_local(
        {"game_id": "g1", "url": "https://youtube.example/watch?v=1"})

    assert produced.name == "g1.mkv"


def test_queue_skips_already_tracked_and_records_ledger(monkeypatch, tmp_path):
    queue = tmp_path / "footage_queue_kbo.json"
    queue.write_text(json.dumps([
        {"sport": "kbo", "game_id": "done_01", "url": "u1"},
        {"sport": "kbo", "game_id": "todo_01", "url": "u2"},
    ]), encoding="utf-8")
    monkeypatch.setattr(footage_bridge, "LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(footage_bridge, "LOCAL_STAGE", tmp_path / "stage")
    monkeypatch.setattr(footage_bridge, "tracking_rows",
                        lambda game_id: 9000 if game_id == "done_01" else 0)
    monkeypatch.setattr(footage_bridge, "download_local",
                        lambda item: Path(tmp_path / "stage" / "todo_01.mp4"))
    monkeypatch.setattr(footage_bridge, "push_and_track",
                        lambda local, item: "tracked rows=9000")

    tracked = footage_bridge.run_queue(queue, limit=5)

    assert tracked == 1
    entries = [json.loads(line) for line
               in (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [entry["game_id"] for entry in entries] == ["todo_01"]
