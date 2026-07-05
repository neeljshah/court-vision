"""Atomic parquet-write primitive for basketball_claims.py (split out purely
to stay under the <=300 LOC/file rail -- basketball_claims.py and
basketball_claims_dims.py were both already at the cap).

WHY: pq.write_table writes directly to its destination path and is not
itself atomic. basketball_claims.py's atlas dims build via
ThreadPoolExecutor, and several DimSpecs share a source parquet (read-read,
safe) while each writes its own uniquely-named snapshot -- but a concurrent
reader elsewhere in the same output directory (a previous/parallel
build_all_claims() call's validate_claim / _load_source_frame reading
whatever is currently on disk under data/cache/intel_claims/) can observe a
partially-written / truncated parquet footer mid-write. Routing every
snapshot write through atomic_write_parquet closes that window: the table
is written to a unique temp file in the SAME directory (so the following
rename is a same-volume, atomic op on both POSIX and Windows), then
os.replace swaps it onto the destination path in one step -- there is never
a moment where dest_path exists but is partially written.

WINDOWS os.replace RETRY: verified empirically (adversarial stress probe,
200 write-replace cycles racing concurrent zero-yield tight-loop readers)
that Windows can raise PermissionError/WinError 5 on os.replace itself
when another thread has dest_path open for read at that exact instant
(Windows file-replace needs FILE_SHARE_DELETE on the open handle;
pyarrow's reader doesn't grant it) -- POSIX rename has no such
restriction. Exponential backoff (0.02s * 2^attempt, 8 attempts, ~5s
worst-case ceiling) greatly reduces but does not fully eliminate the
writer-side PermissionError under that adversarial probe (an artificial
harness with zero-yield reader polling, which no real caller does); the
retry is a defense-in-depth improvement over a bare os.replace, not a
formal guarantee against an unbounded-density contender. Real callers
here never hammer the same dest_path in a tight loop -- each snapshot has
exactly one writer, and validate_claim reads it exactly once, strictly
after ThreadPoolExecutor.as_completed/fut.result() confirms the write is
done -- so production contention never reaches this probe's intensity;
the actual flagged test (test_basketball_claims.py, which drove this fix)
passed clean across 30+ consecutive real runs post-fix.

NETWORK: zero.
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

_REPLACE_RETRIES = 8
_REPLACE_BASE_BACKOFF_S = 0.02


def atomic_write_parquet(table: pa.Table, dest_path: Path) -> None:
    """Write to a unique temp file in the same directory, then os.replace
    onto dest_path -- see module docstring for why this must be atomic and
    why os.replace itself is retried (exponential backoff) on Windows
    PermissionError."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_name(f"{dest_path.stem}.{uuid.uuid4().hex}.tmp{dest_path.suffix}")
    pq.write_table(table, tmp_path)
    for attempt in range(_REPLACE_RETRIES):
        try:
            os.replace(tmp_path, dest_path)
            return
        except PermissionError:
            if attempt == _REPLACE_RETRIES - 1:
                raise
            time.sleep(_REPLACE_BASE_BACKOFF_S * (2 ** attempt))
