"""scripts.platformkit.join_rate_floor -- one shared assert for join-rate-floor
regression tests across id/ticker join seams (game_pk_bridge, market_join,
wc_ticker_map, crps_market/mlb_join).

Each seam measures a resolved/total rate on a REAL on-disk corpus (never a
synthetic stand-in for the join itself) and asserts it has not silently
regressed below a floor set a few points under the last-measured rate; see
each per-seam test's own docstring for its measured baseline + floor
rationale. This is intentionally ONE tiny function, not a framework -- the
seams differ in how they PRODUCE (resolved, total); this only standardizes
the ASSERTION so a real regression fails loudly with the same message shape
everywhere instead of four hand-rolled asserts drifting apart.

INVARIANTS: build only under scripts/platformkit/; ASCII only; no IO.
"""
from __future__ import annotations


def assert_join_rate_floor(resolved: int, total: int, floor: float, *, label: str) -> float:
    """Assert resolved/total >= floor on a real corpus; return the measured rate.

    total must be > 0 -- an empty corpus is a test-setup bug (missing/moved corpus), not
    a 0% join rate; callers should pytest.mark.skipif when the real data dir is absent
    rather than call this with total=0.
    """
    assert total > 0, "%s: expected a non-empty real corpus (got 0 candidates)" % label
    assert 0 <= resolved <= total, (
        "%s: resolved (%d) must partition within total (%d), never exceed it"
        % (label, resolved, total))
    rate = resolved / total
    assert rate >= floor, (
        "%s: join rate regressed: %.4f (%d/%d) < floor %.4f"
        % (label, rate, resolved, total, floor))
    return rate


__all__ = ["assert_join_rate_floor"]
