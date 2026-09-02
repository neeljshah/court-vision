"""Focused regression for G123's single preregistered preprocessing method."""
import numpy as np

from scripts.platformkit.g123_low_contrast_lines import CLIP_LIMIT, TILE_GRID, enhance_contrast


def test_g123_clahe_is_a_whole_frame_bgr_preserving_transform() -> None:
    image = np.zeros((16, 16, 3), dtype=np.uint8)
    image[:, :8] = (20, 40, 60)
    image[:, 8:] = (40, 80, 120)
    result = enhance_contrast(image)
    assert CLIP_LIMIT == 2.0
    assert TILE_GRID == (8, 8)
    assert result.shape == image.shape and result.dtype == image.dtype
    assert np.array_equal(image[:, :8], np.full((16, 8, 3), (20, 40, 60), dtype=np.uint8))
