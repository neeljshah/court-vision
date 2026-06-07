"""tests/test_nba_api_v3_patch_cdn.py — CDN PBP normalization.

Verifies the CDN→v3 actionType translation so pbp_poller._classify keeps
matching after the cdn.nba.com switch.
"""
from __future__ import annotations

from scripts.nba_api_v3_patch import _normalize_cdn_action
from scripts.pbp_poller import _classify
from src.live.event_bus import (
    TOPIC_PBP_FOUL, TOPIC_PBP_MADE_SHOT, TOPIC_PBP_SUB,
    TOPIC_PBP_TIMEOUT, TOPIC_PBP_TURNOVER,
)


def test_normalize_made_3pt_to_made_shot():
    a = {"actionType": "3pt", "subType": "Jump Shot",
         "shotResult": "Made", "description": "X 3PT (3 PTS)"}
    out = _normalize_cdn_action(a)
    assert out["actionType"] == "Made Shot"
    assert out["isFieldGoalMade"] is True
    assert _classify(out) == TOPIC_PBP_MADE_SHOT


def test_normalize_missed_2pt_to_missed_shot():
    a = {"actionType": "2pt", "subType": "Jump Shot",
         "shotResult": "Missed", "description": "MISS X 2PT"}
    out = _normalize_cdn_action(a)
    assert out["actionType"] == "Missed Shot"
    assert out["isFieldGoalMade"] is False
    assert _classify(out) is None  # poller intentionally skips misses


def test_normalize_made_freethrow_to_made_shot():
    a = {"actionType": "freethrow", "subType": "1 of 2",
         "shotResult": "Made", "description": "X FT 1 of 2 (1 PTS)"}
    out = _normalize_cdn_action(a)
    assert out["actionType"] == "Made Shot"
    assert _classify(out) == TOPIC_PBP_MADE_SHOT


def test_normalize_foul_substitution_turnover_timeout():
    cases = [
        ("foul", TOPIC_PBP_FOUL, "Foul"),
        ("substitution", TOPIC_PBP_SUB, "Substitution"),
        ("turnover", TOPIC_PBP_TURNOVER, "Turnover"),
        ("timeout", TOPIC_PBP_TIMEOUT, "Timeout"),
    ]
    for cdn_type, expected_topic, expected_v3 in cases:
        a = {"actionType": cdn_type, "subType": "", "description": "X"}
        out = _normalize_cdn_action(a)
        assert out["actionType"] == expected_v3, f"{cdn_type} → {out['actionType']}"
        assert _classify(out) == expected_topic, f"{cdn_type} → {_classify(out)}"


def test_normalize_rebound_steal_intentionally_unclassified():
    """The poller ignores rebounds/steals — confirm normalization doesn't
    accidentally promote them into a classified topic."""
    for cdn_type in ("rebound", "steal", "jumpball"):
        a = {"actionType": cdn_type, "subType": "defensive",
             "description": "X REBOUND"}
        out = _normalize_cdn_action(a)
        assert _classify(out) is None
