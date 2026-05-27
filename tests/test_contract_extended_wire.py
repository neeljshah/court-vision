"""
tests/test_contract_extended_wire.py — Verify extended contract cols are wired into
_contract_for_player and assemble_features.
"""
from __future__ import annotations

import math
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

STEPHEN_CURRY_ID = 201939
SEASON = "2025-26"

_EXPECTED_KEYS = [
    "contract_years_remaining",
    "contract_expiring_flag",
    "contract_player_option_final",
    "contract_team_option_final",
]


def test_contract_extended_keys_present():
    """_contract_for_player must return all 4 new keys."""
    from src.pipeline.feature_assembler import _contract_for_player
    result = _contract_for_player(STEPHEN_CURRY_ID, "Stephen Curry")
    for key in _EXPECTED_KEYS:
        assert key in result, f"missing key: {key}"


def test_contract_years_remaining_is_number():
    """contract_years_remaining must be a float (may be NaN if player absent)."""
    from src.pipeline.feature_assembler import _contract_for_player
    result = _contract_for_player(STEPHEN_CURRY_ID, "Stephen Curry")
    val = result["contract_years_remaining"]
    assert isinstance(val, float), f"expected float, got {type(val)}"


def test_contract_years_remaining_non_negative_or_nan():
    """years_remaining should be >= 0 or NaN (never negative)."""
    from src.pipeline.feature_assembler import _contract_for_player
    result = _contract_for_player(STEPHEN_CURRY_ID, "Stephen Curry")
    val = result["contract_years_remaining"]
    if not math.isnan(val):
        assert val >= 0.0, f"negative years_remaining: {val}"


def test_contract_expiring_flag_binary_or_nan():
    """expiring_flag must be 0.0, 1.0, or NaN."""
    from src.pipeline.feature_assembler import _contract_for_player
    result = _contract_for_player(STEPHEN_CURRY_ID, "Stephen Curry")
    val = result["contract_expiring_flag"]
    if not math.isnan(val):
        assert val in (0.0, 1.0), f"unexpected expiring_flag value: {val}"


def test_option_flags_binary_or_nan():
    """player/team option flags must be 0.0, 1.0, or NaN."""
    from src.pipeline.feature_assembler import _contract_for_player
    result = _contract_for_player(STEPHEN_CURRY_ID, "Stephen Curry")
    for key in ("contract_player_option_final", "contract_team_option_final"):
        val = result[key]
        if not math.isnan(val):
            assert val in (0.0, 1.0), f"{key} unexpected value: {val}"


def test_fallback_unknown_player():
    """Unknown player should still return all 4 keys (as NaN), not raise."""
    from src.pipeline.feature_assembler import _contract_for_player
    result = _contract_for_player(0, "Nonexistent Player XYZ")
    for key in _EXPECTED_KEYS:
        assert key in result, f"missing key for unknown player: {key}"
        assert math.isnan(result[key]), f"expected NaN for unknown player, got {result[key]}"
