"""G390 native-scale settled-input guard for the one future A8 pass."""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping

LABELS = frozenset(("VISIBLE", "ABSENT", "UNKNOWN"))
REVIEW_STATE = "REVIEWED"
HELDOUT_LABELS = {"VISIBLE": 302, "ABSENT": 188, "UNKNOWN": 59}


@dataclass(frozen=True)
class SealedInput:
    """Validated G389 source rows and the hashes read from disk."""

    frames: list[dict[str, str]]
    reference: dict[str, dict[str, str]]
    hashes: dict[str, str]


def sha256_file(path: Path) -> str:
    """Hash one bounded input file without loading unrelated stores."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(path: Path) -> Path:
    if not path.is_file():
        print("ABSENT-IN-WORKTREE " + path.as_posix())
        raise FileNotFoundError("ABSENT-IN-WORKTREE " + path.as_posix())
    return path


def _rows(path: Path) -> list[dict[str, str]]:
    with _require(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _native(row: Mapping[str, str]) -> bool:
    try:
        return Decimal(row.get("sheet_scale", "")) == Decimal("1.0")
    except InvalidOperation:
        return False


def _unique(rows: list[dict[str, str]], name: str) -> dict[str, dict[str, str]]:
    index = {row.get("frame_key", ""): row for row in rows}
    if "" in index or len(index) != len(rows):
        raise ValueError("duplicate-or-missing-frame-key-" + name)
    return index


def load_sealed_input(
    frames_path: Path,
    reference_path: Path,
    *,
    expected_hashes: Mapping[str, str] | None = None,
    expected_total: int | None = 1620,
    expected_heldout: Mapping[str, int] | None = HELDOUT_LABELS,
) -> SealedInput:
    """Load only a settled native table pair; reject before any G363 score call."""
    frames_path, reference_path = Path(frames_path), Path(reference_path)
    hashes = {"frames": sha256_file(_require(frames_path)),
              "reference": sha256_file(_require(reference_path))}
    if expected_hashes:
        for name, expected in expected_hashes.items():
            if hashes.get(name) != expected:
                raise ValueError("sealed-input-hash-mismatch-" + name)
    frames = _rows(frames_path)
    reference = _unique(_rows(reference_path), "reference")
    frame_index = _unique(frames, "frames")
    scaled = [row.get("frame_key", "") for row in frames if not _native(row)]
    if scaled:
        raise ValueError("sheet-scale-not-native-refused " + scaled[0])
    missing = sorted(set(frame_index) - set(reference))
    extra = sorted(set(reference) - set(frame_index))
    unsettled = [key for key, row in reference.items()
                 if row.get("label") not in LABELS or row.get("review_state") != REVIEW_STATE]
    if missing or extra or unsettled:
        detail = (missing or extra or unsettled)[0]
        raise ValueError("unsettled-reference-refused " + detail)
    if expected_total is not None and len(frames) != expected_total:
        raise ValueError("reference-total-mismatch " + str(len(frames)))
    for row in reference.values():
        for field in ("cx", "cy", "diameter"):
            raw = str(row.get(field, "") or "").strip()
            row[field] = float(raw) if raw else None
    heldout = [reference[row["frame_key"]] for row in frames if row.get("split") == "heldout"]
    if expected_heldout is not None:
        actual = {label: sum(row["label"] == label for row in heldout) for label in LABELS}
        if actual != dict(expected_heldout):
            raise ValueError("heldout-label-count-mismatch " + repr(actual))
    return SealedInput(frames=frames, reference=reference, hashes=hashes)
