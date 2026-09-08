"""Append-only ledger entry builders for the tracking daemon."""
from __future__ import annotations

import time


def corrupt_entry(game_id: str, sport: str, size: int, retained: bool) -> dict:
    """Describe one invalid staged file, including failed-retain recovery.

    Carries `probe_status` as `not_probed` (G318): this file is quarantined on
    its size alone, before any probe runs, so the row must say so rather than
    look like a probe that returned nothing.

    Carries the two additive booleans like every other new row (contract B2):
    a corrupt staged file is 0 rows in 0 s, which is degenerate by D2, and no
    tracker ran on a data dir, so it is never a resume.
    """
    heads = ["staged file is %d bytes, not a video" % size]
    if not retained:
        heads.append("retain_failed: staged source renamed .failed")
    return {"game_id": game_id, "sport": sport, "status": "corrupt",
            "adjudicated": False, "retain_failed": not retained, "rows": 0,
            "passed": None, "failure_heads": heads, "failures": heads,
            "coverage_pct": None, "harness_coverage_pct": None,
            "coordinate_space": None, "rung": None,
            "evaluated_at": None, "seconds": 0, "finished_at": int(time.time()),
            "decoded_frames": None, "evaluated_frames": None, "stride": None,
            "source_resolution": None, "probe_status": "not_probed",
            "degenerate": True, "resumed_partial": False,
            "fresh_solves": None, "rows_per_decoded_frame_step_change": None}


# A run that dies mid-clip still leaves output on disk: unified_pipeline
# checkpoints tracking_data.csv every 2000 frames and the frame-0 checkpoint is
# written minutes before the first real block. So a killed worker leaves a data
# dir holding one or two rows, and the next daemon -- which claims from the
# staging directory alone and never looks at the data dir -- re-launches the
# clip, grades whatever is there, and writes `tracked`. MEASURED on the pod for
# the 2026-09-08 05:26Z volume event: 4 of the 8 clips the relaunched daemon
# picked up had a data dir older than their own start, and all 4 recorded
# between 0 and 2 rows in 365 to 393 s while the 4 with no prior data dir
# recorded thousands. These two booleans let a reader tell the two apart
# without parsing, and rename ONLY the status value that lies.
DEGENERATE_ROWS = 50
DEGENERATE_SECONDS = 600
DEGENERATE_STATUS = "RESUMED_DEGENERATE"


def is_degenerate(rows, seconds) -> bool:
    """Too thin AND too short to be a real completion of a tracking clip."""
    try:
        return int(rows) < DEGENERATE_ROWS and int(seconds) < DEGENERATE_SECONDS
    except (TypeError, ValueError):
        return False


def resumed_partial(directory, started) -> bool:
    """True when this clip's data dir held output before this run began.

    Absence is never a defect (contract B3): no directory, an unreadable one, or
    an unusable start time all report False and the row is left untouched.
    """
    try:
        begin = float(started)
        return any(item.is_file() and item.stat().st_mtime < begin
                   for item in directory.iterdir())
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def mark_degenerate(entry: dict, directory, started) -> dict:
    """Add the two additive fields and downgrade only a lying `tracked`.

    Additive by contract B2: no existing field is renamed or removed and no
    existing status value disappears. A row that is both degenerate and a resume
    stops claiming `tracked`; `rows` stays exactly as measured.
    """
    entry["degenerate"] = is_degenerate(entry.get("rows"), entry.get("seconds"))
    entry["resumed_partial"] = resumed_partial(directory, started)
    if entry["degenerate"] and entry["resumed_partial"] and entry.get("status") == "tracked":
        entry["status"] = DEGENERATE_STATUS
    return entry
