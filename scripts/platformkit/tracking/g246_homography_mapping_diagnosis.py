"""Enumerate G246's fixed-label court correspondences without tuning them."""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking.g243b_amateur_seed_gate import court_lines


SEED_FRAME = 2760
IMAGE_SIZE = (1280, 720)
LABEL_SETS = {
    "clustered": {
        "claims": (
            "paint_near_baseline_left_corner",
            "paint_near_baseline_right_corner",
            "paint_near_free_throw_left_corner",
            "paint_near_free_throw_right_corner",
        ),
        "labels_px": ((45, 385), (283, 276), (363, 424), (624, 306)),
        "court_points_ft": ((19, 0), (31, 0), (19, 19), (31, 19)),
    },
    "spread": {
        "claims": (
            "paint_near_free_throw_left_corner",
            "paint_near_free_throw_right_corner",
            "centre_circle_top",
            "centre_circle_bottom",
        ),
        "labels_px": ((363, 424), (624, 306), (1140, 359), (1160, 468)),
        "court_points_ft": ((19, 19), (31, 19), (25, 36), (25, 48)),
    },
}
CROP_HALF_SIZE = 80


def enumerated_mappings() -> tuple[tuple[int, int, int, int], ...]:
    """Return all one-to-one assignments of four fixed court points."""
    return tuple(itertools.permutations(range(4)))


def render_overlay(image: np.ndarray, labels: np.ndarray, court: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Project the unchanged high-school court model through one correspondence."""
    homography = cv2.getPerspectiveTransform(labels, court)
    inverse = np.linalg.inv(homography)
    rendered = image.copy()
    for line in court_lines():
        projected = cv2.perspectiveTransform(line.reshape(1, -1, 2), inverse)[0]
        if np.isfinite(projected).all() and np.abs(projected).max() < 1_000_000:
            cv2.polylines(rendered, [np.round(projected).astype(np.int32)], False, (0, 255, 255), 2, cv2.LINE_AA)
    for index, point in enumerate(labels, start=1):
        xy = tuple(np.round(point).astype(int))
        cv2.circle(rendered, xy, 7, (0, 0, 255), -1, cv2.LINE_AA)
        cv2.putText(rendered, str(index), (xy[0] + 9, xy[1] - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
    return rendered, homography


def labelled_crop(image: np.ndarray, point: tuple[int, int], text: str) -> np.ndarray:
    """Return a fixed-size pixel crop with its labelled location marked."""
    x, y = point
    height, width = image.shape[:2]
    left, top = max(0, x - CROP_HALF_SIZE), max(0, y - CROP_HALF_SIZE)
    right, bottom = min(width, x + CROP_HALF_SIZE), min(height, y + CROP_HALF_SIZE)
    crop = image[top:bottom, left:right].copy()
    cv2.drawMarker(crop, (x - left, y - top), (0, 0, 255), cv2.MARKER_CROSS, 16, 1, cv2.LINE_AA)
    cv2.putText(crop, text, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 255), 1, cv2.LINE_AA)
    return crop


def build(seed_image: Path, output_dir: Path) -> dict[str, object]:
    """Write eight labelled crops and all 48 exact-correspondence overlays."""
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite {output_dir}")
    image = cv2.imread(str(seed_image), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(seed_image)
    if (image.shape[1], image.shape[0]) != IMAGE_SIZE:
        raise ValueError(f"expected {IMAGE_SIZE}, got {(image.shape[1], image.shape[0])}")
    crops_dir = output_dir / "identity_crops"
    renders_dir = output_dir / "enumerated_renders"
    crops_dir.mkdir(parents=True)
    renders_dir.mkdir()
    report: dict[str, object] = {
        "seed_frame": SEED_FRAME,
        "seed_image": str(seed_image),
        "image_size_px": list(IMAGE_SIZE),
        "model": {"width_ft": 50, "length_ft": 84, "lane_ft": 12, "arc_ft": 19.75},
        "sets": {},
    }
    mappings = enumerated_mappings()
    for set_name, data in LABEL_SETS.items():
        labels = np.float32(data["labels_px"])
        court = np.float32(data["court_points_ft"])
        crop_records = []
        for index, (claim, point) in enumerate(zip(data["claims"], data["labels_px"]), start=1):
            crop_name = f"{set_name}_{index:02d}.jpg"
            if not cv2.imwrite(str(crops_dir / crop_name), labelled_crop(image, point, str(index))):
                raise OSError(f"could not write {crop_name}")
            crop_records.append({"index": index, "claimed_role": claim, "pixel_xy": list(point), "crop": f"identity_crops/{crop_name}"})
        variant_records = []
        for index, mapping in enumerate(mappings):
            mapped_court = court[list(mapping)]
            rendered, homography = render_overlay(image, labels, mapped_court)
            render_name = f"{set_name}_{index:02d}_court_indices_{''.join(map(str, mapping))}.jpg"
            if not cv2.imwrite(str(renders_dir / render_name), rendered):
                raise OSError(f"could not write {render_name}")
            variant_records.append({
                "variant_index": index,
                "court_index_for_label_index": list(mapping),
                "court_points_ft_for_label_order": mapped_court.astype(float).tolist(),
                "render": f"enumerated_renders/{render_name}",
                "homography_image_to_court": homography.astype(float).tolist(),
            })
        report["sets"][set_name] = {"crops": crop_records, "variants": variant_records}
    (output_dir / "enumeration_manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    return report


def write_contact_sheets(output_dir: Path) -> tuple[Path, Path]:
    """Make two review sheets while retaining every full-resolution render."""
    output_paths = []
    for set_name in LABEL_SETS:
        output_path = output_dir / f"{set_name}_contact_sheet.jpg"
        if output_path.exists():
            raise FileExistsError(f"refusing to overwrite {output_path}")
        render_paths = sorted((output_dir / "enumerated_renders").glob(f"{set_name}_*.jpg"))
        if len(render_paths) != 24:
            raise ValueError(f"expected 24 {set_name} renders, got {len(render_paths)}")
        tiles = []
        for index, path in enumerate(render_paths):
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None:
                raise FileNotFoundError(path)
            tile = cv2.resize(image, (320, 180), interpolation=cv2.INTER_AREA)
            cv2.putText(tile, str(index), (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA)
            tiles.append(tile)
        rows = [np.hstack(tiles[offset:offset + 6]) for offset in range(0, 24, 6)]
        if not cv2.imwrite(str(output_path), np.vstack(rows)):
            raise OSError(f"could not write {output_path}")
        output_paths.append(output_path)
    return tuple(output_paths)  # type: ignore[return-value]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--contact-sheets", action="store_true")
    args = parser.parse_args()
    if args.contact_sheets:
        contact_sheets = write_contact_sheets(args.output_dir)
        print("G246_CONTACT_SHEETS=" + str(len(contact_sheets)))
    else:
        report = build(args.seed_image, args.output_dir)
        variants = sum(len(value["variants"]) for value in report["sets"].values())
        crops = sum(len(value["crops"]) for value in report["sets"].values())
        print("G246_CROPS=" + str(crops))
        print("G246_VARIANTS=" + str(variants))


if __name__ == "__main__":
    main()
