"""Focused tests for native full-download section fallback."""
from __future__ import annotations

from scripts.platformkit import section_fallback


def test_section_seconds_parses_bridge_section_syntax():
    assert section_fallback.section_seconds("*00:10:00-00:26:00") == (600, 960)


def test_section_seconds_rejects_reverse_ranges():
    try:
        section_fallback.section_seconds("*00:26:00-00:10:00")
    except ValueError:
        return
    raise AssertionError("reverse ranges must fail")
