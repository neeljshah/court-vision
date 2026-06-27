"""tests for scripts.platformkit.autonomy.progress_tripwire -- liveness != progress.

A FRESH heartbeat must NOT hide a STALLED cursor. Run ONLY this file:
    python -m pytest tests/platformkit/autonomy/test_progress_tripwire.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.autonomy.progress_tripwire import (  # noqa: E402
    HEALTHY,
    HEARTBEAT_STALE,
    IDLE,
    STALLED_CURSOR,
    UNKNOWN,
    classify,
)

NOW = 10_000.0


def test_fresh_heartbeat_and_advancing_cursor_is_healthy():
    r = classify(heartbeat_at=NOW - 5, cursor_at=NOW - 30, now=NOW,
                 hb_fresh_sec=300, stall_sec=1800)
    assert r["status"] == HEALTHY
    assert r["cursor_age"] == 30.0


def test_fresh_heartbeat_but_frozen_cursor_is_flagged_stalled():
    """The decisive case: beating fresh, cursor frozen -> STALLED_CURSOR."""
    r = classify(heartbeat_at=NOW - 5, cursor_at=NOW - 9000, now=NOW,
                 hb_fresh_sec=300, stall_sec=1800)
    assert r["status"] == STALLED_CURSOR
    # liveness != progress: heartbeat is fresh, cursor age is large + exposed.
    assert r["heartbeat_age"] == 5.0
    assert r["cursor_age"] == 9000.0
    assert r["status"] != HEALTHY


def test_cursor_age_always_exposed():
    r = classify(heartbeat_at=NOW - 5, cursor_at=NOW - 100, now=NOW)
    assert "cursor_age" in r and r["cursor_age"] == 100.0


def test_stale_heartbeat_takes_precedence_over_progress():
    r = classify(heartbeat_at=NOW - 9000, cursor_at=NOW - 10, now=NOW,
                 hb_fresh_sec=300, stall_sec=1800)
    assert r["status"] == HEARTBEAT_STALE


def test_idle_is_honest_not_stalled():
    """Fresh beat + genuinely no work -> IDLE, never a false STALLED_CURSOR."""
    r = classify(heartbeat_at=NOW - 5, cursor_at=NOW - 9000, now=NOW,
                 hb_fresh_sec=300, stall_sec=1800, idle=True)
    assert r["status"] == IDLE


def test_unknown_cursor_is_not_silently_healthy():
    """Beating but cursor timestamp unknown -> UNKNOWN, never inferred HEALTHY."""
    r = classify(heartbeat_at=NOW - 5, cursor_at=None, now=NOW,
                 hb_fresh_sec=300, stall_sec=1800)
    assert r["status"] == UNKNOWN
    assert r["status"] != HEALTHY


def test_missing_heartbeat_is_unknown():
    r = classify(heartbeat_at=None, cursor_at=NOW - 10, now=NOW)
    assert r["status"] == UNKNOWN


def test_future_stamp_clamped_to_zero_age():
    r = classify(heartbeat_at=NOW + 500, cursor_at=NOW + 500, now=NOW)
    # future heartbeat clamps to age 0 (fresh) -> not stale; cursor age 0 -> ok.
    assert r["heartbeat_age"] == 0.0
    assert r["cursor_age"] == 0.0
    assert r["status"] == HEALTHY


def test_classify_never_raises():
    r = classify(heartbeat_at="bad", cursor_at="bad", now=NOW)  # type: ignore[arg-type]
    # bad heartbeat -> age None -> UNKNOWN, no raise.
    assert r["status"] in (UNKNOWN, HEARTBEAT_STALE)
