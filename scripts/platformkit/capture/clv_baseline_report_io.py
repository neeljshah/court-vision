"""clv_baseline_report_io.py — I/O helpers for clv_baseline_report (N-CLV-006).

Provides inline JSONL ledger scanning and safe price conversion.  Split from
clv_baseline_report.py to stay within the 300 LOC/file rule.  Logic is
identical — this is a verbatim move, not a rewrite.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Optional

# ---------------------------------------------------------------------------
# Default ledger root — resolved relative to this file's repo location.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_LEDGER_ROOT = _REPO_ROOT / "data" / "lines" / "forward"


def iter_ledger_rows(
    root: Optional[Path] = None,
    days: int = 60,
) -> Iterator[dict]:
    """Yield all ledger rows from the last *days* JSONL files, newest-first sort.

    Walks every sport subdirectory under *root* and reads every ``.jsonl``
    file.  The *days* parameter is a soft limit: it restricts how many date
    files are read per sport directory (sorted descending so the most recent
    files are read first).

    Args:
        root: Ledger root directory.  Defaults to ``data/lines/forward``.
        days: Maximum number of daily files to read per sport directory.

    Yields:
        Parsed record dicts in file-read order.
    """
    base = Path(root) if root is not None else _DEFAULT_LEDGER_ROOT
    if not base.exists():
        return

    for sport_dir in sorted(base.iterdir()):
        if not sport_dir.is_dir():
            continue
        jsonl_files = sorted(sport_dir.glob("*.jsonl"), reverse=True)[:days]
        # Reverse again so output is chronological within the window.
        for jf in reversed(jsonl_files):
            try:
                with open(jf, "r", encoding="utf-8") as fh:
                    for raw_line in fh:
                        stripped = raw_line.strip()
                        if stripped:
                            try:
                                yield json.loads(stripped)
                            except json.JSONDecodeError:
                                pass
            except OSError:
                pass


def safe_price(value: object) -> Optional[float]:
    """Convert a ledger price to float, returning None on failure.

    Args:
        value: Raw price value from ledger (may be str or numeric).

    Returns:
        Float price, or None if not convertible.
    """
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
