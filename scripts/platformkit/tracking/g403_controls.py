"""Fixed, native-coordinate G403 construct controls for later blind use."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


SCENES = (
    "ACTIVE_BALL_ALONE",
    "BALL_BESIDE_RIM_HARDWARE",
    "ACTIVE_PLUS_BENCH_BALL",
    "BALL_BESIDE_JERSEY_PATCH",
    "DISTRACTORS_WITHOUT_BALL",
    "IDENTITY_OBSCURED",
)
LAYOUTS = (
    ("1080P_CENTRE", 1920, 1080, 960, 540),
    ("1080P_LEFT", 1920, 1080, 480, 540),
    ("1080P_RIGHT", 1920, 1080, 1440, 540),
    ("720P_CENTRE", 1280, 720, 640, 360),
    ("720P_RIGHT", 1280, 720, 960, 360),
)
VISIBLE_SCENES = frozenset(SCENES[:4])


@dataclass(frozen=True)
class ControlCase:
    """One answer-bound constructed card at native sheet scale."""

    case_id: str
    scene: str
    layout: str
    width: int
    height: int
    sheet_scale: float
    expected_state: str
    expected_center: Optional[tuple[int, int]]
    expected_diameter: Optional[int]
    ball_bbox: Optional[tuple[int, int, int, int]]
    occlusion_mask: tuple[int, int, int, int]
    distractor_boxes: tuple[tuple[int, int, int, int], ...]
    object_note: str


def _state(scene: str) -> str:
    if scene in VISIBLE_SCENES:
        return "VISIBLE"
    if scene == "DISTRACTORS_WITHOUT_BALL":
        return "ABSENT"
    return "UNKNOWN"


def _note(scene: str) -> str:
    return {
        "ACTIVE_BALL_ALONE": "on-court game ball with visible support",
        "BALL_BESIDE_RIM_HARDWARE": "on-court game ball; rim hardware is a distractor",
        "ACTIVE_PLUS_BENCH_BALL": "on-court game ball; bench ball is a distractor",
        "BALL_BESIDE_JERSEY_PATCH": "on-court game ball; jersey patch is a distractor",
        "DISTRACTORS_WITHOUT_BALL": "no on-court game ball is present",
        "IDENTITY_OBSCURED": "multiple plausible objects have no recoverable identity",
    }[scene]


def _distractor_boxes(scene: str, width: int, height: int, cx: int, cy: int,
                      diameter: int) -> tuple[tuple[int, int, int, int], ...]:
    """Return native pixel geometry for every non-designated object in a card."""
    if scene == "BALL_BESIDE_RIM_HARDWARE":
        return ((cx + diameter, cy - 3 * diameter, cx + 2 * diameter, cy + diameter),)
    if scene == "ACTIVE_PLUS_BENCH_BALL":
        bench_cx = min(width - diameter, cx + 3 * diameter + diameter // 2)
        bench_cy = height // 8
        return ((bench_cx - diameter // 2, bench_cy - diameter // 2,
                 bench_cx + diameter // 2, bench_cy + diameter // 2),)
    if scene == "BALL_BESIDE_JERSEY_PATCH":
        return ((cx - 4 * diameter, cy - diameter, cx - 2 * diameter, cy + diameter),)
    if scene == "DISTRACTORS_WITHOUT_BALL":
        return ((cx - 3 * diameter, cy - diameter, cx - diameter, cy + diameter),
                (cx + diameter, cy - diameter, cx + 3 * diameter, cy + diameter))
    if scene == "IDENTITY_OBSCURED":
        return ((cx - diameter, cy - diameter // 2, cx, cy + diameter // 2),
                (cx, cy - diameter // 2, cx + diameter, cy + diameter // 2))
    return ()


def build_control_catalogue() -> tuple[ControlCase, ...]:
    """Construct the exhaustive 6-by-5 G403 catalogue without rendering it."""
    cases: list[ControlCase] = []
    for scene_index, scene in enumerate(SCENES, start=1):
        for layout_index, (layout, width, height, cx, cy) in enumerate(LAYOUTS, start=1):
            state = _state(scene)
            diameter = 32 if height == 1080 else 24
            bbox = (cx - diameter // 2, cy - diameter // 2, cx + diameter // 2, cy + diameter // 2)
            visible = state == "VISIBLE"
            cases.append(ControlCase(
                case_id="G403-%02d-%02d" % (scene_index, layout_index),
                scene=scene,
                layout=layout,
                width=width,
                height=height,
                sheet_scale=1.0,
                expected_state=state,
                expected_center=(cx, cy) if visible else None,
                expected_diameter=diameter if visible else None,
                ball_bbox=bbox if visible else None,
                occlusion_mask=(0, 0, 0, 0) if visible else bbox,
                distractor_boxes=_distractor_boxes(scene, width, height, cx, cy, diameter),
                object_note=_note(scene),
            ))
    return tuple(cases)


def validate_native_bindings(cases: tuple[ControlCase, ...]) -> None:
    """Raise when a catalogue is not exhaustive or its answer binding is non-native."""
    if len(cases) != len(SCENES) * len(LAYOUTS) or len({case.case_id for case in cases}) != len(cases):
        raise ValueError("catalogue-must-be-exhaustive-and-unique")
    if {(case.scene, case.layout) for case in cases} != {(scene, layout[0]) for scene in SCENES for layout in LAYOUTS}:
        raise ValueError("catalogue-scene-layout-gap")
    for case in cases:
        if case.sheet_scale != 1.0:
            raise ValueError("non-native-sheet-scale")
        for left, top, right, bottom in case.distractor_boxes:
            if not (0 <= left < right <= case.width and 0 <= top < bottom <= case.height):
                raise ValueError("distractor-bbox-outside-native-frame")
        if case.expected_state == "VISIBLE":
            if case.expected_center is None or case.expected_diameter is None or case.ball_bbox is None:
                raise ValueError("visible-case-missing-answer-binding")
            left, top, right, bottom = case.ball_bbox
            cx, cy = case.expected_center
            if not (0 <= left < right <= case.width and 0 <= top < bottom <= case.height):
                raise ValueError("ball-bbox-outside-native-frame")
            if (left + right) // 2 != cx or (top + bottom) // 2 != cy:
                raise ValueError("ball-bbox-centre-mismatch")
        elif any(value is not None for value in (case.expected_center, case.expected_diameter, case.ball_bbox)):
            raise ValueError("non-visible-case-has-centre-binding")
