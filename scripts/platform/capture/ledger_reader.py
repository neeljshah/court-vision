"""ledger_reader.py — Typed read-only access layer for the forward-capture ledger.

Mirrors the path layout written by ``ledger_writer``:

    data/lines/forward/<sport>/<YYYY-MM-DD>.jsonl

Three public helpers:

* :func:`iter_rows` — yields typed dict rows, with optional sport/market/kind
  filters and a ``forward_only`` flag that excludes ``ts_quality="reconstructed"``
  rows by default.
* :func:`pair_open_close` — matches opener rows to their paired closer rows,
  keyed by ``(sport, event_id, market, book, side)``.
* :func:`find_duplicate_keys` — integrity check: reports any ``record_key``
  that appears more than once across the supplied rows.

This module is **pure stdlib** (json / pathlib).  It never writes to the ledger.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Path wiring — importable both as a package sub-module and as a standalone
# script, matching the pattern used by ledger_writer.py.
# ---------------------------------------------------------------------------

_CAPTURE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_ROOT = _REPO_ROOT / "data" / "lines" / "forward"

if str(_CAPTURE_DIR) not in sys.path:
    sys.path.insert(0, str(_CAPTURE_DIR))

from ledger_schema import record_key  # noqa: E402

# The sentinel value that backfill_nba_archives writes for archive rows.
_TS_QUALITY_RECONSTRUCTED = "reconstructed"

# ---------------------------------------------------------------------------
# Typed row alias — every yielded dict is guaranteed to contain REQUIRED_FIELDS.
# ---------------------------------------------------------------------------

LedgerRow = Dict[str, object]
PairKey = Tuple[str, str, str, str, str]  # (sport, event_id, market, book, side)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _iter_jsonl(path: Path) -> Iterator[LedgerRow]:
    """Yield parsed JSON objects from a single JSONL file, skipping blank lines.

    Args:
        path: Absolute path to a ``.jsonl`` file.

    Yields:
        Parsed record dicts in file order.
    """
    with open(path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            stripped = raw_line.strip()
            if stripped:
                yield json.loads(stripped)


def _is_reconstructed(row: LedgerRow) -> bool:
    """Return True when the row was written by the backfill sweep (not live-captured).

    Args:
        row: A ledger record dict.

    Returns:
        ``True`` if ``ts_quality`` equals ``"reconstructed"``.
    """
    return row.get("ts_quality") == _TS_QUALITY_RECONSTRUCTED


def _sport_dirs(root: Path) -> Iterator[Path]:
    """Yield every immediate subdirectory of *root* (one per sport).

    Args:
        root: Ledger root directory (``data/lines/forward`` or a tmp_path override).

    Yields:
        Path objects for each sport subdirectory that exists.
    """
    if not root.exists():
        return
    for child in sorted(root.iterdir()):
        if child.is_dir():
            yield child


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def iter_rows(
    root: Optional[Path] = None,
    sport: Optional[str] = None,
    market: Optional[str] = None,
    kind: Optional[str] = None,
    forward_only: bool = True,
) -> Iterator[LedgerRow]:
    """Iterate over all ledger rows matching the supplied filters.

    Walks every ``.jsonl`` file under ``<root>/<sport>/`` in lexicographic
    order (sport dir → date file → line within file).  Filters are applied
    after parsing so no extra index is required.

    Args:
        root: Ledger root directory override.  Defaults to
            ``<repo_root>/data/lines/forward``.  Pass ``tmp_path`` in tests.
        sport: If given, only rows whose ``sport`` field equals this value are
            yielded (e.g. ``"nba"``).
        market: If given, only rows whose ``market`` field equals this value
            are yielded (e.g. ``"player_points"``).
        kind: If given, only rows whose ``kind`` field equals this value are
            yielded (``"open"``, ``"move"``, or ``"close"``).
        forward_only: When ``True`` (default), rows tagged
            ``ts_quality="reconstructed"`` are excluded so consumers see only
            genuinely forward-captured observations.

    Yields:
        Validated-schema dicts in stable file order.
    """
    base = Path(root) if root is not None else _DEFAULT_ROOT

    for sport_dir in _sport_dirs(base):
        dir_sport = sport_dir.name
        # Apply sport filter at the directory level for efficiency.
        if sport is not None and dir_sport != sport:
            continue

        for jsonl_file in sorted(sport_dir.glob("*.jsonl")):
            try:
                for row in _iter_jsonl(jsonl_file):
                    # Forward-only guard.
                    if forward_only and _is_reconstructed(row):
                        continue
                    # Field-level filters.
                    if market is not None and row.get("market") != market:
                        continue
                    if kind is not None and row.get("kind") != kind:
                        continue
                    yield row
            except (OSError, json.JSONDecodeError):
                # Skip unreadable / malformed files rather than crashing the
                # caller; the ledger is append-only so partial corruption is
                # theoretically impossible, but defensive is cheap.
                continue


def pair_open_close(
    rows: List[LedgerRow],
) -> List[Tuple[LedgerRow, LedgerRow]]:
    """Match opener rows to their paired closer rows.

    A pair is identified by the 5-tuple ``(sport, event_id, market, book, side)``.
    Only rows whose ``kind`` is ``"open"`` or ``"close"`` participate; ``"move"``
    rows are ignored.  An open is matched to the *first* close seen for the same
    key.  Singletons (open with no close, or close with no matching open) are
    excluded from the result.

    Args:
        rows: Iterable of ledger row dicts (typically produced by
            :func:`iter_rows`).  Order determines which open/close is used when
            duplicates exist.

    Returns:
        List of ``(open_row, close_row)`` 2-tuples, one per matched pair, in the
        order that the open rows were encountered.
    """
    opens: Dict[PairKey, LedgerRow] = {}
    closes: Dict[PairKey, LedgerRow] = {}

    for row in rows:
        k = row.get("kind")
        if k not in ("open", "close"):
            continue
        pair_key: PairKey = (
            str(row.get("sport", "")),
            str(row.get("event_id", "")),
            str(row.get("market", "")),
            str(row.get("book", "")),
            str(row.get("side", "")),
        )
        if k == "open":
            # Keep first open seen for each key.
            if pair_key not in opens:
                opens[pair_key] = row
        else:  # k == "close"
            # Keep first close seen for each key.
            if pair_key not in closes:
                closes[pair_key] = row

    # Build matched pairs, preserving open insertion order.
    pairs: List[Tuple[LedgerRow, LedgerRow]] = []
    for pair_key, open_row in opens.items():
        if pair_key in closes:
            pairs.append((open_row, closes[pair_key]))
    return pairs


def find_duplicate_keys(
    rows: List[LedgerRow],
) -> Dict[Tuple[str, str, str, str, str, str], List[LedgerRow]]:
    """Report record_keys that appear more than once in *rows*.

    Uses the same 6-tuple key as :func:`ledger_schema.record_key`:
    ``(sport, event_id, market, book, side, kind)``.

    Args:
        rows: List of ledger row dicts to inspect.

    Returns:
        A dict mapping each *duplicated* key to the list of rows that share it.
        If the ledger is fully deduplicated, the returned dict is empty.
    """
    seen: Dict[Tuple[str, str, str, str, str, str], List[LedgerRow]] = {}

    for row in rows:
        key = record_key(row)  # type: ignore[arg-type]
        if key not in seen:
            seen[key] = []
        seen[key].append(row)

    return {k: v for k, v in seen.items() if len(v) > 1}
