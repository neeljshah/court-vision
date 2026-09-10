"""Build the G374 eye-check contact sheets: 30 evenly spaced frames, every ABSTAIN."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import cv2

from scripts.platformkit.tracking.g364_sheets import sheet_name


PER_PAGE = 10


def _read(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def select(validation: list[dict[str, str]], total: int = 30) -> list[dict[str, str]]:
    """Take every ABSTAIN row plus evenly spaced strict-interior scored rows (A3/B7)."""
    ordered = sorted(validation, key=lambda row: row["frame_key"])
    abstain = [row for row in ordered if row["prediction"] == "ABSTAIN"]
    scored = [row for row in ordered if row["prediction"] != "ABSTAIN"]
    remaining = total - len(abstain)
    if remaining < 1 or remaining > len(scored):
        raise ValueError("eye check cannot place the abstaining rows inside the total")
    step = len(scored) / remaining
    picked = [scored[min(len(scored) - 1, int((index + 0.5) * step))] for index in range(remaining)]
    chosen = {row["frame_key"]: row for row in abstain + picked}
    return sorted(chosen.values(), key=lambda row: row["frame_key"])


def annotate(image, row: dict[str, str], reference: str, terra: str, sol: str):
    """Stamp the prediction, probability and both blind ratings under the sheet."""
    panel = cv2.copyMakeBorder(image, 0, 46, 0, 0, cv2.BORDER_CONSTANT, value=(18, 18, 18))
    base = panel.shape[0] - 46
    cv2.putText(panel, "pred %s p=%s" % (row["prediction"], row["court_probability"][:8]),
                (8, base + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (245, 245, 245), 1, cv2.LINE_AA)
    cv2.putText(panel, "terra %s | sol %s | ref %s" % (terra, sol, reference),
                (8, base + 38), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (245, 245, 245), 1, cv2.LINE_AA)
    return panel


def build(validation: Path, ratings: Path, reference: Path, sheets: Path, output: Path) -> int:
    """Write the annotated contact sheets and return how many frames they carry."""
    rows = select(_read(validation))
    resolved = {row["frame_key"]: row["reference_label"] for row in _read(reference)}
    blind: dict[str, dict[str, str]] = {}
    for record in _read(ratings):
        blind.setdefault(record["frame_key"], {})[record["rater"]] = record["label"]
    output.mkdir(parents=True, exist_ok=True)
    panels = []
    for row in rows:
        image = cv2.imread(str(sheets / (sheet_name(row["frame_key"]) + ".jpg")))
        if image is None:
            raise ValueError("missing eye-check sheet: " + row["frame_key"])
        pair = blind.get(row["frame_key"], {})
        panels.append(annotate(image, row, resolved.get(row["frame_key"], ""),
                               pair.get("terra", ""), pair.get("sol", "")))
    for page in range(0, len(panels), PER_PAGE):
        block = panels[page:page + PER_PAGE]
        columns = [cv2.vconcat(block[index::2]) for index in (0, 1) if block[index::2]]
        height = min(column.shape[0] for column in columns)
        canvas = cv2.hconcat([column[:height] for column in columns])
        cv2.imwrite(str(output / ("eye_check_%02d.jpg" % (page // PER_PAGE + 1))), canvas,
                    [int(cv2.IMWRITE_JPEG_QUALITY), 72])
    with (output / "eye_check.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("frame_key", "prediction", "court_probability",
                                                    "terra", "sol", "reference_label"),
                                lineterminator="\n")
        writer.writeheader()
        for row in rows:
            pair = blind.get(row["frame_key"], {})
            writer.writerow({"frame_key": row["frame_key"], "prediction": row["prediction"],
                             "court_probability": row["court_probability"],
                             "terra": pair.get("terra", ""), "sol": pair.get("sol", ""),
                             "reference_label": resolved.get(row["frame_key"], "")})
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="G374 eye-check contact sheets")
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--ratings", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--sheets", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print("eye_check_frames=%d" % build(args.validation, args.ratings, args.reference,
                                        args.sheets, args.out))


if __name__ == "__main__":
    main()
