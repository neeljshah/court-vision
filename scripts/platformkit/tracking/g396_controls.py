"""G396 sealed control construction for the sol/ASTRA third-rater gate.

Builds two disjoint 30-control sets under seed 396 on the inherited G387 native
tiles, proves disjointness against G392 as well as within G396, and writes one
blind per-rater batch set. It never scores and never writes under data/.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from scripts.platformkit.tracking import g387_tiles as tiles
from scripts.platformkit.tracking import g388_protocol as g388
from scripts.platformkit.tracking import g392_controls as g392c
from scripts.platformkit.tracking import g396_prepare as prepare
from scripts.platformkit.tracking import g396_protocol as protocol

BATCH_SIZE = 10
TILE_OFFSETS = ((0, 0), (640, 0), (1280, 0), (0, 540), (640, 540), (1280, 540))
SETS = ("practice", "qualification")


def build_set(kind: str, transforms: Path, cache: Path, out_dir: Path) -> list[dict[str, str]]:
    """Render one sealed 30-control set, one inherited context each, plus truth."""
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
        offset = TILE_OFFSETS[tile_index - 1]
        source = [row for row in by_context[context] if (int(row["x"]), int(row["y"])) == offset]
        if len(source) != 1:
            raise ValueError("inherited tile offset does not match the sealed transform")
        image = cv2.imread(str(cache / source[0]["tile"]), cv2.IMREAD_COLOR)
        if image is None or image.shape[:2] != (tiles.TILE_HEIGHT, tiles.TILE_WIDTH):
            raise ValueError("inherited tile is unavailable or not 640x540")
        band = g392c._band(rng, offset, float(entry["angle_degrees"]))
        target = out_dir / (str(entry["control_id"]) + ".png")
        if not cv2.imwrite(str(target), g388.render_control_tile(image, band, offset)):
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
            "image_sha256": g392c._sha256(target)})
    return records


def write_batches(records: list[dict[str, str]], images: Path, out_root: Path, kind: str,
                  raters: tuple[str, ...]) -> dict[str, list[str]]:
    """Write one blind per-rater batch file set in the same seeded opaque order."""
    order = [row["control_id"] for row in records]
    random.Random(prepare.SEED).shuffle(order)
    by_id = {row["control_id"]: row for row in records}
    written: dict[str, list[str]] = {}
    for rater in raters:
        directory = out_root / ("batch_%s_%s" % (kind, rater))
        directory.mkdir(parents=True, exist_ok=True)
        paths = []
        for start in range(0, len(order), BATCH_SIZE):
            batch = directory / ("batch_%02d.tsv" % (start // BATCH_SIZE + 1))
            lines = []
            for key in order[start:start + BATCH_SIZE]:
                row = by_id[key]
                lines.append("\t".join([key, (images / row["image"]).as_posix(), row["tile_index"],
                                        row["offset_x"], row["offset_y"],
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
    parser.add_argument("--g392", type=Path, required=True)
    args = parser.parse_args()
    identity = g392c.verify_identity(args.transforms, args.census, args.cache)
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
        raters = ("astra",) if kind == "practice" else protocol.RATERS
        receipt["batches"][kind] = write_batches(records, images, args.work, kind, raters)
        receipt[kind + "_truth_sha256"] = g392c._sha256(target / "truth.csv")
    receipt["within_g396"] = g392c.disjoint(built["practice"], built["qualification"])
    old = tiles.read_csv(args.g392 / "practice" / "truth.csv") + tiles.read_csv(
        args.g392 / "qualification" / "truth.csv")
    receipt["disjoint_from_g392"] = {
        kind: prepare.controls_disjoint(built[kind], old) for kind in SETS}
    receipt["disjoint"] = bool(receipt["within_g396"]["disjoint"]
                               and all(receipt["disjoint_from_g392"].values()))
    (args.evidence / "input").mkdir(parents=True, exist_ok=True)
    (args.evidence / "input" / "control_build_receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in receipt.items() if k != "batches"}, indent=2, sort_keys=True))
    return 0 if receipt["disjoint"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
