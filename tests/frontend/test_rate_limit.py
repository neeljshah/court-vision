"""Per-file test: frontend.rate_limit -- the keyless fixed-window guard (WAVE 4).

Run: python -m pytest tests/frontend/test_rate_limit.py -q
"""
from __future__ import annotations

from frontend.rate_limit import RateLimiter


def test_allows_under_limit():
    lim = RateLimiter(limit=3, window_sec=60.0)
    for _ in range(3):
        allowed, retry = lim.check("c1", now=100.0)
        assert allowed is True and retry == 0.0


def test_blocks_over_limit_with_retry_after():
    lim = RateLimiter(limit=2, window_sec=60.0)
    assert lim.check("c1", now=100.0)[0] is True
    assert lim.check("c1", now=100.0)[0] is True
    allowed, retry = lim.check("c1", now=110.0)
    assert allowed is False
    assert retry > 0.0  # seconds until window reset


def test_window_rolls_over_and_resets():
    lim = RateLimiter(limit=1, window_sec=60.0)
    assert lim.check("c1", now=100.0)[0] is True
    assert lim.check("c1", now=130.0)[0] is False
    # After the window passes, the count resets.
    assert lim.check("c1", now=200.0)[0] is True


def test_per_client_isolation():
    lim = RateLimiter(limit=1, window_sec=60.0)
    assert lim.check("a", now=100.0)[0] is True
    assert lim.check("b", now=100.0)[0] is True  # different client, own bucket
    assert lim.check("a", now=100.0)[0] is False
