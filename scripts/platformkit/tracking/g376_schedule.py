"""G376 -- reconstruct the producer evaluated-tick schedule from the producer's own tables.

Sealed definitions: docs/evidence/tracking/g376_declared_tick_observations_2026-09-10/
g376_prereg_2026-09-10.md (SEAL sha256 32bcad44e602ac870f06e02cf5118272bf1343797906905f0ed4d8d4705173ee).

DECLARED comes from the ledger cadence exactly as G370 expanded it (imported, never copied).
RECONSTRUCTED comes from `ball_tracking.csv`, which the producer writes one row per frame that
reached the tracking body: `live = 1` on an evaluated frame (src/pipeline/unified_pipeline.py:1991)
and `live = 0` on a suspended frame (src/pipeline/unified_pipeline.py:1836-1849). Reads only; no
`src/`, `data/` or deploy path is written.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping

from scripts.platformkit.tracking.g331_evaluated_frames_sidecar import modal_gap
from scripts.platformkit.tracking.g359_held_position import LEDGER_FIELDS, latest_ledger_records
from scripts.platformkit.tracking.g361_source_identity import sha256_file
from scripts.platformkit.tracking.g370_manifest import _schedule as declared_schedule

TRACKING = "tracking_data.csv"
BALL = "ball_tracking.csv"
ROUTE_SIDECAR = "evaluated_frame_count.json"
VERDICT = "harness_verdict.json"
SNAPSHOT_FILES = (TRACKING, BALL, ROUTE_SIDECAR, VERDICT)
NO_SCHEDULE_REASONS = ("ball_table_absent", "ball_table_unreadable", "ball_frame_column_absent",
                       "ball_live_column_absent", "ball_frame_non_integral")

__all__ = ["declared_schedule", "reconstructed_schedule", "route_cap", "section_facts",
           "snapshot_manifest", "LEDGER_FIELDS", "latest_ledger_records", "NO_SCHEDULE_REASONS"]


def integral(value: Any) -> int | None:
    """Return an exact integer, rejecting blanks and fractional values (never rounds)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if number != int(number):
        return None
    return int(number)


def frame_set(path: Path) -> tuple[set[int], int, str]:
    """Distinct integral `frame` values of a table, its row count and a named reason."""
    if not Path(path).exists():
        return set(), 0, "table_absent"
    try:
        with Path(path).open(newline="", encoding="utf-8-sig", errors="replace") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "frame" not in reader.fieldnames:
                return set(), 0, "frame_column_absent"
            frames, rows = set(), 0
            for row in reader:
                rows += 1
                frame = integral(row.get("frame"))
                if frame is None:
                    return set(), rows, "frame_non_integral"
                frames.add(frame)
    except OSError:
        return set(), 0, "table_unreadable"
    return frames, rows, ""


def reconstructed_schedule(ball_path: Path) -> dict[str, Any]:
    """Evaluated (`live = 1`) and suspended (`live = 0`) frame sets, or a named absence."""
    path = Path(ball_path)
    out: dict[str, Any] = {"evaluated": set(), "suspended": set(), "ball_rows": 0,
                           "reason": "", "observed_stride": None}
    if not path.exists():
        out["reason"] = "ball_table_absent"
        return out
    try:
        with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
            reader = csv.DictReader(handle)
            names = reader.fieldnames or []
            if "frame" not in names:
                out["reason"] = "ball_frame_column_absent"
                return out
            if "live" not in names:
                out["reason"] = "ball_live_column_absent"
                return out
            for row in reader:
                out["ball_rows"] += 1
                frame = integral(row.get("frame"))
                if frame is None:
                    out["evaluated"], out["suspended"] = set(), set()
                    out["reason"] = "ball_frame_non_integral"
                    return out
                live = integral(row.get("live"))
                (out["evaluated"] if live == 1 else out["suspended"]).add(frame)
    except OSError:
        out["reason"] = "ball_table_unreadable"
        return out
    out["observed_stride"] = modal_gap(sorted(out["evaluated"]))
    return out


def route_cap(section_dir: Path) -> int | None:
    """The route frame cap the run was launched with, from its own sidecar; None when absent."""
    path = Path(section_dir) / ROUTE_SIDECAR
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("max_frames")
    except (OSError, ValueError, AttributeError):
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _verdict(section_dir: Path) -> dict[str, Any]:
    try:
        payload = json.loads((Path(section_dir) / VERDICT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def section_facts(section_id: str, set_name: str, section_dir: Path,
                  record: Mapping[str, Any]) -> dict[str, Any]:
    """Every fact one section contributes, with no class decided and nothing dropped."""
    section_dir = Path(section_dir)
    declared, declared_reason = declared_schedule(record)
    schedule = reconstructed_schedule(section_dir / BALL)
    tracked, tracking_rows, tracking_reason = frame_set(section_dir / TRACKING)
    verdict = _verdict(section_dir)
    cap = route_cap(section_dir)
    stride = integral(record.get("stride"))
    return {
        "section_id": section_id, "set": set_name,
        "declared": declared, "declared_reason": declared_reason,
        "declared_ticks": len(declared),
        "stride": stride, "decoded_frames": integral(record.get("decoded_frames")),
        "ledger_evaluated_frames": integral(record.get("evaluated_frames")),
        "verdict_evaluated_frames": integral(verdict.get("evaluated_frames")),
        "verdict_stride": integral(verdict.get("stride")),
        "verdict_attempted_frames_capped": integral(verdict.get("attempted_frames_capped")),
        "route_max_frames": cap,
        "route_capped_ticks": (None if cap is None or not stride
                               else min(len(declared), -(-cap // stride))),
        "evaluated": schedule["evaluated"], "suspended": schedule["suspended"],
        "schedule_reason": schedule["reason"], "ball_rows": schedule["ball_rows"],
        "observed_stride": schedule["observed_stride"],
        "tracked": tracked, "tracking_rows": tracking_rows,
        "tracking_reason": tracking_reason,
        "ledger_record": {field: record.get(field) for field in LEDGER_FIELDS},
        "tracking_path": str((section_dir / TRACKING).resolve()),
        "ball_path": str((section_dir / BALL).resolve()),
        "tracking_bytes": (section_dir / TRACKING).stat().st_size
        if (section_dir / TRACKING).exists() else None,
        "ball_bytes": (section_dir / BALL).stat().st_size
        if (section_dir / BALL).exists() else None,
    }


def snapshot_manifest(sections: Mapping[str, str], snapshot_dir: Path,
                      out_path: Path) -> list[dict[str, Any]]:
    """A9/A11 pin sheet: every snapshot file with its byte size and sha256, absence named."""
    rows: list[dict[str, Any]] = []
    for section_id, set_name in sorted(sections.items()):
        for name in SNAPSHOT_FILES:
            path = Path(snapshot_dir) / section_id / name
            rows.append({"section_id": section_id, "set": set_name, "file": name,
                         "present": int(path.exists()),
                         "bytes": path.stat().st_size if path.exists() else "",
                         "sha256": sha256_file(path) if path.exists() else "ABSENT"})
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with Path(out_path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows
