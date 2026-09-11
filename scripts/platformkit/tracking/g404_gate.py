"""G404 frozen play-gate evaluation over the sealed two-second candidate grid.

Decodes the actual frame PTS schedule of every retained median section, freezes the
candidate grid and its exclusions, then labels each candidate with EXACTLY the
frozen G375/G364 cosine nearest reference class. Nothing is fitted, no cutoff or
smoothing is introduced and no ball detector or visibility cue is consulted.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking.g375_diag import backbone, embed, nearest
from scripts.platformkit.tracking.g375_sheets import (QUALITIES, SHEET_MAX_BYTES,
                                                      SHEET_WIDTH)

STEP_S = 2.0
PTS_FIELDS = ("video_id", "frame_index", "pts")
GRID_FIELDS = ("frame_key", "video_id", "canonical_game", "competition", "target_s",
               "pts", "frame_index", "pixel_sha256", "width", "height", "status")
GATE_FIELDS = GRID_FIELDS + ("nearest_class", "cosine_distance", "gate_admitted")


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    with path.open("w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: str(row.get(field, "")).encode(
                "ascii", "replace").decode("ascii") for field in fields})


def decoded_pts(container: Path) -> list[tuple[int, float]]:
    """The ACTUAL decoded frame schedule, never a packet count."""
    command = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "frame=best_effort_timestamp_time", "-of", "csv=p=0", str(container)]
    raw = subprocess.run(command, capture_output=True, text=True, check=True)
    schedule = []
    for index, line in enumerate(raw.stdout.splitlines()):
        value = line.strip().rstrip(",")
        if value and value != "N/A":
            schedule.append((index, float(value)))
    return schedule


def grid_targets(schedule: list[tuple[int, float]]) -> list[tuple[float, int, float]]:
    """Every two seconds strictly inside the span, nearest decoded PTS, earlier tie."""
    start, end = schedule[0][1], schedule[-1][1]
    picks: list[tuple[float, int, float]] = []
    seen: set[int] = set()
    step = 1
    while start + STEP_S * step < end:
        target = start + STEP_S * step
        step += 1
        best = min(schedule, key=lambda item: (abs(item[1] - target), item[1]))
        if best[0] in seen:
            continue
        seen.add(best[0])
        picks.append((target, best[0], best[1]))
    return picks


def decode_frames(container: Path, indices: list[int]) -> dict[int, "np.ndarray"]:
    """Decode each candidate index once, by the same seek the landed sheet rule uses."""
    frames: dict[int, np.ndarray] = {}
    capture = cv2.VideoCapture(str(container))
    try:
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if ok and frame is not None:
                frames[index] = frame
    finally:
        capture.release()
    return frames


def write_sheet(frame: "np.ndarray", sheet: Path) -> int:
    """The landed G375 sheet rule, applied to an already decoded frame."""
    height, width = frame.shape[:2]
    if width > SHEET_WIDTH:
        scale = SHEET_WIDTH / float(width)
        frame = cv2.resize(frame, (SHEET_WIDTH, max(1, int(round(height * scale)))),
                           interpolation=cv2.INTER_AREA)
    sheet.parent.mkdir(parents=True, exist_ok=True)
    for quality in QUALITIES:
        cv2.imwrite(str(sheet), frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if sheet.stat().st_size <= SHEET_MAX_BYTES:
            return sheet.stat().st_size
    raise ValueError("sheet exceeds the sealed size cap")


def run(args) -> int:
    out = Path(args.out_dir)
    (out / "gate_sheets").mkdir(parents=True, exist_ok=True)
    cv2.setNumThreads(1)
    census = [row for row in read_csv(Path(args.census))
              if row["eligibility"] == "ELIGIBLE"]
    archive = np.load(args.reference_npz)
    labels = {row["frame_key"]: row["label"] for row in read_csv(Path(args.reference_labels))}
    keys = [str(key) for key in archive["keys"]]
    reference = np.asarray(archive["embeddings"], dtype=np.float32)
    reference_labels = [labels[key] for key in keys]
    model = backbone(Path(args.weights))
    schedule_rows: list[dict] = []
    grid_rows: list[dict] = []
    for row in sorted(census, key=lambda item: (item["competition"], item["canonical_game"])):
        container = Path(row["median_section_path"])
        schedule = decoded_pts(container)
        schedule_rows.extend({"video_id": row["video_id"], "frame_index": index,
                              "pts": "%.6f" % pts} for index, pts in schedule)
        picks = grid_targets(schedule)
        frames = decode_frames(container, [index for _, index, _ in picks])
        for target, index, pts in picks:
            frame = frames.get(index)
            key = hashlib.sha256(("%s|%d" % (row["video_id"], index)).encode("ascii")).hexdigest()
            if frame is None:
                grid_rows.append({"frame_key": key, "video_id": row["video_id"],
                                  "canonical_game": row["canonical_game"],
                                  "competition": row["competition"],
                                  "target_s": "%.3f" % target, "pts": "%.6f" % pts,
                                  "frame_index": index, "pixel_sha256": "",
                                  "width": 0, "height": 0, "status": "UNDECODABLE"})
                continue
            write_sheet(frame, out / "gate_sheets" / (key + ".jpg"))
            grid_rows.append({"frame_key": key, "video_id": row["video_id"],
                              "canonical_game": row["canonical_game"],
                              "competition": row["competition"],
                              "target_s": "%.3f" % target, "pts": "%.6f" % pts,
                              "frame_index": index,
                              "pixel_sha256": hashlib.sha256(frame.tobytes()).hexdigest(),
                              "width": frame.shape[1], "height": frame.shape[0],
                              "status": "DECODED"})
        print("GRID", row["video_id"], len(picks), flush=True)
    write_csv(out / "decoded_pts.csv", PTS_FIELDS, schedule_rows)
    seen: dict[str, str] = {}
    for item in grid_rows:
        if item["status"] != "DECODED":
            continue
        if item["pixel_sha256"] in seen:
            item["status"] = "DUPLICATE_PIXELS_OF_" + seen[item["pixel_sha256"]]
        else:
            seen[item["pixel_sha256"]] = item["frame_key"]
    write_csv(out / "candidate_grid.csv", GRID_FIELDS, grid_rows)
    usable = [item for item in grid_rows if item["status"] == "DECODED"]
    sheets = [out / "gate_sheets" / (item["frame_key"] + ".jpg") for item in usable]
    picks = nearest(embed(model, sheets), reference, reference_labels)
    gate_rows = []
    for item, (label, distance) in zip(usable, picks):
        gate_rows.append({**item, "nearest_class": label,
                          "cosine_distance": "%.6f" % distance,
                          "gate_admitted": "1" if label == "USABLE_COURT" else "0"})
    for item in grid_rows:
        if item["status"] != "DECODED":
            gate_rows.append({**item, "nearest_class": "", "cosine_distance": "",
                              "gate_admitted": ""})
    gate_rows.sort(key=lambda item: (item["canonical_game"], float(item["pts"]),
                                     item["frame_key"]))
    write_csv(out / "gate_outputs.csv", GATE_FIELDS, gate_rows)
    summary = {"games": len({item["video_id"] for item in grid_rows}),
               "grid_rows": len(grid_rows), "decoded": len(usable),
               "admitted": sum(1 for item in gate_rows if item["gate_admitted"] == "1"),
               "excluded": sum(1 for item in gate_rows if item["gate_admitted"] == "0"),
               "reference_frames": len(keys),
               "weights_sha256": args.weights_sha256,
               "opencv": cv2.__version__}
    (out / "gate_summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True)
                                           + "\n", encoding="ascii")
    print(json.dumps(summary, sort_keys=True))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g404_gate")
    for flag in ("--census", "--reference-npz", "--reference-labels", "--weights",
                 "--weights-sha256", "--out-dir"):
        parser.add_argument(flag, required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
