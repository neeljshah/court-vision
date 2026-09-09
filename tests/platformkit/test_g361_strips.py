"""G361 eye-check strip: written, under the size cap, boxes taken from one frame only."""
from __future__ import annotations

import cv2
import numpy as np

from scripts.platformkit.tracking import g361_strips

GAME = "AAAAAAAAAAA_s90"
TABLE = ("frame,bbox_x1,bbox_y1,bbox_x2,bbox_y2\n"
         "5,10,10,60,80\n5,70,20,120,90\n6,0,0,4,4\n")
ALIGN = ("game_id,landmark,archived_frame,archived_timestamp,refetched_pts,error_frames\n"
         "%s,0,5,0.167,0.167,0.0000\n" % GAME)


def _fixture(root):
    video = root / "clip.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 30.0, (320, 180))
    for index in range(20):
        writer.write(np.full((180, 320, 3), (index * 11) % 255, dtype=np.uint8))
    writer.release()
    table = root / "tracking" / GAME
    table.mkdir(parents=True)
    (table / "tracking_data.csv").write_text(TABLE, encoding="utf-8")
    (root / "alignment.csv").write_text(ALIGN, encoding="utf-8")
    return video


def test_strip_written_under_the_cap(tmp_path):
    video = _fixture(tmp_path)
    assert video.exists() and video.stat().st_size > 0
    g361_strips.main(["--game-id", GAME, "--refetched", str(video),
                      "--tracking", str(tmp_path / "tracking"),
                      "--alignment", str(tmp_path / "alignment.csv"),
                      "--out", str(tmp_path / "strips")])
    strip = tmp_path / "strips" / (GAME + ".jpg")
    assert strip.exists()
    assert 0 < strip.stat().st_size <= g361_strips.CAP


def test_boxes_come_from_one_frame(tmp_path):
    _fixture(tmp_path)
    boxes = g361_strips.archived_boxes(
        tmp_path / "tracking" / GAME / "tracking_data.csv", 5)
    assert boxes == [(10, 10, 60, 80), (70, 20, 120, 90)]
