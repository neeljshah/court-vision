"""Read-only AS-OF census for the atlas and intelligence parquet pools.

The helper examines one parquet store at a time and never opens a store over the
300 MB S223 rail. It writes a stable JSON artifact outside ``data/``; a missing,
oversize, or unreadable declared path remains a named row rather than vanishing.

Run: python -m scripts.platformkit.intel_pool_asof_census
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import pandas as pd
import pyarrow.parquet as pq

MAX_STORE_BYTES = 300 * 1024 * 1024
ATLAS_GLOB = "data/cache/atlas_*.parquet"
INTELLIGENCE_GLOB = "data/intelligence/*.parquet"
ASOF_COLUMNS = ("as_of", "asof_date", "as_of_date", "asof")
DATE_COLUMNS = ASOF_COLUMNS + ("game_date", "date")
GRAIN_COLUMNS = (
    "game_id", "event_id", "player_id", "team_id", "team_tricode",
    "opp_team_id", "opponent_id", "stat", "period", "game_clock_s",
    "seconds_remaining", "asof_date", "as_of", "as_of_date", "game_date",
    "date",
)


def _relative(root: Path, path: Path) -> str:
    """Return a stable, slash-separated repository-relative path."""
    # Do not resolve ``data/``: this checkout uses a directory link whose target
    # is outside the worktree, while its declared store path is inside it.
    return path.relative_to(root).as_posix()


def _producer_map() -> dict[str, str]:
    """Map known intelligence artifact basenames to their producer or ``NONE``."""
    from scripts.platformkit.mcp_server.intelligence_producers import (
        NO_PRODUCER,
        PRODUCERS,
    )

    result = {name: script for script, names in PRODUCERS.items() for name in names}
    result.update({name: "NONE" for name in NO_PRODUCER})
    return result


def declared_store_paths(root: Path) -> list[tuple[str, Path]]:
    """List every present S223 store, or a named no-match declaration per pool."""
    declared = (("atlas", ATLAS_GLOB), ("intelligence", INTELLIGENCE_GLOB))
    paths: list[tuple[str, Path]] = []
    for category, pattern in declared:
        matches = sorted(root.glob(pattern))
        if matches:
            paths.extend((category, path) for path in matches)
        else:
            paths.append((category, root / pattern))
    return paths


def _column_name(columns: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    lower = {column.lower(): column for column in columns}
    return next((lower[name] for name in candidates if name in lower), None)


def _date_bounds(parquet: pq.ParquetFile, column: str) -> tuple[Optional[str], Optional[str], int]:
    """Stream the selected temporal column from every row group."""
    distinct: set[str] = set()
    for batch in parquet.iter_batches(columns=[column], batch_size=1000):
        values = pd.to_datetime(batch.column(0).to_pandas(), errors="coerce").dropna()
        distinct.update(str(value.date()) for value in values)
    if not distinct:
        return None, None, 0
    return min(distinct), max(distinct), len(distinct)


def _grain(columns: Sequence[str]) -> list[str]:
    lower = {column.lower(): column for column in columns}
    return [lower[name] for name in GRAIN_COLUMNS if name in lower]


def _temporal_fields(columns: Sequence[str]) -> list[str]:
    """Return every recognized temporal field in the store's own spelling."""
    lower = {column.lower(): column for column in columns}
    names = []
    for name in DATE_COLUMNS:
        actual = lower.get(name)
        if actual is not None and actual not in names:
            names.append(actual)
    return names


def _base_row(path: Path, category: str, producer: str) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "category": category,
        "size_bytes": None,
        "rows": None,
        "n_cols": None,
        "grain_key_columns": [],
        "temporal_fields": [],
        "classification_field": None,
        "as_of_column": None,
        "n_distinct_as_of": None,
        "date_column": None,
        "date_min": None,
        "date_max": None,
        "label": "UNDATED",
        "producer_module": producer,
        "error": None,
    }


def inspect_store(root: Path, category: str, path: Path, producer: str = "NONE") -> dict[str, Any]:
    """Census one parquet store without opening another store concurrently."""
    row = _base_row(Path(_relative(root, path)), category, producer)
    if not path.exists():
        row["error"] = "NO_MATCHING_FILES: declared path is absent"
        return row
    size = path.stat().st_size
    row["size_bytes"] = size
    if size > MAX_STORE_BYTES:
        row["error"] = "OVER_300_MB: {0} bytes exceeds {1}".format(size, MAX_STORE_BYTES)
        return row
    try:
        parquet = pq.ParquetFile(path)
        columns = list(parquet.schema_arrow.names)
        row["rows"] = int(parquet.metadata.num_rows)
        row["n_cols"] = len(columns)
        row["grain_key_columns"] = _grain(columns)
        row["temporal_fields"] = _temporal_fields(columns)
        asof_column = _column_name(columns, ASOF_COLUMNS)
        date_column = asof_column or _column_name(columns, DATE_COLUMNS)
        row["classification_field"] = date_column
        row["as_of_column"] = asof_column or date_column
        row["date_column"] = date_column
        if date_column is None:
            return row
        date_min, date_max, n_distinct = _date_bounds(parquet, date_column)
        row["date_min"] = date_min
        row["date_max"] = date_max
        row["n_distinct_as_of"] = n_distinct
        if asof_column and n_distinct == 1:
            row["label"] = "SNAPSHOT-ONLY"
        elif n_distinct > 1:
            row["label"] = "AS-OF SAFE"
        return row
    except Exception as exc:  # A census must preserve every unreadable path.
        row["error"] = "UNREADABLE: {0}: {1}".format(type(exc).__name__, str(exc))
        return row


def collect_census(
    root: Path, declared: Optional[Iterable[tuple[str, Path]]] = None,
) -> list[dict[str, Any]]:
    """Inspect declared stores serially and return stable path-sorted census rows."""
    producers = _producer_map()
    entries = declared_store_paths(root) if declared is None else list(declared)
    rows = []
    for category, path in entries:
        producer = producers.get(path.name, "NONE")
        rows.append(inspect_store(root, category, path, producer))
    return sorted(rows, key=lambda item: item["path"])


def recount_checkpoints(root: Path, atlas_as_of: Optional[str]) -> dict[str, Any]:
    """Count checkpoint games and ticks strictly after the supplied atlas date."""
    path = root / "data/cache/inplay_odds/nba_checkpoints_full.parquet"
    result: dict[str, Any] = {
        "path": _relative(root, path), "atlas_as_of": atlas_as_of,
        "n_games": None, "post_as_of_games": None, "post_as_of_ticks": None,
        "error": None,
    }
    if atlas_as_of is None:
        result["error"] = "ATLAS_AS_OF_UNKNOWN: no singleton atlas date supplied"
        return result
    if not path.exists():
        result["error"] = "MISSING_CHECKPOINT_STORE"
        return result
    if path.stat().st_size > MAX_STORE_BYTES:
        result["error"] = "CHECKPOINT_STORE_OVER_300_MB"
        return result
    try:
        parquet = pq.ParquetFile(path)
        cutoff = pd.Timestamp(atlas_as_of)
        game_ids: set[Any] = set()
        post_game_ids: set[Any] = set()
        post_ticks = 0
        for batch in parquet.iter_batches(columns=["game_id", "game_date"], batch_size=1000):
            frame = batch.to_pandas()
            dates = pd.to_datetime(frame["game_date"], errors="coerce")
            post = dates > cutoff
            game_ids.update(frame["game_id"].dropna())
            post_game_ids.update(frame.loc[post, "game_id"].dropna())
            post_ticks += int(post.sum())
        result["n_games"] = len(game_ids)
        result["post_as_of_games"] = len(post_game_ids)
        result["post_as_of_ticks"] = post_ticks
        return result
    except Exception as exc:
        result["error"] = "UNREADABLE: {0}: {1}".format(type(exc).__name__, str(exc))
        return result


def build_artifact(root: Path, atlas_as_of: Optional[str]) -> dict[str, Any]:
    """Build the deterministic S223 JSON payload without modifying any data store."""
    census = collect_census(root)
    return {
        "contract": "docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q",
        "declared_patterns": [ATLAS_GLOB, INTELLIGENCE_GLOB],
        "max_store_bytes": MAX_STORE_BYTES,
        "stores": census,
        "counts_by_label": {
            label: sum(row["label"] == label for row in census)
            for label in ("AS-OF SAFE", "SNAPSHOT-ONLY", "UNDATED")
        },
        "checkpoint_recount": recount_checkpoints(root, atlas_as_of),
    }


def write_artifact(artifact: dict[str, Any], output: Path) -> None:
    """Write stable ASCII JSON to an explicit non-data output path."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only S223 intelligence AS-OF census")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path,
                        default=Path("docs/evidence/harness/S223_intel_pool_asof_census_2026-09-04.json"))
    parser.add_argument("--atlas-as-of", default="2026-05-31")
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    artifact = build_artifact(root, args.atlas_as_of)
    write_artifact(artifact, output)
    for row in artifact["stores"]:
        print("{path}\t{size}\t{label}\t{field}\t{n}\t{producer}\t{error}".format(
            path=row["path"], size=row["size_bytes"], label=row["label"],
            field=row["classification_field"], n=row["n_distinct_as_of"],
            producer=row["producer_module"], error=row["error"] or ""))
    print(json.dumps(artifact["checkpoint_recount"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
