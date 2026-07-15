"""scripts.platformkit.execution.thresholds -- PRE-REGISTERED execution constants.

Registered 2026-07-15, BEFORE any measurement of the gated channels below. These
values must NOT be tuned post-hoc against the same window they gate -- a
threshold moved after seeing its own result is not a gate, it is curve-fitting.
Any future change needs a fresh pre-registration date and a stated reason.

PAPER / UNITS only. No $ figure anywhere.
"""
from __future__ import annotations

PROP_EXPECTED_CLV_MIN_PCT: float = 1.0
INGAME_EXPECTED_CLV_MIN_PCT: float = 1.0
INGAME_MAX_DRIFT_PCT: float = 1.0  # reject if price moved adversely more than this
                                    # between signal time and placement time.
BREAKER_WINDOW_DAYS: int = 30
BREAKER_CAPPED_MAX_PER_DAY: int = 5  # per market_type while rolling CLV < 0.

__all__ = [
    "PROP_EXPECTED_CLV_MIN_PCT", "INGAME_EXPECTED_CLV_MIN_PCT",
    "INGAME_MAX_DRIFT_PCT", "BREAKER_WINDOW_DAYS", "BREAKER_CAPPED_MAX_PER_DAY",
]
