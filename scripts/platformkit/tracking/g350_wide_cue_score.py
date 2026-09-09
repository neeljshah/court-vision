"""Score blinded G350 ratings against the sealed G341 shot list."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

LABELS = ("USABLE_WIDE", "CLOSEUP", "CROWD_GRAPHICS", "UNKNOWN")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="ascii") as handle:
        return list(csv.DictReader(handle))


def cohen_kappa(first: list[str], second: list[str]) -> float:
    if len(first) != len(second) or not first:
        raise ValueError("kappa requires equal nonempty ratings")
    observed = sum(a == b for a, b in zip(first, second)) / len(first)
    left, right = Counter(first), Counter(second)
    expected = sum(left[label] * right[label] for label in LABELS) / (len(first) ** 2)
    return 1.0 if expected == 1.0 and observed == 1.0 else (observed - expected) / (1.0 - expected)


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if not total:
        return (float("nan"), float("nan"))
    share = successes / total
    denominator = 1.0 + z * z / total
    centre = (share + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(share * (1 - share) / total + z * z / (4 * total * total)) / denominator
    return centre - radius, centre + radius


def references(selected: list[dict[str, str]], ratings: list[dict[str, str]], adjudications: list[dict[str, str]]) -> tuple[dict[str, str], float]:
    unit_ids = {row["unit_id"] for row in selected}
    by_unit: dict[str, dict[str, str]] = {unit_id: {} for unit_id in unit_ids}
    for row in ratings:
        unit_id, rater, label = row.get("unit_id", ""), row.get("rater", ""), row.get("label", "")
        if unit_id not in by_unit or rater not in ("terra", "sol") or label not in LABELS:
            raise ValueError("invalid primary rating: %r" % row)
        if rater in by_unit[unit_id]:
            raise ValueError("duplicate primary rating: %s/%s" % (unit_id, rater))
        by_unit[unit_id][rater] = label
    if any(set(row) != {"terra", "sol"} for row in by_unit.values()):
        raise ValueError("every selected unit needs terra and sol ratings")
    adjudicated = {row.get("unit_id", ""): row.get("label", "") for row in adjudications}
    final: dict[str, str] = {}
    for unit_id, pair in by_unit.items():
        if pair["terra"] == pair["sol"]:
            final[unit_id] = pair["terra"]
        else:
            label = adjudicated.get(unit_id)
            if label not in LABELS:
                raise ValueError("missing valid adjudication: %s" % unit_id)
            final[unit_id] = label
    ordered = sorted(unit_ids)
    return final, cohen_kappa([by_unit[key]["terra"] for key in ordered], [by_unit[key]["sol"] for key in ordered])


def score(selected: list[dict[str, str]], ratings: list[dict[str, str]], adjudications: list[dict[str, str]]) -> tuple[list[dict[str, object]], dict[str, object]]:
    final, kappa = references(selected, ratings, adjudications)
    table: Counter[tuple[str, str]] = Counter()
    for row in selected:
        table[(row["predicted_class"], final[row["unit_id"]])] += 1
    wide_total = sum(count for (prediction, _), count in table.items() if prediction == "WIDE")
    true_wide = table[("WIDE", "USABLE_WIDE")]
    reference_wide = sum(count for (_, reference), count in table.items() if reference == "USABLE_WIDE")
    precision = true_wide / wide_total if wide_total else float("nan")
    recall = true_wide / reference_wide if reference_wide else float("nan")
    rows = [{"router_class": prediction, "reference_label": reference, "count": "%06d" % table[(prediction, reference)]}
            for prediction in ("WIDE", "CLOSEUP", "CROWD", "UNKNOWN") for reference in LABELS]
    return rows, {"n": len(selected), "kappa": kappa, "true_wide": true_wide, "router_wide": wide_total,
                  "reference_wide": reference_wide, "precision": precision, "precision_wilson": wilson(true_wide, wide_total),
                  "recall": recall, "recall_wilson": wilson(true_wide, reference_wide),
                  "abstention_share": sum(row["predicted_class"] == "UNKNOWN" for row in selected) / len(selected)}


def cut_check(selected: list[dict[str, str]], propagation: list[dict[str, str]]) -> list[dict[str, str]]:
    """Derive cut safety from G341 records: a shot's first chain cannot exceed one."""
    by_key: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in propagation:
        by_key.setdefault((row["section"], row["shot_id"]), []).append(row)
    checks = []
    for row in selected:
        key = (Path(row["source_path"]).name, row["shot_id"])
        records = sorted(by_key.get(key, []), key=lambda item: int(item["frame_index"]))
        if not records:
            raise ValueError("no G341 propagation records for rated shot: %s" % (key,))
        first_chain = int(records[0]["chain_length"])
        checks.append({"unit_id": row["unit_id"], "section": key[0], "shot_id": key[1],
                       "n_steps": "%06d" % len(records), "first_chain_length": "%06d" % first_chain,
                       "cross_cut_chain": "%06d" % int(first_chain > 1)})
    return checks


def main() -> None:
    parser = argparse.ArgumentParser(description="G350 blind rating scorer")
    parser.add_argument("--shots", type=Path, required=True)
    parser.add_argument("--ratings", type=Path, required=True)
    parser.add_argument("--adjudication", type=Path, required=True)
    parser.add_argument("--confusion", type=Path, required=True)
    parser.add_argument("--propagation", type=Path)
    parser.add_argument("--cut-check", type=Path)
    args = parser.parse_args()
    rows, summary = score(read_rows(args.shots), read_rows(args.ratings), read_rows(args.adjudication))
    args.confusion.parent.mkdir(parents=True, exist_ok=True)
    with args.confusion.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=["router_class", "reference_label", "count"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    if (args.propagation is None) != (args.cut_check is None):
        parser.error("--propagation and --cut-check must be supplied together")
    if args.propagation:
        checks = cut_check(read_rows(args.shots), read_rows(args.propagation))
        with args.cut_check.open("w", newline="", encoding="ascii") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(checks[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(checks)
        summary["cross_cut_chains"] = sum(int(row["cross_cut_chain"]) for row in checks)
    print(json.dumps(summary, sort_keys=True, default=list))


if __name__ == "__main__":
    main()
