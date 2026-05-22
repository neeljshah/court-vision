"""
test_intraday_trigger.py -- Tests for the intraday trigger orchestrator (19.5-02).

Acceptance criterion: intraday_trigger runs a continuous loop polling
foul_trouble_predictor, injury_monitor, and garbage_time_detector every 60s;
qualified events route to bet_selector with a source tag; fires within 3
minutes of a trigger event on replayed data.
"""

from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))

from intraday_trigger import (  # noqa: E402
    POLL_INTERVAL_SECONDS,
    poll_triggers,
    run_intraday_loop,
)


def _foul_box() -> tuple:
    """A live box score with a star in foul trouble (3 fouls, Q2)."""
    return ([
        {"player_id": 1, "player_name": "Star", "team": "BOS",
         "fouls": 3, "usage": 0.31, "is_star": True},
        {"player_id": 2, "player_name": "Mate", "team": "BOS",
         "fouls": 0, "usage": 0.20},
    ], 2)


def _blowout_state() -> list:
    return [{"point_differential": 24.0, "period": 3, "minutes_remaining": 12.0,
             "leading_team": "BOS", "trailing_team": "NYK"}]


def _roster() -> list:
    return [{"player_id": 1, "player_name": "Star", "team": "BOS", "role": "starter"},
            {"player_id": 9, "player_name": "Trail", "team": "NYK", "role": "starter"}]


# ── poll interval ─────────────────────────────────────────────────────────────

def test_poll_interval_is_60_seconds():
    """The orchestrator polls every 60 seconds."""
    assert POLL_INTERVAL_SECONDS == 60


# ── poll_triggers ─────────────────────────────────────────────────────────────

def test_poll_collects_foul_trouble_events():
    """A foul-trouble box score yields source-tagged foul_trouble events."""
    events, _ = poll_triggers(
        box_score_fn=_foul_box,
        injury_fn=lambda: [],
        game_state_fn=lambda: [],
        roster_fn=lambda: [],
        prior_injuries=None,
    )
    foul = [e for e in events if e["source"] == "foul_trouble"]
    assert len(foul) >= 1
    assert all("source" in e for e in events)


def test_poll_collects_garbage_time_events():
    """A blowout game state yields source-tagged garbage_time events."""
    events, _ = poll_triggers(
        box_score_fn=lambda: ([], 0),
        injury_fn=lambda: [],
        game_state_fn=_blowout_state,
        roster_fn=_roster,
        prior_injuries=None,
    )
    gt = [e for e in events if e["source"] == "garbage_time"]
    assert len(gt) >= 1


def test_poll_detects_late_scratch_after_baseline():
    """Late scratch fires once a prior baseline snapshot exists."""
    current = [{"player_name": "Star", "status": "Out", "team_abbrev": "BOS"}]
    # With a prior snapshot showing the player healthy, a scratch is detected.
    events, _ = poll_triggers(
        box_score_fn=lambda: ([], 0),
        injury_fn=lambda: current,
        game_state_fn=lambda: [],
        roster_fn=lambda: [],
        prior_injuries={"star": "Available"},
    )
    scratch = [e for e in events if e["source"] == "late_scratch"]
    assert len(scratch) == 1


# ── run_intraday_loop ─────────────────────────────────────────────────────────

def test_loop_routes_events_to_bet_selector():
    """Qualified events are routed to the (injected) bet_selector route fn."""
    routed: list = []

    summary = run_intraday_loop(
        box_score_fn=_foul_box,
        injury_fn=lambda: [],
        game_state_fn=_blowout_state,
        roster_fn=_roster,
        route_fn=lambda events, date_str: routed.extend(events),
        sleep_fn=lambda s: None,
        max_iterations=1,
    )
    assert summary["iterations"] == 1
    assert summary["events_routed"] >= 2          # foul + garbage time
    assert {e["source"] for e in routed} >= {"foul_trouble", "garbage_time"}


def test_loop_fires_within_three_minutes_of_trigger():
    """Replay: a trigger appearing on poll 2 is routed within 3 minutes.

    At a 60 s cadence, detection on the next poll is +60 s — well inside the
    3-minute target.
    """
    box_states = [([], 0), _foul_box()]   # quiet poll, then foul trouble
    routed_at_poll: list = []

    def box_fn():
        return box_states.pop(0) if box_states else ([], 0)

    def route_fn(events, date_str):
        routed_at_poll.append(len(events))

    run_intraday_loop(
        box_score_fn=box_fn,
        injury_fn=lambda: [],
        game_state_fn=lambda: [],
        roster_fn=lambda: [],
        route_fn=route_fn,
        sleep_fn=lambda s: None,
        poll_interval=POLL_INTERVAL_SECONDS,
        max_iterations=2,
    )
    # Event fired on poll 2 = 60 s after the quiet baseline poll < 180 s.
    assert routed_at_poll and routed_at_poll[-1] >= 1


def test_loop_handles_provider_failure_gracefully():
    """A provider that raises does not crash the loop."""
    def boom():
        raise RuntimeError("feed down")

    summary = run_intraday_loop(
        box_score_fn=boom,
        injury_fn=boom,
        game_state_fn=boom,
        roster_fn=lambda: [],
        route_fn=lambda events, date_str: None,
        sleep_fn=lambda s: None,
        max_iterations=2,
    )
    assert summary["iterations"] == 2


def test_route_intraday_events_persists_with_source_tag(tmp_path, monkeypatch):
    """bet_selector.route_intraday_events writes events keeping the source tag."""
    from src.prediction import bet_selector
    monkeypatch.setattr(bet_selector, "_OUTPUT_DIR", str(tmp_path))

    n = bet_selector.route_intraday_events(
        [{"event": "FOUL_TROUBLE", "source": "foul_trouble", "player_id": 1}],
        date_str="2026-05-21",
    )
    assert n == 1
    import json
    out = tmp_path / "intraday_triggers_20260521.json"
    assert out.exists()
    saved = json.loads(out.read_text())
    assert saved["events"][0]["source"] == "foul_trouble"
    assert "routed_at" in saved["events"][0]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
