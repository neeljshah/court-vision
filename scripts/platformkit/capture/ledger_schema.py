"""ledger_schema.py — Schema definition and validation for the forward-capture ledger.

Each record represents a single observed line snapshot.  The schema is intentionally
minimal and append-only: every field is required so downstream consumers can always
rely on their presence.

Multi-sport from day 1: the ``sport`` field is a top-level required field so records
from different domains never collide.
"""
from __future__ import annotations

from typing import Dict, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_FIELDS: Tuple[str, ...] = (
    "sport",
    "event_id",
    "market",
    "book",
    "price",
    "side",
    "kind",
    "ts_utc_observed",
    "source",
)

VALID_KINDS = frozenset({"open", "move", "close"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate(record: dict) -> dict:
    """Validate a ledger record dict.

    Raises ``ValueError`` if any required field is missing or if ``kind`` is not one
    of ``{"open", "move", "close"}``.  Returns the record unchanged on success so
    callers can chain: ``write(validate(rec))``.

    Args:
        record: Raw record dict to validate.

    Returns:
        The same ``record`` dict, unmodified.

    Raises:
        ValueError: On missing field or invalid ``kind``.
    """
    missing = [f for f in REQUIRED_FIELDS if f not in record]
    if missing:
        raise ValueError(
            f"Ledger record missing required field(s): {missing}. "
            f"Got keys: {sorted(record.keys())}"
        )

    kind = record["kind"]
    if kind not in VALID_KINDS:
        raise ValueError(
            f"Invalid 'kind' value {kind!r}. Must be one of {sorted(VALID_KINDS)}."
        )

    return record


def record_key(record: dict) -> Tuple[str, str, str, str, str, str]:
    """Return a deterministic dedup/idempotency key for a ledger record.

    The key is a 6-tuple: ``(sport, event_id, market, book, side, kind)``.
    Callers that need to avoid writing duplicates should use this key as a
    seen-set check before appending.

    Args:
        record: A *validated* ledger record dict.

    Returns:
        A tuple suitable for use as a dict key or set element.
    """
    return (
        record["sport"],
        record["event_id"],
        record["market"],
        record["book"],
        record["side"],
        record["kind"],
    )
