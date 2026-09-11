"""G382 blind adjudication: archive both rater traces, agree per physical marking, emit final masks."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking.g382_masks import LABELS

MIN_AREA_PX = 24
RATING_FIELDS = ("frame_key", "opaque_id", "rater", "kind", "identifier", "n_points",
                 "area_px", "polygon")
ADJ_FIELDS = ("frame_key", "kind", "identifier", "in_terra", "in_sol", "iou", "decision",
              "final_area_px")


def _mask(shape: tuple[int, int], polygon) -> np.ndarray:
    out = np.zeros(shape, dtype=np.uint8)
    cv2.fillPoly(out, [np.rint(np.asarray(polygon, dtype=np.float32)).astype(np.int32)], 1)
    return out


def _polygons(mask: np.ndarray) -> list[list[list[int]]]:
    """Outer contours only; the caller must reclaim the FILLED footprint, which can exceed mask."""
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [[[int(point[0][0]), int(point[0][1])] for point in contour]
            for contour in contours if len(contour) >= 3 and cv2.contourArea(contour) >= MIN_AREA_PX]


def _emit(shape: tuple[int, int], mask: np.ndarray, claimed: np.ndarray) -> list[list[list[int]]]:
    """Emit only polygons whose REFILLED footprint is still free, then claim it.

    A contour refills solid, so a ring or a nested contour can cover pixels the raster did not.
    Claiming the refilled footprint one polygon at a time is what keeps the final annotation
    disjoint, which the mask reader requires; a polygon that would collide is dropped, never
    silently merged into its neighbour.
    """
    kept = []
    for polygon in _polygons((mask & (1 - claimed)).astype(np.uint8)):
        footprint = _mask(shape, polygon)
        if int((footprint & claimed).sum()):
            continue
        kept.append(polygon)
        claimed |= footprint
    return kept


def load(directory: Path) -> dict[str, dict]:
    return {path.stem: json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(directory.glob("*.json"))}


def rating_rows(frame_key: str, opaque_id: str, rater: str, doc: dict, shape) -> list[dict[str, str]]:
    """Archive every original trace before any adjudication touches it."""
    rows = []
    for item in doc.get("painted_markings", []):
        rows.append(("PAINTED", str(item["physical_marking_id"]), item["polygon"]))
    for item in doc.get("mask_regions", []):
        for polygon in item.get("polygons", []):
            rows.append(("REGION", str(item["label"]).upper(), polygon))
    return [{"frame_key": frame_key, "opaque_id": opaque_id, "rater": rater, "kind": kind,
             "identifier": identifier, "n_points": str(len(polygon)),
             "area_px": str(int(_mask(shape, polygon).sum())),
             "polygon": json.dumps(polygon, separators=(",", ":"))}
            for kind, identifier, polygon in rows]


def _layers(doc: dict, key: str, shape) -> dict[str, np.ndarray]:
    acc: dict[str, np.ndarray] = {}
    if key == "PAINTED":
        items = [(str(item["physical_marking_id"]), [item["polygon"]])
                 for item in doc.get("painted_markings", [])]
    else:
        items = [(str(item["label"]).upper(), item.get("polygons", []))
                 for item in doc.get("mask_regions", [])]
    for identifier, polygons in items:
        layer = acc.setdefault(identifier, np.zeros(shape, dtype=np.uint8))
        for polygon in polygons:
            layer |= _mask(shape, polygon)
    return acc


def _combine(docs: dict[str, dict], key: str, shape, mode: str) -> dict[str, np.ndarray]:
    """Per-identifier agreement mask; both is the conservative primary, either is the bound."""
    sides = {rater: _layers(doc, key, shape) for rater, doc in docs.items()}
    names: set[str] = set()
    for side in sides.values():
        names |= set(side)
    out = {}
    for name in sorted(names):
        layers = [side.get(name, np.zeros(shape, dtype=np.uint8)) for side in sides.values()]
        merged = layers[0].copy()
        for layer in layers[1:]:
            merged = (merged & layer) if mode == "both" else (merged | layer)
        out[name] = merged
    return out


def _iou(first: np.ndarray, second: np.ndarray) -> float:
    union = int((first | second).sum())
    return (int((first & second).sum()) / union) if union else 0.0


def adjudicate(frame_key: str, docs: dict[str, dict], shape, mode: str,
               keep: set[tuple[str, str]]) -> tuple[dict, list[dict[str, str]]]:
    """Emit one final annotation plus the per-identifier disagreement record."""
    painted = _combine(docs, "PAINTED", shape, mode)
    regions = _combine(docs, "REGION", shape, mode)
    claimed = np.zeros(shape, dtype=np.uint8)
    rows, markings, final_regions = [], [], []
    for name, mask in painted.items():
        sides = {rater: any(str(item["physical_marking_id"]) == name
                            for item in doc.get("painted_markings", []))
                 for rater, doc in docs.items()}
        both = all(sides.values())
        keeps = both or (frame_key, name) in keep
        pair = [_mask(shape, item["polygon"]) for doc in docs.values()
                for item in doc.get("painted_markings", []) if str(item["physical_marking_id"]) == name]
        iou = _iou(pair[0], pair[1]) if len(pair) == 2 else 0.0
        polygons = _emit(shape, mask, claimed) if keeps else []
        for index, polygon in enumerate(polygons):
            markings.append({"physical_marking_id": "%s#%d" % (name, index), "polygon": polygon})
        area = sum(int(_mask(shape, polygon).sum()) for polygon in polygons)
        rows.append({"frame_key": frame_key, "kind": "PAINTED", "identifier": name,
                     "in_terra": str(int(sides.get("terra", False))),
                     "in_sol": str(int(sides.get("sol", False))), "iou": "%.6f" % iou,
                     "decision": ("AGREED" if both else ("CLAUDE_KEPT" if keeps else "UNRESOLVED")),
                     "final_area_px": str(area)})
    for name in [label for label in LABELS if label != "PAINTED"]:
        mask = regions.get(name)
        if mask is None:
            continue
        polygons = _emit(shape, mask, claimed)
        if polygons:
            final_regions.append({"label": name, "polygons": polygons})
        area = sum(int(_mask(shape, polygon).sum()) for polygon in polygons)
        sides = {rater: any(str(item["label"]).upper() == name for item in doc.get("mask_regions", []))
                 for rater, doc in docs.items()}
        rows.append({"frame_key": frame_key, "kind": "REGION", "identifier": name,
                     "in_terra": str(int(sides.get("terra", False))),
                     "in_sol": str(int(sides.get("sol", False))), "iou": "",
                     "decision": "AGREED" if all(sides.values()) else "ONE_RATER_ONLY",
                     "final_area_px": str(area)})
    doc = {"frame_key": frame_key, "image": {"width": shape[1], "height": shape[0]},
           "painted_markings": markings, "mask_regions": final_regions}
    return doc, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--terra", type=Path, required=True)
    parser.add_argument("--sol", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=("both", "either"), default="both")
    parser.add_argument("--keep", type=Path, default=None)
    args = parser.parse_args()
    masks = args.out / "masks"
    masks.mkdir(parents=True, exist_ok=True)
    docs = {"terra": load(args.terra), "sol": load(args.sol)}
    keep = set()
    if args.keep and args.keep.is_file():
        with args.keep.open(encoding="utf-8", newline="") as handle:
            keep = {(row["frame_key"], row["identifier"]) for row in csv.DictReader(handle)}
    with args.identity.open(encoding="utf-8", newline="") as handle:
        identity = [row for row in csv.DictReader(handle) if row["status"] == "READY"]
    ratings, adj = [], []
    for row in identity:
        opaque, key = row["opaque_id"], row["frame_key"]
        shape = (int(row["height"]), int(row["width"]))
        present = {rater: docs[rater][opaque] for rater in docs if opaque in docs[rater]}
        for rater, doc in present.items():
            ratings.extend(rating_rows(key, opaque, rater, doc, shape))
        if len(present) != 2:
            adj.append({"frame_key": key, "kind": "FRAME", "identifier": "RATER_COVERAGE",
                        "in_terra": str(int("terra" in present)), "in_sol": str(int("sol" in present)),
                        "iou": "", "decision": "INCOMPLETE", "final_area_px": "0"})
            continue
        doc, rows = adjudicate(key, present, shape, args.mode, keep)
        (masks / (key.replace(":", "_").replace("/", "_") + ".json")).write_text(
            json.dumps(doc, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
        adj.extend(rows)
    for path, fields, rows in ((args.out / "ratings.csv", RATING_FIELDS, ratings),
                               (args.out / "adjudication.csv", ADJ_FIELDS, adj)):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    print("G382_ADJUDICATE mode=%s frames=%d ratings=%d rows=%d"
          % (args.mode, len(identity), len(ratings), len(adj)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
