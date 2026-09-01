"""Focused tests for the bounded independent football OCR sweep."""
from __future__ import annotations

import cv2
import numpy as np

from scripts.platformkit.football_ocr_sweep import (Candidate, MAX_CANDIDATES,
                                                     candidates, preprocess, read)


class Reader:
    def readtext(self, image: np.ndarray, **kwargs: object) -> list[object]:
        return [(None, "4", 0.91)]


def test_candidates_are_deduplicated_and_hard_bounded() -> None:
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    frame[:, :] = (45, 145, 45)
    for x in range(40, 620, 70):
        cv2.rectangle(frame, (x, 120), (x + 18, 165), (255, 255, 255), -1)

    found = candidates(frame)

    assert len(found) == MAX_CANDIDATES
    assert all(item.crop.shape[0] <= int(frame.shape[0] * .30) for item in found)
    assert all(item.crop.shape[1] <= int(frame.shape[1] * .30) for item in found)


def test_preprocessing_variants_preserve_or_enlarge_the_crop() -> None:
    crop = np.full((10, 12, 3), 210, dtype=np.uint8)
    assert preprocess(crop, "raw").shape == crop.shape
    assert preprocess(crop, "gray_otsu").ndim == 2
    assert preprocess(crop, "upscale_3x").shape[:2] == (30, 36)
    assert preprocess(crop, "gray_otsu_upscale_3x").shape == (30, 36)


def test_single_digit_field_read_maps_to_tens_value() -> None:
    candidate = Candidate((2, 3, 10, 12), np.zeros((12, 10, 3), dtype=np.uint8))
    result = read(candidate, "raw", Reader())
    assert result.value == 40
    assert result.confidence == 0.91
