import cv2
import numpy as np

from scripts.platformkit.tracking.soccer_role_filter import _pitch_mask, filter_person_boxes


def _frame() -> np.ndarray:
    return np.full((300, 500, 3), (45, 145, 45), dtype=np.uint8)


def _person(frame: np.ndarray, box: tuple[int, int, int, int], color: tuple[int, int, int]) -> None:
    x1, y1, x2, y2 = box
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, -1)


def test_pitch_cue_rejects_off_pitch_box() -> None:
    frame = _frame()
    frame[:, :80] = (80, 80, 80)
    boxes = [(20, 100, 55, 220), (150, 100, 185, 220)]
    for box in boxes:
        _person(frame, box, (20, 20, 220))
    result = filter_person_boxes(frame, boxes)
    assert [item.cue for item in result["boxes"]] == ["foot_off_pitch_or_touchline", "all_cues_pass"]


def test_pitch_region_is_largest_green_component() -> None:
    frame = _frame()
    frame[:, :80] = (80, 80, 80)
    frame[20:40, 20:40] = (45, 145, 45)
    mask = _pitch_mask(frame)
    assert mask[30, 30] == 0
    assert mask[150, 250] == 255


def test_jersey_cue_rejects_black_kit_on_pitch() -> None:
    frame = _frame()
    boxes = [(80, 80, 110, 200), (140, 85, 170, 205), (200, 90, 230, 210),
             (270, 85, 300, 205), (330, 90, 360, 210), (400, 80, 430, 200)]
    for box, color in zip(boxes, [(20, 20, 220)] * 3 + [(220, 220, 220)] * 2 + [(10, 10, 10)]):
        _person(frame, box, color)
    result = filter_person_boxes(frame, boxes)
    assert result["boxes"][-1].cue == "jersey_outlier"


def test_size_alone_does_not_reject_on_pitch_box() -> None:
    frame = _frame()
    boxes = [(70, 80, 105, 210), (140, 85, 175, 215), (210, 90, 245, 220),
             (290, 90, 325, 220), (370, 175, 385, 220)]
    for box in boxes:
        _person(frame, box, (20, 20, 220))
    result = filter_person_boxes(frame, boxes)
    assert result["boxes"][-1].cue == "all_cues_pass"
