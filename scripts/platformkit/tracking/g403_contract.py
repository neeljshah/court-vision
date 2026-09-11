"""Pure G403 diagnostic contracts; these helpers perform no archive replay."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite
from typing import Iterable, Mapping, Optional, Sequence


VALID_STATES = frozenset({"VISIBLE", "ABSENT", "UNKNOWN"})


@dataclass(frozen=True)
class AnswerStatus:
    """Preserves a raw state label independently from its box-validity result."""

    label_status: str
    box_status: str


@dataclass(frozen=True)
class RoundStatus:
    """The future replay result required before an individual round can pass."""

    round_id: str
    paired: int
    expected_pairs: int
    passed: bool


def _valid_box(box: Optional[Sequence[object]]) -> bool:
    if box is None or len(box) != 4:
        return False
    try:
        left, top, right, bottom = (float(value) for value in box)
    except (TypeError, ValueError):
        return False
    return all(isfinite(value) for value in (left, top, right, bottom)) and right > left and bottom > top


def answer_status(label: object, box: Optional[Sequence[object]]) -> AnswerStatus:
    """Classify label and geometry without allowing one status to erase the other."""
    if label is None or str(label).strip() == "":
        label_status = "MISSING_LABEL"
    elif str(label) not in VALID_STATES:
        label_status = "INVALID_LABEL"
    else:
        label_status = "VALID_LABEL"
    box_status = "VALID_BOX" if _valid_box(box) else "INVALID_GEOMETRY"
    return AnswerStatus(label_status=label_status, box_status=box_status)


def binding_issues(expected_keys: Iterable[str], observed_keys: Iterable[str]) -> dict[str, list[str]]:
    """Return explicit missing and duplicate identifiers for a future archived join."""
    expected = list(expected_keys)
    observed = list(observed_keys)
    duplicates = sorted({key for key in observed if observed.count(key) > 1})
    missing = sorted(set(expected) - set(observed))
    unexpected = sorted(set(observed) - set(expected))
    return {"duplicate_ids": duplicates, "missing_ids": missing, "unexpected_ids": unexpected}


def overall_round_status(rounds: Iterable[RoundStatus]) -> str:
    """Forbid a pooled result from replacing a failed or incomplete individual round."""
    materialized = list(rounds)
    if not materialized:
        raise ValueError("no-rounds")
    if any(row.paired != row.expected_pairs for row in materialized):
        return "INCOMPLETE"
    if any(not row.passed for row in materialized):
        return "FAILED"
    return "DONE"


def retain_centre_gaps(pairs: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """Copy every supplied raw pair and add its gap without excluding any pair."""
    retained: list[dict[str, object]] = []
    for pair in pairs:
        row = dict(pair)
        try:
            dx = float(row["left_cx"]) - float(row["right_cx"])
            dy = float(row["left_cy"]) - float(row["right_cy"])
            row["gap_px"] = hypot(dx, dy) if isfinite(dx) and isfinite(dy) else None
        except (KeyError, TypeError, ValueError):
            row["gap_px"] = None
        retained.append(row)
    return retained
