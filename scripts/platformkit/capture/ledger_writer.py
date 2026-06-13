"""ledger_writer.py — Append-only writer for the forward-capture ledger.

Layout on disk::

    data/lines/forward/<sport>/<YYYY-MM-DD>.jsonl

One compact JSON object per line.  Files are NEVER truncated or overwritten — only
appended.  Durability discipline matches ``scripts/bot_guards/_state.py``:
``flush()`` + ``os.fsync()`` after every write.

The ``root`` parameter on every public function defaults to the repo-canonical path
``<repo_root>/data/lines/forward`` but can be overridden in tests via ``tmp_path``
so real data are never touched during the test suite.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import List, Optional

# Resolve repo root relative to THIS file's location so the module works
# regardless of the caller's CWD.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_ROOT = _REPO_ROOT / "data" / "lines" / "forward"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Import schema from sibling module.  We do a sys.path manipulation so the
# file is importable both as a package sub-module and as a standalone script.
_CAPTURE_DIR = Path(__file__).resolve().parent
if str(_CAPTURE_DIR) not in sys.path:
    sys.path.insert(0, str(_CAPTURE_DIR))

from ledger_schema import validate  # noqa: E402


def _safe_open_mode(mode: str) -> None:
    """Guard against any open() call that would truncate the ledger.

    Raises ``RuntimeError`` if ``mode`` starts with ``'w'`` or ``'x'``.
    ``'a'`` (append) and ``'r'`` (read) are the only permitted modes.

    Args:
        mode: The file-open mode string to validate.

    Raises:
        RuntimeError: If ``mode`` would truncate or create-exclusive the file.
    """
    if mode and mode[0] in ("w", "x"):
        raise RuntimeError(
            f"Refusing to open the ledger in mode {mode!r}. "
            "The ledger is append-only — use mode 'a' or 'r'."
        )


def _date_from_ts(ts_utc_observed: str) -> str:
    """Extract the ISO-8601 date portion (YYYY-MM-DD) from a UTC timestamp string.

    Accepts full ISO strings like ``2026-06-11T18:30:00Z`` or
    ``2026-06-11T18:30:00+00:00`` as well as plain ``2026-06-11``.

    Args:
        ts_utc_observed: ISO-8601 UTC timestamp string from the record.

    Returns:
        Date string in ``YYYY-MM-DD`` format.
    """
    # The date is always the first 10 characters of any ISO-8601 string.
    date_part = ts_utc_observed[:10]
    if len(date_part) != 10 or date_part[4] != "-" or date_part[7] != "-":
        raise ValueError(
            f"Cannot parse date from ts_utc_observed={ts_utc_observed!r}. "
            "Expected ISO-8601 format starting with YYYY-MM-DD."
        )
    return date_part


def _ledger_path(sport: str, date: str, root: Optional[Path]) -> Path:
    """Compute the JSONL file path for a given sport and date.

    Args:
        sport: Sport identifier (e.g. ``"nba"``).
        date: Date string ``YYYY-MM-DD``.
        root: Ledger root directory; defaults to ``data/lines/forward`` under repo root.

    Returns:
        Absolute ``Path`` to the target ``.jsonl`` file.
    """
    base = root if root is not None else _DEFAULT_ROOT
    return Path(base) / sport / f"{date}.jsonl"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def append(record: dict, root: Optional[Path] = None) -> Path:
    """Validate and append a single ledger record to its daily JSONL file.

    The target file is derived exclusively from the record's ``ts_utc_observed``
    field — never from the system clock.  The file is opened in append mode
    (``'a'``) only.  After writing, ``flush()`` + ``os.fsync()`` are called for
    durability.

    Args:
        record: A ledger record dict (all required fields must be present).
        root: Override the ledger root directory.  Defaults to
            ``<repo_root>/data/lines/forward``.  Pass ``tmp_path`` in tests.

    Returns:
        The ``Path`` of the file that was written to.

    Raises:
        ValueError: If the record fails schema validation.
        RuntimeError: If this function is somehow redirected through a truncating
            open mode (internal guard — should never trigger in normal usage).
    """
    validate(record)

    date = _date_from_ts(record["ts_utc_observed"])
    path = _ledger_path(record["sport"], date, root)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Explicit mode guard before opening.
    _safe_open_mode("a")

    line = json.dumps(record, separators=(",", ":")) + "\n"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())

    return path


def read_all(sport: str, date: str, root: Optional[Path] = None) -> List[dict]:
    """Read all records from one day's JSONL ledger file.

    Args:
        sport: Sport identifier (e.g. ``"nba"``).
        date: Date string ``YYYY-MM-DD``.
        root: Override the ledger root directory.

    Returns:
        List of record dicts in append order.  Returns an empty list if the file
        does not exist.
    """
    path = _ledger_path(sport, date, root)
    if not path.exists():
        return []

    records: List[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            raw_line = raw_line.strip()
            if raw_line:
                records.append(json.loads(raw_line))
    return records


def to_parquet(sport: str, date: str, root: Optional[Path] = None) -> Path:
    """Derive a Parquet snapshot from one day's JSONL ledger (read-only derivation).

    The Parquet file is written alongside the JSONL file as
    ``<date>.parquet``.  This function is a convenience export for downstream
    analytics; it never modifies the JSONL source.

    Args:
        sport: Sport identifier.
        date: Date string ``YYYY-MM-DD``.
        root: Override the ledger root directory.

    Returns:
        Path of the written Parquet file.

    Raises:
        FileNotFoundError: If the source JSONL file does not exist.
        ImportError: If pandas or pyarrow is not installed.
    """
    import pandas as pd  # noqa: PLC0415  (optional heavy dep; import deferred)

    records = read_all(sport, date, root)
    if not records:
        jsonl_path = _ledger_path(sport, date, root)
        raise FileNotFoundError(
            f"No ledger records found at {jsonl_path}. "
            "Cannot produce Parquet from an empty or missing file."
        )

    df = pd.DataFrame(records)
    parquet_path = _ledger_path(sport, date, root).with_suffix(".parquet")
    df.to_parquet(parquet_path, index=False)
    return parquet_path
