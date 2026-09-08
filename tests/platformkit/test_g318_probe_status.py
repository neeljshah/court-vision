"""G318: every new ledger row says whether the source probe ran and what it found.

Before this row `probe_source()` returned a five-key dict on BOTH paths, so a
reader failure and a source that was never probed reached the ledger as the same
all-null row and could not be told apart by reading the row.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import cv2

from scripts.platformkit import track_daemon
from scripts.platformkit.track_daemon_ledger import corrupt_entry
from scripts.platformkit.tracking import source_timebase
from scripts.platformkit.tracking.source_timebase import probe_source, probe_status

TIMEBASE = ("source_fps", "source_height", "source_duration", "source_resolution")
SHAPE = ("source_fps", "source_width", "source_height", "source_resolution",
         "source_duration")


class FakeCapture:
    """An opened reader returning exactly the numbers a probe reads from it."""

    def __init__(self, fps: float, width: int, height: int, frames: float = 300.0):
        self._values = {cv2.CAP_PROP_FPS: fps, cv2.CAP_PROP_FRAME_COUNT: frames,
                        cv2.CAP_PROP_FRAME_WIDTH: width, cv2.CAP_PROP_FRAME_HEIGHT: height}

    def isOpened(self) -> bool:
        return True

    def get(self, prop):
        return self._values[prop]

    def release(self) -> None:
        return None


def _capture(monkeypatch, fps, width, height):
    monkeypatch.setattr(source_timebase.cv2, "VideoCapture",
                        lambda _: FakeCapture(fps, width, height))


def _finish_row(tmp_path, monkeypatch, job: dict) -> dict:
    """Run one daemon completion against a temporary ledger and return its row."""
    monkeypatch.setattr(track_daemon, "TRACKING", tmp_path / "tracking")
    monkeypatch.setattr(track_daemon, "LEDGER", tmp_path / "ledger.jsonl")
    track_daemon._finish(job["game_id"], dict(job, video=tmp_path / "v.mp4",
                                              log=tmp_path / "missing.log",
                                              started=time.time(), retained_videos=[]),
                         timed_out=True)
    lines = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


def test_a_path_that_does_not_exist_reports_failed_missing(tmp_path):
    source = probe_source(tmp_path / "nope.mp4")

    assert source["status"] == "failed:missing"
    assert all(source[name] is None for name in TIMEBASE)
    assert source, "the return must stay truthy: callers branch on `if source:`"
    assert all(name in source for name in SHAPE), "no existing key may be dropped"


def test_a_file_the_reader_will_not_open_reports_the_reader_code(tmp_path):
    empty = tmp_path / "zero.mp4"
    empty.write_bytes(b"")

    source = probe_source(empty)

    assert source["status"] == "failed:ffprobe_rc"
    assert all(source[name] is None for name in TIMEBASE)
    assert source


def test_a_readable_source_reports_ok(monkeypatch, tmp_path):
    _capture(monkeypatch, 30.0, 1920, 1080)

    source = probe_source(tmp_path / "good.mp4")

    assert source["status"] == "ok"
    assert source["source_fps"] == 30.0
    assert source["source_resolution"] == "1920x1080"
    assert all(source[name] is not None for name in TIMEBASE)


def test_an_opened_source_without_dimensions_reports_no_video_stream(monkeypatch, tmp_path):
    _capture(monkeypatch, 30.0, 0, 0)

    source = probe_source(tmp_path / "audio.mp4")

    assert source["status"] == "failed:no_video_stream"
    assert source["source_resolution"] is None


def test_an_unreadable_frame_rate_reports_parse(monkeypatch, tmp_path):
    _capture(monkeypatch, 0.0, 1920, 1080)

    source = probe_source(tmp_path / "norate.mp4")

    assert source["status"] == "failed:parse"
    assert source["source_fps"] is None
    assert source["source_duration"] is None


def test_no_probe_result_at_all_is_not_probed():
    assert probe_status(None) == "not_probed"
    assert probe_status({}) == "not_probed"
    assert probe_status({"source_fps": 30.0}) == "not_probed"
    assert probe_status({"status": "ok"}) == "ok"


def test_a_failed_probe_still_writes_a_row_carrying_its_reason(tmp_path, monkeypatch):
    source = probe_source(tmp_path / "gone.mp4")

    row = _finish_row(tmp_path, monkeypatch,
                      {"game_id": "g318a", "sport": "tennis", "source": source})

    assert row["probe_status"] == "failed:missing"
    assert all(row[name] is None for name in TIMEBASE)
    assert row["status"] == "timeout", "the row is still written, not dropped"


def test_a_row_the_daemon_never_probed_says_not_probed(tmp_path, monkeypatch):
    row = _finish_row(tmp_path, monkeypatch, {"game_id": "g318b", "sport": "tennis"})

    assert row["probe_status"] == "not_probed"
    assert all(row.get(name) is None for name in TIMEBASE)


def test_a_quarantined_staged_file_says_not_probed():
    row = corrupt_entry("g318c", "tennis", 12, True)

    assert row["probe_status"] == "not_probed"
    assert all(row.get(name) is None for name in TIMEBASE)
