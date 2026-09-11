"""Export G382 oracle marking-only whole strokes while retaining planned empty frames."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def export(frame_rows: list[dict[str, str]], stroke_rows: list[dict[str, str]]) -> dict[str, object]:
    """Keep a whole stroke once, never split it by the physical marking ids it touches."""
    by_frame: dict[str, list[dict[str, object]]] = {row["frame_key"]: [] for row in frame_rows}
    for row in stroke_rows:
        if row["on_marking"] != "1":
            continue
        identifiers = [item for item in row["physical_marking_ids"].split(",") if item]
        by_frame.setdefault(row["frame_key"], []).append({"stroke_id": row["stroke_id"],
            "family": int(row["family"]), "length_px": float(row["length_px"]),
            "physical_marking_ids": identifiers})
    frames = [{"frame_key": row["frame_key"], "status": row["status"],
               "strokes": sorted(by_frame.get(row["frame_key"], []), key=lambda item: str(item["stroke_id"]))}
              for row in frame_rows]
    return {"oracle_diagnostic": "G383 only", "frames": frames}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path, required=True); parser.add_argument("--strokes", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True); args = parser.parse_args()
    with args.frames.open(encoding="utf-8", newline="") as handle: frames = list(csv.DictReader(handle))
    with args.strokes.open(encoding="utf-8", newline="") as handle: strokes = list(csv.DictReader(handle))
    args.out.write_text(json.dumps(export(frames, strokes), indent=2) + "\n", encoding="utf-8", newline="\n")
    print("G382_EXPORT frames=%d" % len(frames))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
