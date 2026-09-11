"""G387 native-frame census, fixed even selection, and lossless tile export."""
from __future__ import annotations

import csv
import hashlib
import math
import shutil
from pathlib import Path

TILE_WIDTH = 640
TILE_HEIGHT = 540
TILE_OFFSETS = tuple((col * TILE_WIDTH, row * TILE_HEIGHT)
                     for row in range(2) for col in range(3))


def tile_to_native(tile_index: int, x: float, y: float) -> tuple[float, float]:
    """Map one displayed tile coordinate to its lossless native coordinate."""
    if tile_index < 1 or tile_index > len(TILE_OFFSETS) or not (0 <= x < TILE_WIDTH and 0 <= y < TILE_HEIGHT):
        raise ValueError("tile point is outside the sealed tile transform")
    offset_x, offset_y = TILE_OFFSETS[tile_index - 1]
    return offset_x + x, offset_y + y


def native_to_tile(x: float, y: float) -> tuple[int, float, float]:
    """Map a native point to exactly one fixed tile without rescaling."""
    if not (0 <= x < TILE_WIDTH * 3 and 0 <= y < TILE_HEIGHT * 2):
        raise ValueError("native point is outside the sealed context")
    col, row = int(x // TILE_WIDTH), int(y // TILE_HEIGHT)
    return row * 3 + col + 1, x - col * TILE_WIDTH, y - row * TILE_HEIGHT


def sha256(path: Path) -> str:
    """Return the byte hash for one named input, never a directory."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def select_even_retained(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Return the sealed 30-of-49 draw, not a leading slice."""
    retained = [row for row in rows if row.get("retained") == "RETAINED"]
    retained.sort(key=lambda row: (row["video_id"], row["section_id"], int(row["frame_order"])))
    if len(retained) != 49:
        raise ValueError("expected exactly 49 retained source states")
    indices = [math.floor(j * 48 / 29 + 0.5) for j in range(30)]
    if indices == list(range(30)) or indices[-1] != 48 or len(set(indices)) != 30:
        raise ValueError("selection is not the sealed even 30-of-49 draw")
    return [retained[index] for index in indices]


def census(frames: list[dict[str, str]], identities: list[dict[str, str]]) -> list[dict[str, str]]:
    """Verify every original state and return an explicit eligibility table."""
    if len(frames) != 60 or sum(row.get("retained") == "RETAINED" for row in frames) != 49:
        raise ValueError("G382 state accounting differs from 60 planned / 49 retained")
    by_key = {row["frame_key"]: row for row in identities}
    output = []
    for row in frames:
        identity = by_key.get(row["frame_key"], {})
        path = Path(identity.get("native_path", ""))
        ready = identity.get("status") == "READY" and path.is_file()
        digest = sha256(path) if ready else ""
        valid = ready and digest == identity.get("native_sha256", "")
        output.append({
            "frame_key": row["frame_key"], "retained": row["retained"],
            "native_path": str(path), "status": "READY" if valid else "ABSENT",
            "native_sha256": digest, "bytes": str(path.stat().st_size) if valid else "0",
            "width": identity.get("width", ""), "height": identity.get("height", ""),
        })
    return output


def build_tiles(selected: list[dict[str, str]], out_dir: Path) -> list[dict[str, str]]:
    """Copy selected originals once and export six integer-offset native crops each."""
    import cv2

    out_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for order, row in enumerate(selected, start=1):
        source = Path(row["native_path"])
        image = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if image is None or image.shape[:2] != (1080, 1920):
            raise ValueError("native image is unavailable or not 1920x1080: %s" % source)
        opaque_id = "G387_%03d" % order
        context = out_dir / (opaque_id + "_context.png")
        shutil.copyfile(source, context)
        if sha256(source) != sha256(context):
            raise RuntimeError("receiver hash differs from sender hash")
        for tile_index, (x, y) in enumerate(TILE_OFFSETS, start=1):
            tile = image[y:y + TILE_HEIGHT, x:x + TILE_WIDTH]
            target = out_dir / ("%s_tile%d.png" % (opaque_id, tile_index))
            if not cv2.imwrite(str(target), tile):
                raise RuntimeError("could not write tile")
            records.append({"opaque_id": opaque_id, "frame_key": row["frame_key"],
                            "tile": target.name, "x": str(x), "y": str(y),
                            "width": str(TILE_WIDTH), "height": str(TILE_HEIGHT),
                            "context": context.name, "context_sha256": sha256(context)})
    return records


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError("refusing to write a headerless empty evidence table")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
