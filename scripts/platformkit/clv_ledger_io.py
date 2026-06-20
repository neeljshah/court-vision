"""scripts.platformkit.clv_ledger_io -- lock-guarded append/load for the CLV ledger.

Milestone-4 concurrency primitive. The CLV ledger (data/frontend/clv_ledger.jsonl)
is an append-only JSONL that THREE independent processes write to:

  * the paper auto-loop (paper_autobet.record paths -> record_bet / append_settlement),
  * the grader (grade_paper.append_settlement), and
  * the line/snapshot daemons.

Two appends interleaving at the byte level can splice one JSON object into the
middle of another and corrupt the line. This module provides the ONE primitive
those writers should funnel through so that:

  * each append is atomic w.r.t. other appends (an OS advisory lock serialises the
    write + flush + fsync), and
  * a reader that hits the file mid-write tolerates a torn trailing line instead of
    raising.

Design rules:
  * Reuse clv_ledger.DEFAULT_LEDGER as the canonical path (single source of truth).
    Never re-derive the path here.
  * Locking is best-effort / advisory. A transient lock failure NEVER raises from
    append_row -- the write still completes (the lock is an ordering aid, not a
    correctness gate); only torn-byte interleavings are what we actually prevent,
    and a single write() of a newline-terminated line is itself near-atomic on
    local filesystems. The lock removes the residual race.
  * Cross-platform: msvcrt on Windows (this box), fcntl on POSIX, no-op fallback
    elsewhere. Same call sites either way.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII; no secrets;
this tool NEVER places a real bet and NEVER claims an edge.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.clv_ledger import DEFAULT_LEDGER

# --- OS-appropriate advisory file lock ---------------------------------------
# We lock a small sidecar file (<ledger>.lock) rather than the ledger itself so
# that readers opening the ledger never contend with the write lock and a lock
# held on a separate handle cannot interfere with the append handle's offset.
try:  # POSIX
    import fcntl  # type: ignore

    _LOCK_KIND = "fcntl"
except ImportError:  # pragma: no cover - exercised on Windows
    fcntl = None  # type: ignore
    try:
        import msvcrt  # type: ignore

        _LOCK_KIND = "msvcrt"
    except ImportError:  # pragma: no cover - exotic platform
        msvcrt = None  # type: ignore
        _LOCK_KIND = "none"

_LOCK_TIMEOUT_S = 5.0
_LOCK_POLL_S = 0.02


def _lock_path(target: Path) -> Path:
    return target.with_suffix(target.suffix + ".lock")


def _acquire(lock_fh) -> bool:
    """Try to take an exclusive advisory lock on *lock_fh*. Return success.

    Never raises on a transient/unsupported lock -- the caller proceeds either way.
    """
    deadline = time.monotonic() + _LOCK_TIMEOUT_S
    while True:
        try:
            if _LOCK_KIND == "fcntl":
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            if _LOCK_KIND == "msvcrt":
                msvcrt.locking(lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            return False  # no lock backend: caller proceeds unlocked
        except OSError:
            if time.monotonic() >= deadline:
                return False  # give up gracefully; append still proceeds
            time.sleep(_LOCK_POLL_S)


def _release(lock_fh) -> None:
    try:
        if _LOCK_KIND == "fcntl":
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
        elif _LOCK_KIND == "msvcrt":
            try:
                lock_fh.seek(0)
            except OSError:
                pass
            msvcrt.locking(lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass  # best-effort release; closing the handle frees it anyway


# --- public API ---------------------------------------------------------------

def append_row(row: Dict[str, Any], *, path: Optional[Path] = None) -> None:
    """Atomically append one JSON object as a newline-terminated line.

    Serialised against other append_row callers via an OS advisory lock on a
    sidecar .lock file. The line is written in a single write() and flushed +
    fsync'd so a concurrent reader sees either the whole line or nothing.

    NEVER raises on a transient lock contention -- the lock is an ordering aid;
    on lock-timeout the append still proceeds (a single newline-terminated
    write is itself near-atomic on local filesystems).
    """
    target = Path(path) if path is not None else DEFAULT_LEDGER
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(row, default=str) + "\n"
    lock_fh = None
    if _LOCK_KIND != "none":
        try:
            lock_fh = _lock_path(target).open("a+", encoding="utf-8")
        except OSError:
            lock_fh = None
    try:
        if lock_fh is not None:
            _acquire(lock_fh)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass  # fsync may be unsupported on some handles; flush sufficed
    finally:
        if lock_fh is not None:
            _release(lock_fh)
            try:
                lock_fh.close()
            except OSError:
                pass


def load_rows(*, path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read every intact JSONL row. Missing file -> []. Never raises.

    A torn trailing line (a write caught mid-flight) is skipped rather than
    surfaced as an error. Blank lines are ignored. Mirrors clv_ledger.load_ledger
    semantics but is safe to call concurrently with append_row.
    """
    target = Path(path) if path is not None else DEFAULT_LEDGER
    if not target.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        with target.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # tolerate a partial/torn line, never crash
    except OSError:
        return out  # file vanished or is locked for read; return what we have
    return out


def ledger_path() -> Path:
    """Return the canonical CLV ledger JSONL path (single source of truth)."""
    return DEFAULT_LEDGER


__all__ = ["append_row", "load_rows", "ledger_path"]
