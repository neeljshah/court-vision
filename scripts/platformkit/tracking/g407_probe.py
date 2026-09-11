"""G407 native probe, sealed two-second interval and window-bounded re-extraction.

Measures width, height, codec and the presentation-timestamp list of each retained source
with ffprobe, seals one centered two-second native-PTS interval per section using the sealed
`centered_interval` rule, then re-extracts the producer's own coordinate rows bounded to that
interval. Reads only; sources and producer tables are never modified.
"""
from __future__ import annotations

import argparse
import bisect
import json
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g401_timebase import (
    LEGACY_FRAME_CAP, TARGET_DURATION_SECONDS, cap_loss, capped_pts_receipt,
    pts_are_constant_rate,
)
from scripts.platformkit.tracking.g407_accounting import held_pairs
from scripts.platformkit.tracking.g407_census import _coordinate_rows
from scripts.platformkit.tracking.g407_population import centered_interval

STREAM_FIELDS = "width,height,codec_name,avg_frame_rate,r_frame_rate,nb_frames,duration"


def _run(command: list[str]) -> tuple[str, int]:
    done = subprocess.run(command, capture_output=True, text=True)
    return done.stdout, done.returncode


def rational(text: str) -> float | None:
    """Return an exact rational frame rate as a float, never a decoded-count estimate."""
    try:
        value = Fraction(str(text).strip())
    except (ValueError, ZeroDivisionError):
        return None
    return float(value) if value > 0 else None


def probe_source(path: Path, ffprobe: str = "ffprobe") -> dict[str, Any]:
    """Measured stream facts plus the full sorted presentation-timestamp list."""
    out: dict[str, Any] = {"probe_status": "OK", "source_path": str(path)}
    text, code = _run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                       "stream=" + STREAM_FIELDS, "-of", "json", str(path)])
    if code != 0:
        return {"probe_status": "FFPROBE_STREAM_FAILED", "source_path": str(path),
                "returncode": code}
    try:
        stream = (json.loads(text).get("streams") or [{}])[0]
    except (ValueError, IndexError):
        return {"probe_status": "FFPROBE_STREAM_UNPARSED", "source_path": str(path)}
    out.update({"measured_width": stream.get("width"), "measured_height": stream.get("height"),
                "codec_name": stream.get("codec_name"),
                "avg_frame_rate_rational": stream.get("avg_frame_rate"),
                "r_frame_rate_rational": stream.get("r_frame_rate"),
                "container_nb_frames": stream.get("nb_frames"),
                "container_duration_s": stream.get("duration"),
                "measured_fps": rational(stream.get("avg_frame_rate", "0/0"))})
    text, code = _run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                       "packet=pts_time", "-of", "csv=p=0", str(path)])
    if code != 0:
        out["probe_status"] = "FFPROBE_PTS_FAILED"
        return out
    pts = sorted(float(item) for item in text.replace(",", " ").split() if item[:1].isdigit())
    out["decoded_pts_count"] = len(pts)
    out["first_pts"] = pts[0] if pts else None
    out["last_pts"] = pts[-1] if pts else None
    out["pts"] = pts
    out.update(cap_receipt(pts, out.get("measured_fps")))
    return out


def cap_receipt(pts: list[float], fps: float | None,
                frame_cap: int = LEGACY_FRAME_CAP) -> dict[str, Any]:
    """Apply the landed G401 cap mechanics to one measured presentation-timestamp list."""
    if not pts:
        return {"cap_status": "UNKNOWN_NO_PTS", "cap_admitted_count": "UNKNOWN",
                "cap_limited_span_s": "UNKNOWN", "available_span_s": "UNKNOWN",
                "cap_loss_s": "UNKNOWN", "cap_loss_over_5s": "UNKNOWN",
                "cap_target_s": TARGET_DURATION_SECONDS, "cap_frame_cap": frame_cap,
                "pts_constant_rate": "UNKNOWN"}
    receipt = capped_pts_receipt(pts, start_index=0, frame_cap=frame_cap, fps=fps)
    loss = cap_loss(receipt)
    return {"cap_status": receipt["status"], "cap_admitted_count": receipt["admitted_count"],
            "cap_limited_span_s": receipt["cap_limited_span_s"],
            "available_span_s": receipt["available_span_s"], "cap_loss_s": loss,
            "cap_loss_over_5s": int(loss > 5.0), "cap_target_s": TARGET_DURATION_SECONDS,
            "cap_frame_cap": frame_cap,
            "pts_constant_rate": int(pts_are_constant_rate(pts, fps))}


def seal_window(pts: list[float], seconds: float = 2.0) -> dict[str, Any]:
    """Seal the centered native interval and its half-open source-frame bounds."""
    start_pts, stop_pts = centered_interval(pts, seconds)
    start = bisect.bisect_left(pts, start_pts)
    stop = bisect.bisect_left(pts, stop_pts)
    return {"sealed_start_pts": start_pts, "sealed_stop_pts": stop_pts,
            "sealed_start_frame": start, "sealed_stop_frame": stop,
            "sealed_source_frames": stop - start}


def rebuild_trace(trace_path: Path, section_dir: Path, window: dict[str, Any] | None) -> dict:
    """Bound a delivered trace to its sealed window and add full-span held counts."""
    trace = json.loads(Path(trace_path).read_text(encoding="utf-8"))
    evaluated = [int(value) for value in trace["evaluated_tick_ids"]]
    rows = trace.pop("coordinate_rows", [])
    if not rows:
        rows, _, _ = _coordinate_rows(Path(section_dir) / "tracking_data.csv", set(evaluated))
    trace["full_span_held"] = held_pairs(evaluated, rows)
    trace["full_span_scope"] = "ALL_EVALUATED_TICKS"
    if window is None:
        trace["sealed_window"] = {"status": "UNKNOWN_NO_RETAINED_SOURCE"}
        trace["sealed_coordinate_rows"] = []
        trace["sealed_evaluated_tick_ids"] = []
        return trace
    start, stop = window["sealed_start_frame"], window["sealed_stop_frame"]
    trace["sealed_window"] = dict(window)
    trace["sealed_evaluated_tick_ids"] = [tick for tick in evaluated if start <= tick < stop]
    trace["sealed_coordinate_rows"] = [row for row in rows
                                       if start <= int(row["source_frame"]) < stop]
    trace["raw_overrun_rows_outside_sealed_window"] = len(rows) - len(trace["sealed_coordinate_rows"])
    return trace


def main() -> int:
    parser = argparse.ArgumentParser(description="G407 native probe and sealed re-extraction")
    parser.add_argument("--population", required=True)
    parser.add_argument("--traces", required=True)
    parser.add_argument("--tracking-root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--source-root", default="")
    args = parser.parse_args()
    out = Path(args.out)
    (out / "raw_traces").mkdir(parents=True, exist_ok=True)
    payload = json.loads(Path(args.population).read_text(encoding="utf-8"))
    probes = []
    for row in payload["population"]:
        identity = row["section_identity"]
        source = row.get("retained_pod_path") or ""
        if args.source_root and source:
            source = str(Path(args.source_root) / Path(source).name)
        probe: dict[str, Any] = {"section_identity": identity}
        window = None
        if source and Path(source).exists():
            probe.update(probe_source(Path(source), args.ffprobe))
            if probe.get("pts"):
                window = seal_window(probe["pts"])
                probe.update(window)
        else:
            probe.update({"probe_status": "SOURCE_NOT_RETAINED", "source_path": source})
        probe.pop("pts", None)
        probes.append(probe)
        trace = rebuild_trace(Path(args.traces) / (identity + ".json"),
                              Path(args.tracking_root) / identity, window)
        (out / "raw_traces" / (identity + ".json")).write_text(
            json.dumps(trace, sort_keys=True), encoding="utf-8", newline="\n")
    (out / "probes.json").write_text(json.dumps(probes, indent=1, sort_keys=True),
                                     encoding="utf-8", newline="\n")
    print("PROBED %d OK %d SEALED %d" % (
        len(probes), sum(item.get("probe_status") == "OK" for item in probes),
        sum("sealed_start_frame" in item for item in probes)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
