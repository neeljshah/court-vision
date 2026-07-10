"""Per-file smoke test for scripts.platformkit.join_rate_floor -- the shared
assert used by every per-seam aggregate join-rate floor test. No network, no
real corpus reads.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_join_rate_floor.py -q
"""
from __future__ import annotations

import pytest

from scripts.platformkit.join_rate_floor import assert_join_rate_floor


def test_rate_at_or_above_floor_passes_and_returns_measured_rate():
    rate = assert_join_rate_floor(80, 100, 0.75, label="demo")
    assert rate == pytest.approx(0.80)


def test_rate_below_floor_raises():
    with pytest.raises(AssertionError, match="join rate regressed"):
        assert_join_rate_floor(50, 100, 0.75, label="demo")


def test_empty_corpus_raises_setup_error_not_a_silent_zero_rate():
    with pytest.raises(AssertionError, match="non-empty real corpus"):
        assert_join_rate_floor(0, 0, 0.75, label="demo")


def test_resolved_exceeding_total_raises():
    with pytest.raises(AssertionError, match="must partition within total"):
        assert_join_rate_floor(101, 100, 0.75, label="demo")


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, "-q"]))
