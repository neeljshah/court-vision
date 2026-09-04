"""Focused contracts for G224's fixed, resolution-aware line evidence."""
import numpy as np

from scripts.platformkit.tracking.g224_tophat_line_evidence_transfer import kernel_size, tophat_mask


def test_tophat_kernel_scales_once_by_native_height_and_mask_is_single_channel():
    assert [kernel_size(height) for height in (360, 720, 1080)] == [7, 11, 17]
    mask = tophat_mask(np.zeros((720, 1280, 3), dtype=np.uint8))
    assert mask.shape == (720, 1280)
    assert mask.dtype == np.uint8
