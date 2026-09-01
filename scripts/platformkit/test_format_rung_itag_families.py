"""The high-resolution rung must select by HEIGHT, never by itag.

YouTube exposes different HLS itag families per video: 300/301 are 720p60 and
1080p60, while 95/96 are the 30fps equivalents. A fetch hardcoded to `-f 300`
failed outright on a WNBA video whose HLS ladder is 93/94/95/96, even though
that video does publish 720p and 1080p.

Run: python -m pytest scripts/platformkit/test_format_rung_itag_families.py -q
"""
from __future__ import annotations

import re

from scripts.platformkit import footage_bridge
from scripts.platformkit.section_fallback import MIN_SECTION_HEIGHT


def test_no_rung_hardcodes_a_numeric_itag():
    """A bare itag selects one encoding ladder and fails on the other."""
    for rung in footage_bridge.FORMAT_RUNGS:
        assert not re.fullmatch(r"\s*\d+\s*", rung), rung
        # `300`/`301`/`95`/`96` as a standalone selector token is the trap.
        assert not re.search(r"(^|[/+,\s])\d{2,3}([/+,\s]|$)", rung), rung


def test_the_high_resolution_rung_is_expressed_as_a_height_range():
    first = footage_bridge.FORMAT_RUNGS[0].replace(" ", "")
    assert "height>=%d" % MIN_SECTION_HEIGHT in first, first
    assert "height<=" in first, first
