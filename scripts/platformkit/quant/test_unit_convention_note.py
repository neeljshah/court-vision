"""tests for scripts.platformkit.quant.unit_convention_note.

Acceptance criteria (from be-r2-w7-unit-convention-note):
  * helper returns a note distinguishing 'Kelly-style stake_units' from
    'flat 1.0 display unit'.
  * note mentions UNITS not $.
  * note contains no $/dollar/pnl/roi token and no retracted number.
  * deterministic (same args => same output every time).
  * never raises.
"""
from __future__ import annotations

import re

import pytest

from scripts.platformkit.quant.unit_convention_note import (
    UNIT_CONVENTION_NOTE,
    attach_note,
    unit_convention_note,
)

# ---------------------------------------------------------------------------
# Banned tokens -- none of these may appear in any output string
# ---------------------------------------------------------------------------

_BANNED_MONEY_TOKENS = re.compile(
    r"\$|dollar|pnl|roi|profit|bankroll|stake_dollars",
    re.IGNORECASE,
)

# Retracted numbers that must never appear
_BANNED_RETRACTED = re.compile(
    r"18\.38|0\.119|(?<!\d)54%|\+54|78\.11|8\.94|54\.57",
)


def _assert_clean(text: str, label: str = "") -> None:
    """Assert no banned money tokens or retracted numbers in text."""
    assert not _BANNED_MONEY_TOKENS.search(text), (
        f"{label}: banned money token found in: {text!r}"
    )
    assert not _BANNED_RETRACTED.search(text), (
        f"{label}: retracted number found in: {text!r}"
    )


# ---------------------------------------------------------------------------
# Tests for UNIT_CONVENTION_NOTE constant
# ---------------------------------------------------------------------------

class TestUnitConventionNoteConstant:
    def test_is_string(self):
        assert isinstance(UNIT_CONVENTION_NOTE, str)

    def test_mentions_kelly(self):
        assert "Kelly" in UNIT_CONVENTION_NOTE or "kelly" in UNIT_CONVENTION_NOTE.lower()

    def test_mentions_stake_units(self):
        assert "stake_units" in UNIT_CONVENTION_NOTE

    def test_mentions_flat_unit(self):
        assert "flat" in UNIT_CONVENTION_NOTE.lower() and "1.0" in UNIT_CONVENTION_NOTE

    def test_mentions_units_not_dollars(self):
        assert "UNITS" in UNIT_CONVENTION_NOTE or "units" in UNIT_CONVENTION_NOTE.lower()

    def test_no_banned_tokens(self):
        _assert_clean(UNIT_CONVENTION_NOTE, "UNIT_CONVENTION_NOTE")

    def test_mentions_bestbets_board(self):
        assert "bestbets" in UNIT_CONVENTION_NOTE.lower() or "board" in UNIT_CONVENTION_NOTE.lower()

    def test_distinguishes_two_conventions(self):
        note_lower = UNIT_CONVENTION_NOTE.lower()
        assert "kelly" in note_lower, "should mention Kelly sizing"
        assert "flat" in note_lower, "should mention flat display unit"
        assert "1.0" in UNIT_CONVENTION_NOTE, "should mention 1.0 flat unit"


# ---------------------------------------------------------------------------
# Tests for unit_convention_note()
# ---------------------------------------------------------------------------

class TestUnitConventionNoteFunc:
    def test_returns_dict(self):
        result = unit_convention_note()
        assert isinstance(result, dict)

    def test_required_keys_present(self):
        result = unit_convention_note()
        for key in ("note", "kelly_units", "flat_unit", "surface", "units", "edge_claimed"):
            assert key in result, f"missing key: {key}"

    def test_units_field_is_units_not_dollars(self):
        result = unit_convention_note()
        assert result["units"] == "units"

    def test_edge_claimed_is_false(self):
        result = unit_convention_note()
        assert result["edge_claimed"] is False

    def test_note_distinguishes_kelly_from_flat(self):
        result = unit_convention_note()
        note = result["note"]
        assert "Kelly" in note or "kelly" in note.lower()
        assert "flat" in note.lower() or "1.0" in note

    def test_kelly_units_field_content(self):
        result = unit_convention_note()
        field = result["kelly_units"]
        assert "stake_units" in field
        assert "Kelly" in field or "kelly" in field.lower()
        assert "flat_unit" in field

    def test_flat_unit_field_content(self):
        result = unit_convention_note()
        field = result["flat_unit"]
        assert "1.0" in field or "flat" in field.lower()
        assert "board" in field.lower() or "display" in field.lower()

    def test_surface_default(self):
        result = unit_convention_note()
        assert result["surface"] == "quant"

    def test_surface_custom(self):
        result = unit_convention_note(surface="pm_trail")
        assert result["surface"] == "pm_trail"

    def test_no_banned_tokens_in_any_string_field(self):
        result = unit_convention_note()
        for key, value in result.items():
            if isinstance(value, str):
                _assert_clean(value, f"field '{key}'")

    def test_deterministic_default(self):
        r1 = unit_convention_note()
        r2 = unit_convention_note()
        assert r1 == r2

    def test_deterministic_with_surface(self):
        r1 = unit_convention_note(surface="risk")
        r2 = unit_convention_note(surface="risk")
        assert r1 == r2

    def test_never_raises_on_any_surface(self):
        for surface in ("quant", "pm_trail", "risk", "bestbets", "", "x" * 200):
            # must not raise
            result = unit_convention_note(surface=surface)
            assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Tests for attach_note()
# ---------------------------------------------------------------------------

class TestAttachNote:
    def test_returns_dict(self):
        result = attach_note({"a": 1})
        assert isinstance(result, dict)

    def test_injects_unit_convention_note_key(self):
        result = attach_note({"some": "payload"})
        assert "unit_convention_note" in result

    def test_preserves_original_keys(self):
        payload = {"stake_units": 2.5, "model_prob": 0.6}
        result = attach_note(payload)
        assert result["stake_units"] == 2.5
        assert result["model_prob"] == 0.6

    def test_does_not_mutate_original(self):
        payload = {"a": 1}
        attach_note(payload)
        assert "unit_convention_note" not in payload

    def test_nested_note_is_a_dict(self):
        result = attach_note({})
        assert isinstance(result["unit_convention_note"], dict)

    def test_nested_note_has_edge_claimed_false(self):
        result = attach_note({})
        assert result["unit_convention_note"]["edge_claimed"] is False

    def test_surface_carried_into_nested_note(self):
        result = attach_note({}, surface="pm_trail")
        assert result["unit_convention_note"]["surface"] == "pm_trail"

    def test_never_raises_on_bad_payload(self):
        # Should not raise even on empty or unusual payloads.
        for payload in [{}, {"x": None}, {"nested": {"a": 1}}]:
            r = attach_note(payload)
            assert isinstance(r, dict)

    def test_no_banned_tokens_in_nested_note_strings(self):
        result = attach_note({})
        note_block = result["unit_convention_note"]
        for key, value in note_block.items():
            if isinstance(value, str):
                _assert_clean(value, f"attach_note nested field '{key}'")
