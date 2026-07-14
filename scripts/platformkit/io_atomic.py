"""scripts.platformkit.io_atomic -- shared crash-safe atomic write helpers.

Several ledger / append / state writers across platformkit used bare
``write_text`` / ``open(..., "w"|"a")``. A crash mid-write then leaves a torn
JSON / JSONL file (a half-written line, or a truncated object), and the
autonomous daily loop -- which reads these every cycle -- breaks until a human
repairs the file. That defeats the "zero flaws, no Claude" rail.

This module centralises the SAME tmp+os.replace discipline the served-board
writers already use, so the four torn-write call sites can reuse one helper
instead of each growing its own copy:

  write_json_atomic(path, obj, ...)   -- full-file JSON write, tmp + os.replace.
  write_text_atomic(path, text, ...)  -- full-file text write, tmp + os.replace.
  append_jsonl_atomic(path, row, ...) -- append one JSONL row crash-safely.

ATOMIC APPROACH
---------------
* Full-file (write_json_atomic / write_text_atomic): serialise -> write to a
  sibling ``*.tmp`` in the SAME directory -> ``os.replace`` over the target.
  ``os.replace`` is atomic on POSIX and on Windows (same volume), so a reader
  sees either the OLD complete file or the NEW complete file -- never a torn one.
  A crash before the replace leaves only the tmp; the target is untouched.

* Append (append_jsonl_atomic): READ the existing file -> concat the existing
  bytes + the one new ``json.dumps(row) + "\n"`` -> write the whole thing to a
  sibling tmp -> ``os.replace``. This is the STRONGEST append guarantee: a crash
  can NEVER leave a partial line in the target (a bare ``O_APPEND`` write can
  lose its tail on a crash mid-write). Cost is O(file) per append; these ledgers
  are small daily/forever rows where correctness beats micro-throughput.

The data SHAPE is preserved exactly: callers pass the same dicts and the same
encoding / json kwargs they used before, so existing readers parse unchanged.

INVARIANTS: stdlib only; ASCII source; <=300 LOC; no $; calibration not edge.
Never writes data/registry/, never flips a flag.
"""
from __future__ import annotations

import json
import os
import pathlib
import tempfile
from datetime import datetime, timezone
from typing import Any, Union

PathLike = Union[str, "os.PathLike[str]"]

# E14: domains/*/knowledge/validate_*.py (and the M07 mechanism_reval_job that
# drives them) all append to a file literally named this, via this one shared
# function -- no per-domain wrapper exists (see domains/<sport>/knowledge/_data.py
# LEDGER_PATH). Rows carried no timestamp, so a deterministic reval against an
# unchanged corpus produced a byte-identical row indistinguishable from a dupe
# (docs/research/m07_ledger_bloat_spotcheck_2026-07-10.md). Stamping run_ts here
# -- ONE place -- covers every validator without editing 30 call sites.
# ponytail: name-matched, not a dedicated ledger-writer wrapper -- promote to one
# if a second ledger family needs the same stamp.
_KNOWLEDGE_LEDGER_NAME = "validation_ledger.jsonl"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _as_path(path: PathLike) -> pathlib.Path:
    return path if isinstance(path, pathlib.Path) else pathlib.Path(os.fspath(path))


def _replace_via_tmp(target: pathlib.Path, data: str, encoding: str) -> None:
    """Write *data* to a sibling tmp in target's dir, then os.replace over target.

    A new tempfile in the SAME directory guarantees os.replace stays on one
    volume (atomic on Windows too). On any failure the tmp is removed and the
    existing target is left untouched -- no torn file is ever visible.
    """
    target = target.resolve() if not target.is_absolute() else target
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(parent), prefix=".tmp_", suffix=".swap")
    tmp = pathlib.Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        # Windows: os.replace fails with WinError 5 while another process
        # briefly holds the target open (concurrent lane read/replace).
        # Short bounded backoff turns transient contention into a wait
        # instead of killing a long sweep mid-run. Still fails closed.
        for attempt in range(6):
            try:
                os.replace(str(tmp), str(target))
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.25 * (attempt + 1))
    except BaseException:
        # Best-effort cleanup; never leave a stray tmp masquerading as state.
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


def write_text_atomic(path: PathLike, text: str, *, encoding: str = "utf-8") -> None:
    """Atomically write *text* to *path* (tmp + os.replace). Crash-safe full write."""
    _replace_via_tmp(_as_path(path), text, encoding)


def write_json_atomic(
    path: PathLike,
    obj: Any,
    *,
    encoding: str = "utf-8",
    ensure_ascii: bool = True,
    sort_keys: bool = True,
    indent: Any = None,
    trailing_newline: bool = False,
    default: Any = None,
) -> None:
    """Atomically write *obj* as JSON to *path* (tmp + os.replace).

    The json kwargs mirror what the call sites already passed so the on-disk
    SHAPE is byte-identical to the prior bare write -- only the write is now
    crash-safe. ``trailing_newline`` appends a final "\n" when the original
    writer did (some diagnostics were written as a single-line "json + \\n").
    """
    body = json.dumps(
        obj,
        ensure_ascii=ensure_ascii,
        sort_keys=sort_keys,
        indent=indent,
        default=default,
    )
    if trailing_newline:
        body += "\n"
    _replace_via_tmp(_as_path(path), body, encoding)


def _content_sig(row: dict) -> str:
    """Content signature ignoring ``run_ts`` -- for the knowledge-ledger dup guard."""
    return json.dumps({k: v for k, v in row.items() if k != "run_ts"}, sort_keys=True, default=str)


def append_jsonl_atomic(
    path: PathLike,
    row: Any,
    *,
    encoding: str = "ascii",
    ensure_ascii: bool = True,
    sort_keys: bool = True,
    default: Any = None,
) -> None:
    """Append one JSONL *row* to *path* crash-safely (read-modify-write + replace).

    Reads the current file, appends ``json.dumps(row) + "\\n"``, writes the whole
    result to a sibling tmp, then os.replace over the target. A crash can never
    leave a partial trailing line: the target is only ever swapped for a file
    whose every line (including the new one) is complete.

    The serialised row is identical to the prior ``open(path, "a")`` writers, so
    readers that split on newlines and ``json.loads`` each line parse unchanged
    -- EXCEPT for ``validation_ledger.jsonl`` targets (see
    ``_KNOWLEDGE_LEDGER_NAME``), which additionally get a ``run_ts`` key
    stamped in (only if the caller didn't already set one) so re-validation
    passes are no longer indistinguishable from silent duplicates. Readers must
    tolerate its absence on pre-existing rows -- it is additive, not required.

    FORWARD DUP GUARD (``validation_ledger.jsonl`` targets only,
    docs/research/ledger_dedupe_audit_2026-07-10.md): a direct/manual
    ``validate_*.py`` re-run against an unchanged corpus reproduces a
    byte-identical row (content-equal minus ``run_ts``). Rather than adding a
    guard to all ~30 call sites, this shared writer skips the append when an
    existing row's content signature (row minus ``run_ts``) already matches.
    # ponytail: read-scan is O(n) per append -- fine at these sizes (~100
    # rows/ledger); promote to a cached content-sig set/index if a ledger
    # grows enough that this write path gets hot.
    """
    target = _as_path(path)
    is_ledger = target.name == _KNOWLEDGE_LEDGER_NAME
    if isinstance(row, dict) and is_ledger and "run_ts" not in row:
        row = {**row, "run_ts": _utc_now_iso()}
    existing = ""
    if target.is_file():
        existing = target.read_text(encoding=encoding, errors="replace")
        if isinstance(row, dict) and is_ledger and existing:
            new_sig = _content_sig(row)
            for ln in existing.splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    prior = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if isinstance(prior, dict) and _content_sig(prior) == new_sig:
                    return  # duplicate content (ignoring run_ts) -- skip append
        if existing and not existing.endswith("\n"):
            # A pre-existing torn tail would otherwise glue onto our new row.
            existing += "\n"
    line = json.dumps(row, ensure_ascii=ensure_ascii, sort_keys=sort_keys, default=default)
    _replace_via_tmp(target, existing + line + "\n", encoding)


__all__ = ["write_text_atomic", "write_json_atomic", "append_jsonl_atomic"]
