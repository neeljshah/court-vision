"""Create a blind, source-decoded audit sample for the fixed G111 census."""
from __future__ import annotations

import argparse
import base64
import csv
import json
from collections import defaultdict
from pathlib import Path
import random
import struct
import subprocess

import cv2
import numpy as np


ROOT = Path("docs/evidence/tracking")
LABELS = ROOT / "g111_basketball_reach/frame_labels.csv"
OUT = ROOT / "g126_label_audit"
SEED = 1261112026
POD_HOST = "config.pod"
POD_ROOT = "/workspace/nba-ai-system/data/footage_corpus"


def corner_count(row: dict[str, str]) -> int:
    """Return the number of retained G111 paint-corner roles in one row."""
    return sum(bool(item) for item in row["point_features"].split(";"))


def blind_sample(rows: list[dict[str, str]], seed: int = SEED) -> list[dict[str, str]]:
    """Select all scarce some-corner rows plus seeded zero and four strata."""
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        count = corner_count(row)
        groups["none" if count == 0 else "some" if count < 4 else "four"].append(row)
    if set(groups) != {"none", "some", "four"} or len(groups["some"]) < 1:
        raise ValueError("G111 labels lack required label-count strata")
    rng = random.Random(seed)
    selected = list(groups["some"])
    for key, target in (("none", 16), ("four", 15)):
        selected.extend(rng.sample(groups[key], target))
    rng.shuffle(selected)
    return [
        {"audit_id": f"G126_{index:02d}", "clip": row["clip"],
         "source_frame": row["source_frame"], "slot": row["slot"]}
        for index, row in enumerate(selected, 1)
    ]


def read_labels() -> list[dict[str, str]]:
    with LABELS.open(newline="", encoding="ascii") as handle:
        return list(csv.DictReader(handle))


def write_blind_manifest(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    selected = blind_sample(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "blind_selection_manifest.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(selected[0]))
        writer.writeheader()
        writer.writerows(selected)
    return selected


def _remote_payload(rows: list[dict[str, str]]) -> bytes:
    code = """
import base64, cv2, json, struct, sys
root, rows = json.loads(base64.b64decode(sys.argv[1]))
for row in rows:
    cap = cv2.VideoCapture(root + '/' + row['clip'] + '.mp4')
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(row['source_frame']))
    ok, image = cap.read()
    cap.release()
    if not ok: raise RuntimeError(row['audit_id'])
    ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok: raise RuntimeError(row['audit_id'])
    data = encoded.tobytes()
    sys.stdout.buffer.write(struct.pack('!I', len(data)) + data)
"""
    encoded = base64.b64encode(code.encode("ascii")).decode("ascii")
    payload = base64.b64encode(json.dumps([POD_ROOT, rows]).encode("ascii")).decode("ascii")
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", POD_HOST,
         f"echo {encoded} | base64 -d | python3 - {payload}"],
        capture_output=True, check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode("ascii", errors="replace").strip())
    return result.stdout


def decode_source(rows: list[dict[str, str]]) -> None:
    """Read exact source indices from the pod and write reviewer-only JPEGs."""
    payload = _remote_payload(rows)
    destination = OUT / "blind_source_decodes"
    destination.mkdir(parents=True, exist_ok=True)
    offset = 0
    images: list[np.ndarray] = []
    for row in rows:
        length = struct.unpack("!I", payload[offset:offset + 4])[0]
        offset += 4
        data = payload[offset:offset + length]
        offset += length
        image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(row["audit_id"])
        if not cv2.imwrite(str(destination / f"{row['audit_id']}.jpg"), image):
            raise ValueError(row["audit_id"])
        images.append(image)
    if offset != len(payload):
        raise ValueError("unexpected bytes after source frames")
    for page, start in enumerate(range(0, len(images), 9), 1):
        tiles = []
        for index, image in enumerate(images[start:start + 9], start):
            tile = cv2.resize(image, (640, 360), interpolation=cv2.INTER_AREA)
            cv2.putText(tile, rows[index]["audit_id"], (12, 28), cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, (0, 255, 255), 2)
            tiles.append(tile)
        while len(tiles) < 9:
            tiles.append(np.zeros_like(tiles[0]))
        sheet = cv2.vconcat([cv2.hconcat(tiles[i:i + 3]) for i in range(0, 9, 3)])
        cv2.imwrite(str(destination / f"contact_sheet_{page:02d}.jpg"), sheet)


def render_review_sheets(rows: list[dict[str, str]]) -> None:
    """Make ID-keyed sheets from the already-committed G111 renders."""
    labels = {(row["clip"], row["source_frame"], row["slot"]): row for row in read_labels()}
    destination = OUT / "committed_render_review"
    destination.mkdir(parents=True, exist_ok=True)
    images: list[np.ndarray] = []
    for row in rows:
        label = labels[(row["clip"], row["source_frame"], row["slot"])]
        image = cv2.imread(str(ROOT / "g111_basketball_reach" / label["render"]))
        if image is None:
            raise FileNotFoundError(label["render"])
        images.append(image)
    for page, start in enumerate(range(0, len(images), 9), 1):
        tiles = []
        for index, image in enumerate(images[start:start + 9], start):
            tile = cv2.resize(image, (640, 360), interpolation=cv2.INTER_AREA)
            cv2.putText(tile, rows[index]["audit_id"], (12, 28), cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, (0, 255, 255), 2)
            tiles.append(tile)
        while len(tiles) < 9:
            tiles.append(np.zeros_like(tiles[0]))
        sheet = cv2.vconcat([cv2.hconcat(tiles[i:i + 3]) for i in range(0, 9, 3)])
        cv2.imwrite(str(destination / f"contact_sheet_{page:02d}.jpg"), sheet)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decode", action="store_true")
    parser.add_argument("--render-sheets", action="store_true")
    args = parser.parse_args()
    selected = write_blind_manifest(read_labels())
    if args.decode:
        decode_source(selected)
    if args.render_sheets:
        render_review_sheets(selected)
    print(f"g126_blind_frames={len(selected)}")


if __name__ == "__main__":
    main()
