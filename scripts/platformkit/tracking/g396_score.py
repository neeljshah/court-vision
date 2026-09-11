"""G396 deterministic raw-answer scoring helpers; no dispatch or control creation."""
from __future__ import annotations

from scripts.platformkit.tracking import g396_protocol as protocol


def score_rows(truth: dict[str, protocol.Band], answers: dict[str, dict[str, tuple[protocol.Point, protocol.Point, protocol.Point] | None]]) -> list[dict[str, object]]:
    """Score every fixed response, with an absent response as a failed row."""
    rows = []
    for control_id in sorted(truth):
        for rater in protocol.RATERS:
            points = answers.get(rater, {}).get(control_id)
            rows.append({"control_id": control_id, "rater": rater, "answered": points is not None,
                         "passed": protocol.control_passes(truth[control_id], points)})
    return rows


def repeatable(truth: dict[str, protocol.Band], answers: dict[str, dict[str, tuple[protocol.Point, protocol.Point, protocol.Point] | None]]) -> bool:
    """Assert a second raw-answer pass gives byte-for-byte equal logical rows."""
    return score_rows(truth, answers) == score_rows(truth, answers)
