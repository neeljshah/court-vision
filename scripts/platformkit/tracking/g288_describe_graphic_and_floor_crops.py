"""Validate and summarize the G288 descriptive refinement of G287 C and D rows."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


REFINEMENTS = {
    "C": {"C1", "C2", "C3", "C4", "C5"},
    "D": {"D1", "D2", "D3", "D4"},
}


def read_rows(path: Path) -> list[dict[str, str]]:
    """Read a UTF-8 CSV into string-keyed rows."""
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def jpeg_dimensions(path: Path) -> tuple[int, int]:
    """Read JPEG dimensions without decoding or modifying the image."""
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
        length = int.from_bytes(data[position : position + 2], "big")
        if marker in {
            0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9,
            0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
        }:
            height = int.from_bytes(data[position + 3 : position + 5], "big")
            width = int.from_bytes(data[position + 5 : position + 7], "big")
            return width, height
        position += length
    raise ValueError(f"JPEG dimensions not found: {path}")


def selected_g287_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Return exactly G287's committed C and D rows, in presentation order."""
    selected = [row for row in rows if row["category"] in REFINEMENTS]
    if len(rows) != 72:
        raise ValueError("G288 requires G287's complete 72-row verdict CSV")
    counts = Counter(row["category"] for row in selected)
    if counts != Counter({"C": 17, "D": 13}):
        raise ValueError("G288 selection must be exactly 17 C rows and 13 D rows")
    if any(row["detail"].strip() for row in selected):
        raise ValueError("G288 requires the original selected G287 detail fields to be blank")
    return selected


def validate_refinement(
    g287_rows: list[dict[str, str]], refinement_rows: list[dict[str, str]]
) -> None:
    """Require one nonempty descriptive refinement for every selected G287 row."""
    selected = selected_g287_rows(g287_rows)
    expected = {
        (row["order"], row["blind_filename"], row["category"])
        for row in selected
    }
    actual = {
        (row["order"], row["blind_filename"], row["original_category"])
        for row in refinement_rows
    }
    if len(refinement_rows) != 30 or actual != expected:
        raise ValueError("refinement rows must join exactly to the 30 selected G287 rows")
    if len(actual) != len(refinement_rows):
        raise ValueError("refinement rows must be unique")
    for row in refinement_rows:
        category = row["original_category"]
        if row["refinement"] not in REFINEMENTS[category]:
            raise ValueError("refinement code is incompatible with its original G287 category")
        if not row["detail"].strip():
            raise ValueError("every G288 refinement row requires free-text detail")


def summarize(
    g287_rows: list[dict[str, str]], refinement_rows: list[dict[str, str]]
) -> dict[str, Any]:
    """Return additive selection and refinement counts from committed rows."""
    validate_refinement(g287_rows, refinement_rows)
    selected = selected_g287_rows(g287_rows)
    by_category = Counter(row["original_category"] for row in refinement_rows)
    by_refinement = Counter(row["refinement"] for row in refinement_rows)
    return {
        "n_selected_detector_box_observations": len(selected),
        "selected_g287_categories": dict(sorted(by_category.items())),
        "d_breakdown": {key: by_refinement[key] for key in sorted(REFINEMENTS["D"])},
        "c_breakdown": {key: by_refinement[key] for key in sorted(REFINEMENTS["C"])},
        "label_stability_observations": sum(
            bool((row.get("label_stability_observation") or "").strip())
            for row in refinement_rows
        ),
    }


def write_input_manifest(
    refinement_rows: list[dict[str, str]], render_dir: Path, output: Path
) -> None:
    """Write exact paths, bytes, dimensions, and hashes for the 30 viewed JPEGs."""
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("blind_filename", "input_path", "bytes", "width_px", "height_px", "sha256"),
        )
        writer.writeheader()
        for row in refinement_rows:
            path = render_dir / row["blind_filename"]
            width, height = jpeg_dimensions(path)
            writer.writerow(
                {
                    "blind_filename": path.name,
                    "input_path": str(path.resolve()),
                    "bytes": path.stat().st_size,
                    "width_px": width,
                    "height_px": height,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )


def main() -> None:
    """Validate G288 inputs and write its additive summary and input manifest."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--g287-verdicts", type=Path, required=True)
    parser.add_argument("--refinements", type=Path, required=True)
    parser.add_argument("--render-dir", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--input-manifest-output", type=Path, required=True)
    args = parser.parse_args()
    g287_rows = read_rows(args.g287_verdicts)
    refinement_rows = read_rows(args.refinements)
    summary = summarize(g287_rows, refinement_rows)
    args.summary_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_input_manifest(refinement_rows, args.render_dir, args.input_manifest_output)
    print("G288 summary and input manifest written")


if __name__ == "__main__":
    main()
