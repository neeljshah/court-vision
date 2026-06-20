"""scripts.platformkit.feature_spec_core -- the versioned train==inference parity seam.

A FeatureSpec is the SINGLE SOURCE OF TRUTH for one sport's base feature matrix:
the ordered list of named columns, their source column in the walk-forward frame,
the per-column default (applied only when the source column is ABSENT, matching the
adapters' ``row.get(src, default)`` convention), and the cast. Train and inference
both call build_base_matrix, so the column set + order can never silently diverge --
the most expensive bug class in this codebase (silent zero-feature / misaligned width).

This module is sport-blind. Each sport declares its spec in
domains/<sport>/feature_spec.py.

PURE pandas/numpy. No src/kernel/api imports. ASCII only.
ACCURACY ONLY -- NO MARKET EDGE CLAIMED.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

# Supported casts.
CAST_FLOAT = "float"            # float(value); NaN passes through
CAST_BOOL_FLOAT = "bool_float"  # float(bool(value)); mirrors adapter b2b flags
_CASTS = (CAST_FLOAT, CAST_BOOL_FLOAT)

# Supported ops.
OP_IDENTITY = "identity"        # value = col(source)
OP_DIFF = "diff"                # value = col(source) - col(source2) (e.g. p1_elo - p2_elo)
_OPS = (OP_IDENTITY, OP_DIFF)


@dataclass(frozen=True)
class FeatureField:
    """One column in a base feature matrix.

    name    : output column name (the catalog key).
    source  : column read from the walk-forward DataFrame.
    default : value used ONLY when a source column is absent from the frame. None
              means the source is REQUIRED -- an absent source raises (never
              silent-zero). For OP_DIFF the same default fills EITHER absent operand.
    cast    : CAST_FLOAT or CAST_BOOL_FLOAT (applied per operand, then the op).
    source2 : second operand column for OP_DIFF (else None).
    op      : OP_IDENTITY or OP_DIFF.
    """

    name: str
    source: str
    default: Optional[float] = None
    cast: str = CAST_FLOAT
    source2: Optional[str] = None
    op: str = OP_IDENTITY

    def __post_init__(self) -> None:
        if self.cast not in _CASTS:
            raise ValueError(f"unknown cast {self.cast!r} for field {self.name!r}")
        if self.op not in _OPS:
            raise ValueError(f"unknown op {self.op!r} for field {self.name!r}")
        if self.op == OP_DIFF and not self.source2:
            raise ValueError(f"op=diff requires source2 for field {self.name!r}")


@dataclass(frozen=True)
class FeatureSpec:
    """Versioned, ordered feature contract for one sport's base matrix."""

    sport: str
    version: str
    fields: Tuple[FeatureField, ...]

    def col_names(self) -> List[str]:
        return [f.name for f in self.fields]

    def n_features(self) -> int:
        return len(self.fields)

    def catalog_hash(self) -> str:
        """Stable 16-hex hash of (version + each field's name|source|default|cast[+op|source2]).

        The op/source2 suffix is appended ONLY for non-identity fields, so an
        identity-only catalog (e.g. NBA) hashes the same before and after the diff-op
        extension landed.
        """
        parts = [self.version]
        for f in self.fields:
            base = f"{f.name}|{f.source}|{f.default}|{f.cast}"
            if f.op != OP_IDENTITY:
                base += f"|{f.op}|{f.source2}"
            parts.append(base)
        sig = "||".join(parts)
        return hashlib.sha1(sig.encode("ascii", "replace")).hexdigest()[:16]


def _extract(spec: FeatureSpec, df: pd.DataFrame, field: FeatureField,
             src: str, n: int) -> np.ndarray:
    """Extract one operand column with column-level default + cast (float64)."""
    if src not in df.columns:
        if field.default is None:
            raise KeyError(
                f"{spec.sport} feature_spec: required source {src!r} "
                f"absent for field {field.name!r} (would silent-zero)."
            )
        fill = float(bool(field.default)) if field.cast == CAST_BOOL_FLOAT else float(field.default)
        return np.full(n, fill, dtype="float64")
    s = df[src]
    if field.cast == CAST_BOOL_FLOAT:
        return np.array([float(bool(v)) for v in s], dtype="float64")
    return s.astype("float64").to_numpy()


def build_base_matrix(spec: FeatureSpec, df: pd.DataFrame) -> Tuple[np.ndarray, List[str]]:
    """Build the base matrix for ``spec`` from a walk-forward frame.

    Guarantees: columns in spec order; required-source absence raises; a present
    source's NaN values pass through (default applies only to an absent column) --
    byte-identical to the per-row ``float(row.get(src, default))`` adapters use.
    OP_DIFF fields subtract two operands extracted under the same default/cast.
    Returns (matrix [n_rows, n_features] float64, col_names).
    """
    n = len(df)
    cols: List[np.ndarray] = []
    for f in spec.fields:
        a = _extract(spec, df, f, f.source, n)
        if f.op == OP_DIFF:
            cols.append(a - _extract(spec, df, f, f.source2, n))
        else:
            cols.append(a)
    mat = np.column_stack(cols) if cols else np.empty((n, 0), dtype="float64")
    return mat, spec.col_names()


def assert_matches_catalog(spec: FeatureSpec, col_names: Sequence[str]) -> None:
    """Raise AssertionError if ``col_names`` != the frozen catalog (order-sensitive)."""
    expected = spec.col_names()
    if list(col_names) != expected:
        raise AssertionError(
            f"{spec.sport} feature parity FAILED: "
            f"got {list(col_names)} != catalog {expected}"
        )
