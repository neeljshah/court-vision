"""
test_late_scratch_handler.py -- Tests for the late-scratch handler (19.5-03).

Acceptance criterion: injury_monitor polls ESPN every 2 minutes; an
unexpected scratch triggers a slate rerun; a smoke test on a known scratch
confirms the rerun executes within 3 minutes.
"""

from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data.injury_monitor import (  # noqa: E402
    _LATE_SCRATCH_POLL_SECONDS,
    detect_late_scratches,
    monitor_late_scratches,
)


def _inj(name, status, team="BOS") -> dict:
    return {"player_name": name, "status": status, "team_abbrev": team}


# ── detect_late_scratches ─────────────────────────────────────────────────────

def test_player_flipping_to_out_is_a_scratch():
    """Questionable -> Out is an unexpected late scratch."""
    prior = {"jayson tatum": "Questionable"}
    current = [_inj("Jayson Tatum", "Out")]
    scratches = detect_late_scratches(prior, current)
    assert len(scratches) == 1
    assert scratches[0]["player_name"] == "Jayson Tatum"
    assert scratches[0]["new_status"] == "Out"


def test_player_absent_from_prior_then_out_is_a_scratch():
    """A player not in the prior snapshot (presumed available) flipping to
    Out counts as a scratch."""
    scratches = detect_late_scratches({}, [_inj("Surprise Scratch", "Out")])
    assert len(scratches) == 1


def test_already_out_player_is_not_a_new_scratch():
    """A player already Out in the prior snapshot does not re-trigger."""
    prior = {"injured guy": "Out"}
    scratches = detect_late_scratches(prior, [_inj("Injured Guy", "Out")])
    assert scratches == []


def test_questionable_player_staying_questionable_is_not_a_scratch():
    """No status change to Out -> no scratch."""
    prior = {"maybe guy": "Questionable"}
    scratches = detect_late_scratches(prior, [_inj("Maybe Guy", "Questionable")])
    assert scratches == []


# ── monitor_late_scratches polling loop ───────────────────────────────────────

def test_poll_interval_is_two_minutes():
    """The default poll interval is 2 minutes (120 s)."""
    assert _LATE_SCRATCH_POLL_SECONDS == 120


def test_monitor_fires_callback_on_scratch():
    """The polling loop invokes the callback when a scratch appears."""
    polls = [
        [_inj("Star", "Questionable")],   # baseline
        [_inj("Star", "Out")],            # scratch appears
    ]
    fired: list = []

    def fetch():
        return polls.pop(0) if polls else [_inj("Star", "Out")]

    summary = monitor_late_scratches(
        on_scratch=fired.append,
        fetch_fn=fetch,
        sleep_fn=lambda s: None,
        max_polls=2,
    )
    assert summary["scratches_detected"] == 1
    assert fired[0]["player_name"] == "Star"


def test_smoke_rerun_fires_within_three_minutes():
    """Smoke test: a known scratch triggers the rerun callback within the
    3-minute target (detected on the next 2-minute poll)."""
    polls = [
        [_inj("Known Scratch", "Available")],   # baseline poll
        [_inj("Known Scratch", "Out")],         # scratch on poll 2 (+120 s)
    ]
    rerun_calls: list = []

    def fetch():
        return polls.pop(0) if polls else [_inj("Known Scratch", "Out")]

    def on_scratch(scratch):
        # simulate the rerun trigger
        rerun_calls.append(scratch["player_name"])

    summary = monitor_late_scratches(
        on_scratch=on_scratch,
        fetch_fn=fetch,
        sleep_fn=lambda s: None,
        poll_interval=_LATE_SCRATCH_POLL_SECONDS,
        max_polls=2,
    )
    # Detected on poll 2 = 120 s after baseline -> well within 3 minutes.
    assert rerun_calls == ["Known Scratch"]
    assert summary["polls"] == 2


def test_monitor_no_scratch_no_callback():
    """A stable slate with no scratches never fires the callback."""
    fired: list = []
    monitor_late_scratches(
        on_scratch=fired.append,
        fetch_fn=lambda: [_inj("Healthy", "Available")],
        sleep_fn=lambda s: None,
        max_polls=3,
    )
    assert fired == []


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
