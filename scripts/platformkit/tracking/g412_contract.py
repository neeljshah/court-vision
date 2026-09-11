"""Pure coordinate and receipt controls for the G412 proposed writer contract."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any, Mapping

CROP_ORIGIN_Y_PX = 60
PADDING_PX = 15
BOX_FRAME = "topcut60_pad15"
LEGACY_FIELDS = ("player_id", "team", "bbox", "x2d", "y2d", "confidence")


@dataclass(frozen=True)
class Box:
    """An xyxy box in cropped-frame coordinates."""

    x1: float
    y1: float
    x2: float
    y2: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)


def _clip(box: Box, width: int, height: int) -> Box:
    return Box(
        max(0, min(width, box.x1)), max(0, min(height, box.y1)),
        max(0, min(width, box.x2)), max(0, min(height, box.y2)),
    )


def native_boxes(stored_xyxy: Box, crop_width: int, crop_height: int) -> tuple[Box, Box]:
    """Return native padded and detector-form boxes after cropped-space clipping."""
    if crop_width <= 0 or crop_height <= 0:
        raise ValueError("invalid-cropped-dimensions")
    padded = _clip(stored_xyxy, crop_width, crop_height)
    detector = _clip(
        Box(stored_xyxy.x1 + PADDING_PX, stored_xyxy.y1 + PADDING_PX,
            stored_xyxy.x2 - PADDING_PX, stored_xyxy.y2 - PADDING_PX),
        crop_width, crop_height,
    )
    return (
        Box(padded.x1, padded.y1 + CROP_ORIGIN_Y_PX, padded.x2,
            padded.y2 + CROP_ORIGIN_Y_PX),
        Box(detector.x1, detector.y1 + CROP_ORIGIN_Y_PX, detector.x2,
            detector.y2 + CROP_ORIGIN_Y_PX),
    )


def additive_receipt(route: str, stored_xyxy: Box | None, crop_width: int,
                     crop_height: int, source_frame: int | None) -> dict[str, Any]:
    """Create only additive receipt fields, retaining UNKNOWN routes and empty boxes."""
    if stored_xyxy is None:
        return {"box_frame": "", "box_crop_origin_y_px": "", "box_padding_px": "",
                "box_receipt_status": "EMPTY", "box_receipt_reason": "absent-box"}
    if source_frame is None or source_frame < 0:
        raise ValueError("source-frame-required")
    if route != "fresh_box":
        return {"box_frame": "UNKNOWN", "box_crop_origin_y_px": "UNKNOWN",
                "box_padding_px": "UNKNOWN", "box_receipt_status": "UNKNOWN",
                "box_receipt_reason": "unbound-" + route}
    padded, detector = native_boxes(stored_xyxy, crop_width, crop_height)
    return {
        "box_frame": BOX_FRAME,
        "box_crop_origin_y_px": CROP_ORIGIN_Y_PX,
        "box_padding_px": PADDING_PX,
        "box_receipt_status": "BOUND",
        "box_receipt_reason": "",
        "native_padded_xyxy": padded.as_tuple(),
        "native_detector_xyxy": detector.as_tuple(),
        "source_frame": source_frame,
    }


def proposed_writer_row(legacy: Mapping[str, Any], route: str, stored_xyxy: Box | None,
                        crop_width: int, crop_height: int,
                        source_frame: int | None) -> dict[str, Any]:
    """Model the proposed additive serialization without changing legacy fields."""
    missing = [field for field in LEGACY_FIELDS if field not in legacy]
    if missing:
        raise ValueError("legacy-field-absent-" + missing[0])
    result = dict(legacy)
    result.update(additive_receipt(route, stored_xyxy, crop_width, crop_height, source_frame))
    return result


def construct_cases() -> list[dict[str, Any]]:
    """Enumerate the sealed 2 x 4 x 2 x 2 constructive matrix."""
    sizes = ((1920, 1020), (1280, 660))
    locations = ("interior", "top_crop_boundary", "right_boundary", "bottom_boundary")
    states = ("fresh_integer", "fractional_prediction")
    statuses = ("nonempty", "empty")
    rows = []
    for ordinal, (size, location, state, status) in enumerate(
            product(sizes, locations, states, statuses)):
        width, height = size
        box = _case_box(location, width, height, state) if status == "nonempty" else None
        rows.append({"case_id": "C{0:02d}".format(ordinal + 1), "crop_width": width,
                     "crop_height": height, "location": location, "box_state": state,
                     "status": status, "stored_xyxy": None if box is None else box.as_tuple()})
    return rows


def _case_box(location: str, width: int, height: int, state: str) -> Box:
    delta = 0.5 if state == "fractional_prediction" else 0.0
    choices = {
        "interior": (100 + delta, 120 + delta, 300 + delta, 500 + delta),
        "top_crop_boundary": (40 + delta, -12 + delta, 220 + delta, 130 + delta),
        "right_boundary": (width - 90 + delta, 80 + delta, width + 25 + delta, 420 + delta),
        "bottom_boundary": (80 + delta, height - 100 + delta, 260 + delta, height + 30 + delta),
    }
    return Box(*choices[location])


def valid_prereg_seal(path: Path) -> bool:
    """Check the prereg file itself after CRLF-to-LF normalization."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = re.search(r"(?:^|\n)SEAL sha256 ([0-9a-f]{64})\n?$", text)
    if match is None:
        return False
    start = match.start() + (1 if text.startswith("\n", match.start()) else 0)
    return hashlib.sha256(text[:start].encode("utf-8")).hexdigest() == match.group(1)


def valid_repeat_shape(receipt: Mapping[str, Any]) -> bool:
    """Validate the required repeat-receipt parent shape without accepting results."""
    runs = receipt.get("runs")
    if not isinstance(runs, list) or "identical" not in receipt:
        return False
    return all(isinstance(run, Mapping) and {"stdout", "returncode", "command"} <= set(run)
               for run in runs)


_CRLF = (chr(13) + chr(10)).encode()
_LF = chr(10).encode()


def sha256_bytes(payload: bytes) -> str:
    """Digest raw bytes."""
    return hashlib.sha256(payload).hexdigest()


def file_digests(path: Path) -> tuple[int, str, str]:
    """Return (bytes, on-disk sha256, LF-normalized sha256) for one file."""
    raw = path.read_bytes()
    return len(raw), sha256_bytes(raw), sha256_bytes(raw.replace(_CRLF, _LF))


def write_lf(path: Path, text: str) -> str:
    """Write text with LF line endings on any platform; return its sha256."""
    payload = text.replace(chr(13) + chr(10), chr(10)).encode(chr(117) + chr(116) + chr(102) + chr(45) + chr(56))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return sha256_bytes(payload)


def write_csv_lf(path: Path, header: list[str], rows: list[dict[str, Any]]) -> str:
    """Write a CSV with LF endings, retaining every declared column."""
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(_cell(row.get(key, "")) for key in header))
    return write_lf(path, chr(10).join(lines) + chr(10))


def _cell(value: Any) -> str:
    """Quote one CSV cell without altering its value."""
    text = "" if value is None else str(value)
    if any(ch in text for ch in (",", chr(34), chr(10))):
        return chr(34) + text.replace(chr(34), chr(34) * 2) + chr(34)
    return text
