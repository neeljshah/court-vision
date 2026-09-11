"""G388 eye-check renders: control overlays, real traces, and pair audit cards.

Drawing only. It computes no metric and decides no verdict.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.platformkit.tracking import g387_tiles as t
from scripts.platformkit.tracking import g388_protocol as protocol
from scripts.platformkit.tracking import g388_score as score

TRUTH_COLOUR = (0, 255, 0)
RATER_COLOUR = {"terra": (0, 0, 255), "sol": (255, 128, 0)}
AUDIT_COLOUR = (0, 255, 255)


def _tile_point(point: protocol.Point, tile_index: int) -> tuple[int, int]:
    local = protocol.native_to_tile(point, t.TILE_OFFSETS[tile_index - 1])
    return int(round(local[0])), int(round(local[1]))


def control_overlays(known: Path, images: Path, out_dirs: dict[str, Path], out: Path) -> int:
    """Draw the sealed centreline and every answered point on all 30 controls."""
    import cv2

    out.mkdir(parents=True, exist_ok=True)
    rows = t.read_csv(known)
    for row in rows:
        tile_index = int(row["tile_index"])
        image = cv2.imread(str(images / row["image"]), cv2.IMREAD_COLOR)
        if image is None:
            continue
        truth = protocol.Band((float(row["x1"]), float(row["y1"])), (float(row["x2"]), float(row["y2"])))
        cv2.line(image, _tile_point(truth.first, tile_index), _tile_point(truth.second, tile_index),
                 TRUTH_COLOUR, 1)
        for rater, directory in out_dirs.items():
            points = score.read_control_response(directory / (row["control_id"] + ".json"), tile_index)
            if points is None:
                cv2.putText(image, rater + " NO RESPONSE", (10, 20 + 20 * list(out_dirs).index(rater)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, RATER_COLOUR[rater], 1)
                continue
            for point in points:
                cv2.circle(image, _tile_point(point, tile_index), 7, RATER_COLOUR[rater], 2)
        cv2.imwrite(str(out / (row["control_id"] + "_eye.png")), image)
    return len(rows)


def _context_image(cache: Path, transforms: list[dict[str, str]], context: str):
    import cv2

    return cv2.imread(str(cache / next(r for r in transforms if r["opaque_id"] == context)["context"]),
                      cv2.IMREAD_COLOR)


def real_overlays(transforms_path: Path, cache: Path, results: list[dict[str, object]], out: Path) -> int:
    """Draw both raters' native traces on each full context for the even eye check."""
    import cv2

    out.mkdir(parents=True, exist_ok=True)
    rows = t.read_csv(transforms_path)
    drawn = 0
    for record in results:
        context = str(record["context_id"]).replace("G388_", "G387_")
        image = _context_image(cache, rows, context)
        if image is None:
            continue
        for rater in ("terra", "sol"):
            for fragment in record[rater + "_fragments"]:
                points = [tuple(int(round(value)) for value in point)
                          for point in (fragment.first, fragment.second, fragment.third)]
                cv2.line(image, points[0], points[1], RATER_COLOUR[rater], 2)
                for point in points:
                    cv2.circle(image, point, 8, RATER_COLOUR[rater], 2)
                cv2.putText(image, "%s %s t%d" % (rater[:1].upper(), fragment.family, fragment.tile),
                            (points[0][0] + 10, points[0][1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            RATER_COLOUR[rater], 2)
        cv2.putText(image, "%s T=%s S=%s pairs=%d" % (record["context_id"], record["terra_state"],
                                                      record["sol_state"], len(record["pairs"])),
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        cv2.imwrite(str(out / (str(record["context_id"]) + "_trace.jpg")), image,
                    [cv2.IMWRITE_JPEG_QUALITY, 90])
        drawn += 1
    return drawn


def audit_points(fragment: protocol.Fragment) -> list[protocol.Point]:
    """Return the sealed nine evenly spaced native audit points of one fragment."""
    line = fragment.line()
    step = protocol.AUDIT_POINTS - 1
    return [(line.first[0] + index * (line.second[0] - line.first[0]) / step,
             line.first[1] + index * (line.second[1] - line.first[1]) / step)
            for index in range(protocol.AUDIT_POINTS)]


def audit_cards(transforms_path: Path, cache: Path, results: list[dict[str, object]], out: Path) -> list[str]:
    """Render one zoomed card per candidate pair carrying both nine-point series."""
    import cv2

    out.mkdir(parents=True, exist_ok=True)
    written = []
    rows = t.read_csv(transforms_path)
    for record in results:
        context = str(record["context_id"])
        image = _context_image(cache, rows, context.replace("G388_", "G387_"))
        if image is None:
            continue
        for order, pair in enumerate(record["pairs"], start=1):
            card = image.copy()
            xs, ys = [], []
            for rater, fragment in zip(("terra", "sol"), pair):
                for point in audit_points(fragment):
                    location = (int(round(point[0])), int(round(point[1])))
                    cv2.circle(card, location, 4, RATER_COLOUR[rater], -1)
                    cv2.circle(card, location, 4, AUDIT_COLOUR, 1)
                    xs.append(location[0]); ys.append(location[1])
            pad = 90
            x0, x1 = max(0, min(xs) - pad), min(card.shape[1], max(xs) + pad)
            y0, y1 = max(0, min(ys) - pad), min(card.shape[0], max(ys) + pad)
            crop = card[y0:y1, x0:x1]
            if crop.size == 0:
                continue
            scale = min(3.0, 900.0 / max(1, crop.shape[1]))
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
            name = "%s_pair%d.png" % (context, order)
            cv2.imwrite(str(out / name), crop)
            written.append(name)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("controls", "real"), required=True)
    parser.add_argument("--known", type=Path)
    parser.add_argument("--images", type=Path)
    parser.add_argument("--transforms", type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--out-terra", type=Path, required=True)
    parser.add_argument("--out-sol", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    dirs = {"terra": args.out_terra, "sol": args.out_sol}
    if args.mode == "controls":
        print(json.dumps({"control_overlays": control_overlays(args.known, args.images, dirs, args.out)}))
        return 0
    contexts = sorted({row["opaque_id"].replace("G387_", "G388_") for row in t.read_csv(args.transforms)})
    results = score.pair_contexts(contexts, dirs)
    print(json.dumps({"traces": real_overlays(args.transforms, args.cache, results, args.out),
                      "audit_cards": audit_cards(args.transforms, args.cache, results,
                                                 args.out.parent / "audit_cards")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
