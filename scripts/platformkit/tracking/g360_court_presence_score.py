"""Score G360 blind court-presence ratings against the sealed held-out list."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path


LABELS = ("USABLE_COURT", "CLOSEUP", "CROWD_GRAPHICS", "UNKNOWN")
PREDICTIONS = ("COURT", "NON_COURT", "ABSTAIN")


def wilson(successes: int, total: int) -> tuple[float, float]:
    """Return a two-sided Wilson 95 percent interval."""
    if not total:
        return float("nan"), float("nan")
    z = 1.959963984540054
    share = successes / total
    denominator = 1.0 + z * z / total
    center = (share + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(share * (1 - share) / total + z * z / (4 * total ** 2)) / denominator
    return center - radius, center + radius


def kappa(left: list[str], right: list[str]) -> float:
    """Compute Cohen kappa for the fixed four-label reference vocabulary."""
    if not left or len(left) != len(right):
        raise ValueError("kappa needs equal nonempty ratings")
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    left_counts, right_counts = Counter(left), Counter(right)
    expected = sum(left_counts[label] * right_counts[label] for label in LABELS) / len(left) ** 2
    return 1.0 if observed == expected == 1.0 else (observed - expected) / (1.0 - expected)


def references(heldout: list[dict[str, str]], ratings: list[dict[str, str]],
               adjudication: list[dict[str, str]]) -> tuple[dict[str, str], float]:
    """Resolve one adjudicated reference per sealed frame."""
    expected = {row["frame_key"] for row in heldout}
    pairs: dict[str, dict[str, str]] = {key: {} for key in expected}
    for row in ratings:
        key, rater, label = row.get("frame_key", ""), row.get("rater", ""), row.get("label", "")
        if key not in pairs or rater not in ("terra", "sol") or label not in LABELS or rater in pairs[key]:
            raise ValueError("invalid primary rating: %r" % row)
        pairs[key][rater] = label
    if any(set(pair) != {"terra", "sol"} for pair in pairs.values()):
        raise ValueError("every sealed frame needs both primary ratings")
    adjudicated = {row.get("frame_key", ""): row.get("label", "") for row in adjudication}
    final: dict[str, str] = {}
    for key, pair in pairs.items():
        final[key] = pair["terra"] if pair["terra"] == pair["sol"] else adjudicated.get(key, "")
        if final[key] not in LABELS:
            raise ValueError("missing valid adjudication: %s" % key)
    ordered = sorted(expected)
    return final, kappa([pairs[key]["terra"] for key in ordered], [pairs[key]["sol"] for key in ordered])


def score(heldout: list[dict[str, str]], ratings: list[dict[str, str]],
          adjudication: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, object]]:
    """Return additive confusion/per-competition rows and summary statistics."""
    final, agreement = references(heldout, ratings, adjudication)
    confusion = Counter((row["prediction"], final[row["frame_key"]]) for row in heldout)
    total = len(heldout)
    rows = [{"prediction": prediction, "reference_label": label,
             "count": "%06d" % confusion[(prediction, label)],
             "share_per_mille": "%06d" % round(1000 * confusion[(prediction, label)] / total)}
            for prediction in PREDICTIONS for label in LABELS]
    per_competition: list[dict[str, str]] = []
    for competition in sorted({row["competition"] for row in heldout}):
        subset = [row for row in heldout if row["competition"] == competition]
        for prediction in PREDICTIONS:
            count = sum(row["prediction"] == prediction for row in subset)
            per_competition.append({"competition": competition, "prediction": prediction,
                                    "count": "%06d" % count,
                                    "share_per_mille": "%06d" % round(1000 * count / len(subset))})
    court = sum(row["prediction"] == "COURT" for row in heldout)
    reference = sum(final[row["frame_key"]] == "USABLE_COURT" for row in heldout)
    true_positive = confusion[("COURT", "USABLE_COURT")]
    counts = {prediction: sum(row["prediction"] == prediction for row in heldout) for prediction in PREDICTIONS}
    summary = {"n": total, "kappa": agreement, "precision": true_positive / court if court else float("nan"),
               "recall": true_positive / reference if reference else float("nan"),
               "precision_wilson": wilson(true_positive, court), "recall_wilson": wilson(true_positive, reference),
               "abstention_share": counts["ABSTAIN"] / total, "predicted_counts": counts,
               "bar_sample": total >= 200 and min(counts.values()) >= 30}
    return rows, per_competition, summary


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="ascii") as handle:
        return list(csv.DictReader(handle))


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="G360 blind rating scorer")
    parser.add_argument("--heldout", type=Path, required=True)
    parser.add_argument("--ratings", type=Path, required=True)
    parser.add_argument("--adjudication", type=Path, required=True)
    parser.add_argument("--confusion", type=Path, required=True)
    parser.add_argument("--per-competition", type=Path, required=True)
    args = parser.parse_args()
    confusion, per_competition, summary = score(_read(args.heldout), _read(args.ratings), _read(args.adjudication))
    _write(args.confusion, confusion)
    _write(args.per_competition, per_competition)
    print(json.dumps(summary, sort_keys=True, default=list))


if __name__ == "__main__":
    main()
