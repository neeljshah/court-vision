"""Reproduce the G154 local tracking-table eligibility census."""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from itertools import chain
from pathlib import Path


MIN_FRAMES_FOR_METRICS = 30
CANONICAL_COLUMNS = frozenset(("frame", "track_id", "cls", "x", "y"))
NBA_PRODUCTION_COLUMNS = frozenset(("frame", "timestamp", "player_id", "team", "x_position", "y_position"))
EXPECTED_SPACES = {
    "baseball": {"court_feet", "metric_local"},
    "basketball": {"court_feet"},
    "football": {"court_feet"},
    "kbo": {"court_feet", "metric_local"},
    "npb": {"court_feet", "metric_local"},
    "soccer": {"pitch_metres"},
    "tennis": {"court_feet"},
    "wnba": {"court_feet"},
}
BLOCKER_ORDER = (
    "unknown_sport_routing",
    "empty_or_header_only",
    "metric_local_scope",
    "coordinate_contract_rejection",
    "missing_required_coordinate_or_schema",
    "INSUFFICIENT_DATA",
    "reaches_gate",
)
ROLLUP_BUCKET = {
    "reaches_gate": "reaches_gate",
    "coordinate_contract_rejection": "coordinate_contract_rejection",
    "INSUFFICIENT_DATA": "INSUFFICIENT_DATA",
    "empty_or_header_only": "empty_or_header_only",
    "unknown_sport_routing": "other",
    "metric_local_scope": "other",
    "missing_required_coordinate_or_schema": "other",
}


@dataclass(frozen=True)
class TableCensus:
    """One exhaustive local tracking table classification."""

    table: str
    sport: str
    data_state: str
    n_frames_when_needed: str
    coordinate_spaces: str
    usable_player_fields: str
    unique_positive_modal_stride: str
    first_blocker: str
    rollup_bucket: str


def sport_for_table(name: str) -> str | None:
    """Infer the existing corpus sport routing from its table-directory name."""
    lowered = name.lower()
    if "tennis" in lowered:
        return "tennis"
    if "wnba" in lowered:
        return "wnba"
    if lowered.startswith(("mlb_", "baseball_")):
        return "baseball"
    for sport in ("football", "soccer", "kbo", "npb"):
        if lowered.startswith(f"{sport}_"):
            return sport
    if re.fullmatch(r"\d+(?:\.f\d+)?", name):
        return "basketball"
    return None


def _positive_modal_stride(player_frames: dict[str, set[int]]) -> int | None:
    gaps = Counter(
        later - earlier
        for frames in player_frames.values()
        for earlier, later in zip(sorted(frames), sorted(frames)[1:])
        if later > earlier
    )
    if not gaps:
        return None
    top = max(gaps.values())
    modes = [gap for gap, count in gaps.items() if count == top]
    return modes[0] if len(modes) == 1 else None


def census_table(path: Path) -> TableCensus:
    """Classify one CSV with G109/G142's frozen first-blocker ordering."""
    sport = sport_for_table(path.parent.name)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        if sport is None and NBA_PRODUCTION_COLUMNS <= fields:
            sport = "basketball"
        first_row = next(reader, None)
        if sport is None:
            return _record(path, sport, "empty" if first_row is None else "nonempty", "", "", None,
                           "unknown_sport_routing")
        if first_row is None:
            return _record(path, sport, "empty", "", "", None, "empty_or_header_only")
        if "coordinate_space" not in fields or not CANONICAL_COLUMNS <= fields:
            return _record(path, sport, "nonempty", "", "", None,
                           "missing_required_coordinate_or_schema")
        rows = 0
        frames: set[str] = set()
        spaces: set[str] = set()
        player_frames: dict[str, set[int]] = defaultdict(set)
        for row in chain((first_row,), reader):
            if not any(value not in (None, "") for value in row.values()):
                continue
            rows += 1
            frame = (row.get("frame") or "").strip()
            if frame:
                frames.add(frame)
            space = (row.get("coordinate_space") or "").strip()
            if space:
                spaces.add(space)
            if (row.get("cls") or "").strip() == "player":
                track_id = (row.get("track_id") or "").strip()
                try:
                    player_frames[track_id].add(int(float(frame)))
                except (TypeError, ValueError):
                    pass

    stride = _positive_modal_stride(player_frames)
    usable_players = bool(player_frames) and all(player_frames)
    if spaces == {"metric_local"}:
        blocker = "metric_local_scope"
    elif spaces and not spaces <= EXPECTED_SPACES[sport]:
        blocker = "coordinate_contract_rejection"
    elif "coordinate_space" not in fields or not spaces or not CANONICAL_COLUMNS <= fields:
        blocker = "missing_required_coordinate_or_schema"
    elif not usable_players or stride is None:
        blocker = "missing_required_coordinate_or_schema"
    elif len(frames) < MIN_FRAMES_FOR_METRICS:
        blocker = "INSUFFICIENT_DATA"
    else:
        blocker = "reaches_gate"
    record = _record(path, sport, "nonempty", "|".join(sorted(spaces)),
                     str(len(frames)), stride, blocker)
    return TableCensus(**{**asdict(record), "usable_player_fields": "yes" if usable_players else "no"})


def _record(path: Path, sport: str | None, data_state: str, spaces: str,
            n_frames: str, stride: int | None, blocker: str) -> TableCensus:
    """Build one classification record without inventing unneeded row totals."""
    return TableCensus(
        table=path.parent.name,
        sport=sport or "UNKNOWN",
        data_state=data_state,
        n_frames_when_needed=n_frames,
        coordinate_spaces=spaces,
        usable_player_fields=("yes" if stride is not None else ""),
        unique_positive_modal_stride=str(stride) if stride is not None else "",
        first_blocker=blocker,
        rollup_bucket=ROLLUP_BUCKET[blocker],
    )


def census_root(tracking_root: Path) -> list[TableCensus]:
    """Enumerate every immediate local `tracking_data.csv` table exactly once."""
    paths = sorted(tracking_root.glob("*/tracking_data.csv"))
    return [census_table(path) for path in paths]


def write_census(rows: list[TableCensus], output_root: Path) -> None:
    """Write per-table and denominator-explicit pooled and sport summaries."""
    output_root.mkdir(parents=True, exist_ok=True)
    denominator = len(rows)
    with (output_root / "table_census.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0]).keys()) if rows else list(TableCensus.__annotations__))
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
    pooled = Counter(row.rollup_bucket for row in rows)
    with (output_root / "bucket_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("first_blocker", "tables", "census_denominator_local_tables", "share_of_census_denominator"))
        writer.writeheader()
        for bucket in ("reaches_gate", "coordinate_contract_rejection", "INSUFFICIENT_DATA", "empty_or_header_only", "other"):
            count = pooled[bucket]
            writer.writerow({"first_blocker": bucket, "tables": count, "census_denominator_local_tables": denominator, "share_of_census_denominator": f"{count / denominator:.6f}" if denominator else ""})
    per_sport: dict[str, Counter[str]] = defaultdict(Counter)
    sport_totals = Counter(row.sport for row in rows)
    for row in rows:
        per_sport[row.sport][row.rollup_bucket] += 1
    with (output_root / "sport_bucket_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("sport", "first_blocker", "tables", "sport_census_denominator_local_tables", "share_of_sport_census_denominator"))
        writer.writeheader()
        for sport in sorted(sport_totals):
            for bucket in ("reaches_gate", "coordinate_contract_rejection", "INSUFFICIENT_DATA", "empty_or_header_only", "other"):
                count, denominator = per_sport[sport][bucket], sport_totals[sport]
                writer.writerow({"sport": sport, "first_blocker": bucket, "tables": count, "sport_census_denominator_local_tables": denominator, "share_of_sport_census_denominator": f"{count / denominator:.6f}"})


def main() -> None:
    """Run the local-only G154 census and emit its reusable CSV artifacts."""
    parser = argparse.ArgumentParser()
    parser.add_argument("tracking_root", type=Path)
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    rows = census_root(args.tracking_root)
    write_census(rows, args.output_root)
    counts = Counter(row.rollup_bucket for row in rows)
    print("local_tables={} reaches_gate={} coordinate_contract_rejection={} insufficient_data={} empty_or_header_only={} other={}".format(
        len(rows), counts["reaches_gate"], counts["coordinate_contract_rejection"], counts["INSUFFICIENT_DATA"], counts["empty_or_header_only"], counts["other"]
    ))


if __name__ == "__main__":
    main()
