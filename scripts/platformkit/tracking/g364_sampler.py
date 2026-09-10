"""Sampling and split guards for the frozen G364 court-presence head."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


PREDICTIONS = ("COURT", "NON_COURT", "ABSTAIN")


def interior_indices(frame_count: int, count: int) -> list[int]:
    """Return count evenly spaced strict-interior positions, never a head slice."""
    if frame_count < 3 or count < 1:
        raise ValueError("section needs at least three frames and one requested index")
    last = frame_count - 1
    indices = [((position + 1) * last) // (count + 1) for position in range(count)]
    if len(set(indices)) != count or indices[0] <= 0 or indices[-1] >= last:
        raise ValueError("section is too short for unique interior samples")
    return indices


def frame_key(row: dict[str, str]) -> str:
    """Return the stable per-tick key required for evidence and evaluator states."""
    required = ("source_sha256", "section_id", "frame_index")
    if any(not row.get(field) for field in required):
        raise ValueError("frame key requires source_sha256, section_id, and frame_index")
    return ":".join(row[field] for field in required)


def assert_game_disjoint(development: list[dict[str, str]],
                         validation: list[dict[str, str]]) -> None:
    """Reject any overlapping game identifier across the sealed split."""
    left = {row.get("game_id", "") for row in development}
    right = {row.get("game_id", "") for row in validation}
    overlap = sorted((left & right) - {""})
    if overlap:
        raise ValueError("development and validation games overlap: " + ",".join(overlap))


def evenly_pick(rows: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    """Pick rows across the full sorted population using strict interior positions."""
    ordered = sorted(rows, key=lambda row: (row["section_id"], int(row["frame_index"])))
    if count > len(ordered):
        raise ValueError("requested quota exceeds available frozen predictions")
    if count == len(ordered):
        return ordered
    positions = interior_indices(len(ordered), count)
    return [ordered[position] for position in positions]


def validation_quota(rows: list[dict[str, str]], total: int = 300) -> list[dict[str, str]]:
    """Select frozen predictions with the preregistered court/non-court quotas."""
    if total < 120:
        raise ValueError("validation total cannot satisfy both 60-frame quotas")
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        prediction = row.get("prediction", "")
        if prediction not in PREDICTIONS:
            raise ValueError("unknown frozen prediction: " + prediction)
        groups[prediction].append(row)
    selected = evenly_pick(groups["COURT"], 60) + evenly_pick(groups["NON_COURT"], 60)
    selected += evenly_pick(groups["ABSTAIN"], total - len(selected))
    keys = [frame_key(row) for row in selected]
    if len(set(keys)) != len(keys):
        raise ValueError("validation manifest has duplicate frame keys")
    return sorted(selected, key=frame_key)


def sample_sections(sections: list[dict[str, str]], per_section: int = 12) -> list[dict[str, str]]:
    """Expand every pinned section into its fixed evenly spaced interior frames."""
    output: list[dict[str, str]] = []
    for row in sections:
        for required in ("source_sha256", "source_path", "section_id", "game_id", "competition", "frame_count"):
            if not row.get(required):
                raise ValueError("section is missing " + required)
        for index in interior_indices(int(row["frame_count"]), per_section):
            output.append({**row, "frame_index": "%06d" % index})
    keys = [frame_key(row) for row in output]
    if len(keys) != len(set(keys)):
        raise ValueError("section manifest creates duplicate stable frame keys")
    return sorted(output, key=frame_key)


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read one bounded manifest CSV in text mode."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    """Write an LF manifest with an additive stable frame key."""
    if not rows:
        raise ValueError("refusing to write an empty validation manifest")
    fields = list(rows[0])
    if "frame_key" not in fields:
        fields.append("frame_key")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "frame_key": frame_key(row)})


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="G364 frozen-prediction validation sampler")
    parser.add_argument("action", choices=("interior", "validation"))
    parser.add_argument("--sections", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--development", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--total", type=int, default=300)
    parser.add_argument("--per-section", type=int, default=12)
    args = parser.parse_args()
    if args.action == "interior":
        if args.sections is None:
            parser.error("--sections is required for interior")
        selected = sample_sections(read_csv(args.sections), args.per_section)
    else:
        if args.predictions is None or args.development is None:
            parser.error("--predictions and --development are required for validation")
        development, selected = read_csv(args.development), validation_quota(read_csv(args.predictions), args.total)
        assert_game_disjoint(development, selected)
    write_csv(args.out, selected)
    print("validation_frames=%d sections=%d games=%d competitions=%d" % (
        len(selected), len({row["section_id"] for row in selected}),
        len({row["game_id"] for row in selected}), len({row["competition"] for row in selected})))


if __name__ == "__main__":
    main()
