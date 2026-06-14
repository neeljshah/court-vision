"""scripts.platformkit.frontend.book_norm — normalize book labels to operators.

HONEST (binding): the value of a multi-book feed is line-shop / devig / CLV, which
exists ONLY across genuinely DIFFERENT operators — never one book vs itself.

The same operator can appear under time/variant suffixes (ESPN lists DraftKings
pregame AND "draftkings - live odds").  Counting those as two books fabricates a
FALSE cross-book arbitrage (a stale pregame ML vs an in-play line is not
risk-free).  ``normalize_book`` collapses such variants so only different
OPERATORS count as distinct books.  Pure stdlib; no package imports.
"""
from __future__ import annotations

from typing import Any

# Trailing time/variant suffixes that denote the SAME operator at another time.
_BOOK_VARIANT_SUFFIXES = (
    " - live odds", " - live", " (live)", " live odds", " live",
    " - pregame", " pregame",
)


def normalize_book(raw: Any) -> str:
    """Normalize a book label to its operator: lowercase, strip a variant suffix.

    'DraftKings - Live Odds' -> 'draftkings'.  Empty/None -> 'unknown'.
    """
    b = str(raw or "").strip().lower()
    for suf in _BOOK_VARIANT_SUFFIXES:
        if b.endswith(suf):
            b = b[: -len(suf)].strip()
            break
    return b or "unknown"


__all__ = ["normalize_book"]
