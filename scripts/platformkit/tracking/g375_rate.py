"""G375 rating parser: blind rater batches to ratings, kappa and disagreements.

Sealed by `docs/evidence/tracking/g375_corpus_sport_purity_2026-09-10/
g375_prereg_2026-09-10.md` (SEAL sha256
2f178a9d533cd9a36f90477ef5b81d499fbe282708433fa29a55344a830242b2). A token outside
the five sealed labels is kept verbatim in the raw batch file and mapped to UNKNOWN.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from scripts.platformkit.tracking.g375_census import read_csv, write_csv

LABELS = ("BASKETBALL_PLAY", "BASKETBALL_NONPLAY", "OTHER_SPORT", "NON_SPORT", "UNKNOWN")
LINE = re.compile(r"(sheet_\d{4})\.jpg\s*,\s*([A-Za-z_]+)\s*,\s*([A-Za-z ]*?)\s*,\s*(\d+)\s*$")
BATCH = re.compile(r"g375_rater_([a-z]+)_(\d+)")
FIELDS = ("sheet_id", "rater", "label", "other_sport", "confidence_permille", "raw_label")
ADJ_FIELDS = ("sheet_id", "terra_label", "sol_label", "final_label", "other_sport")


def parse_batch(text: str, rater: str) -> dict[str, dict[str, str]]:
    """Take the last well-formed line per sheet; everything else is ignored, not guessed."""
    found: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        match = LINE.search(line.strip())
        if match is None:
            continue
        raw = match.group(2).upper()
        found[match.group(1)] = {
            "sheet_id": match.group(1), "rater": rater,
            "label": raw if raw in LABELS else "UNKNOWN",
            "other_sport": match.group(3).strip().lower(),
            "confidence_permille": match.group(4), "raw_label": match.group(2)}
    return found


def collect(raw_dir: Path) -> list[dict[str, str]]:
    """Read every archived batch output and return one row per rater and sheet."""
    rows: dict[tuple[str, str], dict[str, str]] = {}
    for path in sorted(set(raw_dir.glob("*.log")) | set(raw_dir.glob("*.txt"))):
        match = BATCH.search(path.name)
        if match is None:
            continue
        rater = match.group(1)
        text = path.read_text(encoding="utf-8", errors="replace")
        for sheet_id, row in parse_batch(text, rater).items():
            rows[(rater, sheet_id)] = row
    return [rows[key] for key in sorted(rows)]


def kappa(pairs: list[tuple[str, str]]) -> float:
    """Cohen kappa over the five sealed categories; 1.0 when both raters never vary."""
    if not pairs:
        raise ValueError("kappa needs at least one jointly rated sheet")
    total = len(pairs)
    observed = sum(left == right for left, right in pairs) / total
    left_counts = {label: 0 for label in LABELS}
    right_counts = {label: 0 for label in LABELS}
    for left, right in pairs:
        left_counts[left] = left_counts.get(left, 0) + 1
        right_counts[right] = right_counts.get(right, 0) + 1
    expected = sum(left_counts.get(label, 0) * right_counts.get(label, 0)
                   for label in set(left_counts) | set(right_counts)) / (total * total)
    if expected >= 1.0:
        return 1.0
    return (observed - expected) / (1.0 - expected)


def disagreements(rows: list[dict[str, str]]) -> tuple[list[str], list[tuple[str, str]]]:
    """Return the sheets whose two raters differ, and the jointly rated label pairs."""
    by_sheet: dict[str, dict[str, dict[str, str]]] = {}
    for row in rows:
        by_sheet.setdefault(row["sheet_id"], {})[row["rater"]] = row
    split, pairs = [], []
    for sheet_id in sorted(by_sheet):
        seen = by_sheet[sheet_id]
        if len(seen) < 2:
            continue
        raters = sorted(seen)
        left, right = seen[raters[0]]["label"], seen[raters[1]]["label"]
        pairs.append((left, right))
        if left != right:
            split.append(sheet_id)
    return split, pairs


def final_labels(rows: list[dict[str, str]],
                 adjudicated: dict[str, str]) -> list[dict[str, str]]:
    """Agreement is final unadjudicated; every disagreement needs a blind adjudication."""
    by_sheet: dict[str, dict[str, dict[str, str]]] = {}
    for row in rows:
        by_sheet.setdefault(row["sheet_id"], {})[row["rater"]] = row
    out: list[dict[str, str]] = []
    for sheet_id in sorted(by_sheet):
        seen = by_sheet[sheet_id]
        raters = sorted(seen)
        labels = {seen[name]["label"] for name in raters}
        if len(labels) == 1 and len(raters) >= 2:
            final = labels.pop()
        elif sheet_id in adjudicated:
            final = adjudicated[sheet_id]
        else:
            raise ValueError("sheet %s has no agreement and no adjudication" % sheet_id)
        sports = [seen[name]["other_sport"] for name in raters if seen[name]["other_sport"]]
        out.append({"sheet_id": sheet_id,
                    "terra_label": seen.get("terra", {}).get("label", ""),
                    "sol_label": seen.get("sol", {}).get("label", ""),
                    "final_label": final,
                    "other_sport": sports[0] if sports and final == "OTHER_SPORT" else ""})
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="G375 blind rating parser")
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--ratings", type=Path, required=True)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--adjudication", type=Path)
    args = parser.parse_args()
    rows = collect(args.raw)
    write_csv(args.ratings, rows, FIELDS)
    split, pairs = disagreements(rows)
    print("ratings=%d sheets=%d raters=%d joint=%d disagreements=%d" % (
        len(rows), len({row["sheet_id"] for row in rows}),
        len({row["rater"] for row in rows}), len(pairs), len(split)))
    if pairs:
        print("agreement=%.6f kappa=%.6f" % (
            sum(left == right for left, right in pairs) / len(pairs), kappa(pairs)))
    print("DISAGREEMENTS " + " ".join(split))
    if args.labels is not None:
        adjudicated = {row["sheet_id"]: row["final_label"]
                       for row in (read_csv(args.adjudication)
                                   if args.adjudication and args.adjudication.exists() else [])}
        write_csv(args.labels, final_labels(rows, adjudicated), ADJ_FIELDS)


if __name__ == "__main__":
    main()
