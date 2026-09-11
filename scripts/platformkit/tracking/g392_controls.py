"""G392 identity verification, sealed practice/qualification controls, rater batches.

Builds two disjoint 30-control sets on the inherited G387 native tiles under seed
392. It never scores, never opens a rater response, and never writes under data/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

from scripts.platformkit.tracking import g387_tiles as tiles
from scripts.platformkit.tracking import g388_protocol as g388
from scripts.platformkit.tracking import g392_prepare as prepare
from scripts.platformkit.tracking import g392_protocol as protocol

BATCH_SIZE = 10
LENGTH = 240.0
SETS = ("practice", "qualification")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_identity(transforms: Path, census: Path, cache: Path) -> dict[str, object]:
    """Confirm every inherited tile, context and retained native still matches."""
    rows = tiles.read_csv(transforms)
    tile_ok, tile_bad, ctx = 0, [], {}
    for row in rows:
        target = cache / row["tile"]
        if target.is_file() and _sha256(target) == row["tile_sha256"]:
            tile_ok += 1
        else:
            tile_bad.append(row["tile"])
        ctx[row["context"]] = row["context_sha256"]
    ctx_ok, ctx_bad = 0, []
    for name, digest in sorted(ctx.items()):
        target = cache / name
        if target.is_file() and _sha256(target) == digest:
            ctx_ok += 1
        else:
            ctx_bad.append(name)
    native_ok, native_absent = 0, []
    for row in tiles.read_csv(census):
        if row.get("retained") != "RETAINED":
            continue
        source = Path(row["native_path"])
        if source.is_file() and _sha256(source) == row["native_sha256"]:
            native_ok += 1
        else:
            native_absent.append(row["frame_key"])
    return {"tiles": len(rows), "tiles_matched": tile_ok, "tiles_mismatched": tile_bad,
            "contexts": len(ctx), "contexts_matched": ctx_ok, "contexts_mismatched": ctx_bad,
            "retained_natives": native_ok + len(native_absent), "natives_matched": native_ok,
            "natives_absent": native_absent,
            "holds": not tile_bad and not ctx_bad and not native_absent
            and tile_ok == 180 and ctx_ok == 30}


def _band(rng: random.Random, tile_offset: tuple[int, int], angle_degrees: float) -> g388.Band:
    """Place a finite 240 px centreline wholly inside one 640x540 tile."""
    angle = math.radians(angle_degrees)
    half_x = abs(math.cos(angle)) * LENGTH / 2
    half_y = abs(math.sin(angle)) * LENGTH / 2
    margin = 12.0
    cx = rng.uniform(half_x + margin, tiles.TILE_WIDTH - half_x - margin)
    cy = rng.uniform(half_y + margin, tiles.TILE_HEIGHT - half_y - margin)
    dx, dy = math.cos(angle) * LENGTH / 2, math.sin(angle) * LENGTH / 2
    first = g388.tile_to_native((cx - dx, cy - dy), tile_offset)
    second = g388.tile_to_native((cx + dx, cy + dy), tile_offset)
    return g388.Band(first, second)


def build_set(kind: str, transforms: Path, cache: Path, out_dir: Path) -> list[dict[str, str]]:
    """Render one sealed 30-control set, one context each, and archive its truth."""
    import cv2

    rows = tiles.read_csv(transforms)
    by_context: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_context.setdefault(row["opaque_id"], []).append(row)
    contexts = sorted(by_context)
    if len(contexts) != protocol.CONTROL_COUNT:
        raise ValueError("expected exactly 30 inherited contexts")
    plan = prepare.control_plan(kind)
    rng = random.Random("%d-%s" % (prepare.SEED, kind))
    out_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for context, entry in zip(contexts, plan):
        tile_index = int(entry["tile_index"])
        offset = prepare.TILE_OFFSETS[tile_index - 1]
        source = [row for row in by_context[context]
                  if (int(row["x"]), int(row["y"])) == offset]
        if len(source) != 1:
            raise ValueError("inherited tile offset does not match the sealed transform")
        image = cv2.imread(str(cache / source[0]["tile"]), cv2.IMREAD_COLOR)
        if image is None or image.shape[:2] != (tiles.TILE_HEIGHT, tiles.TILE_WIDTH):
            raise ValueError("inherited tile is unavailable or not 640x540")
        band = _band(rng, offset, float(entry["angle_degrees"]))
        rendered = g388.render_control_tile(image, band, offset)
        target = out_dir / (str(entry["control_id"]) + ".png")
        if not cv2.imwrite(str(target), rendered):
            raise RuntimeError("could not write a control image")
        records.append({
            "control_id": str(entry["control_id"]), "control_set": kind,
            "seed": str(prepare.SEED), "source_context": context,
            "tile_index": str(tile_index), "offset_x": str(offset[0]),
            "offset_y": str(offset[1]), "background_tile": source[0]["tile"],
            "background_sha256": source[0]["tile_sha256"],
            "angle_degrees": "%.1f" % float(entry["angle_degrees"]),
            "x1": "%.3f" % band.first[0], "y1": "%.3f" % band.first[1],
            "x2": "%.3f" % band.second[0], "y2": "%.3f" % band.second[1],
            "length_px": "%.3f" % band.length(), "image": target.name,
            "image_sha256": _sha256(target)})
    return records


def disjoint(practice: list[dict[str, str]], qualification: list[dict[str, str]]) -> dict[str, object]:
    """Prove no pixel digest and no truth tuple is shared between the two sets."""
    def keys(rows):
        return ({row["image_sha256"] for row in rows},
                {(row["source_context"], row["tile_index"], row["x1"], row["y1"],
                  row["x2"], row["y2"]) for row in rows},
                {(row["source_context"], row["tile_index"]) for row in rows})

    left, right = keys(practice), keys(qualification)
    return {"shared_pixels": sorted(left[0] & right[0]),
            "shared_truth": sorted(str(item) for item in left[1] & right[1]),
            "shared_context_tile": sorted(str(item) for item in left[2] & right[2]),
            "disjoint": not (left[0] & right[0]) and not (left[1] & right[1])
            and not (left[2] & right[2])}


def write_batches(records: list[dict[str, str]], images: Path, out_root: Path,
                  kind: str) -> dict[str, list[str]]:
    """Write one blind per-rater batch file set in a seeded opaque order."""
    order = [row["control_id"] for row in records]
    random.Random(prepare.SEED).shuffle(order)
    by_id = {row["control_id"]: row for row in records}
    written: dict[str, list[str]] = {}
    for rater in prepare.RATERS:
        directory = out_root / ("batch_%s_%s" % (kind, rater))
        directory.mkdir(parents=True, exist_ok=True)
        paths = []
        for start in range(0, len(order), BATCH_SIZE):
            batch = directory / ("batch_%02d.tsv" % (start // BATCH_SIZE + 1))
            lines = []
            for key in order[start:start + BATCH_SIZE]:
                row = by_id[key]
                lines.append("\t".join([key, (images / row["image"]).as_posix(),
                                        row["tile_index"], row["offset_x"], row["offset_y"],
                                        str(tiles.TILE_WIDTH), str(tiles.TILE_HEIGHT)]))
            batch.write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")
            paths.append(batch.as_posix())
        written[rater] = paths
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transforms", type=Path, required=True)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    identity = verify_identity(args.transforms, args.census, args.cache)
    if not identity["holds"]:
        print(json.dumps(identity, indent=2, sort_keys=True))
        return 1
    receipt: dict[str, object] = {"identity": identity, "batches": {}}
    built = {}
    for kind in SETS:
        images = args.work / ("images_" + kind)
        records = build_set(kind, args.transforms, args.cache, images)
        built[kind] = records
        target = args.evidence / kind
        target.mkdir(parents=True, exist_ok=True)
        tiles.write_csv(target / "truth.csv", records)
        receipt["batches"][kind] = write_batches(records, images, args.work, kind)
        receipt[kind + "_truth_sha256"] = _sha256(target / "truth.csv")
    receipt["disjoint"] = disjoint(built["practice"], built["qualification"])
    (args.evidence / "input").mkdir(parents=True, exist_ok=True)
    (args.evidence / "input" / "control_build_receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["disjoint"]["disjoint"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
