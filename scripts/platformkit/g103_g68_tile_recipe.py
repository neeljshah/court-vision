"""Rebuild the 33 G84 source tiles from read-only basketball pod clips."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np


ROOT = Path("docs/evidence/tracking")
G84_MANIFEST = ROOT / "g84_candidate_quality/sample_manifest.csv"
OUT = ROOT / "g103_recall"
MANIFEST = OUT / "tile_manifest.csv"
TILES = OUT / "rebuilt_tiles"
POD_HOST = "config.pod"
POD_ROOT = "/workspace/nba-ai-system/data/footage_corpus"
TILE_WIDTH = 640
TILE_HEIGHT = 384
HEADER_HEIGHT = 24
JPEG_QUALITY = 92


def _name(row: dict[str, str]) -> str:
    return f"{row['clip']}__f{row['frame_index']}.jpg"


def _pixel_sha256(image: np.ndarray) -> str:
    return hashlib.sha256(image.tobytes()).hexdigest()


def _crop_sheet_tile(sheet_root: Path, row: dict[str, str]) -> np.ndarray:
    sheet = sheet_root / row["clip"] / f"sheet_{int(row['sheet_row']) // 25:02d}.jpg"
    image = cv2.imread(str(sheet))
    if image is None:
        raise FileNotFoundError(sheet)
    cell_height, cell_width = image.shape[0] // 5, image.shape[1] // 5
    tile_y, tile_x = divmod(int(row["sheet_row"]) % 25, 5)
    return image[
        tile_y * cell_height:(tile_y + 1) * cell_height,
        tile_x * cell_width:(tile_x + 1) * cell_width,
    ].copy()


def initialize(source_sheets: Path) -> list[dict[str, str]]:
    """Write the fixed 33-tile recipe and source-tile checksum manifest."""
    with G84_MANIFEST.open(newline="", encoding="ascii") as handle:
        selected = list(csv.DictReader(handle))
    rows = []
    for selected_row in selected:
        tile = _crop_sheet_tile(source_sheets, selected_row)
        rows.append({
            "clip": selected_row["clip"],
            "frame_index": selected_row["frame_index"],
            "source_clip": f"{selected_row['clip']}.mp4",
            "source_sheet_row": selected_row["sheet_row"],
            "tile_filename": _name(selected_row),
            "tile_width": str(TILE_WIDTH),
            "tile_height": str(TILE_HEIGHT),
            "header_height": str(HEADER_HEIGHT),
            "header_text": f"f{selected_row['frame_index']}",
            "header_origin_x": "8",
            "header_origin_y": "13",
            "header_font": "FONT_HERSHEY_SIMPLEX",
            "header_font_scale": "0.3",
            "header_bgr": "0,255,255",
            "header_thickness": "1",
            "jpeg_quality": str(JPEG_QUALITY),
            "source_tile_pixel_sha256": _pixel_sha256(tile),
        })
    OUT.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def _read_manifest() -> list[dict[str, str]]:
    with MANIFEST.open(newline="", encoding="ascii") as handle:
        return list(csv.DictReader(handle))


def _remote_payload(rows: Iterable[dict[str, str]]) -> bytes:
    code = """
import base64, cv2, json, numpy as np, struct, sys
root, rows = json.loads(base64.b64decode(sys.argv[1]))
for row in rows:
    capture = cv2.VideoCapture(root + '/' + row['source_clip'])
    capture.set(cv2.CAP_PROP_POS_FRAMES, int(row['frame_index']))
    ok, frame = capture.read()
    if not ok:
        raise RuntimeError(row['source_clip'] + ':' + row['frame_index'])
    frame = cv2.resize(frame, (640, 360))
    tile = np.zeros((int(row['tile_height']), int(row['tile_width']), 3), dtype=frame.dtype)
    tile[int(row['header_height']):] = frame
    cv2.putText(tile, row['header_text'], (int(row['header_origin_x']), int(row['header_origin_y'])),
                cv2.FONT_HERSHEY_SIMPLEX, float(row['header_font_scale']), (0, 255, 255),
                int(row['header_thickness']))
    ok, encoded = cv2.imencode('.jpg', tile, [cv2.IMWRITE_JPEG_QUALITY, int(row['jpeg_quality'])])
    if not ok:
        raise RuntimeError(row['tile_filename'])
    data = encoded.tobytes()
    sys.stdout.buffer.write(struct.pack('!I', len(data)) + data)
"""
    encoded_code = base64.b64encode(code.encode("ascii")).decode("ascii")
    payload = base64.b64encode(json.dumps([POD_ROOT, list(rows)]).encode("ascii")).decode("ascii")
    command = f"echo {encoded_code} | base64 -d | python3 - {payload}"
    completed = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", POD_HOST, command],
        check=False, capture_output=True,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.decode("ascii", errors="replace").strip())
    return completed.stdout


def _records(data: bytes, count: int) -> list[bytes]:
    records: list[bytes] = []
    offset = 0
    for _ in range(count):
        if offset + 4 > len(data):
            raise ValueError("truncated pod tile record header")
        length = struct.unpack("!I", data[offset:offset + 4])[0]
        offset += 4
        if offset + length > len(data):
            raise ValueError("truncated pod tile record body")
        records.append(data[offset:offset + length])
        offset += length
    if offset != len(data):
        raise ValueError("unexpected bytes after pod tile records")
    return records


def rebuild(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Pull only required source frames and write their reconstructed tiles."""
    TILES.mkdir(parents=True, exist_ok=True)
    by_clip: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_clip.setdefault(row["clip"], []).append(row)
    results = []
    for clip_rows in by_clip.values():
        records = _records(_remote_payload(clip_rows), len(clip_rows))
        for row, encoded in zip(clip_rows, records):
            destination = TILES / row["tile_filename"]
            destination.write_bytes(encoded)
            image = cv2.imdecode(np.frombuffer(encoded, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError(destination)
            actual = _pixel_sha256(image)
            results.append({
                "clip": row["clip"], "frame_index": row["frame_index"],
                "tile": str(destination.as_posix()),
                "expected_source_tile_pixel_sha256": row["source_tile_pixel_sha256"],
                "rebuilt_tile_pixel_sha256": actual,
                "checksum_match": str(actual == row["source_tile_pixel_sha256"]).lower(),
            })
    return results


def write_verification(rows: list[dict[str, str]]) -> int:
    """Rebuild and record every source-tile checksum comparison."""
    results = rebuild(rows)
    path = OUT / "tile_checksum_verification.csv"
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    matches = sum(row["checksum_match"] == "true" for row in results)
    print(f"tile_checksum_matches={matches}/{len(results)}")
    return 0 if matches == len(results) else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--initialize-source-sheets", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.initialize_source_sheets:
        initialize(args.initialize_source_sheets)
        print("manifest_tiles=33")
    if args.verify:
        return write_verification(_read_manifest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
