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

# Pre-registered 2026-07-15 (docs/research/execution-quality/EXECUTION_BACKLOG.md
# lever #3 / build spec #3), BEFORE any forward measurement: captured Kalshi
# spread_bp p50=200bp, p75=500bp, p90=3000bp (n=191,424). 800bp keeps ~p75 of
# quoted volume while suppressing placement into the wide tail that measured a
# mean 7.4pp give-up. Not tuned post-hoc -- see this file's module docstring.
INGAME_MAX_SPREAD_BP: float = 800.0

__all__ = [
    "PROP_EXPECTED_CLV_MIN_PCT", "INGAME_EXPECTED_CLV_MIN_PCT",
    "INGAME_MAX_DRIFT_PCT", "BREAKER_WINDOW_DAYS", "BREAKER_CAPPED_MAX_PER_DAY",
    "INGAME_MAX_SPREAD_BP",
]
