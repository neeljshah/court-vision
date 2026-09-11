"""G384 arm accounting that closes unmet supply without invoking a scorer."""
from __future__ import annotations

import csv
from pathlib import Path

ARM_FIELDS = ("arm", "state", "unmet_quotas", "candidate_heldout_executions")


def accounting(readiness: dict[str, bool], candidate_heldout_executions: int = 0) -> list[dict]:
    """Return every arm's state and every named unmet prerequisite."""
    if candidate_heldout_executions > 1:
        raise ValueError("second-candidate-heldout-execution-refused")
    common = ("reference_complete", "reference_usable", "heldout_visible_150",
              "heldout_absent_150", "time_budget")
    needs = {
        "A0": (),
        "A8": common + ("development_boxes_500", "development_games_5"),
        "A9": common + ("pinned_licence_dependency_receipt",),
        "A10": common + ("A8_available",),
    }
    rows = []
    for arm, required in needs.items():
        unmet = [name for name in required if not readiness.get(name, False)]
        state = "ARCHIVED BASELINE" if arm == "A0" else (
            "READY" if not unmet else "CLOSED AT LIMIT")
        rows.append({"arm": arm, "state": state, "unmet_quotas": ";".join(unmet),
                     "candidate_heldout_executions": candidate_heldout_executions})
    return rows


def write_receipt(path: Path, readiness: dict[str, bool], executions: int = 0) -> list[dict]:
    """Write the arm receipt with every unmet quota explicit."""
    rows = accounting(readiness, executions)
    with Path(path).open("w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ARM_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return rows
