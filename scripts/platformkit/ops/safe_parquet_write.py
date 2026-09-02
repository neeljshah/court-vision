"""scripts.platformkit.ops.safe_parquet_write -- refuse-to-shrink parquet write.

S95 (from the S91 truncation post-mortem). Every domains/*/ingest_*.py ends the
same way: read the existing parquet, concat + dedup the new batch onto it, then
``df.to_parquet(out, index=False)``. Two failure modes in that shape destroyed
data on disk:

  1. the read of the existing file was wrapped in ``except Exception`` that only
     logged "-- overwriting", so a single unreadable/torn file made the current
     batch REPLACE the entire corpus. That is how
     data/domains/mlb/espn_boxscores.parquet ended up holding 2 rows (the
     2026-07-14..07-16 All-Star-break batch) in place of ~3 weeks of finals --
     see docs/evidence/harness/S91_mlb_outcome_source_2026-09-03.md.
  2. ``to_parquet`` writes in place, so a crash mid-write leaves a torn target
     that the NEXT run then fails to read -> mode 1 -> total loss.

``write_parquet_atomic`` closes both:

  * temp file in the SAME directory + ``os.replace`` -- a reader sees the old
    complete file or the new complete file, never a torn one, and a failed
    write removes its temp and leaves the target untouched.
  * a row-count precondition: replacing an existing parquet with a SMALLER one
    raises :class:`ShrinkRefused` unless the caller passes ``allow_shrink=True``.
    The existing count is read from the parquet FOOTER (metadata only, no full
    load); if that read fails the exception PROPAGATES -- an unreadable existing
    file is never silently overwritten.

WHY REFUSING TO SHRINK IS SAFE FOR THESE WRITERS: each one concats existing+new
and dedups keep="last", so the merged frame is a superset of the rows on disk
and its count can only grow or stay equal. A shrink means the merge did not
happen -- exactly the S91 bug. A deliberate rebuild/prune passes allow_shrink.

INVARIANTS: additive (no existing behaviour changes on the happy path);
<=300 LOC; no $ / ROI / edge language; never writes data/registry/.

Test: cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/ops/test_safe_parquet_write.py -q
"""
from __future__ import annotations

import logging
import os
import pathlib
import tempfile
import time
from typing import Any, Union

log = logging.getLogger(__name__)

PathLike = Union[str, "os.PathLike[str]"]

_REPLACE_ATTEMPTS = 6
_REPLACE_BACKOFF_S = 0.25


class ShrinkRefused(RuntimeError):
    """Raised when a write would replace an existing parquet with fewer rows."""


def existing_row_count(path: pathlib.Path) -> int:
    """Row count of an existing parquet, from its footer metadata only.

    Raises whatever pyarrow raises on a missing/torn/unreadable file -- callers
    MUST NOT swallow it, that swallow is the S91 defect.
    """
    import pyarrow.parquet as pq
    return int(pq.ParquetFile(str(path)).metadata.num_rows)


def write_parquet_atomic(df: Any, path: PathLike, *,
                         allow_shrink: bool = False) -> pathlib.Path:
    """Atomically write *df* to *path*, refusing to shrink an existing parquet.

    Returns the written path. Raises ShrinkRefused if the target exists with
    more rows than *df* and ``allow_shrink`` is False; propagates any error
    from reading the existing footer or from the write itself.
    """
    target = pathlib.Path(os.fspath(path))
    if target.exists() and not allow_shrink:
        n_old = existing_row_count(target)  # unreadable -> raises, never overwrites
        if len(df) < n_old:
            log.error("ShrinkRefused: %s holds %d rows, refusing to write %d",
                      target, n_old, len(df))
            raise ShrinkRefused(
                "%s holds %d rows; refusing to replace it with %d "
                "(pass allow_shrink=True for a deliberate rebuild)"
                % (target, n_old, len(df)))
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=".tmp_",
                                    suffix=".parquet")
    os.close(fd)  # pandas/pyarrow write by path, not by descriptor
    tmp = pathlib.Path(tmp_name)
    try:
        df.to_parquet(tmp, index=False)
        # Windows: os.replace can hit WinError 5 while another lane briefly holds
        # the target open. Bounded backoff turns contention into a wait; still
        # fails closed. ponytail: same 6-try shape as io_atomic._replace_via_tmp.
        for attempt in range(_REPLACE_ATTEMPTS):
            try:
                os.replace(str(tmp), str(target))
                break
            except PermissionError:
                if attempt == _REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(_REPLACE_BACKOFF_S * (attempt + 1))
    except BaseException:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise
    return target


__all__ = ["ShrinkRefused", "existing_row_count", "write_parquet_atomic"]
