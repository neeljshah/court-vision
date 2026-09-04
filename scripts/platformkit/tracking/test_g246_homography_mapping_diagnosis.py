"""Focused checks for the fixed-input G246 correspondence enumerator."""
from __future__ import annotations

import numpy as np
import cv2

from scripts.platformkit.tracking.g246_homography_mapping_diagnosis import (
    LABEL_SETS,
    enumerated_mappings,
    labelled_crop,
    render_overlay,
    write_contact_sheets,
)


def test_enumeration_is_all_four_point_bijections() -> None:
    mappings = enumerated_mappings()
    assert len(mappings) == 24
    assert len(set(mappings)) == 24
    assert all(sorted(mapping) == [0, 1, 2, 3] for mapping in mappings)


def test_render_and_crop_keep_input_shape() -> None:
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    source = LABEL_SETS["clustered"]
    rendered, matrix = render_overlay(image, np.float32(source["labels_px"]), np.float32(source["court_points_ft"]))
    crop = labelled_crop(image, (45, 385), "1")
    assert rendered.shape == image.shape
    assert matrix.shape == (3, 3)
    assert crop.shape[:2] == (160, 125)


def test_contact_sheets_require_complete_existing_render_set(tmp_path) -> None:
    renders = tmp_path / "enumerated_renders"
    renders.mkdir()
    blank = np.zeros((720, 1280, 3), dtype=np.uint8)
    for set_name in LABEL_SETS:
        for index in range(24):
            assert cv2.imwrite(str(renders / f"{set_name}_{index:02d}.jpg"), blank)
    paths = write_contact_sheets(tmp_path)
    assert len(paths) == 2
    assert all(path.exists() for path in paths)
