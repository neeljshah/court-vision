"""Score frozen G364 validation predictions against blind adjudicated labels."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from scripts.platformkit.tracking.g364_sampler import assert_game_disjoint
from scripts.platformkit.tracking.g364_train import LABELS


PREDICTIONS = ("COURT", "NON_COURT", "ABSTAIN")


def wilson(successes: int, total: int) -> tuple[float, float]:
    """Return a two-sided Wilson 95 percent interval."""
    if not total:
        return float("nan"), float("nan")
    z, share = 1.959963984540054, successes / total
    denominator = 1.0 + z * z / total
    center = (share + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(share * (1 - share) / total + z * z / (4 * total ** 2)) / denominator
    return center - radius, center + radius


def kappa(left: list[str], right: list[str]) -> float:
    """Return Cohen kappa over the four preregistered labels."""
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    left_counts, right_counts = Counter(left), Counter(right)
    expected = sum(left_counts[label] * right_counts[label] for label in LABELS) / len(left) ** 2
    return 1.0 if observed == expected == 1.0 else (observed - expected) / (1.0 - expected)


def references(validation: list[dict[str, str]], ratings: list[dict[str, str]],
               adjudication: list[dict[str, str]]) -> tuple[dict[str, str], float]:
    """Resolve exactly two blind ratings and blind adjudication for every frame."""
    expected = {row["frame_key"] for row in validation}
    pairs: dict[str, dict[str, str]] = {key: {} for key in expected}
    for row in ratings:
        key, rater, label = row.get("frame_key", ""), row.get("rater", ""), row.get("label", "")
        if key not in pairs or rater not in ("terra", "sol") or label not in LABELS or rater in pairs[key]:
            raise ValueError("invalid blind rating")
        pairs[key][rater] = label
    if any(set(pair) != {"terra", "sol"} for pair in pairs.values()):
        raise ValueError("every sealed frame requires both blind ratings")
    overrides = {row.get("frame_key", ""): row.get("label", "") for row in adjudication}
    resolved = {key: pair["terra"] if pair["terra"] == pair["sol"] else overrides.get(key, "")
                for key, pair in pairs.items()}
    if any(label not in LABELS for label in resolved.values()):
        raise ValueError("missing blind adjudication")
    ordered = sorted(expected)
    return resolved, kappa([pairs[key]["terra"] for key in ordered], [pairs[key]["sol"] for key in ordered])


def score(validation: list[dict[str, str]], ratings: list[dict[str, str]],
          adjudication: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, object]]:
    """Return additive full and per-competition confusion rows plus frozen metrics."""
    resolved, agreement = references(validation, ratings, adjudication)
    buckets: dict[str, list[dict[str, str]]] = {"ALL": validation}
    buckets.update({competition: [row for row in validation if row["competition"] == competition]
                    for competition in sorted({row["competition"] for row in validation})})
    output: list[dict[str, str]] = []
    for scope, subset in buckets.items():
        cells = Counter((row["prediction"], resolved[row["frame_key"]]) for row in subset)
        output.extend({"scope": scope, "prediction": prediction, "reference_label": label,
                       "count": "%06d" % cells[(prediction, label)]}
                      for prediction in PREDICTIONS for label in LABELS)
    all_cells = Counter((row["prediction"], resolved[row["frame_key"]]) for row in validation)
    court = sum(row["prediction"] == "COURT" for row in validation)
    usable = sum(label == "USABLE_COURT" for label in resolved.values())
    true_positive = all_cells[("COURT", "USABLE_COURT")]
    counts = {item: sum(row["prediction"] == item for row in validation) for item in PREDICTIONS}
    summary = {"n": len(validation), "kappa": agreement,
               "precision": true_positive / court if court else float("nan"),
               "recall": true_positive / usable if usable else float("nan"),
               "precision_wilson": wilson(true_positive, court), "recall_wilson": wilson(true_positive, usable),
               "abstention_share": counts["ABSTAIN"] / len(validation), "unknown_share":
               sum(label == "UNKNOWN" for label in resolved.values()) / len(validation),
               "predicted_counts": counts, "bar_sample": len(validation) >= 300 and min(counts.values()) >= 30}
    return output, summary


def _read(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def main() -> None:
    parser = argparse.ArgumentParser(description="G364 frozen validation scorer")
    parser.add_argument("--development", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--ratings", type=Path, required=True)
    parser.add_argument("--adjudication", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--confusion", type=Path, required=True)
    args = parser.parse_args()
    development, validation = _read(args.development), _read(args.validation)
    assert_game_disjoint(development, validation)
    bound_hashes = {row.get("model_sha256", "") for row in validation}
    if bound_hashes != {_sha256(args.model)}:
        raise ValueError("sealed validation manifest does not bind this frozen model")
    confusion, summary = score(validation, _read(args.ratings), _read(args.adjudication))
    args.confusion.parent.mkdir(parents=True, exist_ok=True)
    with args.confusion.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(confusion[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(confusion)
    print(json.dumps(summary, sort_keys=True, default=list))


if __name__ == "__main__":
    main()
