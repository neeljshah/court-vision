"""Sealed G374 quota sampler for frozen G364 court-presence predictions."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
from collections import defaultdict
from pathlib import Path

from scripts.platformkit.tracking.g364_sampler import PREDICTIONS, frame_key, read_csv, write_csv


SEED = 374
TOTAL = 300
MIN_PER_SCORED_STRATUM = 60


def _stable_key(row: dict[str, str]) -> str:
    """Return the already-bound key or derive it from the frozen manifest fields."""
    return row.get("frame_key") or frame_key(row)


def _seed_fraction(prediction: str) -> float:
    digest = hashlib.sha256(("g374:%d:%s" % (SEED, prediction)).encode("ascii")).digest()
    return (int.from_bytes(digest[:8], "big") + 0.5) / 2 ** 64


def fixed_spacing_pick(rows: list[dict[str, str]], count: int,
                       prediction: str) -> list[dict[str, str]]:
    """Pick sorted strict-interior rows across the full stratum from a seeded start."""
    ordered = sorted(rows, key=_stable_key)
    if count > len(ordered):
        raise ValueError("requested quota exceeds available frozen predictions")
    if count == len(ordered):
        return ordered
    if len(ordered) < count + 2:
        raise ValueError("stratum cannot support strict-interior fixed spacing")
    span, start = len(ordered) - 2, _seed_fraction(prediction)
    indices = [1 + math.floor((position + start) * span / count)
               for position in range(count)]
    if len(set(indices)) != count or indices[0] <= 0 or indices[-1] >= len(ordered) - 1:
        raise ValueError("fixed-spacing draw is not unique strict interior")
    return [ordered[index] for index in indices]


def proportional_counts(court_available: int, non_court_available: int,
                        total: int = TOTAL) -> dict[str, int]:
    """Allocate the non-abstaining remainder proportionally, retaining both floors."""
    if total < 2 * MIN_PER_SCORED_STRATUM:
        raise ValueError("total cannot meet both scored-stratum floors")
    if min(court_available, non_court_available) < MIN_PER_SCORED_STRATUM:
        raise ValueError("frozen stratum is below its required 60-frame floor")
    available = court_available + non_court_available
    if total > available:
        raise ValueError("requested quota exceeds available frozen predictions")
    raw = {"COURT": total * court_available / available,
           "NON_COURT": total * non_court_available / available}
    counts = {name: math.floor(value) for name, value in raw.items()}
    for name in sorted(counts, key=lambda item: (raw[item] - counts[item], item), reverse=True):
        if sum(counts.values()) == total:
            break
        counts[name] += 1
    if min(counts.values()) < MIN_PER_SCORED_STRATUM:
        raise ValueError("proportional quota violates a scored-stratum floor")
    return counts


def adjudicated_quota(rows: list[dict[str, str]], total: int = TOTAL) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Select all abstentions and a fixed-spacing proportional scored remainder."""
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        prediction = row.get("prediction", "")
        if prediction not in PREDICTIONS:
            raise ValueError("unknown frozen prediction: " + prediction)
        groups[prediction].append(row)
    abstain = sorted(groups["ABSTAIN"], key=_stable_key)
    remainder = total - len(abstain)
    counts = proportional_counts(len(groups["COURT"]), len(groups["NON_COURT"]), remainder)
    selected = abstain[:]
    selected += fixed_spacing_pick(groups["COURT"], counts["COURT"], "COURT")
    selected += fixed_spacing_pick(groups["NON_COURT"], counts["NON_COURT"], "NON_COURT")
    selected_keys = {_stable_key(row) for row in selected}
    if len(selected) != total or len(selected_keys) != total:
        raise ValueError("sealed draw is not exactly 300 unique frame keys")
    excluded = [{"frame_key": _stable_key(row), "prediction": row["prediction"],
                 "reason": "quota_not_selected"}
                for row in sorted(rows, key=_stable_key) if _stable_key(row) not in selected_keys]
    return sorted(selected, key=_stable_key), excluded


def write_excluded(path: Path, rows: list[dict[str, str]]) -> None:
    """Write every omitted frozen key with its fixed reason using LF line endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("frame_key", "prediction", "reason"),
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="G374 sealed adjudicated quota sampler")
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--excluded", type=Path, required=True)
    args = parser.parse_args()
    selected, excluded = adjudicated_quota(read_csv(args.predictions))
    write_csv(args.validation, selected)
    write_excluded(args.excluded, excluded)
    counts = {label: sum(row["prediction"] == label for row in selected) for label in PREDICTIONS}
    print("selected=%d court=%d non_court=%d abstain=%d excluded=%d" %
          (len(selected), counts["COURT"], counts["NON_COURT"], counts["ABSTAIN"], len(excluded)))


if __name__ == "__main__":
    main()
