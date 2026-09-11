"""Read and rasterize the blinded G382 painted-marking and exclusion polygons."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

LABELS = ("PAINTED", "STANDS", "LED", "SCORE_BUG", "OTHER", "UNREADABLE")
UNKNOWN = "UNKNOWN"
LABEL_CODES = {name: index + 1 for index, name in enumerate(LABELS)}


@dataclass(frozen=True)
class Marking:
    """One rater-traced physical marking in native-pixel coordinates."""
    physical_marking_id: str
    polygon: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class MaskDocument:
    """Validated frame annotation; unmasked pixels are intentionally UNKNOWN."""
    frame_key: str
    width: int
    height: int
    markings: tuple[Marking, ...]
    regions: tuple[tuple[str, tuple[tuple[float, float], ...]], ...]


def _polygon(value: object) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, list) or len(value) < 3:
        raise ValueError("polygon needs at least three points")
    points = tuple((float(item[0]), float(item[1])) for item in value)
    if any(len(item) != 2 for item in value):
        raise ValueError("polygon point is not x,y")
    return points


def read(path: Path) -> MaskDocument:
    """Read the documented G382 JSON schema and reject absent identity or labels."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    image = raw.get("image", {})
    markings = tuple(Marking(str(item["physical_marking_id"]), _polygon(item["polygon"]))
                     for item in raw.get("painted_markings", []))
    if not raw.get("frame_key") or len({item.physical_marking_id for item in markings}) != len(markings):
        raise ValueError("annotation needs frame_key and unique physical marking ids")
    regions = []
    for item in raw.get("mask_regions", []):
        label = str(item["label"]).upper()
        if label not in LABELS or label == "PAINTED":
            raise ValueError("mask label must be a non-painted G382 exclusion label")
        for polygon in item.get("polygons", []):
            regions.append((label, _polygon(polygon)))
    width, height = int(image.get("width", 0)), int(image.get("height", 0))
    if width < 1 or height < 1:
        raise ValueError("annotation image dimensions are required")
    return MaskDocument(str(raw["frame_key"]), width, height, markings, tuple(regions))


def _fill(target: np.ndarray, polygon: tuple[tuple[float, float], ...], value: int) -> None:
    cv2.fillPoly(target, [np.rint(np.asarray(polygon, dtype=np.float32)).astype(np.int32)], value)


def rasterize(document: MaskDocument) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Return exclusive base labels and one native mask per physical marking."""
    labels = np.zeros((document.height, document.width), dtype=np.uint8)
    physical: dict[str, np.ndarray] = {}
    for marking in document.markings:
        mask = np.zeros_like(labels); _fill(mask, marking.polygon, 1)
        if np.any((labels != 0) & (mask != 0)):
            raise ValueError("painted markings overlap another labeled region")
        labels[mask != 0] = LABEL_CODES["PAINTED"]
        physical[marking.physical_marking_id] = mask
    for label, polygon in document.regions:
        mask = np.zeros_like(labels); _fill(mask, polygon, 1)
        if np.any((labels != 0) & (mask != 0)):
            raise ValueError("mask regions overlap")
        labels[mask != 0] = LABEL_CODES[label]
    return labels, physical


def label_name(code: int) -> str:
    """Translate a raster value while keeping the no-mask remainder explicit."""
    return UNKNOWN if code == 0 else LABELS[code - 1]
