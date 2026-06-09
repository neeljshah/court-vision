"""tests/test_brain_narrate.py — Tests for src/brain/narrate.py.

Invariants verified:
  * war_room_brief returns non-empty, deterministic string containing team names + win prob.
  * bet_narrative returns deterministic text containing selection + edge.
  * Source code contains no 'anthropic' import and no network calls.
  * Same inputs always produce identical outputs (byte-stable).
"""
from __future__ import annotations

import importlib
import inspect
import os


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SUMMARY = {
    "home": "NYK",
    "away": "SAS",
    "home_mean": 112.4,
    "away_mean": 107.8,
    "total": 220.2,
    "home_win_prob": 0.54,
    "applied_keys": ["home_road", "rest_b2b"],
    "scouting_factors": ["who_decides_late", "blowout_variance"],
    "risk_flags": [],
}

PICK = {
    "market": "PTS",
    "selection": "OVER",
    "line": 27.5,
    "edge": 0.14,
    "model_prob": 0.61,
    "book": "BetMGM",
}


# ---------------------------------------------------------------------------
# war_room_brief tests
# ---------------------------------------------------------------------------

def test_war_room_brief_nonempty():
    """war_room_brief returns a non-empty string."""
    from brain.narrate import war_room_brief
    result = war_room_brief(SUMMARY)
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_war_room_brief_deterministic():
    """Same input produces byte-identical output on repeated calls."""
    from brain.narrate import war_room_brief
    r1 = war_room_brief(SUMMARY)
    r2 = war_room_brief(SUMMARY)
    assert r1 == r2, "war_room_brief is not deterministic"


def test_war_room_brief_contains_team_names():
    """Output contains both team abbreviations."""
    from brain.narrate import war_room_brief
    result = war_room_brief(SUMMARY)
    assert "NYK" in result, f"Home team 'NYK' not found in brief:\n{result}"
    assert "SAS" in result, f"Away team 'SAS' not found in brief:\n{result}"


def test_war_room_brief_contains_win_prob():
    """Output contains a representation of the home win probability."""
    from brain.narrate import war_room_brief
    result = war_room_brief(SUMMARY)
    # home_win_prob=0.54 -> formatted as "54.0%" by :.1%
    assert "54.0%" in result, f"Win prob '54.0%' not found in brief:\n{result}"


def test_war_room_brief_multiline():
    """Output is multi-line (4+ lines as designed)."""
    from brain.narrate import war_room_brief
    result = war_room_brief(SUMMARY)
    lines = [l for l in result.split("\n") if l.strip()]
    assert len(lines) >= 4, f"Expected >=4 lines, got {len(lines)}:\n{result}"


def test_war_room_brief_optional_safe_empty_dict():
    """war_room_brief never raises on an empty input dict."""
    from brain.narrate import war_room_brief
    result = war_room_brief({})
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_war_room_brief_optional_safe_partial():
    """war_room_brief works with only home/away keys."""
    from brain.narrate import war_room_brief
    result = war_room_brief({"home": "BOS", "away": "MIA"})
    assert "BOS" in result
    assert "MIA" in result


def test_war_room_brief_risk_flags_present():
    """Risk flags appear in output when provided."""
    from brain.narrate import war_room_brief
    summary_with_flag = dict(SUMMARY, risk_flags=["blowout_risk"])
    result = war_room_brief(summary_with_flag)
    assert "blowout_risk" in result


def test_war_room_brief_no_risk_flags_message():
    """'No rare risk flags' message appears when risk_flags is empty."""
    from brain.narrate import war_room_brief
    result = war_room_brief(SUMMARY)
    assert "No rare risk flags" in result


# ---------------------------------------------------------------------------
# bet_narrative tests
# ---------------------------------------------------------------------------

def test_bet_narrative_nonempty():
    """bet_narrative returns a non-empty string."""
    from brain.narrate import bet_narrative
    result = bet_narrative(PICK)
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_bet_narrative_deterministic():
    """Same input produces byte-identical output on repeated calls."""
    from brain.narrate import bet_narrative
    r1 = bet_narrative(PICK)
    r2 = bet_narrative(PICK)
    assert r1 == r2, "bet_narrative is not deterministic"


def test_bet_narrative_contains_selection():
    """Output contains the selection string."""
    from brain.narrate import bet_narrative
    result = bet_narrative(PICK)
    assert "OVER" in result, f"Selection 'OVER' not found in:\n{result}"


def test_bet_narrative_contains_edge():
    """Output contains a reference to the edge value."""
    from brain.narrate import bet_narrative
    result = bet_narrative(PICK)
    # edge=0.14 -> "0.14 units"
    assert "0.14" in result, f"Edge '0.14' not found in:\n{result}"


def test_bet_narrative_contains_model_prob():
    """Output contains model probability."""
    from brain.narrate import bet_narrative
    result = bet_narrative(PICK)
    # model_prob=0.61 -> "61.0%"
    assert "61.0%" in result, f"Model prob '61.0%' not found in:\n{result}"


def test_bet_narrative_contains_book():
    """Output contains the book name when provided."""
    from brain.narrate import bet_narrative
    result = bet_narrative(PICK)
    assert "BetMGM" in result, f"Book 'BetMGM' not found in:\n{result}"


def test_bet_narrative_optional_safe_empty():
    """bet_narrative never raises on empty dict."""
    from brain.narrate import bet_narrative
    result = bet_narrative({})
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_bet_narrative_optional_safe_no_book():
    """bet_narrative works without book key."""
    from brain.narrate import bet_narrative
    pick_no_book = {k: v for k, v in PICK.items() if k != "book"}
    result = bet_narrative(pick_no_book)
    assert "OVER" in result


def test_bet_narrative_under_side():
    """UNDER side is correctly reflected in the narrative."""
    from brain.narrate import bet_narrative
    under_pick = dict(PICK, selection="UNDER")
    result = bet_narrative(under_pick)
    assert "UNDER" in result


# ---------------------------------------------------------------------------
# No anthropic / no network assertions
# ---------------------------------------------------------------------------

def test_no_anthropic_in_source():
    """The narrate module source must not contain an 'import anthropic' statement."""
    import brain.narrate as mod
    source = inspect.getsource(mod)
    # Check for actual import statements, not docstring mentions
    forbidden_imports = ["import anthropic", "from anthropic"]
    for token in forbidden_imports:
        assert token not in source, (
            f"Found {token!r} in brain.narrate source — "
            "LLM dependency must not exist here."
        )


def test_no_network_in_source():
    """The narrate module source must not contain network-related imports."""
    import brain.narrate as mod
    source = inspect.getsource(mod)
    forbidden = ["import requests", "import httpx", "import urllib.request",
                 "import aiohttp", "socket."]
    for token in forbidden:
        assert token not in source, (
            f"Found network token {token!r} in brain.narrate source."
        )


def test_no_anthropic_import_at_runtime():
    """Importing brain.narrate must not trigger an anthropic import."""
    import sys
    # Ensure anthropic is NOT already imported (skip check if it is, test still passes)
    if "anthropic" in sys.modules:
        return  # can't assert absence if already present from elsewhere
    import brain.narrate  # noqa: F401 — side-effect check
    assert "anthropic" not in sys.modules, (
        "Importing brain.narrate caused anthropic to be imported."
    )


# ---------------------------------------------------------------------------
# is_enabled tests
# ---------------------------------------------------------------------------

def test_is_enabled_default_off():
    """is_enabled() returns False when CV_NARRATE is unset."""
    from brain.narrate import is_enabled
    # Ensure the flag env var is unset for this test
    env_key = "CV_NARRATE"
    prev = os.environ.pop(env_key, None)
    try:
        assert is_enabled() is False
    finally:
        if prev is not None:
            os.environ[env_key] = prev


def test_is_enabled_on_when_set():
    """is_enabled() returns True when CV_NARRATE=1."""
    from brain.narrate import is_enabled
    env_key = "CV_NARRATE"
    prev = os.environ.get(env_key)
    os.environ[env_key] = "1"
    try:
        assert is_enabled() is True
    finally:
        if prev is None:
            del os.environ[env_key]
        else:
            os.environ[env_key] = prev
