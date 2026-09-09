"""Load native-rule court templates and rasterise their semantic strokes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

_ROOT = Path(__file__).with_name("templates")
_TO_FT = {"ft": 1.0, "m": 3.280839895013123}


def load_template(league: str) -> dict[str, Any]:
    """Load a named template, retaining native values and adding feet values."""
    raw = json.loads((_ROOT / f"{league.lower()}.json").read_text(encoding="utf-8"))
    scale = _TO_FT[raw["native_unit"]]
    raw["feet"] = {key: value * scale for key, value in raw.items() if isinstance(value, (int, float)) and not key.endswith("_ft")}
    raw["feet"].update({key: value for key, value in raw.items() if key.endswith("_ft") and isinstance(value, (int, float))})
    raw["feet"]["center_line_x"] = raw["feet"]["length"] / 2.0
    return raw


def _arc(center: tuple[float, float], radius: float, start: float, stop: float) -> np.ndarray:
    angles = np.linspace(start, stop, 49)
    return np.column_stack((center[0] + radius * np.cos(angles), center[1] + radius * np.sin(angles)))


def _stroke(semantic_id: str, family: str, points: list[tuple[float, float]] | np.ndarray) -> dict[str, Any]:
    return {"semantic_id": semantic_id, "family": family, "points": np.asarray(points, dtype=np.float32)}


def segments(template: dict[str, Any]) -> list[dict[str, Any]]:
    """Return court-feet polylines tagged with semantic ID and orientation family."""
    f = template["feet"]; length, width = f["length"], f["width"]
    half_lane = f["lane_width"] / 2.0; mid = width / 2.0; depth = f["lane_depth"]
    out = [_stroke("SIDELINE", "X", [(0, 0), (length, 0)]), _stroke("SIDELINE", "X", [(0, width), (length, width)]),
           _stroke("BASELINE", "Y", [(0, 0), (0, width)]), _stroke("BASELINE", "Y", [(length, 0), (length, width)]),
           _stroke("CENTRE", "Y", [(length / 2, 0), (length / 2, width)])]
    for x, side in ((0.0, 1.0), (length, -1.0)):
        far = x + side * depth
        out += [_stroke("LANE_L", "X", [(x, mid-half_lane), (far, mid-half_lane)]),
                _stroke("LANE_R", "X", [(x, mid+half_lane), (far, mid+half_lane)]),
                _stroke("FT_CIRCLE", "ARC", _arc((far, mid), f["free_throw_circle_radius"], 0, 2*np.pi)),
                _stroke("RA", "ARC", _arc((x + side*f["basket_center_ft"], mid), f["restricted_radius"], -np.pi/2 if side > 0 else np.pi/2, np.pi/2 if side > 0 else 3*np.pi/2))]
        basket = (x + side*f["basket_center_ft"], mid)
        offset = f["corner_sideline_offset"]
        for y in (offset, width-offset):
            end_x = basket[0] + side * max(0.0, (f["three_arc_radius"]**2 - (y-mid)**2)**0.5)
            out.append(_stroke("CORNER_3", "X", [(x, y), (end_x, y)]))
        angle = float(np.arcsin((mid - offset) / f["three_arc_radius"]))
        out.append(_stroke("ARC_3", "ARC", _arc(basket, f["three_arc_radius"], -angle if side > 0 else np.pi-angle, angle if side > 0 else np.pi+angle)))
    out.append(_stroke("CIRCLE", "ARC", _arc((length/2, mid), f["center_circle_radius"], 0, 2*np.pi)))
    return out


def render(template: dict[str, Any], H: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Rasterise template strokes through court-to-image homography H."""
    width, height = size; image = np.zeros((height, width), dtype=np.uint8)
    for segment in segments(template):
        pts = cv2.perspectiveTransform(segment["points"].reshape(-1, 1, 2), H).reshape(-1, 2)
        cv2.polylines(image, [np.rint(pts).astype(np.int32)], False, 255, 1, cv2.LINE_AA)
    return image
