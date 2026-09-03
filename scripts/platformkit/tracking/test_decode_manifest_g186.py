"""G186 regression coverage for metadata-first decoded-frame counts."""
from __future__ import annotations

import json
import logging
from types import SimpleNamespace

from scripts.platformkit.tracking import decode_manifest


def test_metadata_count_avoids_full_decode_and_logs_the_fast_path(tmp_path, monkeypatch, caplog):
    """A valid container count must avoid the slow ``-count_frames`` fallback."""
    video = tmp_path / "broadcast.mp4"
    video.write_bytes(b"fixture")
    calls = []

    def fake_run(command, check, capture_output, text):
        calls.append(command)
        assert check and capture_output and text
        assert "-count_frames" not in command
        return SimpleNamespace(stdout=json.dumps({
            "streams": [{"nb_frames": "250200", "r_frame_rate": "30/1",
                         "duration": "8340.000000"}],
            "format": {"duration": "8340.000000"},
        }))

    monkeypatch.setattr(decode_manifest.subprocess, "run", fake_run)

    with caplog.at_level(logging.INFO, logger=decode_manifest.__name__):
        assert decode_manifest.decoded_frame_count(video) == 250200

    assert len(calls) == 1
    assert "path=metadata" in caplog.text


def test_inconsistent_metadata_keeps_the_full_decode_fallback(tmp_path, monkeypatch, caplog):
    """Duration/rate disagreement is unsafe and must retain the exact decoder count."""
    video = tmp_path / "vfr-or-stale.mp4"
    video.write_bytes(b"fixture")
    calls = []

    def fake_run(command, check, capture_output, text):
        calls.append(command)
        if "-count_frames" in command:
            return SimpleNamespace(stdout="17\n")
        return SimpleNamespace(stdout=json.dumps({
            "streams": [{"nb_frames": "99", "r_frame_rate": "30/1",
                         "duration": "1.000000"}],
            "format": {"duration": "1.000000"},
        }))

    monkeypatch.setattr(decode_manifest.subprocess, "run", fake_run)

    with caplog.at_level(logging.INFO, logger=decode_manifest.__name__):
        assert decode_manifest.decoded_frame_count(video) == 17

    assert len(calls) == 2
    assert "-count_frames" in calls[1]
    assert "path=decode_fallback" in caplog.text
