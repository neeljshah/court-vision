"""Diagnose G68 source-tile reconstruction against surviving source sheets."""
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

from scripts.platformkit.g103_g68_tile_recipe import _crop_sheet_tile, _read_manifest


ROOT = Path("docs/evidence/tracking")
OUT = ROOT / "g110_tiles"
POD_HOST = "config.pod"
POD_ROOT = "/workspace/nba-ai-system/data/footage_corpus"
JPEG_QUALITY = 92


def _pixel_sha256(image: np.ndarray) -> str:
    return hashlib.sha256(image.tobytes()).hexdigest()


def _records(payload: bytes, count: int) -> list[bytes]:
    """Unpack exact-length network records from the read-only pod probe."""
    result: list[bytes] = []
    offset = 0
    for _ in range(count):
        if offset + 4 > len(payload):
            raise ValueError("truncated record header")
        length = struct.unpack("!I", payload[offset:offset + 4])[0]
        offset += 4
        if offset + length > len(payload):
            raise ValueError("truncated record body")
        result.append(payload[offset:offset + length])
        offset += length
    if offset != len(payload):
        raise ValueError("unexpected bytes after records")
    return result


def _decode(encoded: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(encoded, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("could not decode pod image")
    return image


def pixel_stats(first: np.ndarray, second: np.ndarray) -> dict[str, str]:
    """Return exact and magnitude comparisons for same-sized BGR images."""
    if first.shape != second.shape:
        raise ValueError("pixel comparisons require matching dimensions")
    delta = np.abs(first.astype(np.int16) - second.astype(np.int16))
    changed = np.any(delta != 0, axis=2)
    return {
        "pixel_equal": str(bool(np.array_equal(first, second))).lower(),
        "changed_pixels": str(int(changed.sum())),
        "total_pixels": str(int(changed.size)),
        "changed_pixel_share": f"{changed.mean():.9f}",
        "mean_abs_channel_delta": f"{delta.mean():.9f}",
        "max_abs_channel_delta": str(int(delta.max())),
    }


def _remote_payload(code: str, payload: object) -> bytes:
    encoded_code = base64.b64encode(code.encode("ascii")).decode("ascii")
    encoded_payload = base64.b64encode(json.dumps(payload).encode("ascii")).decode("ascii")
    command = f"echo {encoded_code} | base64 -d | python3 - {encoded_payload}"
    completed = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", POD_HOST, command],
        check=False,
        capture_output=True,
    )
    if completed.returncode:
        error = completed.stderr.decode("ascii", errors="replace").strip()
        raise RuntimeError(error)
    return completed.stdout


def _remote_tiles(rows: Iterable[dict[str, str]]) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    code = """
import base64, cv2, json, numpy as np, struct, sys
root, rows = json.loads(base64.b64decode(sys.argv[1]))
def tile(frame):
    frame = cv2.resize(frame, (640, 360))
    result = np.zeros((384, 640, 3), dtype=frame.dtype)
    result[24:] = frame
    return result
def emit(image, extension, params):
    ok, encoded = cv2.imencode(extension, image, params)
    if not ok:
        raise RuntimeError('encode failed')
    data = encoded.tobytes()
    sys.stdout.buffer.write(struct.pack('!I', len(data)) + data)
for row in rows:
    path = root + '/' + row['source_clip']
    seek = cv2.VideoCapture(path)
    seek.set(cv2.CAP_PROP_POS_FRAMES, int(row['frame_index']))
    ok, frame = seek.read()
    seek.release()
    if not ok:
        raise RuntimeError('seek:' + row['source_clip'] + ':' + row['frame_index'])
    sequential = cv2.VideoCapture(path)
    for _ in range(int(row['frame_index']) + 1):
        ok, sequential_frame = sequential.read()
        if not ok:
            raise RuntimeError('sequential:' + row['source_clip'] + ':' + row['frame_index'])
    sequential.release()
    seek_tile, sequential_tile = tile(frame), tile(sequential_frame)
    emit(seek_tile, '.jpg', [cv2.IMWRITE_JPEG_QUALITY, 92])
    emit(seek_tile, '.png', [])
    emit(sequential_tile, '.png', [])
"""
    row_list = list(rows)
    by_clip: dict[str, list[dict[str, str]]] = {}
    for row in row_list:
        by_clip.setdefault(row["source_clip"], []).append(row)
    received: dict[tuple[str, str], tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for clip_rows in by_clip.values():
        records = _records(_remote_payload(code, [POD_ROOT, clip_rows]), len(clip_rows) * 3)
        for row, index in zip(clip_rows, range(0, len(records), 3)):
            received[(row["clip"], row["frame_index"])] = (
                _decode(records[index]), _decode(records[index + 1]), _decode(records[index + 2])
            )
    return [received[(row["clip"], row["frame_index"])] for row in row_list]


def _remote_metadata(source_clips: list[str]) -> list[dict[str, str]]:
    code = """
import base64, cv2, json, os, sys
root, clips = json.loads(base64.b64decode(sys.argv[1]))
rows = []
for clip in clips:
    capture = cv2.VideoCapture(root + '/' + clip)
    frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = capture.get(cv2.CAP_PROP_FPS)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    capture.release()
    rows.append({'source_clip': clip, 'frame_count': frames, 'fps': fps,
                 'width': width, 'height': height,
                 'duration_seconds': frames / fps if fps else None})
sys.stdout.write(json.dumps(rows, separators=(',', ':')))
"""
    payload = _remote_payload(code, [POD_ROOT, source_clips])
    return [{key: str(value) for key, value in row.items()}
            for row in json.loads(payload.decode("ascii"))]


def write_provenance_search(source_sheets: Path) -> None:
    """Search the current WFl stream for low-frequency matches to original sheet crops."""
    rows = [row for row in _read_manifest() if row["clip"] == "ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss"]
    targets = []
    for row in rows:
        original = _original_tile(source_sheets, row)[24:]
        gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
        fingerprint = cv2.resize(gray, (32, 18), interpolation=cv2.INTER_AREA)
        targets.append({"frame_index": row["frame_index"], "fingerprint": base64.b64encode(fingerprint.tobytes()).decode("ascii")})
    code = """
import base64, cv2, json, numpy as np, sys
root, clip, targets = json.loads(base64.b64decode(sys.argv[1]))
for target in targets:
    target['array'] = np.frombuffer(base64.b64decode(target['fingerprint']), dtype=np.uint8).reshape(18, 32)
best = [(float('inf'), -1) for _ in targets]
capture = cv2.VideoCapture(root + '/' + clip)
index = 0
while True:
    ok, frame = capture.read()
    if not ok:
        break
    small = cv2.resize(cv2.cvtColor(cv2.resize(frame, (640, 360)), cv2.COLOR_BGR2GRAY), (32, 18), interpolation=cv2.INTER_AREA)
    for position, target in enumerate(targets):
        distance = float(np.abs(small.astype(np.int16) - target['array'].astype(np.int16)).mean())
        if distance < best[position][0]:
            best[position] = (distance, index)
    index += 1
capture.release()
print(json.dumps([{'source_frame_index': target['frame_index'], 'best_current_frame_index': found[1], 'best_mean_abs_gray_delta': found[0]} for target, found in zip(targets, best)], separators=(',', ':')))
"""
    payload = _remote_payload(code, [POD_ROOT, rows[0]["source_clip"], targets])
    result = json.loads(payload.decode("ascii"))
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "wfl_provenance_search.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(result[0]))
        writer.writeheader()
        writer.writerows(result)


def _side_by_side(original: np.ndarray, rebuilt: np.ndarray, destination: Path) -> None:
    image = np.hstack((original, rebuilt))
    cv2.putText(image, "ORIGINAL SHEET CROP", (8, 42), cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 0, 255), 1)
    cv2.putText(image, "REBUILT SEEK", (648, 42), cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 0, 255), 1)
    if not cv2.imwrite(str(destination), image, [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise ValueError(destination)


def _original_tile(source_sheets: Path, row: dict[str, str]) -> np.ndarray:
    source_row = {**row, "sheet_row": row["source_sheet_row"]}
    return _crop_sheet_tile(source_sheets, source_row)


def run(source_sheets: Path) -> dict[str, int]:
    """Write the fixed 33-tile diagnosis using read-only original sheets and pod clips."""
    rows = _read_manifest()
    if len(rows) != 33 or len({(row["clip"], row["frame_index"]) for row in rows}) != 33:
        raise ValueError("G110 requires 33 unique G84 tiles")
    originals = [_original_tile(source_sheets, row) for row in rows]
    for row, original in zip(rows, originals):
        if _pixel_sha256(original) != row["source_tile_pixel_sha256"]:
            raise ValueError(f"source sheet differs from G103 manifest: {row['tile_filename']}")
    rebuilt = _remote_tiles(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    sides = OUT / "side_by_side"
    sides.mkdir(exist_ok=True)
    results: list[dict[str, str]] = []
    for row, original, (seek_jpeg, seek_raw, sequential_raw) in zip(rows, originals, rebuilt):
        original_seek = pixel_stats(original, seek_jpeg)
        seek_sequential = pixel_stats(seek_raw, sequential_raw)
        results.append({
            "clip": row["clip"], "frame_index": row["frame_index"],
            "source_sheet_row": row["source_sheet_row"],
            "original_pixel_sha256": _pixel_sha256(original),
            "seek_jpeg_pixel_sha256": _pixel_sha256(seek_jpeg),
            "seek_raw_pixel_sha256": _pixel_sha256(seek_raw),
            "sequential_raw_pixel_sha256": _pixel_sha256(sequential_raw),
            **{f"original_vs_seek_{key}": value for key, value in original_seek.items()},
            **{f"seek_vs_sequential_{key}": value for key, value in seek_sequential.items()},
        })
        _side_by_side(original, seek_jpeg, sides / row["tile_filename"])
    with (OUT / "pixel_triage.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    metadata = _remote_metadata(sorted({row["source_clip"] for row in rows}))
    with (OUT / "current_source_metadata.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(metadata[0]))
        writer.writeheader()
        writer.writerows(metadata)
    return {
        "original_seek_pixel_equal": sum(item["original_vs_seek_pixel_equal"] == "true" for item in results),
        "seek_sequential_pixel_equal": sum(item["seek_vs_sequential_pixel_equal"] == "true" for item in results),
        "tiles": len(results),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sheets", required=True, type=Path)
    parser.add_argument("--provenance-search", action="store_true")
    arguments = parser.parse_args()
    if arguments.provenance_search:
        write_provenance_search(arguments.source_sheets)
        print("wfl_provenance_search=3")
        return 0
    summary = run(arguments.source_sheets)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
