"""G388 control generation, tile receipts, and blind rater batch assembly.

Renders the 30 sealed known-band controls on the inherited G387 native tiles and
writes the batch files. It never scores and never opens a rater response.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from scripts.platformkit.tracking import g387_tiles as tiles
from scripts.platformkit.tracking import g388_protocol as protocol

BATCH_SIZE = 10
RATERS = ("terra", "sol")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_tiles(transforms: Path, cache: Path) -> dict[str, object]:
    """Confirm every inherited tile is byte-identical to its landed receipt."""
    rows = tiles.read_csv(transforms)
    matched, missing, mismatched = 0, [], []
    for row in rows:
        target = cache / row["tile"]
        if not target.is_file():
            missing.append(row["tile"])
        elif _sha256(target) == row["tile_sha256"]:
            matched += 1
        else:
            mismatched.append(row["tile"])
    return {"tiles": len(rows), "matched": matched, "missing": missing, "mismatched": mismatched}


def build_controls(transforms: Path, cache: Path, out_dir: Path) -> list[dict[str, str]]:
    """Draw the frozen band on one inherited tile per control and archive truth."""
    import cv2

    rows = tiles.read_csv(transforms)
    by_context: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_context.setdefault(row["opaque_id"], []).append(row)
    contexts = sorted(by_context)
    if len(contexts) != protocol.CONTROL_COUNT:
        raise ValueError("expected exactly 30 inherited contexts")
    out_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for index, context in enumerate(contexts):
        tile_index, band = protocol.control_band(index, tiles.TILE_OFFSETS)
        source = by_context[context][tile_index]
        if (int(source["x"]), int(source["y"])) != tiles.TILE_OFFSETS[tile_index]:
            raise ValueError("inherited tile offset does not match the sealed transform")
        image = cv2.imread(str(cache / source["tile"]), cv2.IMREAD_COLOR)
        if image is None or image.shape[:2] != (tiles.TILE_HEIGHT, tiles.TILE_WIDTH):
            raise ValueError("inherited tile is unavailable or not 640x540")
        rendered = protocol.render_control_tile(image, band, tiles.TILE_OFFSETS[tile_index])
        opaque = "G388_C%03d" % (index + 1)
        target = out_dir / (opaque + "_control.png")
        if not cv2.imwrite(str(target), rendered):
            raise RuntimeError("could not write a control image")
        records.append({
            "control_id": opaque, "source_context": context, "tile_index": str(tile_index + 1),
            "background_tile": source["tile"], "background_sha256": source["tile_sha256"],
            "x1": "%.3f" % band.first[0], "y1": "%.3f" % band.first[1],
            "x2": "%.3f" % band.second[0], "y2": "%.3f" % band.second[1],
            "angle_degrees": "%.1f" % ((index % 3) * 30.0),
            "length_px": "%.3f" % band.length(), "image": target.name,
            "image_sha256": _sha256(target)})
    return records


def write_batches(records: list[dict[str, str]], images: Path, out_root: Path) -> dict[str, list[str]]:
    """Write per-rater blind batches in the sealed seed-388 opaque order."""
    order = protocol.opaque_order([row["control_id"] for row in records])
    by_id = {row["control_id"]: row for row in records}
    written: dict[str, list[str]] = {}
    for rater in RATERS:
        directory = out_root / ("batch_control_" + rater)
        directory.mkdir(parents=True, exist_ok=True)
        paths = []
        for start in range(0, len(order), BATCH_SIZE):
            chunk = order[start:start + BATCH_SIZE]
            batch = directory / ("batch_%02d.tsv" % (start // BATCH_SIZE + 1))
            lines = ["%s\t%s\t%s" % (key, (images / by_id[key]["image"]).as_posix(),
                                     by_id[key]["tile_index"]) for key in chunk]
            batch.write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")
            paths.append(batch.as_posix())
        written[rater] = paths
    return written


def write_real_batches(transforms: Path, cache: Path, out_root: Path) -> dict[str, list[str]]:
    """Write per-rater real batches listing all six tiles of each sealed context."""
    rows = tiles.read_csv(transforms)
    by_context: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_context.setdefault(row["opaque_id"], []).append(row)
    contexts = sorted(by_context)
    order = protocol.opaque_order(contexts)
    written: dict[str, list[str]] = {}
    for rater in RATERS:
        directory = out_root / ("batch_real_" + rater)
        directory.mkdir(parents=True, exist_ok=True)
        paths = []
        for start in range(0, len(order), BATCH_SIZE):
            lines = []
            for key in order[start:start + BATCH_SIZE]:
                tile_paths = [(cache / row["tile"]).as_posix()
                              for row in sorted(by_context[key], key=lambda item: item["tile"])]
                lines.append("%s\t%s" % (key.replace("G387_", "G388_"), ",".join(tile_paths)))
            batch = directory / ("batch_%02d.tsv" % (start // BATCH_SIZE + 1))
            batch.write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")
            paths.append(batch.as_posix())
        written[rater] = paths
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transforms", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    receipt = verify_tiles(args.transforms, args.cache)
    if receipt["matched"] != receipt["tiles"]:
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 1
    records = build_controls(args.transforms, args.cache, args.images)
    controls_dir = args.evidence / "controls"
    controls_dir.mkdir(parents=True, exist_ok=True)
    tiles.write_csv(controls_dir / "known_points.csv", records)
    batches = write_batches(records, args.images, args.images.parent)
    real = write_real_batches(args.transforms, args.cache, args.images.parent)
    receipt.update({"controls": len(records), "control_batches": batches, "real_batches": real,
                    "known_points_sha256": _sha256(controls_dir / "known_points.csv")})
    (args.evidence / "input").mkdir(parents=True, exist_ok=True)
    (args.evidence / "input" / "control_build_receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
