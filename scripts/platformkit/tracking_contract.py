"""Normalize tracking tables into the platform tracking contract.

The contract is intentionally limited to structural validation.  It does not
claim tracking accuracy or judge sport-specific quality thresholds.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


CANONICAL_SPORTS = frozenset({
    "basketball", "wnba", "tennis", "soccer", "baseball", "npb", "kbo",
    "football",
})
REQUIRED_COLUMNS = ("frame", "track_id", "cls", "x", "y")
ALIASES = {"player_id": "track_id", "ft_x": "x", "ft_y": "y"}


@dataclass(frozen=True)
class TrackingContractReport:
    """JSON-serializable structural result for one tracking input."""

    canonical_sport: str | None
    coordinate_units: str
    required_columns: list[str]
    row_count: int
    frame_count: int
    duplicate_key_count: int
    status: str
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Return the report as a plain JSON-compatible mapping."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialize the report with deterministic key ordering."""
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


def _load_table(source: str | Path | pd.DataFrame) -> tuple[pd.DataFrame, str | None]:
    if isinstance(source, pd.DataFrame):
        return source.copy(), None
    path = Path(source)
    if not path.exists():
        return pd.DataFrame(), f"input not found: {path}"
    try:
        if path.suffix.lower() in {".parquet", ".pq"}:
            return pd.read_parquet(path), None
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path), None
    except (OSError, ValueError, ImportError) as exc:
        return pd.DataFrame(), f"could not read input: {exc}"
    return pd.DataFrame(), "input must be a CSV or Parquet table"


def _normalize_columns(table: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Apply only documented aliases and reject ambiguous alias pairs."""
    errors: list[str] = []
    rename: dict[str, str] = {}
    for alias, canonical in ALIASES.items():
        if alias in table.columns and canonical in table.columns:
            errors.append(f"ambiguous aliases for {canonical}: {alias} and {canonical}")
        elif alias in table.columns:
            rename[alias] = canonical
    return table.rename(columns=rename), errors


def normalize_tracking_table(
    source: str | Path | pd.DataFrame,
    sport: str,
    coordinate_units: str | None = None,
) -> tuple[pd.DataFrame, TrackingContractReport]:
    """Return canonical tracking rows and their fail-closed validation report.

    A missing input is ``DATA_PENDING``. Structural problems are ``REJECT``;
    otherwise a non-empty, canonical table is ``PASS``.
    """
    units = coordinate_units.strip() if isinstance(coordinate_units, str) else "unspecified"
    units = units or "unspecified"
    table, load_error = _load_table(source)
    canonical_sport = sport.lower().strip() if isinstance(sport, str) else None
    errors: list[str] = []
    input_pending = False
    if load_error:
        input_pending = load_error.startswith("input not found")
        errors.append(load_error)
    if canonical_sport not in CANONICAL_SPORTS:
        errors.append(f"unknown sport: {sport}")
    if input_pending:
        normalized = pd.DataFrame(columns=REQUIRED_COLUMNS)
        missing: list[str] = []
    else:
        normalized, alias_errors = _normalize_columns(table)
        errors.extend(alias_errors)
        missing = [column for column in REQUIRED_COLUMNS if column not in normalized.columns]
    if missing:
        errors.append("missing required columns: " + ", ".join(missing))
    if not missing:
        normalized = normalized.loc[:, REQUIRED_COLUMNS].copy()
        player_rows = normalized["cls"].astype(str).str.lower().eq("player")
        if player_rows.any():
            numeric = normalized.loc[player_rows, ["x", "y"]].apply(
                pd.to_numeric, errors="coerce"
            )
            if not np.isfinite(numeric.to_numpy(dtype=float)).all():
                errors.append("non-finite player coordinates")
    else:
        normalized = pd.DataFrame(columns=REQUIRED_COLUMNS)

    row_count = int(len(normalized))
    frame_count = int(normalized["frame"].nunique(dropna=True)) if not missing else 0
    duplicate_key_count = (
        int(normalized.duplicated(["frame", "track_id"]).sum()) if not missing else 0
    )
    if input_pending:
        status = "DATA_PENDING"
    elif row_count == 0 and not errors:
        status = "DATA_PENDING"
        errors.append("input contains no tracking rows")
    else:
        status = "PASS"
    if any(error != load_error and error != "input contains no tracking rows" for error in errors):
        status = "REJECT"
    report = TrackingContractReport(
        canonical_sport if canonical_sport in CANONICAL_SPORTS else None,
        units,
        list(REQUIRED_COLUMNS),
        row_count,
        frame_count,
        duplicate_key_count,
        status,
        errors,
    )
    return normalized, report


def main(argv: list[str] | None = None) -> int:
    """Normalize a CSV/Parquet file and print or write its JSON report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("table")
    parser.add_argument("sport")
    parser.add_argument("--coordinate-units")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    _, report = normalize_tracking_table(args.table, args.sport, args.coordinate_units)
    payload = report.to_json() + "\n"
    if args.report:
        args.report.write_text(payload, encoding="ascii")
    else:
        print(payload, end="")
    return 0 if report.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
