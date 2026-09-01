"""Fail-closed corpus evidence gate for tracking-teacher feature families."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from scripts.platformkit.runtime_contract import TRAINING_ONLY, classify_feature


NONE = "NONE"
IMAGE_PX_DECLARED = "IMAGE_PX_DECLARED"
METRIC_LOCAL = "METRIC_LOCAL"
HARNESS_PASS_10 = "HARNESS_PASS_10"
_FAMILIES = {
    NONE: (),
    IMAGE_PX_DECLARED: ("image_region",),
    METRIC_LOCAL: ("image_region", "metric_local"),
    HARNESS_PASS_10: ("image_region", "metric_local", "court_metric"),
}


def _has_image_px(tracking_dir: Path) -> bool:
    for path in tracking_dir.rglob("*.csv") if tracking_dir.is_dir() else ():
        try:
            frame = pd.read_csv(path, usecols=["coordinate_space"])
        except (OSError, ValueError, pd.errors.ParserError):
            continue
        if frame["coordinate_space"].eq("image_px").any():
            return True
    return False


def _has_local_scale(tracking_dir: Path) -> bool:
    for path in tracking_dir.rglob("teacher_meta.json") if tracking_dir.is_dir() else ():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for segment in payload.get("segments", []):
            if isinstance(segment, dict) and segment.get("scale_px_per_ft") is not None:
                return True
    return False


def _passed_reports(reports_dir: Path) -> int:
    passed = 0
    for path in reports_dir.rglob("*.json") if reports_dir.is_dir() else ():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        passed += payload.get("passed") is True
    return passed


def corpus_rung(sport: str, reports_dir: str | Path, tracking_dir: str | Path) -> str:
    """Return the highest rung supported by real artifacts, never by file count."""
    del sport
    tracking = Path(tracking_dir)
    if not _has_image_px(tracking):
        return NONE
    if not _has_local_scale(tracking):
        return IMAGE_PX_DECLARED
    if _passed_reports(Path(reports_dir)) < 10:
        return METRIC_LOCAL
    return HARNESS_PASS_10


def unlocked_families(rung: str) -> tuple[str, ...]:
    """Return only the feature families admitted by a measured rung."""
    if rung not in _FAMILIES:
        raise ValueError("unknown teacher-feature rung: %s" % rung)
    return _FAMILIES[rung]


def assert_family_unlocked(sport: str, family: str, reports_dir: str | Path,
                           tracking_dir: str | Path) -> None:
    """Raise when evidence has not unlocked the requested family."""
    rung = corpus_rung(sport, reports_dir, tracking_dir)
    if family not in unlocked_families(rung):
        raise ValueError("teacher family %s is locked at measured rung %s" % (family, rung))


def assert_teacher_columns(names: Iterable[str]) -> None:
    """Require every teacher feature name to be training-only by contract."""
    invalid = [name for name in names if classify_feature(name) != TRAINING_ONLY]
    if invalid:
        raise ValueError("teacher columns must be TRAINING_ONLY: %s" % ", ".join(invalid))
