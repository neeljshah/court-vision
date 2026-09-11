"""G396 eye-check renders: control overlays, real traces and pair audit cards.

Drawing only. It computes no metric and decides no verdict.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.platformkit.tracking import g387_tiles as tiles
from scripts.platformkit.tracking import g392_score as score
from scripts.platformkit.tracking import g396_protocol as protocol

RATER_COLOUR = {"astra": (0, 0, 255), "sol": (255, 128, 0)}
AUDIT_COLOUR = (0, 255, 255)
PAD = 90


def control_overlays(truth: Path, images: Path, out_root: Path, control_set: str,
                     raters: tuple[str, ...], out: Path) -> int:
    """Draw the sealed centreline and every answered point on each control."""
    import cv2

    out.mkdir(parents=True, exist_ok=True)
    rows = tiles.read_csv(truth)
    for row in rows:
        image = cv2.imread(str(images / row["image"]), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("control image missing: %s" % row["image"])
        offset = (int(row["offset_x"]), int(row["offset_y"]))
        first = (int(round(float(row["x1"]) - offset[0])), int(round(float(row["y1"]) - offset[1])))
        second = (int(round(float(row["x2"]) - offset[0])), int(round(float(row["y2"]) - offset[1])))
        cv2.line(image, first, second, (0, 255, 0), 1, cv2.LINE_AA)
        for index, rater in enumerate(raters):
            payload = score.read_response(out_root / ("%s_%s" % (control_set, rater)), row["control_id"])
            points = score.native_points(payload, offset)[0] if payload is not None else None
            if points is None:
                cv2.putText(image, rater + " NO RESPONSE", (10, 20 + 20 * index),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, RATER_COLOUR[rater], 1)
                continue
            for point in points:
                cv2.circle(image, (int(round(point[0] - offset[0])), int(round(point[1] - offset[1]))),
                           7, RATER_COLOUR[rater], 2)
        cv2.putText(image, "%s %s" % (row["control_id"], "/".join(raters)), (8, 530),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1, cv2.LINE_AA)
        cv2.imwrite(str(out / (row["control_id"] + "_eye.jpg")), image,
                    [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    return len(rows)


def _context(cache: Path, rows: list[dict[str, str]], label: str):
    import cv2

    key = "G387_" + label.split("_")[1]
    context_rows = [row for row in rows if row["opaque_id"] == key]
    image = cv2.imread(str(cache / context_rows[0]["context"]), cv2.IMREAD_COLOR)
    if image is not None:
        return image
    tiles_by_row = []
    for y in sorted({int(row["y"]) for row in context_rows}):
        tile_images = [cv2.imread(str(cache / row["tile"]), cv2.IMREAD_COLOR)
                       for row in sorted((row for row in context_rows if int(row["y"]) == y),
                                         key=lambda row: int(row["x"]))]
        if any(tile is None for tile in tile_images):
            return None
        tiles_by_row.append(cv2.hconcat(tile_images))
    return cv2.vconcat(tiles_by_row)


def real_overlays(transforms: Path, cache: Path, results: list[dict[str, object]], out: Path) -> int:
    """Draw both raters' native traces on each full context for the even eye check."""
    import cv2

    out.mkdir(parents=True, exist_ok=True)
    rows = tiles.read_csv(transforms)
    drawn = 0
    for record in results:
        label = str(record["context_id"])
        image = _context(cache, rows, label)
        if image is None:
            continue
        for rater in RATER_COLOUR:
            for fragment in record[rater + "_fragments"]:
                points = [tuple(int(round(value)) for value in point)
                          for point in (fragment.first, fragment.second, fragment.third)]
                cv2.line(image, points[0], points[1], RATER_COLOUR[rater], 2)
                for point in points:
                    cv2.circle(image, point, 8, RATER_COLOUR[rater], 2)
                cv2.putText(image, "%s %s t%d" % (rater[:1].upper(), fragment.family, fragment.tile),
                            (points[0][0] + 10, points[0][1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            RATER_COLOUR[rater], 2)
        cv2.putText(image, "%s A=%s S=%s pairs=%d" % (label, record["astra_state"],
                                                      record["sol_state"], len(record["pairs"])),
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        cv2.imwrite(str(out / (label + "_trace.jpg")), image, [cv2.IMWRITE_JPEG_QUALITY, 90])
        drawn += 1
    return drawn


def audit_points(fragment: protocol.Fragment) -> list[protocol.Point]:
    """Return the sealed nine evenly spaced native audit points of one fragment."""
    line = fragment.line()
    step = protocol.AUDIT_POINTS - 1
    return [(line.first[0] + index * (line.second[0] - line.first[0]) / step,
             line.first[1] + index * (line.second[1] - line.first[1]) / step)
            for index in range(protocol.AUDIT_POINTS)]


def audit_cards(transforms: Path, cache: Path, results: list[dict[str, object]], out: Path) -> list[str]:
    """Render one zoomed card per candidate pair carrying both nine-point series."""
    import cv2

    out.mkdir(parents=True, exist_ok=True)
    rows = tiles.read_csv(transforms)
    written = []
    for record in results:
        label = str(record["context_id"])
        image = _context(cache, rows, label)
        if image is None:
            continue
        for order, pair in enumerate(record["pairs"], start=1):
            card = image.copy()
            xs, ys = [], []
            for rater, fragment in zip(("astra", "sol"), pair):
                for point in audit_points(fragment):
                    location = (int(round(point[0])), int(round(point[1])))
                    cv2.circle(card, location, 4, RATER_COLOUR[rater], -1)
                    cv2.circle(card, location, 4, AUDIT_COLOUR, 1)
                    xs.append(location[0])
                    ys.append(location[1])
            x0, x1 = max(0, min(xs) - PAD), min(card.shape[1], max(xs) + PAD)
            y0, y1 = max(0, min(ys) - PAD), min(card.shape[0], max(ys) + PAD)
            crop = card[y0:y1, x0:x1]
            if crop.size == 0:
                continue
            scale = min(3.0, 900.0 / max(1, crop.shape[1]))
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
            name = "%s_pair%d.png" % (label, order)
            cv2.imwrite(str(out / name), crop)
            written.append(name)
    return written


def audit_strips(transforms: Path, cache: Path, results: list[dict[str, object]], out: Path) -> list[str]:
    """Render each rater's nine raw audit-point crops for every candidate pair."""
    import cv2

    out.mkdir(parents=True, exist_ok=True)
    rows = tiles.read_csv(transforms)
    written = []
    for record in results:
        image = _context(cache, rows, str(record["context_id"]))
        if image is None:
            continue
        for order, pair in enumerate(record["pairs"], start=1):
            for rater, fragment in zip(("astra", "sol"), pair):
                panels = []
                for point in audit_points(fragment):
                    x, y = (int(round(value)) for value in point)
                    panel = image[max(0, y - 125):y + 125, max(0, x - 125):x + 125].copy()
                    if panel.shape[:2] != (250, 250):
                        panel = cv2.copyMakeBorder(panel, 0, 250 - panel.shape[0], 0,
                                                   250 - panel.shape[1], cv2.BORDER_CONSTANT)
                    cv2.circle(panel, (125, 125), 18, AUDIT_COLOUR, 1)
                    cv2.line(panel, (115, 125), (135, 125), AUDIT_COLOUR, 1)
                    cv2.line(panel, (125, 115), (125, 135), AUDIT_COLOUR, 1)
                    panels.append(panel)
                name = "%s_pair%d_%s_clicks.jpg" % (record["context_id"], order, rater)
                cv2.imwrite(str(out / name), cv2.hconcat(panels), [cv2.IMWRITE_JPEG_QUALITY, 90])
                written.append(name)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("all", "controls", "real"), default="controls")
    parser.add_argument("--truth", type=Path)
    parser.add_argument("--images", type=Path)
    parser.add_argument("--out-root", type=Path)
    parser.add_argument("--set", dest="control_set")
    parser.add_argument("--raters", nargs="+")
    parser.add_argument("--transforms", type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--practice-images", type=Path)
    parser.add_argument("--qualification-images", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "all":
        if not all((args.out_root, args.transforms, args.cache, args.practice_images,
                    args.qualification_images)):
            parser.error("all requires out-root, transforms, cache and both image directories")
        base = args.out
        counts = {
            "practice": control_overlays(args.out_root / "practice" / "truth.csv",
                                         args.practice_images, args.out_root, "practice",
                                         ("astra",), base / "practice"),
            "qualification": control_overlays(args.out_root / "qualification" / "truth.csv",
                                              args.qualification_images, args.out_root,
                                              "qualification", ("astra", "sol"),
                                              base / "qualification"),
        }
        contexts = sorted({"G396_" + row["opaque_id"].split("_")[1]
                           for row in tiles.read_csv(args.transforms)})
        results = __import__("scripts.platformkit.tracking.g396_real", fromlist=["pair_contexts"]).pair_contexts(
            contexts, {rater: args.out_root / ("real_" + rater) for rater in RATER_COLOUR})
        counts["real"] = real_overlays(args.transforms, args.cache, results, base / "real")
        counts["audit_cards"] = len(audit_cards(args.transforms, args.cache, results,
                                                  base / "audit_cards"))
        counts["audit_clicks"] = len(audit_strips(args.transforms, args.cache, results,
                                                    base / "audit_clicks"))
        print(json.dumps(counts, indent=2, sort_keys=True))
        return 0
    if args.mode == "controls":
        if not all((args.truth, args.images, args.out_root, args.control_set, args.raters)):
            parser.error("controls requires truth, images, out-root, set and raters")
        made = control_overlays(args.truth, args.images, args.out_root, args.control_set,
                                tuple(args.raters), args.out)
        print(json.dumps({"control_overlays": made}, indent=2, sort_keys=True))
        return 0
    if not all((args.transforms, args.cache, args.out_root)):
        parser.error("real requires transforms, cache and out-root")
    contexts = sorted({"G396_" + row["opaque_id"].split("_")[1]
                       for row in tiles.read_csv(args.transforms)})
    results = __import__("scripts.platformkit.tracking.g396_real", fromlist=["pair_contexts"]).pair_contexts(
        contexts, {rater: args.out_root / ("real_" + rater) for rater in RATER_COLOUR})
    print(json.dumps({"traces": real_overlays(args.transforms, args.cache, results, args.out),
                      "audit_cards": audit_cards(args.transforms, args.cache, results,
                                                 args.out.parent / "audit_cards"),
                      "audit_clicks": audit_strips(args.transforms, args.cache, results,
                                                   args.out.parent / "audit_clicks")},
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
