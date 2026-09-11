"""G394 eye check: 30 evenly spaced paired native renders over the whole 549 set.

Sampling runs over every scored held-out key, not over the detections, so frames
with no detection at all are drawn in their own right. Reference is green, the
archived A0 route cyan, archived A8 red and the candidate A10 magenta.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "/workspace/wt/a7")

from scripts.platformkit.tracking.g394_finish import EVIDENCE  # noqa: E402
from scripts.platformkit.tracking.g394_run import G389, rows, sheet, write_csv  # noqa: E402

INDEX_FIELDS = ("position", "frame_key", "game", "label", "a0_case", "a8_case", "a10_case",
                "a0_predictions", "a8_predictions", "a10_predictions",
                "a10_distance_720p", "render")
COLOURS = {"A0": (0, 180, 255), "A8": (255, 0, 0), "A10": (255, 0, 255)}


def case(row: dict[str, str] | None, label: str) -> str:
    """Name one arm's outcome on one frame, keeping no-detection explicit."""
    if row is None:
        return "NO_SCORE"
    if int(row["tp"]):
        return "TP"
    if int(row["n_predictions"]) == 0:
        return "NO_DETECTION/FN" if label == "VISIBLE" else "NO_DETECTION"
    return "FP/FN" if label == "VISIBLE" else "FP"


def main(count: int = 30) -> None:
    """Draw the fixed even sample and write its index."""
    from PIL import Image, ImageDraw

    scores: dict[str, dict[str, dict[str, str]]] = {}
    for row in rows(EVIDENCE / "paired_frame_scores.csv"):
        scores.setdefault(row["frame_key"], {})[row["arm"]] = row
    preds: dict[str, dict[str, dict[str, str]]] = {}
    for row in rows(EVIDENCE / "predictions.csv"):
        preds.setdefault(row["frame_key"], {})[row["arm"]] = row
    reference = {row["frame_key"]: row for row in rows(G389 / "reference_v3.csv")}
    keys = sorted(scores)
    picked = [keys[round(i * (len(keys) - 1) / (count - 1))] for i in range(count)]
    out = EVIDENCE / "renders"
    out.mkdir(parents=True, exist_ok=True)
    index = []
    for position, key in enumerate(picked):
        image = Image.open(sheet(key)).convert("RGB")
        draw = ImageDraw.Draw(image)
        ref = reference[key]
        if ref["label"] == "VISIBLE" and ref["cx"]:
            cx, cy = float(ref["cx"]), float(ref["cy"])
            radius = max(float(ref["diameter"] or 24.0), 24.0)
            draw.rectangle([cx - radius, cy - radius, cx + radius, cy + radius],
                           outline=(0, 255, 0), width=4)
        for arm, colour in COLOURS.items():
            prediction = preds.get(key, {}).get(arm)
            if not prediction:
                continue
            x, y = float(prediction["x"]), float(prediction["y"])
            half_w, half_h = float(prediction["w"]) / 2.0, float(prediction["h"]) / 2.0
            draw.rectangle([x - half_w, y - half_h, x + half_w, y + half_h],
                           outline=colour, width=4)
        arms = scores[key]
        draw.text((20, 20), "%s %s A0=%s A8=%s A10=%s REF=GREEN A0=CYAN A8=RED A10=MAGENTA"
                  % (key[:12], ref["label"], case(arms.get("A0"), ref["label"]),
                     case(arms.get("A8"), ref["label"]), case(arms.get("A10"), ref["label"])),
                  fill=(255, 255, 0))
        name = "render_%02d_%s.jpg" % (position, key[:12])
        image.save(out / name, quality=70)
        index.append({
            "position": position, "frame_key": key,
            "game": arms["A10"]["game"], "label": ref["label"],
            "a0_case": case(arms.get("A0"), ref["label"]),
            "a8_case": case(arms.get("A8"), ref["label"]),
            "a10_case": case(arms.get("A10"), ref["label"]),
            "a0_predictions": arms["A0"]["n_predictions"],
            "a8_predictions": arms["A8"]["n_predictions"],
            "a10_predictions": arms["A10"]["n_predictions"],
            "a10_distance_720p": arms["A10"]["distance_720p"], "render": name})
    write_csv(out / "renders_index.csv", INDEX_FIELDS, index)
    tally: dict[str, int] = {}
    for row in index:
        tally[row["a10_case"]] = tally.get(row["a10_case"], 0) + 1
    print("G394 RENDERS COMPLETE n=%d a10_cases=%s" % (len(index), sorted(tally.items())),
          flush=True)


if __name__ == "__main__":
    sys.exit(main())
