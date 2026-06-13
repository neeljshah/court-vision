"""tests/platform/test_equivalence_check_deep_diff.py

Unit tests for _deep_diff in
scripts/platformkit/proof_common/equivalence_check.py.

KEY property under test: a real divergence is NEVER silently missed.
No false "equal" — every structural or value difference must appear
in the returned diff list.
"""
from __future__ import annotations

import math
from typing import Any, List

import pytest

from scripts.platformkit.proof_common.equivalence_check import _deep_diff


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _has_diff(result: List[str]) -> bool:
    """True if _deep_diff reported at least one divergence."""
    return len(result) > 0


# ---------------------------------------------------------------------------
# Case 1 — identical dicts → empty diff
# ---------------------------------------------------------------------------

class TestIdentical:
    def test_empty_dicts(self):
        assert _deep_diff({}, {}) == []

    def test_flat_dict_identical(self):
        d = {"a": 1, "b": "hello", "c": 3.14}
        assert _deep_diff(d, d.copy()) == []

    def test_nested_dict_identical(self):
        d = {"outer": {"inner": 42}}
        assert _deep_diff(d, {"outer": {"inner": 42}}) == []

    def test_identical_scalars(self):
        assert _deep_diff(7, 7) == []
        assert _deep_diff("x", "x") == []
        assert _deep_diff(True, True) == []

    def test_identical_lists(self):
        assert _deep_diff([1, 2, 3], [1, 2, 3]) == []

    def test_identical_empty_list(self):
        assert _deep_diff([], []) == []


# ---------------------------------------------------------------------------
# Case 2 — missing key → only-in-old
# ---------------------------------------------------------------------------

class TestMissingKey:
    def test_key_only_in_old(self):
        old = {"a": 1, "b": 2}
        new = {"a": 1}
        diffs = _deep_diff(old, new)
        assert _has_diff(diffs), "Missing key not detected"
        assert any("only-in-old" in d for d in diffs)

    def test_nested_missing_key(self):
        old = {"x": {"y": 1, "z": 2}}
        new = {"x": {"y": 1}}
        diffs = _deep_diff(old, new)
        assert _has_diff(diffs), "Nested missing key not detected"
        assert any("only-in-old" in d for d in diffs)


# ---------------------------------------------------------------------------
# Case 3 — extra key → only-in-new
# ---------------------------------------------------------------------------

class TestExtraKey:
    def test_key_only_in_new(self):
        old = {"a": 1}
        new = {"a": 1, "b": 99}
        diffs = _deep_diff(old, new)
        assert _has_diff(diffs), "Extra key not detected"
        assert any("only-in-new" in d for d in diffs)

    def test_nested_extra_key(self):
        old = {"x": {"y": 1}}
        new = {"x": {"y": 1, "z": 2}}
        diffs = _deep_diff(old, new)
        assert _has_diff(diffs), "Nested extra key not detected"
        assert any("only-in-new" in d for d in diffs)


# ---------------------------------------------------------------------------
# Case 4 — NaN == NaN treated as EQUAL (no spurious diff)
# ---------------------------------------------------------------------------

class TestNaN:
    def test_nan_nan_no_diff(self):
        diffs = _deep_diff(float("nan"), float("nan"))
        assert diffs == [], f"NaN vs NaN should be equal, got: {diffs}"

    def test_nan_in_dict_no_diff(self):
        d = {"score": float("nan")}
        diffs = _deep_diff(d, {"score": float("nan")})
        assert diffs == [], f"NaN in dict should be equal, got: {diffs}"

    def test_nan_vs_zero_is_diff(self):
        diffs = _deep_diff(float("nan"), 0.0)
        assert _has_diff(diffs), "NaN vs 0.0 should be detected as different"

    def test_nan_vs_float_is_diff(self):
        diffs = _deep_diff(float("nan"), 1.5)
        assert _has_diff(diffs), "NaN vs 1.5 should be detected as different"


# ---------------------------------------------------------------------------
# Case 5 — type mismatch → diff reported
# ---------------------------------------------------------------------------

class TestTypeMismatch:
    def test_int_vs_str(self):
        diffs = _deep_diff(1, "1")
        assert _has_diff(diffs), "int vs str not detected"
        assert any("type" in d for d in diffs)

    def test_list_vs_dict(self):
        diffs = _deep_diff([], {})
        assert _has_diff(diffs), "list vs dict not detected"
        assert any("type" in d for d in diffs)

    def test_int_vs_float(self):
        # int and float are different types in Python.
        diffs = _deep_diff(1, 1.0)
        assert _has_diff(diffs), "int vs float not detected as type mismatch"
        assert any("type" in d for d in diffs)

    def test_none_vs_zero(self):
        diffs = _deep_diff(None, 0)
        assert _has_diff(diffs), "None vs 0 not detected"

    def test_bool_vs_int(self):
        # bool is a subclass of int in Python, but type(True) is bool != int.
        diffs = _deep_diff(True, 1)
        assert _has_diff(diffs), "bool vs int not detected as type mismatch"


# ---------------------------------------------------------------------------
# Case 6 — nested divergence shows dotted path
# ---------------------------------------------------------------------------

class TestDottedPath:
    def test_nested_value_divergence_path(self):
        old = {"level1": {"level2": {"value": 10}}}
        new = {"level1": {"level2": {"value": 99}}}
        diffs = _deep_diff(old, new, "root")
        assert _has_diff(diffs)
        # Expect a dotted path like root.level1.level2.value
        assert any("level1" in d and "level2" in d and "value" in d for d in diffs), (
            f"Expected dotted path in diff, got: {diffs}"
        )

    def test_path_prefix_propagated(self):
        diffs = _deep_diff({"k": 1}, {"k": 2}, path="prefix")
        assert _has_diff(diffs)
        assert any("prefix" in d for d in diffs)

    def test_list_index_in_path(self):
        diffs = _deep_diff([1, 2, 3], [1, 9, 3], path="arr")
        assert _has_diff(diffs)
        # Should reference index [1]
        assert any("[1]" in d for d in diffs)


# ---------------------------------------------------------------------------
# Case 7 — list length mismatch reported
# ---------------------------------------------------------------------------

class TestListLength:
    def test_longer_new_list(self):
        diffs = _deep_diff([1, 2], [1, 2, 3])
        assert _has_diff(diffs), "Longer new list not detected"
        assert any("length" in d for d in diffs)

    def test_shorter_new_list(self):
        diffs = _deep_diff([1, 2, 3], [1])
        assert _has_diff(diffs), "Shorter new list not detected"
        assert any("length" in d for d in diffs)

    def test_empty_vs_nonempty(self):
        diffs = _deep_diff([], [1])
        assert _has_diff(diffs), "Empty vs non-empty list not detected"
        assert any("length" in d for d in diffs)

    def test_length_mismatch_and_element_diffs_both_reported(self):
        # zip stops at the shorter list, so common elements are still compared.
        diffs = _deep_diff([1, 99], [1, 2, 3])
        assert any("length" in d for d in diffs)
        # The element at index 1 differs (99 vs 2).
        assert any("[1]" in d for d in diffs)


# ---------------------------------------------------------------------------
# Case 8 — identical lists → empty diff (already in TestIdentical, repeat
#           explicitly here per spec)
# ---------------------------------------------------------------------------

class TestIdenticalLists:
    def test_identical_int_list(self):
        lst = [10, 20, 30]
        assert _deep_diff(lst, list(lst)) == []

    def test_identical_mixed_list(self):
        lst = [1, "two", 3.0]
        assert _deep_diff(lst, [1, "two", 3.0]) == []

    def test_identical_nested_list(self):
        lst = [[1, 2], [3, 4]]
        assert _deep_diff(lst, [[1, 2], [3, 4]]) == []


# ---------------------------------------------------------------------------
# Key-property meta-tests: real divergence is NEVER silently missed
# ---------------------------------------------------------------------------

class TestNoMissedDivergences:
    """Exhaustive spot-check: any changed value must produce a non-empty diff."""

    @pytest.mark.parametrize("old,new", [
        ({"a": 1}, {"a": 2}),
        ({"a": "x"}, {"a": "y"}),
        ({"a": 1.0}, {"a": 1.1}),
        ({"a": True}, {"a": False}),
        ({"a": [1, 2]}, {"a": [1, 3]}),
        ({"a": {"b": 1}}, {"a": {"b": 2}}),
        ([1, 2, 3], [1, 2, 4]),
        (1, 2),
        ("hello", "world"),
    ])
    def test_changed_value_always_produces_diff(self, old, new):
        diffs = _deep_diff(old, new)
        assert _has_diff(diffs), (
            f"MISSED DIVERGENCE: old={old!r} new={new!r} produced empty diff"
        )

    def test_float_off_by_epsilon_detected(self):
        """No tolerance — even a 1-ULP difference must be caught."""
        import struct
        # Produce the next representable float after 1.0
        bits = struct.unpack("Q", struct.pack("d", 1.0))[0] + 1
        next_float = struct.unpack("d", struct.pack("Q", bits))[0]
        diffs = _deep_diff(1.0, next_float)
        assert _has_diff(diffs), "1-ULP float difference was silently missed"
