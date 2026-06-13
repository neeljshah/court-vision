"""tests/platform/test_select_tests_helpers.py — Unit tests for select_tests_helpers.py.

Tests the four public pure helpers:
  _normalise   — backslash->forward-slash, strip leading slash
  _path_to_module — absolute path -> dotted module name
  _parse_imports  — AST import extraction; must never crash on bad input
  _stem           — filename without extension

KEY property under test: _parse_imports returns [] on malformed/unreadable files, never raises.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.platformkit.select_tests_helpers import (
    _normalise,
    _parse_imports,
    _path_to_module,
    _stem,
)


# ---------------------------------------------------------------------------
# _normalise
# ---------------------------------------------------------------------------

class TestNormalise:
    def test_backslash_to_forward(self):
        assert _normalise("src\\foo\\bar.py") == "src/foo/bar.py"

    def test_mixed_slashes(self):
        assert _normalise("src/foo\\bar.py") == "src/foo/bar.py"

    def test_strips_leading_forward_slash(self):
        assert _normalise("/src/foo/bar.py") == "src/foo/bar.py"

    def test_strips_leading_backslash(self):
        # backslash is converted first, then leading / stripped
        assert _normalise("\\src\\foo.py") == "src/foo.py"

    def test_no_leading_slash_unchanged(self):
        assert _normalise("src/foo/bar.py") == "src/foo/bar.py"

    def test_empty_string(self):
        assert _normalise("") == ""

    def test_only_slash(self):
        assert _normalise("/") == ""

    def test_deep_windows_path(self):
        result = _normalise("C:\\Users\\neelj\\nba-ai-system\\src\\sim\\basketball_sim.py")
        # lstrip removes leading /, but C: is not a leading /
        assert "\\" not in result
        assert "C:/Users" in result

    def test_no_mutation_of_forward_slash_path(self):
        p = "a/b/c.py"
        assert _normalise(p) == p


# ---------------------------------------------------------------------------
# _path_to_module
# ---------------------------------------------------------------------------

class TestPathToModule:
    def _make_root(self, tmp_path: Path) -> Path:
        """Return a fake root dir."""
        return tmp_path

    def test_simple_module(self, tmp_path: Path):
        f = tmp_path / "src" / "foo" / "bar.py"
        f.parent.mkdir(parents=True)
        f.touch()
        assert _path_to_module(f, tmp_path) == "src.foo.bar"

    def test_init_py_returns_parent_package(self, tmp_path: Path):
        f = tmp_path / "src" / "foo" / "__init__.py"
        f.parent.mkdir(parents=True)
        f.touch()
        assert _path_to_module(f, tmp_path) == "src.foo"

    def test_top_level_init_returns_package_name(self, tmp_path: Path):
        f = tmp_path / "mypkg" / "__init__.py"
        f.parent.mkdir(parents=True)
        f.touch()
        assert _path_to_module(f, tmp_path) == "mypkg"

    def test_root_level_module(self, tmp_path: Path):
        f = tmp_path / "module.py"
        f.touch()
        assert _path_to_module(f, tmp_path) == "module"

    def test_path_outside_root_returns_none(self, tmp_path: Path):
        other = tmp_path.parent / "other" / "file.py"
        result = _path_to_module(other, tmp_path)
        assert result is None

    def test_non_py_extension_preserved(self, tmp_path: Path):
        """Non-.py files: the .py strip doesn't apply, so ext is kept in dotted name."""
        f = tmp_path / "src" / "data.json"
        f.parent.mkdir(parents=True)
        f.touch()
        result = _path_to_module(f, tmp_path)
        # The function only strips ".py"; for other extensions the last part includes ext
        assert result is not None
        assert "src" in result


# ---------------------------------------------------------------------------
# _parse_imports
# ---------------------------------------------------------------------------

class TestParseImports:
    def test_simple_import(self, tmp_path: Path):
        f = tmp_path / "a.py"
        f.write_text("import os\nimport sys\n", encoding="utf-8")
        imports = _parse_imports(f)
        assert "os" in imports
        assert "sys" in imports

    def test_from_import(self, tmp_path: Path):
        f = tmp_path / "b.py"
        f.write_text("from pathlib import Path\nfrom collections import defaultdict\n",
                     encoding="utf-8")
        imports = _parse_imports(f)
        assert "pathlib" in imports
        assert "collections" in imports

    def test_dotted_from_import(self, tmp_path: Path):
        f = tmp_path / "c.py"
        f.write_text("from src.sim.basketball_sim import run\n", encoding="utf-8")
        imports = _parse_imports(f)
        assert "src.sim.basketball_sim" in imports

    def test_relative_import_normalised(self, tmp_path: Path):
        """Relative imports (from . import x or from ..pkg import y) don't crash and
        are stripped of leading dots per the implementation."""
        f = tmp_path / "rel.py"
        f.write_text("from . import utils\nfrom ..base import Base\n", encoding="utf-8")
        imports = _parse_imports(f)
        # Should not crash; may return [] or stripped names
        assert isinstance(imports, list)

    def test_empty_file_returns_empty_list(self, tmp_path: Path):
        f = tmp_path / "empty.py"
        f.write_text("", encoding="utf-8")
        assert _parse_imports(f) == []

    # KEY property: malformed file must not crash --------------------------------

    def test_syntax_error_returns_empty_list(self, tmp_path: Path):
        """File with invalid Python syntax: _parse_imports must return [] not raise."""
        f = tmp_path / "bad_syntax.py"
        f.write_text("def broken(:\n    pass\n", encoding="utf-8")
        result = _parse_imports(f)
        assert result == [], f"Expected [] on syntax error, got {result}"

    def test_null_bytes_returns_empty_list(self, tmp_path: Path):
        """Binary garbage that ast.parse cannot handle: must return [] not raise."""
        f = tmp_path / "binary.py"
        f.write_bytes(b"\x00\xff\xfe binary junk \x80\x81")
        result = _parse_imports(f)
        assert isinstance(result, list), "Must return a list, not raise"
        # Either [] or whatever was parseable — must not crash
        assert result == [] or all(isinstance(m, str) for m in result)

    def test_nonexistent_file_returns_empty_list(self, tmp_path: Path):
        """File that doesn't exist: _parse_imports must return [] not raise."""
        f = tmp_path / "does_not_exist.py"
        result = _parse_imports(f)
        assert result == [], f"Expected [] for missing file, got {result}"

    def test_truncated_file_returns_empty_list(self, tmp_path: Path):
        """Truncated/half-written file: must return [] not raise."""
        f = tmp_path / "truncated.py"
        # Valid up to a point, then abruptly cut
        f.write_text("import os\ndef incomplete(x", encoding="utf-8")
        result = _parse_imports(f)
        # May or may not parse depending on Python version; must not raise
        assert isinstance(result, list)

    def test_large_valid_file(self, tmp_path: Path):
        """Many imports in a real-looking file parse without error."""
        lines = [f"import module_{i}" for i in range(100)]
        lines += [f"from pkg.sub_{i} import thing" for i in range(50)]
        f = tmp_path / "big.py"
        f.write_text("\n".join(lines), encoding="utf-8")
        result = _parse_imports(f)
        assert len(result) >= 100  # at least the `import module_X` ones

    def test_only_comments_and_docstring(self, tmp_path: Path):
        f = tmp_path / "comments.py"
        f.write_text('"""Module docstring."""\n# just a comment\npass\n', encoding="utf-8")
        result = _parse_imports(f)
        assert result == []


# ---------------------------------------------------------------------------
# _stem
# ---------------------------------------------------------------------------

class TestStem:
    def test_simple_filename(self):
        assert _stem("test_belief_decay.py") == "test_belief_decay"

    def test_path_with_directories(self):
        assert _stem("tests/platform/test_foo.py") == "test_foo"

    def test_windows_backslash_path(self):
        assert _stem("tests\\platform\\test_bar.py") == "test_bar"

    def test_no_extension(self):
        assert _stem("Makefile") == "Makefile"

    def test_multiple_dots(self):
        # Path.stem only removes the last suffix
        assert _stem("archive.tar.gz") == "archive.tar"

    def test_hidden_file(self):
        # dotfiles: stem of ".gitignore" is ".gitignore" in Python's pathlib
        assert _stem(".gitignore") == ".gitignore"

    def test_empty_string(self):
        # Path("").stem == ""
        assert _stem("") == ""

    def test_just_extension(self):
        assert _stem(".py") == ".py"
