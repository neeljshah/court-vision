"""Per-file tests for predict_service.progress_semantics.engine_honest_note.

Acceptance criteria (from BACKLOG be-r2-w6-progress-engine-semantics):
  A. engine_enabled=True  -> note contains 'measurement loop' AND
                             'real-money gate = DENY'
  B. engine_enabled=False -> note is non-empty but need NOT contain the above
  C. note NEVER contains $, roi, pnl, or any retracted figure
     (18.38 / 0.119 / 54% / 78.11 / 8.94 / 54.57)
  D. function NEVER raises on a partial or None status dict
"""
from __future__ import annotations

import pytest

from predict_service.progress_semantics import engine_honest_note

# ---------------------------------------------------------------------------
# A. engine_enabled=True via explicit kwarg
# ---------------------------------------------------------------------------

def test_enabled_contains_measurement_loop():
    note = engine_honest_note(engine_enabled=True)
    assert "measurement loop" in note.lower(), (
        f"Expected 'measurement loop' in note, got: {note!r}"
    )


def test_enabled_contains_real_money_deny():
    note = engine_honest_note(engine_enabled=True)
    assert "real-money gate = deny" in note.lower(), (
        f"Expected 'real-money gate = DENY' in note, got: {note!r}"
    )


def test_enabled_via_status_dict():
    status = {"engine_enabled": True, "ts": 1234567890}
    note = engine_honest_note(status=status)
    assert "measurement loop" in note.lower()
    assert "real-money gate = deny" in note.lower()


# ---------------------------------------------------------------------------
# B. engine_enabled=False
# ---------------------------------------------------------------------------

def test_disabled_returns_non_empty_string():
    note = engine_honest_note(engine_enabled=False)
    assert isinstance(note, str) and len(note) > 0


def test_disabled_does_not_claim_measurement_loop_is_running():
    # The disabled note should not say the loop IS running.
    note = engine_honest_note(engine_enabled=False)
    # "measurement loop is running" is the enabled phrasing; disabled must not use it
    assert "measurement loop is running" not in note.lower()


def test_disabled_via_status_dict():
    status = {"engine_enabled": False}
    note = engine_honest_note(status=status)
    assert isinstance(note, str) and len(note) > 0
    assert "real-money gate = deny" in note.lower()


# ---------------------------------------------------------------------------
# C. No banned content regardless of engine_enabled
# ---------------------------------------------------------------------------

_BANNED = [
    "$",        # dollar sign
    "roi",
    "pnl",
    "profit",
    "18.38",
    "0.119",
    "78.11",
    "8.94",
    "54.57",
]


@pytest.mark.parametrize("enabled", [True, False])
def test_no_banned_content(enabled: bool):
    note = engine_honest_note(engine_enabled=enabled)
    note_lower = note.lower()
    for frag in _BANNED:
        assert frag.lower() not in note_lower, (
            f"Banned fragment {frag!r} found in note: {note!r}"
        )


@pytest.mark.parametrize("enabled", [True, False])
def test_no_percent_54_edge_claim(enabled: bool):
    """The retracted +54% edge figure must not appear."""
    note = engine_honest_note(engine_enabled=enabled)
    assert "54%" not in note, f"Retracted 54% found in note: {note!r}"


# ---------------------------------------------------------------------------
# D. Never raises on partial/None/malformed status dicts
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_status", [
    None,
    {},
    {"engine_enabled": None},
    {"other_key": 99},
    {"engine_enabled": "yes"},  # non-bool truthy string
    {"engine_enabled": 0},
    {"engine_enabled": 1},
    [],                         # wrong type entirely
    "not a dict",
    42,
])
def test_never_raises_on_bad_status(bad_status):
    """engine_honest_note must not raise regardless of status dict shape."""
    try:
        note = engine_honest_note(status=bad_status)  # type: ignore[arg-type]
        assert isinstance(note, str) and len(note) > 0
    except Exception as exc:
        pytest.fail(f"engine_honest_note raised on status={bad_status!r}: {exc}")


def test_none_status_no_kwarg_defaults_to_disabled():
    """No args -> defaults to disabled note, non-empty, no raises."""
    note = engine_honest_note()
    assert isinstance(note, str) and len(note) > 0


def test_explicit_override_beats_status_dict():
    """explicit engine_enabled kwarg overrides whatever is in the status dict."""
    status = {"engine_enabled": False}
    note = engine_honest_note(status=status, engine_enabled=True)
    assert "measurement loop" in note.lower()
    assert "real-money gate = deny" in note.lower()
