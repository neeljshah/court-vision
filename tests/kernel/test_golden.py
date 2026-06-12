"""tests.kernel.test_golden — Hermetic tests for kernel.testing.golden.

All tests use pytest's ``tmp_path`` fixture so no filesystem side-effects
escape the test session.  No network, no GPU, no domain code.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

from kernel.testing.golden import (
    compare_golden,
    load_golden,
    save_golden,
    verify_manifest,
    write_manifest,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def gdir(tmp_path: pathlib.Path) -> pathlib.Path:
    """An isolated golden directory for each test."""
    d = tmp_path / "goldens"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# save / load round-trip
# ---------------------------------------------------------------------------


class TestSaveLoadRoundTrip:
    def test_array_round_trip(self, gdir: pathlib.Path) -> None:
        arr = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
        save_golden("arr", arr, gdir)
        restored = load_golden("arr", gdir)
        assert isinstance(restored, np.ndarray)
        assert np.array_equal(arr, restored)
        assert arr.dtype == restored.dtype

    def test_dict_round_trip(self, gdir: pathlib.Path) -> None:
        data = {"a": 1, "b": [2, 3], "c": "hello"}
        save_golden("meta", data, gdir)
        restored = load_golden("meta", gdir)
        assert restored == data

    def test_scalar_int_round_trip(self, gdir: pathlib.Path) -> None:
        save_golden("n", 42, gdir)
        assert load_golden("n", gdir) == 42

    def test_scalar_float_round_trip(self, gdir: pathlib.Path) -> None:
        save_golden("f", 3.14159265358979, gdir)
        assert load_golden("f", gdir) == 3.14159265358979

    def test_list_round_trip(self, gdir: pathlib.Path) -> None:
        lst = [1, "two", 3.0, None]
        save_golden("lst", lst, gdir)
        assert load_golden("lst", gdir) == lst

    def test_array_full_precision(self, gdir: pathlib.Path) -> None:
        """Saved array must preserve full float64 precision (no rounding)."""
        arr = np.array([1.0 + 1e-15, 2.0 - 1e-15], dtype=np.float64)
        save_golden("precise", arr, gdir)
        restored = load_golden("precise", gdir)
        assert np.array_equal(arr, restored), "full precision must be preserved"

    def test_load_missing_raises(self, gdir: pathlib.Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_golden("nonexistent", gdir)


# ---------------------------------------------------------------------------
# compare_golden — EXACT equality
# ---------------------------------------------------------------------------


class TestCompareGolden:
    # ---- arrays ----

    def test_array_exact_match(self, gdir: pathlib.Path) -> None:
        arr = np.array([10, 20, 30], dtype=np.int32)
        save_golden("a", arr, gdir)
        ok, msg = compare_golden("a", arr.copy(), gdir)
        assert ok is True
        assert msg == "ok"

    def test_array_tiny_float_diff_is_not_ok(self, gdir: pathlib.Path) -> None:
        """A 1e-12 perturbation must be detected (no allclose tolerance)."""
        arr = np.array([1.0, 2.0, 3.0], dtype=np.float64)
        save_golden("b", arr, gdir)
        perturbed = arr.copy()
        perturbed[1] += 1e-12
        ok, msg = compare_golden("b", perturbed, gdir)
        assert ok is False
        assert "mismatch" in msg.lower() or "differ" in msg.lower()

    def test_array_single_element_changed(self, gdir: pathlib.Path) -> None:
        arr = np.array([1, 2, 3, 4, 5], dtype=np.int64)
        save_golden("c", arr, gdir)
        bad = arr.copy()
        bad[3] = 99
        ok, msg = compare_golden("c", bad, gdir)
        assert ok is False
        assert "differ" in msg or "mismatch" in msg

    def test_array_shape_mismatch(self, gdir: pathlib.Path) -> None:
        arr = np.zeros((3, 4), dtype=np.float32)
        save_golden("shape", arr, gdir)
        ok, msg = compare_golden("shape", np.zeros((4, 3), dtype=np.float32), gdir)
        assert ok is False
        assert "shape" in msg.lower()

    def test_array_dtype_mismatch(self, gdir: pathlib.Path) -> None:
        arr = np.zeros((2, 2), dtype=np.float32)
        save_golden("dtype", arr, gdir)
        ok, msg = compare_golden("dtype", np.zeros((2, 2), dtype=np.float64), gdir)
        assert ok is False
        assert "dtype" in msg.lower()

    # ---- JSON-able scalars/dicts ----

    def test_dict_exact_match(self, gdir: pathlib.Path) -> None:
        data = {"x": 1, "y": 2}
        save_golden("d", data, gdir)
        ok, msg = compare_golden("d", {"x": 1, "y": 2}, gdir)
        assert ok is True

    def test_dict_value_changed(self, gdir: pathlib.Path) -> None:
        data = {"x": 1, "y": 2}
        save_golden("e", data, gdir)
        ok, msg = compare_golden("e", {"x": 1, "y": 99}, gdir)
        assert ok is False
        assert "mismatch" in msg.lower()

    def test_scalar_exact_match(self, gdir: pathlib.Path) -> None:
        save_golden("s", 7, gdir)
        ok, _ = compare_golden("s", 7, gdir)
        assert ok is True

    def test_scalar_mismatch(self, gdir: pathlib.Path) -> None:
        save_golden("t", 7, gdir)
        ok, msg = compare_golden("t", 8, gdir)
        assert ok is False

    def test_missing_golden_returns_false(self, gdir: pathlib.Path) -> None:
        ok, msg = compare_golden("ghost", np.array([1]), gdir)
        assert ok is False
        assert "ghost" in msg

    # ---- type crossing ----

    def test_array_vs_scalar_type_mismatch(self, gdir: pathlib.Path) -> None:
        arr = np.array([1.0])
        save_golden("type_cross", arr, gdir)
        ok, msg = compare_golden("type_cross", 1.0, gdir)
        assert ok is False

    def test_scalar_vs_array_type_mismatch(self, gdir: pathlib.Path) -> None:
        save_golden("type_cross2", 1.0, gdir)
        ok, msg = compare_golden("type_cross2", np.array([1.0]), gdir)
        # stored is float (JSON), current is array — mismatch
        assert ok is False


# ---------------------------------------------------------------------------
# Manifest write + verify
# ---------------------------------------------------------------------------


class TestManifest:
    def test_manifest_write_and_verify_clean(self, gdir: pathlib.Path) -> None:
        arr = np.array([1, 2, 3])
        save_golden("m_arr", arr, gdir)
        save_golden("m_dict", {"k": "v"}, gdir)
        write_manifest(gdir)
        ok, msg = verify_manifest(gdir)
        assert ok is True, msg

    def test_manifest_detects_hand_edit(self, gdir: pathlib.Path) -> None:
        """Byte-editing a golden file after manifest creation must fail verify."""
        save_golden("editable", {"val": 42}, gdir)
        write_manifest(gdir)

        # Corrupt the file silently
        json_path = gdir / "editable.json"
        original = json_path.read_text(encoding="utf-8")
        json_path.write_text(original.replace("42", "99"), encoding="utf-8")

        ok, msg = verify_manifest(gdir)
        assert ok is False
        assert "editable.json" in msg or "digest changed" in msg.lower()

    def test_manifest_missing_raises_false(self, gdir: pathlib.Path) -> None:
        save_golden("x", 1, gdir)
        # Do NOT write manifest
        ok, msg = verify_manifest(gdir)
        assert ok is False
        assert "not found" in msg.lower() or "manifest" in msg.lower()

    def test_manifest_empty_dir(self, gdir: pathlib.Path) -> None:
        write_manifest(gdir)
        ok, msg = verify_manifest(gdir)
        assert ok is True, msg

    def test_manifest_detects_deleted_file(self, gdir: pathlib.Path) -> None:
        save_golden("will_delete", [1, 2], gdir)
        write_manifest(gdir)
        (gdir / "will_delete.json").unlink()
        ok, msg = verify_manifest(gdir)
        assert ok is False
        assert "will_delete.json" in msg or "missing" in msg.lower()

    def test_manifest_array_and_json_together(self, gdir: pathlib.Path) -> None:
        save_golden("combo_arr", np.eye(3), gdir)
        save_golden("combo_json", [1, 2, 3], gdir)
        write_manifest(gdir)
        ok, msg = verify_manifest(gdir)
        assert ok is True, msg
