import numpy as np
import pytest

from scripts.platformkit.detection.shim import _decode_yolox, _nms, get_detector


def test_yolox_grid_decode_known_cell() -> None:
    prediction = np.zeros((8400, 6), dtype=np.float32)
    prediction[1, :6] = [0.5, 0.25, 0.0, 0.0, 0.9, 0.8]
    boxes, scores, classes = _decode_yolox(prediction)
    np.testing.assert_allclose(boxes[1], [8.0, -2.0, 16.0, 6.0])
    assert scores[1] == pytest.approx(0.72)
    assert classes[1] == 0


def test_nms_removes_overlapping_boxes() -> None:
    boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11]], dtype=np.float32)
    scores = np.array([0.9, 0.8], dtype=np.float32)
    np.testing.assert_array_equal(_nms(boxes, scores), [0])


def test_factory_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="unknown detector backend"):
        get_detector("not-a-detector")
