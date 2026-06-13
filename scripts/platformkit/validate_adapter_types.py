"""scripts/platformkit/validate_adapter_types.py — Scorecard data types.

Defines the Status enum and CheckResult dataclass shared across the
validate_adapter module family.  Kept separate so it can be imported
without pulling in kernel or argparse.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum


# ---------------------------------------------------------------------------
# Result enum
# ---------------------------------------------------------------------------


class Status(str, Enum):
    """Scorecard status codes."""
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    NOT_YET_CONTRACTED = "NOT_YET_CONTRACTED"


@dataclass
class CheckResult:
    """One scorecard row."""

    item: str
    status: Status
    detail: str = ""

    def __str__(self) -> str:
        pad = 40
        base = f"  [{self.status.value:<20}]  {self.item:<{pad}}"
        if self.detail:
            return f"{base}  # {self.detail}"
        return base
