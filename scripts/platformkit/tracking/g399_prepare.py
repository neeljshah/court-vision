"""Prepare-only receipts and gates for the G399 retained-source census."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from scripts.platformkit.tracking import g399_protocol as protocol


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def qualification_receipt(scores: Path, audit_clicks: Path) -> dict[str, object]:
    """Recompute the exact G396 qualified-rater before-condition."""
    rows = _rows(scores)
    passed = {rater: {row["control_id"] for row in rows if row["rater"] == rater and row["passed"] == "1"}
              for rater in protocol.RATERS}
    joint = len(passed["astra"] & passed["sol"])
    clicks = _rows(audit_clicks)
    audit_passes = sum(row["same_band"] == "YES" and "9/9" in row["points_within_3px"] for row in clicks)
    holds = len(rows) == 60 and len(passed["astra"]) == 30 and len(passed["sol"]) == 27 and joint == 27 and audit_passes == 3
    return {"qualification_rows": len(rows), "astra_passed": len(passed["astra"]),
            "sol_passed": len(passed["sol"]), "joint_passed": joint,
            "real_audit_passes": audit_passes, "holds": holds}


def runtime_receipt(instruction_paths: dict[str, Path], runtime: Path) -> dict[str, object]:
    """Name frozen instruction bytes and ensure both high configurations exist."""
    config = json.loads(runtime.read_text(encoding="utf-8"))
    result = {rater: {"path": path.as_posix(), "exists": path.is_file(),
                      "sha256": _sha256(path) if path.is_file() else "ABSENT"}
              for rater, path in instruction_paths.items()}
    runtime_ok = all(config.get(rater, {}).get("config_reasoning_effort") == "high" for rater in protocol.RATERS)
    return {"instructions": result, "runtime_sha256": _sha256(runtime),
            "runtime_high": runtime_ok, "holds": runtime_ok and all(item["exists"] for item in result.values())}


def source_receipts(source_identity: Path, source_root: Path | None = None) -> list[dict[str, object]]:
    """Rehash source objects one at a time; absence remains an explicit row."""
    output = []
    for row in _rows(source_identity):
        stored = Path(row["source_path"])
        path = source_root / stored.name if source_root else stored
        record = {"attempt_id": row["attempt_id"], "source_path": str(path),
                  "expected_sha256": row["source_sha256"], "expected_bytes": int(row["source_bytes"])}
        if not path.is_file():
            record.update({"status": "ABSENT", "actual_sha256": "", "actual_bytes": ""})
        else:
            actual_bytes = path.stat().st_size
            actual_sha = _sha256(path)
            record.update({"status": "MATCH" if actual_bytes == record["expected_bytes"] and actual_sha == record["expected_sha256"] else "CHANGED",
                           "actual_sha256": actual_sha, "actual_bytes": actual_bytes})
        output.append(record)
    return output


def select_targets(first_pts: float, last_pts: float, decoded_pts: list[float]) -> list[dict[str, float]]:
    """Return the two non-duplicated planned PTS rows for a decoded source."""
    chosen = protocol.planned_targets(first_pts, last_pts, decoded_pts)
    return [{"target_fraction": fraction, "selected_pts": pts} for fraction, pts in zip((1.0 / 3.0, 2.0 / 3.0), chosen)]


def supply_verdict(decoded_unique: int, recovered: int) -> str:
    """Separate the required decoded census from the necessary recovery supply."""
    if decoded_unique < 30:
        return "NOT VALIDATED"
    return "DONE_NECESSARY_ONLY" if recovered >= 30 else "CLOSED AT LIMIT"
