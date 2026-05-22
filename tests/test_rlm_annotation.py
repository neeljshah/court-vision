"""
test_rlm_annotation.py -- Tests for RLM signal integration (16.7-04).

Acceptance criterion: line_timing ingests the RLM (reverse line movement)
field from action_network; steam events are annotated with rlm=True/False;
public-driven moves are tagged correctly.
"""

from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data import line_timing  # noqa: E402
from src.data.line_timing import (  # noqa: E402
    annotate_rlm,
    annotate_steam_from_action_network,
)


def _steam(direction: str) -> dict:
    return {"event": "STEAM", "direction": direction, "velocity": 0.3,
            "magnitude": 0.8 if direction == "over" else -0.8}


def test_public_over_steam_under_is_rlm():
    """Public heavy over but line steamed under -> reverse line movement."""
    event = annotate_rlm(_steam("under"), public_bets_pct=72.0)
    assert event["rlm"] is True
    assert event["move_source"] == "sharp"


def test_public_over_steam_over_is_public_driven():
    """Public heavy over and line steamed over -> public-driven, NOT rlm."""
    event = annotate_rlm(_steam("over"), public_bets_pct=72.0)
    assert event["rlm"] is False
    assert event["move_source"] == "public"


def test_public_under_steam_over_is_rlm():
    """Public heavy under but line steamed over -> reverse line movement."""
    event = annotate_rlm(_steam("over"), public_bets_pct=22.0)
    assert event["rlm"] is True
    assert event["move_source"] == "sharp"


def test_public_under_steam_under_is_public_driven():
    """Public heavy under and line steamed under -> public-driven, NOT rlm."""
    event = annotate_rlm(_steam("under"), public_bets_pct=22.0)
    assert event["rlm"] is False
    assert event["move_source"] == "public"


def test_neutral_public_is_not_rlm():
    """No clear public side -> rlm False, move source unknown."""
    event = annotate_rlm(_steam("over"), public_bets_pct=50.0)
    assert event["rlm"] is False
    assert event["move_source"] == "unknown"


def test_none_event_passes_through():
    """A None event (no steam) annotates to None without error."""
    assert annotate_rlm(None, public_bets_pct=70.0) is None
    assert annotate_steam_from_action_network(None, "Anyone", "pts") is None


def test_ingests_rlm_from_action_network(monkeypatch):
    """annotate_steam_from_action_network pulls the public lean from
    action_network and tags the event accordingly."""
    import src.data.action_network as an

    monkeypatch.setattr(
        an, "get_sharp_pct",
        lambda player, stat: {"public_bets_pct": 78.0, "public_money_pct": 70.0,
                              "rlm": True, "steam_move": True, "found": True},
    )
    # public 78% over, steam under -> RLM
    event = annotate_steam_from_action_network(_steam("under"), "Jayson Tatum", "pts")
    assert event["rlm"] is True
    assert event["public_bets_pct"] == 78.0


def test_action_network_failure_leaves_rlm_unannotated(monkeypatch):
    """If action_network raises, rlm is left None rather than crashing."""
    import src.data.action_network as an

    def boom(player, stat):
        raise RuntimeError("feed down")

    monkeypatch.setattr(an, "get_sharp_pct", boom)
    event = annotate_steam_from_action_network(_steam("over"), "Player", "pts")
    assert event["rlm"] is None


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
