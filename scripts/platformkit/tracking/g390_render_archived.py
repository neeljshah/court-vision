"""Render the G390 fixed sample from archived reference and prediction CSVs."""
from __future__ import annotations

import csv
from pathlib import Path


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _require_file(path: Path, name: str) -> None:
    if not path.is_file():
        raise FileNotFoundError("archived-" + name + "-required " + str(path))


def _boxes(path: Path, arm: str) -> dict[str, dict[str, str]]:
    return {row["frame_key"]: row for row in _read_rows(path) if row["arm"] == arm}


def render_archived(
    scores_path: Path,
    reference_path: Path,
    sheets_path: Path,
    a0_predictions_path: Path,
    a8_predictions_path: Path,
    output_path: Path,
    count: int = 30,
) -> dict[str, int]:
    """Render even G390 cases, refusing absent archived prediction inputs."""
    from PIL import Image, ImageDraw

    _require_file(a0_predictions_path, "a0-predictions")
    _require_file(a8_predictions_path, "a8-predictions")
    _require_file(scores_path, "scores")
    _require_file(reference_path, "reference")
    a0 = _boxes(a0_predictions_path, "A0")
    a8 = _boxes(a8_predictions_path, "A8")
    if not a0_predictions_path.samefile(a8_predictions_path) and not a8:
        raise ValueError("archived-a8-predictions-empty")
    reference = {row["frame_key"]: row for row in _read_rows(reference_path)}
    cases = sorted(
        (row for row in _read_rows(scores_path) if row["arm"] == "A8"),
        key=lambda row: row["frame_key"],
    )
    if len(cases) < count:
        raise ValueError("insufficient-scored-cases")
    output_path.mkdir(parents=True, exist_ok=True)
    picked = [cases[round(i * (len(cases) - 1) / (count - 1))] for i in range(count)]
    index: list[dict[str, object]] = []
    for position, row in enumerate(picked):
        key = row["frame_key"]
        image = Image.open(sheets_path / (key[:12] + ".jpg")).convert("RGB")
        draw = ImageDraw.Draw(image)
        ref = reference[key]
        if ref["label"] == "VISIBLE" and ref["cx"]:
            cx, cy, diameter = float(ref["cx"]), float(ref["cy"]), max(float(ref["diameter"]), 24.0)
            draw.rectangle([cx - diameter, cy - diameter, cx + diameter, cy + diameter], outline=(0, 255, 0), width=4)
        for prediction, color in ((a0.get(key), (0, 180, 255)), (a8.get(key), (255, 0, 0))):
            if prediction:
                x, y = float(prediction["x"]), float(prediction["y"])
                half_w, half_h = float(prediction["w"]) / 2.0, float(prediction["h"]) / 2.0
                draw.rectangle([x - half_w, y - half_h, x + half_w, y + half_h], outline=color, width=4)
        case = "TP" if int(row["tp"]) else "FP" if int(row["fp"]) else "NO_DETECTION"
        if not int(row["tp"]) and ref["label"] == "VISIBLE":
            case += "/FN"
        draw.text((20, 20), "%s %s %s REF=GREEN A0=CYAN A8=RED" % (key[:12], ref["label"], case), fill=(255, 255, 0))
        name = "render_%02d_%s.jpg" % (position, key[:12])
        image.save(output_path / name, quality=70)
        index.append({"position": position, "frame_key": key, "label": ref["label"], "case": case,
                      "n_predictions": row.get("n_predictions", ""), "distance_720p": row.get("distance_720p", ""),
                      "a0_predictions": int(key in a0), "a8_predictions": int(key in a8), "render": name})
    with (output_path / "renders_index.csv").open("w", encoding="ascii", newline="\n") as handle:
        expected = ["position", "frame_key", "label", "case", "n_predictions", "distance_720p", "a0_predictions", "a8_predictions", "render"]
        assert list(index[0]) == expected, list(index[0])  # B2: parent fields retained beside the aliases
        writer = csv.DictWriter(handle, fieldnames=expected, lineterminator="\n")
        writer.writeheader()
        writer.writerows(index)
    return {"renders": len(index), "a0_rows": len(a0), "a8_rows": len(a8)}
