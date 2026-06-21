"""Per-file test for scripts.platformkit.paper.et_day.et_day_of.

Run ONLY this file (full suite freezes the box):
    python -m pytest scripts/platformkit/paper/test_et_day.py -q

Focus: a BARE calendar date (YYYY-MM-DD) is already an ET day and must NOT be rolled
back a day by a spurious UTC->ET shift (the bug that hid placed props dated 'today').
"""
from __future__ import annotations

from scripts.platformkit.paper.et_day import et_day_of


def test_bare_date_is_returned_unchanged():
    # A date has no time to convert: it must stay the same ET day, not shift back.
    assert et_day_of("2026-06-21") == "2026-06-21"
    assert et_day_of("2026-01-01") == "2026-01-01"
    assert et_day_of(" 2026-12-31 ") == "2026-12-31"  # trimmed, still bare date


def test_full_utc_timestamp_still_converts_to_et():
    # 00:30 UTC is the prior ET calendar day (20:30 ET) -- real timestamps still shift.
    assert et_day_of("2026-06-21T00:30:00Z") == "2026-06-20"
    # Midday UTC is the same ET day.
    assert et_day_of("2026-06-21T16:00:00Z") == "2026-06-21"


def test_empty_and_malformed_are_honest():
    assert et_day_of("") == "unknown"
    assert et_day_of(None) == "unknown"  # type: ignore[arg-type]
    # A non-date 10-char string is not a bare date -> falls through to prefix/parse.
    assert et_day_of("notadateee") in ("notadateee", "unknown")
