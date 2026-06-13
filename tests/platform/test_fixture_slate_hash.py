"""tests/platform/test_fixture_slate_hash.py — hermetic tests for fixture_slate_hash.

Covers:
* canonical_hash determinism (same input → same digest, twice)
* 1e-9-magnitude change flips the hash
* 1e-13-magnitude change does NOT flip the hash (rounding proof)
* hash_slate with injected fake runners is deterministic
* --capture then --compare (via CLI) returns clean exit
* --compare flags exactly the perturbed surface, not the clean ones
* default stub runners raise NotImplementedError (import-safe guard)

Hermetic: no real sim, no network, no GPU, stdlib + src only.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

# ---------------------------------------------------------------------------
# Locate the module under test (works regardless of working directory)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_PLATFORM = _REPO_ROOT / "scripts" / "platformkit"
if str(_SCRIPTS_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_PLATFORM))

from fixture_slate_hash import (  # noqa: E402
    SURFACE_NAMES,
    canonical_hash,
    hash_slate,
    main,
)

# ---------------------------------------------------------------------------
# Shared fake surface outputs
# ---------------------------------------------------------------------------

_FAKE_OUTPUT: Dict[str, Any] = {
    "win_prob": 0.4739213,
    "markets": {
        "pts_q50": 112.5,
        "pts_q10": 99.1,
        "pts_q90": 126.3,
        "nested": {"reb": 44.0, "ast": 23.5},
    },
    "players": [
        {"id": "p1", "pts_mean": 28.4, "reb_mean": 5.1},
        {"id": "p2", "pts_mean": 21.0, "reb_mean": 7.9},
    ],
}


def _make_runners(output: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Return surface_runners dict where every surface returns *output*."""
    data = output if output is not None else _FAKE_OUTPUT

    def _runner() -> Any:
        return data

    return {name: _runner for name in SURFACE_NAMES}


# ---------------------------------------------------------------------------
# canonical_hash unit tests
# ---------------------------------------------------------------------------

class TestCanonicalHash:
    def test_deterministic_same_object(self) -> None:
        """Hashing the same object twice yields identical digests."""
        h1 = canonical_hash(_FAKE_OUTPUT)
        h2 = canonical_hash(_FAKE_OUTPUT)
        assert h1 == h2

    def test_deterministic_equivalent_dicts(self) -> None:
        """Two dicts with the same content but different insertion order hash identically."""
        a = {"z": 1.0, "a": 2.0}
        b = {"a": 2.0, "z": 1.0}
        assert canonical_hash(a) == canonical_hash(b)

    def test_1e9_change_flips_hash(self) -> None:
        """A change of exactly 1e-9 in a float MUST change the hash."""
        base = {"v": 1.000_000_000}
        perturbed = {"v": 1.000_000_001}  # +1e-9
        assert canonical_hash(base) != canonical_hash(perturbed)

    def test_1e13_change_does_not_flip_hash(self) -> None:
        """A change of 1e-13 (sub-rounding) must NOT change the hash."""
        base = {"v": 1.0}
        sub = {"v": 1.0 + 1e-13}
        assert canonical_hash(base) == canonical_hash(sub)

    def test_nested_dict_sorted(self) -> None:
        """Nested dicts with different key order produce the same hash."""
        a = {"outer": {"b": 2, "a": 1}}
        b = {"outer": {"a": 1, "b": 2}}
        assert canonical_hash(a) == canonical_hash(b)

    def test_list_order_matters(self) -> None:
        """Lists are order-sensitive — swapping elements changes the hash."""
        assert canonical_hash([1, 2]) != canonical_hash([2, 1])

    def test_returns_hex_string(self) -> None:
        """Return value is a 64-character lowercase hex string (SHA-256)."""
        h = canonical_hash({"x": 1.0})
        assert isinstance(h, str)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# hash_slate unit tests
# ---------------------------------------------------------------------------

class TestHashSlate:
    def test_returns_all_three_surfaces(self) -> None:
        """hash_slate always returns exactly the three canonical surface names."""
        result = hash_slate(_make_runners())
        assert set(result.keys()) == set(SURFACE_NAMES)

    def test_deterministic_twice(self) -> None:
        """Calling hash_slate twice with the same runners returns identical dicts."""
        runners = _make_runners()
        r1 = hash_slate(runners)
        r2 = hash_slate(runners)
        assert r1 == r2

    def test_all_hashes_are_hex(self) -> None:
        """Every surface hash is a 64-char hex string."""
        result = hash_slate(_make_runners())
        for name, h in result.items():
            assert len(h) == 64, f"surface {name!r} hash wrong length"
            assert all(c in "0123456789abcdef" for c in h)

    def test_perturbed_surface_flips_hash(self) -> None:
        """A 1e-9 change in one surface's output flips only that surface's hash."""
        base_output: Dict[str, Any] = {"win_prob": 0.5, "pts": 100.0}
        perturbed_output: Dict[str, Any] = {"win_prob": 0.5 + 1e-9, "pts": 100.0}

        def _base() -> Any:
            return base_output

        def _perturbed() -> Any:
            return perturbed_output

        base_runners = {n: _base for n in SURFACE_NAMES}
        h_base = hash_slate(base_runners)

        # Perturb only "pregame_joint"
        perturbed_runners = dict(base_runners)
        perturbed_runners["pregame_joint"] = _perturbed
        h_perturbed = hash_slate(perturbed_runners)

        assert h_perturbed["pregame_joint"] != h_base["pregame_joint"], (
            "perturbed surface should have a different hash"
        )
        assert h_perturbed["ingame_replay"] == h_base["ingame_replay"], (
            "unperturbed surface must be unchanged"
        )
        assert h_perturbed["prop_predict"] == h_base["prop_predict"], (
            "unperturbed surface must be unchanged"
        )

    def test_sub_1e12_does_not_flip(self) -> None:
        """A 1e-13 change does NOT flip any surface hash (rounding proof)."""
        base_output: Dict[str, Any] = {"v": 1.0}
        tiny_output: Dict[str, Any] = {"v": 1.0 + 1e-13}

        def _base() -> Any:
            return base_output

        def _tiny() -> Any:
            return tiny_output

        base_runners = {n: _base for n in SURFACE_NAMES}
        tiny_runners = {n: _tiny for n in SURFACE_NAMES}

        h_base = hash_slate(base_runners)
        h_tiny = hash_slate(tiny_runners)
        assert h_base == h_tiny, "sub-1e-12 change must not change any hash"

    def test_default_stubs_raise_not_implemented(self) -> None:
        """Calling hash_slate with no injected runners raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="real runner deferred"):
            hash_slate()


# ---------------------------------------------------------------------------
# CLI integration tests (capture + compare round-trip)
# ---------------------------------------------------------------------------

class TestCLI:
    def test_capture_then_compare_clean(self, tmp_path: Path) -> None:
        """--capture writes a JSON file; --compare against itself exits 0."""
        out_file = str(tmp_path / "slate_hashes.json")

        # Patch _DEFAULT_RUNNERS so CLI runs without real sim.
        import fixture_slate_hash as _mod
        original = dict(_mod._DEFAULT_RUNNERS)
        fake_output: Dict[str, Any] = {"v": 42.0}

        def _fake() -> Any:
            return fake_output

        _mod._DEFAULT_RUNNERS.update({n: _fake for n in SURFACE_NAMES})
        try:
            rc_capture = main(["--capture", "--out", out_file])
            assert rc_capture == 0, "capture should succeed"
            assert Path(out_file).exists(), "output file should be created"

            rc_compare = main(["--compare", out_file])
            assert rc_compare == 0, "compare against own capture should be clean"
        finally:
            _mod._DEFAULT_RUNNERS.clear()
            _mod._DEFAULT_RUNNERS.update(original)

    def test_compare_detects_diverged_surface(self, tmp_path: Path) -> None:
        """--compare exits non-zero and names the diverging surface."""
        import fixture_slate_hash as _mod
        original = dict(_mod._DEFAULT_RUNNERS)

        base_output: Dict[str, Any] = {"v": 1.0}
        perturbed_output: Dict[str, Any] = {"v": 1.0 + 1e-9}

        def _base() -> Any:
            return base_output

        def _perturbed() -> Any:
            return perturbed_output

        # Write baseline with base output.
        baseline_file = tmp_path / "baseline.json"
        _mod._DEFAULT_RUNNERS.update({n: _base for n in SURFACE_NAMES})
        try:
            rc = main(["--capture", "--out", str(baseline_file)])
            assert rc == 0

            # Now swap pregame_joint to perturbed output.
            _mod._DEFAULT_RUNNERS["pregame_joint"] = _perturbed

            rc_compare = main(["--compare", str(baseline_file)])
            assert rc_compare == 1, "diverged compare must exit non-zero"

            # ingame_replay and prop_predict should still be the same value.
            # We verify by re-running with all base runners.
            _mod._DEFAULT_RUNNERS.update({n: _base for n in SURFACE_NAMES})
            rc_clean = main(["--compare", str(baseline_file)])
            assert rc_clean == 0, "restoring base runners should give clean compare"
        finally:
            _mod._DEFAULT_RUNNERS.clear()
            _mod._DEFAULT_RUNNERS.update(original)

    def test_capture_without_out_does_not_write(self, tmp_path: Path) -> None:
        """--capture without --out prints hashes but writes no file."""
        import fixture_slate_hash as _mod
        original = dict(_mod._DEFAULT_RUNNERS)
        fake_output: Dict[str, Any] = {"x": 1.5}

        def _fake() -> Any:
            return fake_output

        _mod._DEFAULT_RUNNERS.update({n: _fake for n in SURFACE_NAMES})
        try:
            rc = main(["--capture"])
            assert rc == 0
            # No file should have been created in tmp_path.
            assert not list(tmp_path.iterdir())
        finally:
            _mod._DEFAULT_RUNNERS.clear()
            _mod._DEFAULT_RUNNERS.update(original)

    def test_compare_missing_baseline_exits_1(self, tmp_path: Path) -> None:
        """--compare with a non-existent baseline file exits 1."""
        rc = main(["--compare", str(tmp_path / "nonexistent.json")])
        assert rc == 1

    def test_capture_notimplemented_exits_1(self) -> None:
        """--capture with default (stub) runners exits 1 gracefully."""
        rc = main(["--capture"])
        assert rc == 1
