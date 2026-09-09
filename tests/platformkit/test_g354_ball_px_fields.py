"""G354 synthetic producer checks; run after applying ball_px.patch."""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
PIPELINE = Path(os.environ.get("G354_PIPELINE_SRC", REPO / "src" / "pipeline" / "unified_pipeline.py"))
BALL_TRACKER = Path(os.environ.get("G354_BALL_TRACKER_SRC", REPO / "src" / "tracking" / "ball_detect_track.py"))
OLD_FIELDS = ("frame", "timestamp", "ball_x2d", "ball_y2d", "detected", "live", "ball_inferred")


def _row_dict() -> ast.Dict:
    tree = ast.parse(PIPELINE.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            values = {key.value: value for key, value in zip(node.keys, node.values)
                      if isinstance(key, ast.Constant)}
            live = values.get("live")
            if ("ball_x2d_px" in values and "ball_inferred" in values
                    and isinstance(live, ast.Constant) and live.value == 1):
                found.append(node)
    assert len(found) == 1, "G354 live ball-row fields are absent or ambiguous"
    return found[0]


def _value(field: str, px: tuple[int, int] | None) -> object:
    row = _row_dict()
    values = {key.value: value for key, value in zip(row.keys, row.values)
              if isinstance(key, ast.Constant)}
    expression = ast.Expression(values[field])
    ast.fix_missing_locations(expression)
    return eval(compile(expression, str(PIPELINE), "eval"), {}, {
        "frame_idx": 7, "timestamp_sec": 0.233, "ball_pos": (400, 220),
        "ball_px_pos": px, "self": SimpleNamespace(ball_det=SimpleNamespace(ball_inferred=False)),
    })  # noqa: S307 - evaluates only AST from the shipped source under fixed synthetic inputs


def test_g354_px_fields_equal_the_synthetic_detector_center() -> None:
    assert (_value("ball_x2d_px", (71, 38)), _value("ball_y2d_px", (71, 38))) == (71, 38)
    assert '"ball_x2d_px", "ball_y2d_px"]' in PIPELINE.read_text(encoding="utf-8")


def test_g354_missing_detection_clears_not_stale() -> None:
    sequence = [(71, 38), None]
    rows = [(_value("ball_x2d_px", point), _value("ball_y2d_px", point)) for point in sequence]
    assert rows == [(71, 38), ("", "")]
    source = PIPELINE.read_text(encoding="utf-8")
    assert "self._last_ball_px:       Optional[tuple]      = None" in source
    assert "self._last_ball_px = None" in source
    assert BALL_TRACKER.read_text(encoding="utf-8").count("last_2d_pos_px") >= 3


def test_g354_zero_pixel_component_is_not_blank() -> None:
    assert (_value("ball_x2d_px", (0, 38)), _value("ball_y2d_px", (0, 38))) == (0, 38)
    source = PIPELINE.read_text(encoding="utf-8")
    assert "ball_px_pos is not None" in source


def test_g354_existing_fields_are_byte_identical_on_the_synthetic_sequence() -> None:
    row = _row_dict()
    values = {key.value: value for key, value in zip(row.keys, row.values)
              if isinstance(key, ast.Constant)}
    candidate = {field: eval(compile(ast.fix_missing_locations(ast.Expression(values[field])),
                                     str(PIPELINE), "eval"), {}, {
        "frame_idx": 7, "timestamp_sec": 0.233, "ball_pos": (400, 220),
        "ball_px_pos": (71, 38), "self": SimpleNamespace(ball_det=SimpleNamespace(ball_inferred=False)),
    }) for field in OLD_FIELDS}  # noqa: S307 - evaluates only shipped old-field AST
    golden = {"frame": 7, "timestamp": 0.233, "ball_x2d": 400, "ball_y2d": 220,
              "detected": 1, "live": 1, "ball_inferred": 0}
    assert json.dumps(candidate, separators=(",", ":"), sort_keys=False).encode() == (
        json.dumps(golden, separators=(",", ":"), sort_keys=False).encode())
