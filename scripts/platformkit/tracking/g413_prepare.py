"""Preparation guards for G413; this module deliberately performs no measurement."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
G406 = ROOT / "docs/evidence/tracking/g406_masked_target_pixel_audit_2026-09-11"
G412 = ROOT / "docs/evidence/tracking/g412_box_frame_contract_2026-09-12"


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def prereg_seal_valid(path: Path) -> bool:
    """Validate a preregistration seal from file bytes after CRLF-to-LF normalization."""
    body = path.read_bytes().replace(b"\r\n", b"\n")
    marker = b"SEAL sha256 "
    index = body.find(marker)
    if index < 0:
        return False
    expected = body[index + len(marker):].split(b"\n", 1)[0].strip()
    return len(expected) == 64 and hashlib.sha256(body[:index]).hexdigest().encode("ascii") == expected


def prerequisite_status() -> dict[str, Any]:
    """Name every missing G412 binding input without replacing it from another tree."""
    required = ("input_hashes.csv", "transforms.json", "per_frame.csv", "summary.json", "SHA256SUMS")
    missing = [_display_path(G412 / name) for name in required if not (G412 / name).is_file()]
    g406_required = ("draw.csv", "source_receipts.csv", "all_masked_rows.csv", "comparator_detections.csv", "associations.csv")
    g406_missing = [_display_path(G406 / name) for name in g406_required if not (G406 / name).is_file()]
    return {"status": "READY" if not missing and not g406_missing else "PARTIAL",
            "missing_g412": missing, "missing_g406": g406_missing,
            "before_condition": "G412 accepted handoff with full hashes, preserved G406 outputs, and 60 original draw keys"}


def require_prerequisites() -> None:
    """Fail closed before a finisher can associate or calculate a residual."""
    status = prerequisite_status()
    if status["status"] != "READY":
        absent = status["missing_g412"] + status["missing_g406"]
        raise RuntimeError("; ".join("ABSENT-IN-WORKTREE " + item for item in absent))
