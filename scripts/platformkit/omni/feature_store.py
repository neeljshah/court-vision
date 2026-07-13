"""scripts.platformkit.omni.feature_store -- persistent as-of feature store.

Parquet-backed, one file per sport: data/omni/feature_store/<sport>.parquet.

Row schema (all required):
    entity          : str    -- entity id (player/team/game, sport-defined)
    key             : str    -- feature name
    value           : float  -- feature value
    knowable_at     : ts     -- when this value became knowable (the leak guard)
    computed_at     : ts     -- when the row was computed/written
    pipeline_version: str    -- producer version tag

This is the persistent counterpart to scripts.platformkit.asof_common's
in-memory Accumulator pattern: that module walks one corpus forward once;
this module PERSISTS as-of feature rows across runs/sports so callers can
later ask "what did we know about (entity, key) as of ts T" without
re-deriving it. Same leak contract: a row is only visible to a query whose
asof_ts >= knowable_at.

Append semantics: read existing parquet (if any) + concat new rows + atomic
tmp-write + os.replace. Fine at current scale.
# ponytail: single-file-per-sport, full read+concat on every put; partition
# by date or move to a real table format if a sport's file gets big enough
# that this read-modify-write gets slow.

PURE pandas/pyarrow + stdlib. ASCII only. No $/edge claims.
"""
from __future__ import annotations

import os
import pathlib
import tempfile
from typing import Sequence

import pandas as pd

_SCHEMA_COLS = ["entity", "key", "value", "knowable_at", "computed_at", "pipeline_version"]
_STORE_ROOT = pathlib.Path("data/omni/feature_store")


def _store_path(sport: str) -> pathlib.Path:
    return _STORE_ROOT / f"{sport}.parquet"


def _write_parquet_atomic(path: pathlib.Path, df: pd.DataFrame) -> None:
    """tmp-in-same-dir + os.replace, mirroring io_atomic's text discipline for binary parquet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".parquet")
    os.close(fd)
    tmp = pathlib.Path(tmp_name)
    try:
        df.to_parquet(tmp, index=False)
        os.replace(str(tmp), str(path))
    except BaseException:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


def _validate_schema(df: pd.DataFrame) -> None:
    missing_cols = [c for c in _SCHEMA_COLS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"feature rows missing required columns: {missing_cols}")
    if df["knowable_at"].isna().any():
        n_bad = int(df["knowable_at"].isna().sum())
        raise ValueError(f"{n_bad} row(s) missing knowable_at -- rejected (leak-guard input contract)")


def put_features(sport: str, df: pd.DataFrame) -> int:
    """Validate + append feature rows for *sport*. Returns total row count after write.

    Rejects (raises ValueError) if required columns are absent or any row has a
    null knowable_at -- a feature store row that can never be as-of-queried
    safely must never be written silently.
    """
    _validate_schema(df)
    new_rows = df[_SCHEMA_COLS].copy()
    new_rows["knowable_at"] = pd.to_datetime(new_rows["knowable_at"], utc=True)
    new_rows["computed_at"] = pd.to_datetime(new_rows["computed_at"], utc=True)

    path = _store_path(sport)
    if path.is_file():
        existing = pd.read_parquet(path)
        combined = pd.concat([existing, new_rows], ignore_index=True)
    else:
        combined = new_rows.reset_index(drop=True)

    _write_parquet_atomic(path, combined)
    return len(combined)


def get_asof(
    sport: str,
    entities: Sequence[str],
    keys: Sequence[str],
    asof_ts,
) -> pd.DataFrame:
    """Return the latest row per (entity, key) with knowable_at <= asof_ts.

    Rows with knowable_at > asof_ts are never returned -- the leak guard.
    Missing (entity, key) pairs are simply absent from the result; callers
    that need to fail loudly on missing coverage should call
    ``assert_coverage`` on the result.
    """
    path = _store_path(sport)
    if not path.is_file():
        return pd.DataFrame(columns=_SCHEMA_COLS)

    df = pd.read_parquet(path)
    asof_ts = pd.Timestamp(asof_ts)
    if asof_ts.tzinfo is None:
        asof_ts = asof_ts.tz_localize("UTC")
    else:
        asof_ts = asof_ts.tz_convert("UTC")

    mask = (
        df["entity"].isin(list(entities))
        & df["key"].isin(list(keys))
        & (df["knowable_at"] <= asof_ts)
    )
    visible = df.loc[mask]
    if visible.empty:
        return pd.DataFrame(columns=_SCHEMA_COLS)

    # Latest knowable_at per (entity, key); tie-break on computed_at (later write wins).
    ordered = visible.sort_values(["knowable_at", "computed_at"], kind="mergesort")
    latest = ordered.groupby(["entity", "key"], as_index=False).tail(1)
    return latest.reset_index(drop=True)


def assert_coverage(df: pd.DataFrame, entities: Sequence[str], keys: Sequence[str]) -> None:
    """Raise ValueError if any requested (entity, key) pair is absent from *df*.

    Never let a caller silently treat "missing" as 0.0 -- a coverage gap must
    surface as a loud failure, not a quiet wrong number.
    """
    have = set(zip(df["entity"], df["key"]))
    want = {(e, k) for e in entities for k in keys}
    missing = want - have
    if missing:
        raise ValueError(f"missing feature coverage for {len(missing)} (entity, key) pair(s): {sorted(missing)}")


__all__ = ["put_features", "get_asof", "assert_coverage"]
