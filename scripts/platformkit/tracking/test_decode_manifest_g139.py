"""G139 coverage for ffprobe program/global duplicate count output."""
from __future__ import annotations

from types import SimpleNamespace

from scripts.platformkit.tracking import decode_manifest


def test_identical_program_and_global_frame_counts_are_one_denominator(tmp_path, monkeypatch):
    video = tmp_path / "affected.mpegts"
    video.write_bytes(b"fixture")
    seen = {}

    def fake_run(command, check, capture_output, text):
        seen["command"] = command
        assert check and capture_output and text
        return SimpleNamespace(stdout="39000\n39000\n")

    monkeypatch.setattr(decode_manifest.subprocess, "run", fake_run)

    assert decode_manifest.decoded_frame_count(video) == 39000
    assert seen["command"][4:6] == ["-select_streams", "v:0"]
