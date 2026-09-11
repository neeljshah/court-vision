"""G378 sealed controls: the mirror flip and the masked-evidence abstention.

Both subsets are drawn EVENLY over a frame-key-sorted set, never from its head (contract A3, B7).
Both re-read the same archived frame cache through the same sealed cue as the scored run.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import cv2

from scripts.platformkit.tracking.g378_cue import call, masked, mirrored
from scripts.platformkit.tracking.g378_sheets import _even, _rows

CONTROL_TARGET = 30
OPPOSITE = {"LEFT": "RIGHT", "RIGHT": "LEFT"}
CONTROL_COLUMNS = ("control,frame_key,base_call,control_call,expected,pass").split(",")


def _cache_lookup(frames: Path) -> dict:
    return {row["frame_key"]: row["cache"] for row in _rows(frames)}


def run(frames: Path, cue_csv: Path, cache: Path, out: Path, summary: Path) -> int:
    """Mirror over the resolved calls, mask over all decoded frames; expected 30 of 30 each."""
    lookup = _cache_lookup(frames)
    cue_rows = sorted(_rows(cue_csv), key=lambda row: row["frame_key"])
    resolved = [row for row in cue_rows if row["call"] in OPPOSITE]
    rows = []
    for row in _even(resolved, CONTROL_TARGET):
        frame = cv2.imread(str(cache / lookup[row["frame_key"]]), cv2.IMREAD_COLOR)
        result = call(mirrored(frame))
        rows.append({"control": "mirror", "frame_key": row["frame_key"], "base_call": row["call"],
                     "control_call": result["call"], "expected": OPPOSITE[row["call"]],
                     "pass": int(result["call"] == OPPOSITE[row["call"]])})
    for row in _even(cue_rows, CONTROL_TARGET):
        frame = cv2.imread(str(cache / lookup[row["frame_key"]]), cv2.IMREAD_COLOR)
        result = call(masked(frame))
        rows.append({"control": "masked", "frame_key": row["frame_key"], "base_call": row["call"],
                     "control_call": result["call"], "expected": "UNKNOWN",
                     "pass": int(result["call"] == "UNKNOWN")})
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=CONTROL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    report = {}
    for name in ("mirror", "masked"):
        subset = [row for row in rows if row["control"] == name]
        report[name] = {"n": len(subset), "n_pass": sum(row["pass"] for row in subset),
                        "target": CONTROL_TARGET,
                        "meets": len(subset) == CONTROL_TARGET
                        and sum(row["pass"] for row in subset) == CONTROL_TARGET}
    payload = json.loads(summary.read_text(encoding="ascii")) if summary.exists() else {"row": "G378"}
    payload["controls"] = report
    summary.write_text(json.dumps(payload, indent=1) + "\n", encoding="ascii")
    print("CONTROLS mirror=%d/%d masked=%d/%d"
          % (report["mirror"]["n_pass"], report["mirror"]["n"],
             report["masked"]["n_pass"], report["masked"]["n"]))
    return 0


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("frames", "cue", "cache", "out", "summary"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv[1:])
    return run(Path(args.frames), Path(args.cue), Path(args.cache), Path(args.out),
               Path(args.summary))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
