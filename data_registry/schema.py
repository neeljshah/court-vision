"""data_registry.schema -- typed census rows + drift findings + stable hashing.

Pure dataclasses and helpers; no I/O. ``CensusRow`` is the per-corpus fingerprint
the inventory persists; ``DriftFinding`` is one detected problem. ASCII only.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Dict, List

# Severity levels. "block" fails the fail-closed gate; "warn" is surfaced only.
SEV_BLOCK = "block"
SEV_WARN = "warn"


@dataclass(frozen=True)
class CensusRow:
    """Fingerprint of one corpus file (metadata-only; never loads row data)."""

    sport: str
    name: str                       # file stem, e.g. "games"
    path: str                       # repo-relative path
    n_rows: int
    n_cols: int
    columns: Dict[str, str]         # column name -> arrow dtype string
    schema_hash: str                # stable hash of sorted (col:dtype)
    is_empty: bool

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "CensusRow":
        return CensusRow(
            sport=d["sport"], name=d["name"], path=d["path"],
            n_rows=int(d["n_rows"]), n_cols=int(d["n_cols"]),
            columns=dict(d["columns"]), schema_hash=d["schema_hash"],
            is_empty=bool(d["is_empty"]),
        )


@dataclass(frozen=True)
class DriftFinding:
    """One detected census problem (0-row, missing corpus, schema/row drift)."""

    sport: str
    name: str
    kind: str            # zero_rows | missing_corpus | removed_columns | row_regression | schema_change
    severity: str        # SEV_BLOCK | SEV_WARN
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)

    def __str__(self) -> str:  # ASCII one-liner for CLI output
        return f"[{self.severity}] {self.sport}/{self.name} {self.kind}: {self.detail}"


def schema_hash(columns: Dict[str, str]) -> str:
    """Stable 16-hex-char hash of the sorted (column:dtype) signature."""
    sig = "|".join(f"{c}:{columns[c]}" for c in sorted(columns))
    return hashlib.sha1(sig.encode("ascii", "replace")).hexdigest()[:16]


def make_census_row(
    sport: str, name: str, path: str, n_rows: int, columns: Dict[str, str]
) -> CensusRow:
    """Build a CensusRow, computing n_cols / schema_hash / is_empty consistently."""
    return CensusRow(
        sport=sport,
        name=name,
        path=path,
        n_rows=int(n_rows),
        n_cols=len(columns),
        columns=dict(columns),
        schema_hash=schema_hash(columns),
        is_empty=(int(n_rows) == 0),
    )
