"""tests/platform/test_kernel_api_map.py — tests for kernel_api_map.py.

Hermetic, offline. Uses a synthetic mini-package in tmp_path.
Never imports kernel modules.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Resolve the script without importing kernel
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.kernel_api_map import (
    build_api_map,
    diff_maps,
    main,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mini_pkg(tmp_path: Path) -> Path:
    """Create a synthetic mini-package with 2 modules."""
    pkg = tmp_path / "fakepkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")

    # Module A: public class + private class + public function + private function
    (pkg / "mod_a.py").write_text(
        """
class PublicClass:
    def public_method(self): ...
    def another_public(self): ...
    def _private_method(self): ...

class _PrivateClass:
    def should_be_excluded(self): ...

def public_func(): ...
def _private_func(): ...
""",
        encoding="utf-8",
    )

    # Module B: public dataclass-style class + standalone function
    (pkg / "mod_b.py").write_text(
        """
class AnotherPublic:
    def run(self): ...

def helper(): ...
""",
        encoding="utf-8",
    )
    return tmp_path  # root is tmp_path, package is "fakepkg"


# ---------------------------------------------------------------------------
# Unit tests: build_api_map
# ---------------------------------------------------------------------------

class TestBuildApiMap:
    def test_captures_only_public_symbols(self, mini_pkg: Path) -> None:
        result = build_api_map(str(mini_pkg / "fakepkg"))
        mod_a_key = "fakepkg.mod_a"
        assert mod_a_key in result
        entry = result[mod_a_key]

        # Public class present, private class absent
        assert "PublicClass" in entry["classes"]
        assert "_PrivateClass" not in entry["classes"]

        # Public function present, private function absent
        assert "public_func" in entry["functions"]
        assert "_private_func" not in entry["functions"]

    def test_captures_only_public_methods(self, mini_pkg: Path) -> None:
        result = build_api_map(str(mini_pkg / "fakepkg"))
        methods = result["fakepkg.mod_a"]["classes"]["PublicClass"]
        assert "public_method" in methods
        assert "another_public" in methods
        assert "_private_method" not in methods

    def test_deterministic_two_runs_equal(self, mini_pkg: Path) -> None:
        run1 = build_api_map(str(mini_pkg / "fakepkg"))
        run2 = build_api_map(str(mini_pkg / "fakepkg"))
        assert run1 == run2

    def test_output_sorted(self, mini_pkg: Path) -> None:
        result = build_api_map(str(mini_pkg / "fakepkg"))
        keys = list(result.keys())
        assert keys == sorted(keys), "Top-level keys must be sorted"
        for entry in result.values():
            class_keys = list(entry["classes"].keys())
            assert class_keys == sorted(class_keys)
            for methods in entry["classes"].values():
                assert methods == sorted(methods)
            assert entry["functions"] == sorted(entry["functions"])

    def test_missing_root_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            build_api_map(str(tmp_path / "nonexistent"))

    def test_both_modules_present(self, mini_pkg: Path) -> None:
        result = build_api_map(str(mini_pkg / "fakepkg"))
        assert "fakepkg.mod_a" in result
        assert "fakepkg.mod_b" in result
        assert "AnotherPublic" in result["fakepkg.mod_b"]["classes"]
        assert "helper" in result["fakepkg.mod_b"]["functions"]


# ---------------------------------------------------------------------------
# Unit tests: diff_maps
# ---------------------------------------------------------------------------

class TestDiffMaps:
    def _base(self) -> dict:
        return {
            "pkg.mod": {
                "classes": {"Foo": ["bar", "baz"]},
                "functions": ["helper"],
            }
        }

    def test_clean_diff_empty(self) -> None:
        m = self._base()
        diff = diff_maps(m, m)
        assert not any(v for v in diff.values()), "No drift expected on identical maps"

    def test_added_function(self) -> None:
        frozen = self._base()
        current = json.loads(json.dumps(frozen))
        current["pkg.mod"]["functions"].append("new_fn")
        diff = diff_maps(frozen, current)
        assert "pkg.mod::new_fn" in diff["added_functions"]
        assert not diff["removed_functions"]

    def test_removed_function(self) -> None:
        frozen = self._base()
        current = json.loads(json.dumps(frozen))
        current["pkg.mod"]["functions"] = []
        diff = diff_maps(frozen, current)
        assert "pkg.mod::helper" in diff["removed_functions"]

    def test_added_class(self) -> None:
        frozen = self._base()
        current = json.loads(json.dumps(frozen))
        current["pkg.mod"]["classes"]["NewClass"] = ["run"]
        diff = diff_maps(frozen, current)
        assert "pkg.mod::NewClass" in diff["added_classes"]

    def test_removed_class(self) -> None:
        frozen = self._base()
        current = json.loads(json.dumps(frozen))
        del current["pkg.mod"]["classes"]["Foo"]
        diff = diff_maps(frozen, current)
        assert "pkg.mod::Foo" in diff["removed_classes"]

    def test_added_method(self) -> None:
        frozen = self._base()
        current = json.loads(json.dumps(frozen))
        current["pkg.mod"]["classes"]["Foo"].append("new_method")
        diff = diff_maps(frozen, current)
        assert "pkg.mod::Foo.new_method" in diff["added_methods"]

    def test_removed_method(self) -> None:
        frozen = self._base()
        current = json.loads(json.dumps(frozen))
        current["pkg.mod"]["classes"]["Foo"] = ["bar"]  # removed "baz"
        diff = diff_maps(frozen, current)
        assert "pkg.mod::Foo.baz" in diff["removed_methods"]

    def test_added_module(self) -> None:
        frozen = self._base()
        current = json.loads(json.dumps(frozen))
        current["pkg.new_mod"] = {"classes": {}, "functions": ["x"]}
        diff = diff_maps(frozen, current)
        assert "pkg.new_mod" in diff["added_modules"]

    def test_removed_module(self) -> None:
        frozen = self._base()
        current: dict = {}
        diff = diff_maps(frozen, current)
        assert "pkg.mod" in diff["removed_modules"]


# ---------------------------------------------------------------------------
# Integration tests: freeze → check round-trip via CLI
# ---------------------------------------------------------------------------

class TestCLIRoundTrip:
    def test_freeze_then_check_clean(self, mini_pkg: Path, tmp_path: Path) -> None:
        map_file = tmp_path / "api_map.json"
        pkg_root = str(mini_pkg / "fakepkg")

        # Freeze
        rc = main(["--freeze", "--out", str(map_file), "--root", pkg_root])
        assert rc == 0
        assert map_file.exists()

        # Check: no changes → exit 0
        rc = main(["--check", "--map", str(map_file), "--root", pkg_root])
        assert rc == 0

    def test_check_exits_nonzero_on_added_symbol(
        self, mini_pkg: Path, tmp_path: Path
    ) -> None:
        map_file = tmp_path / "api_map.json"
        pkg_root = str(mini_pkg / "fakepkg")

        # Freeze current state
        main(["--freeze", "--out", str(map_file), "--root", pkg_root])

        # Add a new public function to mod_a
        mod_a = mini_pkg / "fakepkg" / "mod_a.py"
        existing = mod_a.read_text(encoding="utf-8")
        mod_a.write_text(existing + "\ndef brand_new_fn(): ...\n", encoding="utf-8")

        rc = main(["--check", "--map", str(map_file), "--root", pkg_root])
        assert rc != 0

    def test_check_exits_nonzero_on_removed_symbol(
        self, mini_pkg: Path, tmp_path: Path
    ) -> None:
        map_file = tmp_path / "api_map.json"
        pkg_root = str(mini_pkg / "fakepkg")

        main(["--freeze", "--out", str(map_file), "--root", pkg_root])

        # Remove public_func from mod_a
        mod_a = mini_pkg / "fakepkg" / "mod_a.py"
        src = mod_a.read_text(encoding="utf-8")
        src = src.replace("def public_func(): ...", "")
        mod_a.write_text(src, encoding="utf-8")

        rc = main(["--check", "--map", str(map_file), "--root", pkg_root])
        assert rc != 0

    def test_check_missing_map_returns_nonzero(self, tmp_path: Path) -> None:
        rc = main(
            ["--check", "--map", str(tmp_path / "no_such.json"), "--root", "kernel"]
        )
        assert rc != 0


# ---------------------------------------------------------------------------
# Smoke test: real kernel tree
# ---------------------------------------------------------------------------

class TestRealKernelSmoke:
    def test_real_kernel_nonempty(self) -> None:
        """build_api_map on real kernel/ returns a non-empty dict."""
        kernel_root = _REPO_ROOT / "kernel"
        result = build_api_map(str(kernel_root))
        assert len(result) > 0, "Expected at least one module in kernel/"

    def test_real_kernel_contains_sport_context(self) -> None:
        """kernel.config.context::SportContext must appear in the surface map."""
        kernel_root = _REPO_ROOT / "kernel"
        result = build_api_map(str(kernel_root))
        assert "kernel.config.context" in result, (
            "kernel.config.context missing from surface map"
        )
        classes = result["kernel.config.context"]["classes"]
        assert "SportContext" in classes, (
            "SportContext not found in kernel.config.context classes"
        )
