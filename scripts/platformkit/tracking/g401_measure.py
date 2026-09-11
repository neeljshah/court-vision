"""Decoded-PTS measurement and the two G401 tables.

The only impure function is `decode_pts`, which shells out to ffprobe on a
retained source copy. Everything else is arithmetic over that list.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

from scripts.platformkit.tracking.g401_timebase import (
    LEGACY_FRAME_CAP,
    TARGET_DURATION_SECONDS,
    capped_pts_receipt,
    cap_loss,
    validated_frame_cap,
)

LOSS_DECISION_SECONDS = 5.0
DAEMON_START_FRAME = 0
# A step is on the nominal grid when it is an integer multiple of 1/fps. PTS are
# stored in an integer timebase, so a fifth of a frame is a generous rounding
# bound that still excludes a genuinely variable rate. A zero step is a
# duplicate PTS and a step above one interval is a dropped frame: both are
# counted and reported, and neither makes the RATE invalid.
GRID_TOLERANCE_FRAMES = 0.2


def decode_pts(video: Path) -> list[float]:
    """Every decoded video-frame PTS in seconds, in presentation order."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True, check=True).stdout
    values = [float(line.strip().rstrip(",")) for line in out.splitlines()
              if line.strip().rstrip(",") not in ("", "N/A")]
    return sorted(values)


def pts_summary(pts: list[float], fps: float | None) -> dict:
    """Identity and regularity of one source's decoded PTS schedule."""
    empty = {"pts_count": 0, "first_pts": None, "last_pts": None,
             "available_span_s": None, "monotonic": None, "rate_validated": False,
             "uniform_steps": False, "off_grid_steps": None,
             "duplicate_pts_steps": None, "dropped_frames": None,
             "max_interval_error_s": None}
    if not pts or not fps or fps <= 0:
        return empty
    interval = 1.0 / fps
    steps = [right - left for left, right in zip(pts, pts[1:])]
    if not steps:
        return empty
    multiples = [step / interval for step in steps]
    off_grid = sum(1 for m in multiples
                   if abs(m - round(m)) > GRID_TOLERANCE_FRAMES)
    duplicates = sum(1 for m in multiples if round(m) == 0)
    dropped = sum(round(m) - 1 for m in multiples if round(m) > 1)
    error = max(abs(step - interval) for step in steps)
    return {"pts_count": len(pts), "first_pts": pts[0], "last_pts": pts[-1],
            "available_span_s": pts[-1] - pts[0] + interval,
            "monotonic": all(step > 0 for step in steps),
            "rate_validated": off_grid == 0,
            "uniform_steps": error <= interval * GRID_TOLERANCE_FRAMES,
            "off_grid_steps": off_grid, "duplicate_pts_steps": duplicates,
            "dropped_frames": dropped, "max_interval_error_s": error}


def policy_row(entry: dict, summary: dict | None, fps: float | None) -> dict:
    """One sealed window section: available span, cap-limited span, loss."""
    row = {"game_id": entry["game_id"], "source_name": entry.get("_source_name"),
           "shipped_utc": entry.get("_shipped_utc"), "status": entry.get("status"),
           "source_fps": fps, "stride": entry.get("stride"),
           "ledger_decoded_frames": entry.get("decoded_frames"),
           "first_processed_frame": entry.get("_first_frame"),
           "last_processed_frame": entry.get("_last_frame"),
           "source_retained": summary is not None,
           "available_span_s": None, "cap_limited_span_s": None,
           "loss_s": None, "loss_over_decision": None,
           "attribution": "UNKNOWN", "unknown_reason": None}
    if summary is None:
        row["unknown_reason"] = "source_absent_before_retention"
        return row
    row.update({"pts_count": summary["pts_count"],
                "pts_rate_validated": summary["rate_validated"],
                "pts_duplicate_steps": summary["duplicate_pts_steps"],
                "pts_dropped_frames": summary["dropped_frames"],
                "available_span_s": summary["available_span_s"]})
    if not fps or not summary["available_span_s"]:
        row["unknown_reason"] = "no_validated_fps_or_span"
        return row
    if entry.get("status") != "tracked" or entry.get("_last_frame") is None:
        row["attribution"] = "FAILED_ATTEMPT" if entry.get("status") != "tracked" \
            else "NO_FRAME_ORDER"
        row["unknown_reason"] = "no_recorded_frame_order"
        return row
    if not summary["rate_validated"]:
        row["attribution"] = "MALFORMED_PTS"
        row["unknown_reason"] = "pts_off_nominal_grid"
        return row
    interval = 1.0 / fps
    limited = (entry["_last_frame"] - DAEMON_START_FRAME + 1) * interval
    row["cap_limited_span_s"] = limited
    row["measured_last_processed_pts_s"] = limited - interval
    loss = max(0.0, min(TARGET_DURATION_SECONDS,
                        summary["available_span_s"]) - limited)
    row["loss_s"] = loss
    exhausted = entry["_last_frame"] + (entry.get("stride") or 1) >= summary["pts_count"]
    row["attribution"] = "EOF" if exhausted else "CAP"
    row["loss_over_decision"] = bool(loss > LOSS_DECISION_SECONDS
                                     and row["attribution"] == "CAP")
    return row


def policy_totals(rows: list[dict]) -> dict:
    """The sealed primary metric plus every separately attributed bucket."""
    unscored = [r for r in rows if r["loss_s"] is None]
    unknown = [r for r in unscored if r["attribution"] != "FAILED_ATTEMPT"]
    over = [r for r in rows if r.get("loss_over_decision")]
    buckets: dict[str, int] = {}
    for row in rows:
        buckets[row["attribution"]] = buckets.get(row["attribution"], 0) + 1
    return {"window_sections": len(rows),
            "cap_loss_over_5s_count": len(over),
            "primary_metric": len(over) / len(rows) if rows else None,
            "unknown_sections": len(unknown),
            "unscored_sections": len(unscored),
            "attribution_counts": buckets,
            "policy_status": ("POSITIVE_LOSS" if over else
                              "PARTIAL_UNKNOWN" if unknown else "ZERO_LOSS")}


def paired_caps(name: str, pts: list[float], fps: float | None,
                rate_validated: bool) -> dict:
    """Arm A (legacy 3000) and arm B (validated-fps cap) over one PTS stream."""
    cap_b, basis = validated_frame_cap(fps, pts_valid=rate_validated)
    arm_a = capped_pts_receipt(pts, start_index=DAEMON_START_FRAME,
                               frame_cap=LEGACY_FRAME_CAP, fps=fps)
    arm_b = capped_pts_receipt(pts, start_index=DAEMON_START_FRAME,
                               frame_cap=cap_b, fps=fps)
    interval = 1.0 / fps if fps and fps > 0 else None
    extent_b = float(arm_b["cap_limited_span_s"] or 0.0)
    reach = (abs(extent_b - TARGET_DURATION_SECONDS) <= interval
             if interval else False)
    return {"source_name": name, "source_frame_count": len(pts),
            "validated_fps": fps, "cap_basis": basis,
            "arm_a_frame_cap": LEGACY_FRAME_CAP, "arm_b_frame_cap": cap_b,
            "arm_a_read_frames": arm_a["admitted_count"],
            "arm_b_read_frames": arm_b["admitted_count"],
            "arm_a_last_admitted_pts": arm_a["last_admitted_pts"],
            "arm_a_first_excluded_pts": arm_a["first_excluded_pts"],
            "arm_b_last_admitted_pts": arm_b["last_admitted_pts"],
            "arm_b_first_excluded_pts": arm_b["first_excluded_pts"],
            "arm_a_span_s": arm_a["cap_limited_span_s"],
            "arm_b_span_s": arm_b["cap_limited_span_s"],
            "arm_a_status": arm_a["status"], "arm_b_status": arm_b["status"],
            "arm_a_loss_s": cap_loss(arm_a), "arm_b_loss_s": cap_loss(arm_b),
            "native_frame_interval_s": interval,
            "arm_b_reaches_target": bool(reach),
            "declared_stride_opportunities": math.ceil(
                arm_b["admitted_count"] / max(1, round((fps or 0) / 10.0)))
            if fps and fps > 35 else None}
