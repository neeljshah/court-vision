"""Census-only adapters for every in-play price/checkpoint parquet under data/cache/inplay_odds/."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable

from scripts.platformkit.eval_gate.adapter_contract import CENSUS_FIELDS

_DIRECT = {
    "sport": {"sport"}, "venue": {"venue"}, "game_id": {"ticker_or_slug"}, "target_id": {"market_type", "side"},
    "event_id": {"event_key"}, "event_time": {"ts"}, "m0_time": {"ts"},
    "m0_probabilities": {"prob"}, "outcome": {"result_where_known"},
}
_DERIVABLE = {
    "league", "season", "corpus", "class_order", "sequence", "received_at",
    "feature_available_at", "prediction_at", "provenance", "m0_source", "state_key",
    "input_hash", "code_hash", "seal_hash",
}
# Additive alias table (fix 1d, 2026-09-08): a field is AVAILABLE if ANY listed alias
# column name is present, even when the exact field name is not. Verified via metadata-only
# schema reads of the real stores under data/cache/inplay_odds/ -- see the memo's Corrections
# section for which columns were checked and why only this one alias was added.
_ALIASES = {
    "outcome": {"outcome_home_win"},
}


def classify_columns(columns: Iterable[str], field: str) -> str:
    """Return the fixed field-presence classification without opening row values."""
    available = set(columns)
    if field in available:
        return "AVAILABLE"
    if field in _DIRECT and _DIRECT[field].issubset(available):
        return "AVAILABLE"
    if field in _ALIASES and _ALIASES[field] & available:
        return "AVAILABLE"
    if field in _DERIVABLE:
        return "DERIVABLE"
    return "UNAVAILABLE"


def _sport_from_stem(stem: str) -> str:
    """Derive the census sport label from a parquet filename stem (no data read)."""
    token = stem.split("_", 1)[0]
    return token if token in ("soccer", "tennis") else token.upper()


def discover_inplay_parquets(directory: Path) -> list[tuple[str, Path]]:
    """List every *.parquet under directory as (sport, path), sport inferred from the filename."""
    return [(_sport_from_stem(path.stem), path) for path in sorted(Path(directory).glob("*.parquet"))]


def census_price_parquet(path: Path, sport: str) -> list[dict[str, object]]:
    """Read one parquet metadata footer and emit every S323 field classification."""
    import pyarrow.parquet as pq

    source = Path(path)
    parquet = pq.ParquetFile(source)
    columns = parquet.schema.names
    count = int(parquet.metadata.num_rows)
    return [{"sport": sport, "store": source.name, "field": field,
             "availability": classify_columns(columns, field), "n": count}
            for field in CENSUS_FIELDS]


def census_mlb(path: Path) -> list[dict[str, object]]:
    """Census an MLB price store only; no model or outcome is fabricated."""
    return census_price_parquet(path, "MLB")


def census_soccer(path: Path) -> list[dict[str, object]]:
    """Census a soccer price store only; no game companion input is assumed."""
    return census_price_parquet(path, "soccer")


def census_tennis(path: Path) -> list[dict[str, object]]:
    """Census a tennis price store only; no game companion input is assumed."""
    return census_price_parquet(path, "tennis")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", action="append", default=[],
                        help="SPORT=path; repeat once per parquet")
    parser.add_argument("--all-inplay", type=Path,
                        help="census every parquet under this directory; sport inferred from filename")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows: list[dict[str, object]] = []
    store_count = 0
    for source in args.source:
        sport, raw_path = source.split("=", 1)
        rows.extend(census_price_parquet(Path(raw_path), sport))
        store_count += 1
    if args.all_inplay:
        for sport, path in discover_inplay_parquets(args.all_inplay):
            rows.extend(census_price_parquet(path, sport))
            store_count += 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=("sport", "store", "field", "availability", "n"))
        writer.writeheader()
        for row in rows:
            row["n"] = "%06d" % int(row["n"])
            writer.writerow(row)
    print("stores=%d rows=%d" % (store_count, len(rows)))


if __name__ == "__main__":
    main()
