"""Capture one production-route detector stream for the G336 harness."""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

import cv2


class Capture(NamedTuple):
    """One route capture. `ms` is retained as the pre-amendment name for wall ms (B2)."""

    records: list
    rows: list
    assoc_ms: float
    wall_ms: float

    @property
    def ms(self) -> float:
        """Alias kept so no field this module ever published was removed."""
        return self.wall_ms


class RouteRefused(Exception):
    """scripts/run_clip.py's own gate refused this section; carries its exit code."""

    def __init__(self, code):
        super().__init__("run_clip refused this section with exit code %s" % code)
        self.code = code


def _signature(crop) -> list[float]:
    """Emit the HSV signature for one detector crop (always recorded)."""
    if crop is None or crop.size == 0:
        return [0.0, 0.0, 0.0]
    return [float(x) for x in cv2.mean(cv2.cvtColor(crop, cv2.COLOR_BGR2HSV))[:3]]


def _deep(det: dict) -> list[float] | None:
    """The route's own OSNet vector for this detection, when it attached one.

    The route attaches `deep_emb` only to detections its `moving_indices` filter
    selects (advanced_tracker.py:1507-1516), so coverage is recorded per section
    and the amendment prereg decides HSV-vs-OSNet from the measured coverage.
    """
    emb = det.get("deep_emb")
    return None if emb is None else [round(float(x), 6) for x in emb]


def capture_section(section: str, video: str, source_height: int, start: int, cap: int,
                    output: Path, raw_path: Path, bypass_preflight: bool = False) -> Capture:
    """Run the unmodified production route once and write its observed detector stream.

    The route's own production preflight is NEVER neutralised: a section it refuses
    raises `RouteRefused` and is recorded as refused, never scored. `bypass_preflight`
    is kept only so a caller built against the pre-fix-1b signature fails loudly
    instead of with a stale TypeError; passing True is always rejected (B2).
    """
    if bypass_preflight:
        raise ValueError(
            "bypass_preflight is void since fix 1b; the production preflight is never bypassed")
    from src.tracking.advanced_tracker import AdvancedFeetDetector
    original_match = AdvancedFeetDetector._match_team_bytetrack
    original_get = AdvancedFeetDetector.get_players_pos
    records: list[dict] = []

    def wrapped_get(self, M, M1, frame, timestamp, map_2d, *args, **kwargs):
        self._g336_frame = int(timestamp)
        return original_get(self, M, M1, frame, timestamp, map_2d, *args, **kwargs)

    assoc = [0.0]  # baseline association-only milliseconds, summed over every team call

    def wrapped_match(self, team, detections):
        tick = time.perf_counter()
        matched, slots, unmatched = original_match(self, team, detections)
        assoc[0] += (time.perf_counter() - tick) * 1000.0
        by_det = {index: slot for slot, index in matched}
        frame = int(getattr(self, "_g336_frame", -1))
        for index, det in enumerate(detections):
            if det.get("team") != team:
                continue
            y1, x1, y2, x2 = det["bbox"]
            records.append({"section": section, "frame": frame, "team": team,
                            "score": float(det.get("score", 1.0)),
                            "bbox": [float(x1), float(y1), float(x2), float(y2)],
                            "sig": _signature(det.get("crop_bgr")), "deep": _deep(det),
                            "baseline_slot": by_det.get(index)})
        return matched, slots, unmatched

    AdvancedFeetDetector.get_players_pos = wrapped_get
    AdvancedFeetDetector._match_team_bytetrack = wrapped_match
    argv = ["scripts/run_clip.py", "--video", video, "--start-frame", str(start),
            "--frames", str(cap), "--no-show", "--skip-features", "--data-dir", str(output)]
    before = time.perf_counter()
    old_argv = sys.argv
    from scripts import run_clip
    try:
        sys.argv = argv
        try:
            run_clip.main()
        except SystemExit as exc:
            raise RouteRefused(exc.code) from None
    finally:
        sys.argv = old_argv
        AdvancedFeetDetector.get_players_pos = original_get
        AdvancedFeetDetector._match_team_bytetrack = original_match
    elapsed = (time.perf_counter() - before) * 1000.0
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    with (output / "tracking_data.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return Capture(records, rows, assoc[0], elapsed)


def read_raw(path: Path) -> list[dict]:
    """Read one G336 detector stream emitted by the production-route wrapper."""
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def baseline_from_raw(raw: list[dict], source_height: int) -> list[dict]:
    """Convert matched detector observations to G310-compatible production slot rows."""
    from scripts.platformkit.tracking.g336_track_id_continuity import baseline_instances
    by_section: dict[str, list[dict]] = defaultdict(list)
    sigs: dict[tuple[str, int, int], list[float]] = {}
    for row in raw:
        slot = row.get("baseline_slot")
        if slot is None:
            continue
        x1, y1, x2, y2 = row["bbox"]
        converted = {"frame": row["frame"], "player_id": slot, "team": row["team"],
                     "bbox_x1": x1, "bbox_y1": y1, "bbox_x2": x2, "bbox_y2": y2}
        by_section[row["section"]].append(converted)
        sigs[(row["section"], int(row["frame"]), int(slot))] = row["sig"]
    out: list[dict] = []
    for section, rows in by_section.items():
        for row in baseline_instances(rows, source_height, section):
            slot = int(next(item["player_id"] for item in rows if int(item["frame"]) == row["frame"]
                            and item["team"] == row["team"] and item["bbox_x1"] == row["bbox"][0]))
            row["sig"] = sigs.get((section, row["frame"], slot), [0.0, 0.0, 0.0])
            out.append(row)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="G336 production-route detector recorder")
    ap.add_argument("--section", required=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--height", required=True, type=int)
    ap.add_argument("--start", default=90, type=int)
    ap.add_argument("--cap", default=540, type=int)
    ap.add_argument("--output", required=True)
    ap.add_argument("--raw", required=True)
    args = ap.parse_args()
    got = capture_section(args.section, args.video, args.height, args.start, args.cap,
                          Path(args.output), Path(args.raw))
    # `ms=` is the pre-amendment field name, kept as an alias of wall_ms (B2).
    print("G336_CAPTURE section=%s raw=%d rows=%d assoc_ms=%.3f wall_ms=%.3f ms=%.3f" %
          (args.section, len(got.records), len(got.rows), got.assoc_ms, got.wall_ms, got.ms))


if __name__ == "__main__":
    main()
