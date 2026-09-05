"""Validate and summarize G287's sealed footpoint-content re-judgment."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


CATEGORY_ORDER = ("A", "B", "C", "D", "E", "F", "G")
CATEGORY_LABELS = {
    "A": "PLAYER_FEET",
    "B": "PLAYER_BODY_NOT_FEET",
    "C": "BARE_COURT_OR_FLOOR",
    "D": "BROADCAST_GRAPHIC_OR_SCORE_TICKER",
    "E": "PERSON_NOT_PLAYER_IN_PLAY",
    "F": "SOMETHING_ELSE",
    "G": "CANNOT_JUDGE",
}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read a UTF-8 CSV as string-keyed dictionaries."""
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def jpeg_dimensions(path: Path) -> tuple[int, int]:
    """Read JPEG width and height without decoding or changing the input."""
    data = path.read_bytes()
    if data[:2] != b"\xff\xd8":
        raise ValueError(f"not a JPEG: {path}")
    position = 2
    while position + 9 <= len(data):
        if data[position] != 0xFF:
            position += 1
            continue
        while position < len(data) and data[position] == 0xFF:
            position += 1
        marker = data[position]
        position += 1
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        segment_length = int.from_bytes(data[position : position + 2], "big")
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            height = int.from_bytes(data[position + 3 : position + 5], "big")
            width = int.from_bytes(data[position + 5 : position + 7], "big")
            return width, height
        position += segment_length
    raise ValueError(f"JPEG dimensions not found: {path}")


def write_input_manifest(blind_render_dir: Path, output_path: Path) -> None:
    """Archive the exact 72 opened JPEG inputs and their native dimensions."""
    images = sorted(blind_render_dir.glob("blind_*.jpg"))
    if len(images) != 72:
        raise ValueError("G287 input manifest requires exactly 72 blind JPEGs")
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("input_path", "bytes", "width_px", "height_px", "sha256"))
        writer.writeheader()
        for image in images:
            width, height = jpeg_dimensions(image)
            writer.writerow(
                {
                    "input_path": str(image.resolve()),
                    "bytes": image.stat().st_size,
                    "width_px": width,
                    "height_px": height,
                    "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                }
            )


def validate_blinded_rows(
    order_rows: list[dict[str, str]], verdict_rows: list[dict[str, str]]
) -> None:
    """Raise ValueError unless the sealed G287 blind materials are complete."""
    if len(order_rows) != 72 or len(verdict_rows) != 72:
        raise ValueError("G287 requires exactly 72 order rows and 72 verdict rows")
    expected_orders = [str(index) for index in range(1, 73)]
    if [row["order"] for row in order_rows] != expected_orders:
        raise ValueError("order must be the complete sequence 1..72")
    if [row["order"] for row in verdict_rows] != expected_orders:
        raise ValueError("verdict order must be the complete sequence 1..72")
    order_names = [row["blind_filename"] for row in order_rows]
    verdict_names = [row["blind_filename"] for row in verdict_rows]
    if len(set(order_names)) != 72 or order_names != verdict_names:
        raise ValueError("blind filenames must be unique and agree between files")
    categories = [row["category"] for row in verdict_rows]
    if any(category not in CATEGORY_ORDER for category in categories):
        raise ValueError("verdict category is outside G287's seven-category schema")
    for row in verdict_rows:
        if row["category"] == "F" and not row["detail"].strip():
            raise ValueError("SOMETHING_ELSE requires free-text detail")
        if row["category"] != "F" and row["detail"].strip():
            raise ValueError("only SOMETHING_ELSE may carry free-text detail")


def g273_verdict_by_filename(rows: list[dict[str, str]]) -> dict[str, str]:
    """Normalize G273's committed CSV fields to filename -> coarse verdict."""
    result: dict[str, str] = {}
    for row in rows:
        filename = row.get("blind_filename") or row.get("blind_id")
        if not filename and row.get("blind_index"):
            filename = f"blind_{int(row['blind_index']):03d}.jpg"
        verdict = row.get("verdict") or row.get("category")
        if not filename or not verdict:
            raise ValueError("G273 verdict CSV needs a blind filename/id and verdict/category")
        result[filename] = verdict
    return result


def summarize(
    order_rows: list[dict[str, str]],
    verdict_rows: list[dict[str, str]],
    g273_rows: list[dict[str, str]],
) -> dict[str, Any]:
    """Return additive counts and the G273-by-G287 contingency table."""
    validate_blinded_rows(order_rows, verdict_rows)
    g273_by_name = g273_verdict_by_filename(g273_rows)
    if set(g273_by_name) != {row["blind_filename"] for row in verdict_rows}:
        raise ValueError("G273 verdict rows must join exactly to all 72 G287 rows")
    counts = Counter(row["category"] for row in verdict_rows)
    table: dict[str, dict[str, int]] = {}
    by_name = {row["blind_filename"]: row["category"] for row in verdict_rows}
    for coarse in ("PLAYER", "PERSON NOT PLAYER IN PLAY", "NOT A PERSON", "CANNOT JUDGE"):
        table[coarse] = {
            category: sum(
                g273_by_name[name] == coarse and by_name[name] == category
                for name in by_name
            )
            for category in CATEGORY_ORDER
        }
    return {
        "n_detector_box_observations": len(verdict_rows),
        "counts": {category: counts[category] for category in CATEGORY_ORDER},
        "fractions": {
            category: round(counts[category] / len(verdict_rows), 6)
            for category in CATEGORY_ORDER
        },
        "g273_by_g287": table,
    }


def main() -> None:
    """Run the post-unblind additive summary from sealed CSV inputs."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--order", type=Path, required=True)
    parser.add_argument("--verdicts", type=Path, required=True)
    parser.add_argument("--g273-verdicts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--blind-render-dir", type=Path)
    parser.add_argument("--input-manifest", type=Path)
    args = parser.parse_args()
    summary = summarize(
        read_csv_rows(args.order),
        read_csv_rows(args.verdicts),
        read_csv_rows(args.g273_verdicts),
    )
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if bool(args.blind_render_dir) != bool(args.input_manifest):
        parser.error("--blind-render-dir and --input-manifest must be supplied together")
    if args.blind_render_dir and args.input_manifest:
        write_input_manifest(args.blind_render_dir, args.input_manifest)
    print("G287 summary written")


if __name__ == "__main__":
    main()
