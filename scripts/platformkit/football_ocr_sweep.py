"""Measure bounded multi-candidate NFL field-numeral OCR without adapter imports.

Run: python -m scripts.platformkit.football_ocr_sweep VIDEO --output DIR
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

MAX_CANDIDATES = 6
MAX_CROP_FRACTION = 0.30
MIN_CONFIDENCE = 0.60
VARIANTS = ("raw", "gray_otsu", "upscale_3x", "gray_otsu_upscale_3x")
VALID_VALUES = frozenset((10, 20, 30, 40, 50))


class TextReader(Protocol):
    def readtext(self, image: np.ndarray, **kwargs: object) -> list[object]: ...


@dataclass(frozen=True)
class Candidate:
    box: tuple[int, int, int, int]
    crop: np.ndarray


@dataclass(frozen=True)
class Read:
    value: int | None
    confidence: float
    variant: str
    box: tuple[int, int, int, int]


def _field_mask(frame: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    grass = cv2.inRange(hsv, np.array((35, 30, 20)), np.array((95, 255, 255)))
    size = max(3, int(round(min(frame.shape[:2]) * 0.012))) | 1
    return cv2.dilate(grass, np.ones((size, size), np.uint8))


def field_view(frame: np.ndarray) -> bool:
    return bool((_field_mask(frame) > 0).mean() >= 0.35)


def _iou(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    left, top = max(ax, bx), max(ay, by)
    right, bottom = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    overlap = max(0, right - left) * max(0, bottom - top)
    union = aw * ah + bw * bh - overlap
    return overlap / union if union else 0.0


def candidates(frame: np.ndarray) -> list[Candidate]:
    """Return no more than six field-paint digit crops, each bounded in pixels."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    white = cv2.inRange(hsv, np.array((0, 0, 165)), np.array((180, 100, 255)))
    paint = cv2.bitwise_and(white, _field_mask(frame))
    contours, _ = cv2.findContours(paint, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    raw: list[tuple[int, int, int, int]] = []
    max_width = max(1, int(frame.shape[1] * MAX_CROP_FRACTION))
    max_height = max(1, int(frame.shape[0] * MAX_CROP_FRACTION))
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        aspect = width / max(height, 1)
        if 18 <= height <= max_height and 0.12 <= aspect <= 2.5 and width <= max_width:
            margin = max(8, int(round(height * 0.35)))
            left, top = max(0, x - margin), max(0, y - margin)
            right, bottom = min(frame.shape[1], x + width + margin), min(frame.shape[0], y + height + margin)
            if right - left <= max_width and bottom - top <= max_height:
                raw.append((left, top, right - left, bottom - top))
    kept: list[tuple[int, int, int, int]] = []
    for box in sorted(raw, key=lambda item: item[2] * item[3], reverse=True):
        if all(_iou(box, prior) < 0.50 for prior in kept):
            kept.append(box)
        if len(kept) == MAX_CANDIDATES:
            break
    return [Candidate(box, frame[y:y + height, x:x + width]) for x, y, width, height in kept]


def preprocess(crop: np.ndarray, variant: str) -> np.ndarray:
    if variant not in VARIANTS:
        raise ValueError("unknown variant %s" % variant)
    image = crop
    if variant.startswith("gray_otsu"):
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _threshold, image = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if variant.endswith("upscale_3x"):
        image = cv2.resize(image, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    return image


def _value(text: object) -> int | None:
    digits = "".join(char for char in str(text) if char.isdigit())
    if digits in {"1", "2", "3", "4", "5"}:
        return int(digits) * 10
    return int(digits) if digits and int(digits) in VALID_VALUES else None


def read(candidate: Candidate, variant: str, reader: TextReader) -> Read:
    best = Read(None, 0.0, variant, candidate.box)
    for result in reader.readtext(preprocess(candidate.crop, variant), allowlist="0123456789", detail=1):
        if len(result) < 3:
            continue
        confidence = float(result[2])
        value = _value(result[1])
        if value is not None and confidence >= MIN_CONFIDENCE and confidence > best.confidence:
            best = Read(value, confidence, variant, candidate.box)
    return best


def _reader() -> TextReader:
    import easyocr
    return easyocr.Reader(["en"], gpu=False, verbose=False)


def _render(frame: np.ndarray, reads: list[Read], label: str) -> np.ndarray:
    image = frame.copy()
    for item in reads:
        x, y, width, height = item.box
        color = (0, 255, 0) if item.value is not None else (0, 0, 255)
        cv2.rectangle(image, (x, y), (x + width, y + height), color, 2)
        cv2.putText(image, "%s %.2f" % (str(item.value), item.confidence), (x, max(18, y - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    cv2.putText(image, label, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
    return image


def measure(video: Path, output: Path, positions: int = 120, render_count: int = 10) -> dict:
    """Run the crop sweep and return all rates and downstream gate denominators."""
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError("could not open %s" % video)
    output.mkdir(parents=True, exist_ok=True)
    reader = _reader()
    count = max(1, int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
    corpus: list[Candidate] = []
    frames: list[tuple[int, np.ndarray, list[Candidate]]] = []
    sampled = field_views = 0
    try:
        for index in np.linspace(0, count - 1, num=positions, dtype=int):
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if not ok:
                continue
            sampled += 1
            if not field_view(frame):
                continue
            field_views += 1
            found = candidates(frame)
            corpus.extend(found)
            frames.append((int(index), frame, found))
    finally:
        capture.release()
    rates = {variant: sum(read(item, variant, reader).value is not None for item in corpus) for variant in VARIANTS}
    winner = max(VARIANTS, key=lambda variant: (rates[variant], -VARIANTS.index(variant)))
    distribution: dict[str, int] = {}
    distinct_frames = 0
    rendered: list[tuple[float, np.ndarray]] = []
    for index, frame, found in frames:
        reads = [read(item, winner, reader) for item in found]
        valid = [item for item in reads if item.value is not None]
        distribution[str(len(valid))] = distribution.get(str(len(valid)), 0) + 1
        distinct_frames += int(len({item.value for item in valid}) >= 2)
        rendered.append((max((item.confidence for item in valid), default=0.0), _render(frame, reads, "frame=%d valid=%d" % (index, len(valid)))))
    for label, ordered in (("worst", sorted(rendered, key=lambda item: item[0])),
                           ("best", sorted(rendered, key=lambda item: item[0], reverse=True))):
        for rank, (_score, image) in enumerate(ordered[:render_count], 1):
            cv2.imwrite(str(output / ("%s_%02d.jpg" % (label, rank))), image)
    report = {"sampled_frames": sampled, "field_view_frames": field_views, "candidate_crops": len(corpus),
              "max_candidates_per_frame": MAX_CANDIDATES, "variant_valid_reads": rates,
              "variant_valid_rate": {key: value / max(len(corpus), 1) for key, value in rates.items()},
              "winner": winner, "winning_valid_read_distribution": distribution,
              "frames_two_different_valid_numerals": distinct_frames,
              "gate": {"minimum_crops": 40, "minimum_field_views": 60, "minimum_distinct_frames": 30,
                       "pass": len(corpus) >= 40 and field_views >= 60 and distinct_frames >= 30}}
    (output / "ocr_sweep.json").write_text(json.dumps(report, indent=2), encoding="ascii")
    return report


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--positions", type=int, default=120)
    args = parser.parse_args(argv[1:])
    print(json.dumps(measure(args.video, args.output, args.positions), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv))
