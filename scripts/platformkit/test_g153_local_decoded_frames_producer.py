"""G153: the real completion path persists its decoder-backed denominator."""

from __future__ import annotations

import json
import time

import cv2
import numpy as np

from scripts.platformkit import track_daemon


def test_real_completion_path_writes_decoded_frames_to_local_ledger(tmp_path, monkeypatch):
    video = tmp_path / "tennis__g153.mp4"
    writer = cv2.VideoWriter(
        str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (32, 32), True
    )
    assert writer.isOpened()
    for value in (0, 64, 128, 255):
        writer.write(np.full((32, 32, 3), value, dtype=np.uint8))
    writer.release()

    tracking = tmp_path / "tracking"
    output = tracking / "g153_local"
    output.mkdir(parents=True)
    (output / "tracking_data.csv").write_text(
        "frame,track_id,cls,x,y,coordinate_space\n0,1,player,1.0,2.0,court_feet\n",
        encoding="utf-8",
    )
    ledger = tmp_path / "track_daemon_ledger.jsonl"
    monkeypatch.setattr(track_daemon, "TRACKING", tracking)
    monkeypatch.setattr(track_daemon, "LEDGER", ledger)
    monkeypatch.setattr(track_daemon, "CORPUS", tmp_path / "corpus")

    track_daemon._finish(
        video.name,
        {
            "game_id": "g153_local",
            "sport": "tennis",
            "video": video,
            "log": tmp_path / "complete.log",
            "started": time.time() - 1,
            "source": None,
        },
    )

    row = json.loads(ledger.read_text(encoding="utf-8"))
    assert row["status"] == "tracked"
    assert row["adjudicated"] is True
    assert row["decoded_frames"] == 4
