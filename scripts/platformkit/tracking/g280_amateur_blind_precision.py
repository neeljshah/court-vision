"""Prepare and summarize G280's sealed, blind retained-detection sample."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any

import cv2
import pandas as pd


SAMPLE_SIZE = 72
SAMPLE_SEED = 28020260904
BLIND_SEED = 28020904
CROP_WIDTH, CROP_HEIGHT = 512, 640
VERDICTS = ("PLAYER", "PERSON NOT PLAYER IN PLAY", "NOT A PERSON", "CANNOT JUDGE")


def canonical_hash(value: object) -> str:
    """Return a content commitment independent of JSON whitespace."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


def select_evenly(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sample one retained detector-box observation from each equal-width frame bin."""
    low, high = min(row["frame"] for row in rows), max(row["frame"] for row in rows)
    rng, selected = random.Random(SAMPLE_SEED), []
    for index in range(SAMPLE_SIZE):
        start = low + (high - low + 1) * index // SAMPLE_SIZE
        stop = low + (high - low + 1) * (index + 1) // SAMPLE_SIZE - 1
        eligible = [row for row in rows if start <= row["frame"] <= stop]
        if not eligible:
            raise RuntimeError("empty G280 frame bin %d" % (index + 1))
        selected.append({**rng.choice(eligible), "frame_bin": index + 1,
                         "frame_bin_inclusive": [start, stop]})
    return selected


def blind_order(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Shuffle independently of the uniform frame-bin sample."""
    indexes = list(range(len(rows)))
    random.Random(BLIND_SEED).shuffle(indexes)
    return [{**rows[source], "blind_index": index + 1} for index, source in enumerate(indexes)]


def crop(image, x: float, y: float):
    """Keep the footpoint centred at native source-pixel resolution, without a box."""
    left, top = round(x) - CROP_WIDTH // 2, round(y) - CROP_HEIGHT // 2
    padded = cv2.copyMakeBorder(image, CROP_HEIGHT, CROP_HEIGHT, CROP_WIDTH, CROP_WIDTH,
                                cv2.BORDER_CONSTANT)
    return padded[top + CROP_HEIGHT:top + 2 * CROP_HEIGHT,
                  left + CROP_WIDTH:left + 2 * CROP_WIDTH].copy()


def render(video: Path, ordered: list[dict[str, Any]], output: Path) -> None:
    """Render blind footpoint-centred crops only; neither boxes nor IDs are drawn."""
    renders = output / "blind_renders"
    renders.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError("could not open source video")
    for row in ordered:
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(row["frame"]))
        ok, image = capture.read()
        if not ok:
            raise RuntimeError("could not decode source frame %s" % row["frame"])
        path = renders / ("blind_%03d.jpg" % row["blind_index"])
        if not cv2.imwrite(str(path), crop(image, row["x"], row["y"]), [cv2.IMWRITE_JPEG_QUALITY, 88]):
            raise RuntimeError("could not write " + str(path))
    capture.release()


def prepare(input_csv: Path, video: Path, output: Path) -> dict[str, Any]:
    """Create the sealed blind packet; do not open its unblind map while labelling."""
    frame = pd.read_csv(input_csv)
    required = {"frame", "track_id", "cls", "x", "y"}
    if missing := required.difference(frame.columns):
        raise ValueError("missing fields: " + ",".join(sorted(missing)))
    detections = frame.loc[frame["cls"].eq("player"), list(required)].to_dict("records")
    if len(detections) < SAMPLE_SIZE:
        raise ValueError("fewer retained detector boxes than blind sample size")
    ordered = blind_order(select_evenly(detections))
    output.mkdir(parents=True, exist_ok=True)
    mapping = [{"blind_index": row["blind_index"], "frame": int(row["frame"]),
                "track_id": int(row["track_id"]), "frame_bin": row["frame_bin"],
                "frame_bin_inclusive": row["frame_bin_inclusive"], "x": float(row["x"]),
                "y": float(row["y"]), "render": "blind_renders/blind_%03d.jpg" % row["blind_index"]}
               for row in ordered]
    (output / "blind_order_commitment.json").write_text(json.dumps({
        "sample_size": SAMPLE_SIZE, "sample_seed": SAMPLE_SEED, "blind_seed": BLIND_SEED,
        "unblind_map_sha256": canonical_hash(mapping),
        "sampling": "one uniformly random retained detector-box observation from each equal-width source-frame bin; conditioned on nothing downstream",
        "crop_policy": "512x640 native-pixel crop centred on the retained footpoint; no detector box drawn or inferred",
    }, indent=2) + "\n", encoding="ascii")
    with (output / "blind_presentation_order.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle); writer.writerow(("blind_index", "render"))
        writer.writerows((row["blind_index"], "blind_renders/blind_%03d.jpg" % row["blind_index"])
                         for row in ordered)
    with (output / "blind_verdicts.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle); writer.writerow(("blind_index", "verdict"))
        writer.writerows((row["blind_index"], "") for row in ordered)
    render(video, ordered, output)
    (output / "unblind_map.json").write_text(json.dumps(mapping, indent=2) + "\n", encoding="ascii")
    return {"retained_detector_box_population": len(detections), "sample_size": SAMPLE_SIZE,
            "distinct_sample_frames": len({row["frame"] for row in ordered}),
            "distinct_track_ids": len({row["track_id"] for row in ordered})}


def two_proportion(sample_count: int, sample_n: int, baseline_count: int) -> dict[str, float]:
    """Return the requested pooled two-sided two-proportion test."""
    pooled = (sample_count + baseline_count) / (sample_n + 72)
    se = math.sqrt(pooled * (1.0 - pooled) * (1.0 / sample_n + 1.0 / 72))
    z = ((sample_count / sample_n) - (baseline_count / 72)) / se if se else 0.0
    return {"pooled_p": pooled, "se": se, "z": z, "nominal_two_sided_p": math.erfc(abs(z) / math.sqrt(2.0))}


def summarize(output: Path) -> dict[str, Any]:
    """Unblind only after committed blind order and verdicts are complete."""
    mapping = json.loads((output / "unblind_map.json").read_text(encoding="ascii"))
    commitment = json.loads((output / "blind_order_commitment.json").read_text(encoding="ascii"))
    if canonical_hash(mapping) != commitment["unblind_map_sha256"]:
        raise RuntimeError("unblind map does not match sealed commitment")
    with (output / "blind_verdicts.csv").open(newline="", encoding="ascii") as handle:
        verdicts = {int(row["blind_index"]): row["verdict"] for row in csv.DictReader(handle)}
    if set(verdicts) != {row["blind_index"] for row in mapping} or any(v not in VERDICTS for v in verdicts.values()):
        raise ValueError("blind verdicts must be complete and use G273's four unchanged categories")
    counts = {verdict: sum(value == verdict for value in verdicts.values()) for verdict in VERDICTS}
    n = len(mapping)
    result = {"sample_size": n, "counts": counts,
              "fractions": {key: value / n for key, value in counts.items()},
              "g273_two_proportion_tests": {
                  "PLAYER": two_proportion(counts["PLAYER"], n, 43),
                  "NOT A PERSON": two_proportion(counts["NOT A PERSON"], n, 15),
              }, "nominal_note": "two-sided nominal p values; no multiplicity correction"}
    (output / "blind_measurement_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "summarize"))
    parser.add_argument("--input", type=Path)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = (prepare(args.input, args.video, args.output) if args.action == "prepare" else
              summarize(args.output))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
