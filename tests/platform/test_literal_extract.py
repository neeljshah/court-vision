"""
tests/platform/test_literal_extract.py

Hermetic, offline tests for scripts/platformkit/literal_extract.py.

Each test writes a synthetic source file to tmp_path so no real project
module is ever imported or executed.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

# Make the scripts/platformkit package importable without installing it
_SCRIPTS_PLATFORM = Path(__file__).parent.parent.parent / "scripts" / "platformkit"
if str(_SCRIPTS_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_PLATFORM))

from literal_extract import (  # noqa: E402
    extract_assignment,
    extract_dict_value,
    extract_line_literal,
)


# ---------------------------------------------------------------------------
# Fixtures — synthetic source files
# ---------------------------------------------------------------------------

@pytest.fixture()
def simple_module(tmp_path: Path) -> Path:
    """Module with a variety of module-level assignments."""
    src = textwrap.dedent("""\
        # synthetic test module — never import this
        VERSION = "2.3.1"
        MAX_RETRIES = 5
        PI = 3.14159
        ENABLED = True
        ITEMS = [1, 2, 3]
        NESTED = {"a": 1, "b": [2, 3]}
        _PRIVATE = 42

        # annotated assignment
        TIMEOUT: int = 30

        # this is NOT a literal (call expression)
        COMPUTED = int("99")
    """)
    p = tmp_path / "fake_config.py"
    p.write_text(src, encoding="utf-8")
    return p


@pytest.fixture()
def dict_module(tmp_path: Path) -> Path:
    """Module with a top-level dict literal."""
    src = textwrap.dedent("""\
        SETTINGS = {
            "host": "localhost",
            "port": 5432,
            "debug": False,
            "ratio": 0.75,
        }
        OTHER = "irrelevant"
    """)
    p = tmp_path / "fake_settings.py"
    p.write_text(src, encoding="utf-8")
    return p


@pytest.fixture()
def class_module(tmp_path: Path) -> Path:
    """Module with a class containing assignments."""
    src = textwrap.dedent("""\
        class Config:
            BATCH_SIZE = 64
            LEARNING_RATE = 0.001
            NAME = "mlp"

        GLOBAL = 99
    """)
    p = tmp_path / "fake_class.py"
    p.write_text(src, encoding="utf-8")
    return p


@pytest.fixture()
def expression_module(tmp_path: Path) -> Path:
    """Module with numeric literals embedded in expressions / conditions."""
    src = textwrap.dedent("""\
        import math

        def check(margin):
            if abs(margin) >= 18:
                return True
            if margin <= -5.5:
                return False
            return None
    """)
    p = tmp_path / "fake_expr.py"
    p.write_text(src, encoding="utf-8")
    return p


@pytest.fixture()
def crlf_module(tmp_path: Path) -> Path:
    """Module with Windows CRLF line endings."""
    src = "VALUE = 7\r\nOTHER = 8\r\n"
    p = tmp_path / "fake_crlf.py"
    p.write_bytes(src.encode("utf-8"))
    return p


# ---------------------------------------------------------------------------
# extract_assignment — happy paths
# ---------------------------------------------------------------------------

class TestExtractAssignment:
    def test_string(self, simple_module: Path) -> None:
        assert extract_assignment(simple_module, "VERSION") == "2.3.1"

    def test_integer(self, simple_module: Path) -> None:
        assert extract_assignment(simple_module, "MAX_RETRIES") == 5

    def test_float(self, simple_module: Path) -> None:
        assert extract_assignment(simple_module, "PI") == pytest.approx(3.14159)

    def test_bool(self, simple_module: Path) -> None:
        assert extract_assignment(simple_module, "ENABLED") is True

    def test_list(self, simple_module: Path) -> None:
        assert extract_assignment(simple_module, "ITEMS") == [1, 2, 3]

    def test_nested_dict(self, simple_module: Path) -> None:
        assert extract_assignment(simple_module, "NESTED") == {"a": 1, "b": [2, 3]}

    def test_private_name(self, simple_module: Path) -> None:
        assert extract_assignment(simple_module, "_PRIVATE") == 42

    def test_annotated_assignment(self, simple_module: Path) -> None:
        assert extract_assignment(simple_module, "TIMEOUT") == 30

    def test_crlf_file(self, crlf_module: Path) -> None:
        assert extract_assignment(crlf_module, "VALUE") == 7
        assert extract_assignment(crlf_module, "OTHER") == 8

    # qualname (class-level) -------------------------------------------------

    def test_class_level_int(self, class_module: Path) -> None:
        assert extract_assignment(class_module, "BATCH_SIZE", qualname="Config") == 64

    def test_class_level_float(self, class_module: Path) -> None:
        assert extract_assignment(
            class_module, "LEARNING_RATE", qualname="Config"
        ) == pytest.approx(0.001)

    def test_class_level_string(self, class_module: Path) -> None:
        assert extract_assignment(class_module, "NAME", qualname="Config") == "mlp"

    def test_global_not_shadowed_by_class(self, class_module: Path) -> None:
        # Without qualname, should find the module-level GLOBAL, not class member
        assert extract_assignment(class_module, "GLOBAL") == 99


# ---------------------------------------------------------------------------
# extract_assignment — error paths
# ---------------------------------------------------------------------------

class TestExtractAssignmentErrors:
    def test_missing_name_raises(self, simple_module: Path) -> None:
        with pytest.raises(ValueError, match="not found"):
            extract_assignment(simple_module, "DOES_NOT_EXIST")

    def test_non_literal_raises(self, simple_module: Path) -> None:
        with pytest.raises(ValueError, match="not a literal"):
            extract_assignment(simple_module, "COMPUTED")

    def test_missing_class_raises(self, class_module: Path) -> None:
        with pytest.raises(ValueError, match="not found"):
            extract_assignment(class_module, "BATCH_SIZE", qualname="NoSuchClass")

    def test_name_in_wrong_class_raises(self, class_module: Path) -> None:
        # GLOBAL exists at module level but not inside Config
        with pytest.raises(ValueError, match="not found"):
            extract_assignment(class_module, "GLOBAL", qualname="Config")

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises((FileNotFoundError, OSError)):
            extract_assignment(tmp_path / "no_such_file.py", "X")

    def test_syntax_error_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.py"
        bad.write_text("def (: pass\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Syntax error"):
            extract_assignment(bad, "X")


# ---------------------------------------------------------------------------
# extract_dict_value — happy paths
# ---------------------------------------------------------------------------

class TestExtractDictValue:
    def test_string_value(self, dict_module: Path) -> None:
        assert extract_dict_value(dict_module, "SETTINGS", "host") == "localhost"

    def test_int_value(self, dict_module: Path) -> None:
        assert extract_dict_value(dict_module, "SETTINGS", "port") == 5432

    def test_bool_value(self, dict_module: Path) -> None:
        assert extract_dict_value(dict_module, "SETTINGS", "debug") is False

    def test_float_value(self, dict_module: Path) -> None:
        assert extract_dict_value(dict_module, "SETTINGS", "ratio") == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# extract_dict_value — error paths
# ---------------------------------------------------------------------------

class TestExtractDictValueErrors:
    def test_missing_dict_raises(self, dict_module: Path) -> None:
        with pytest.raises(ValueError, match="not found"):
            extract_dict_value(dict_module, "NO_DICT", "host")

    def test_missing_key_raises(self, dict_module: Path) -> None:
        with pytest.raises(ValueError, match="Key"):
            extract_dict_value(dict_module, "SETTINGS", "missing_key")

    def test_not_a_dict_raises(self, dict_module: Path) -> None:
        with pytest.raises(ValueError, match="not a dict literal"):
            extract_dict_value(dict_module, "OTHER", "anything")


# ---------------------------------------------------------------------------
# extract_line_literal — happy paths
# ---------------------------------------------------------------------------

class TestExtractLineLiteral:
    def test_integer_in_condition(self, expression_module: Path) -> None:
        # Line 4: "    if abs(margin) >= 18:"
        result = extract_line_literal(expression_module, 4, r">=\s*(\d+)")
        assert result == 18
        assert isinstance(result, int)

    def test_negative_float_in_condition(self, expression_module: Path) -> None:
        # Line 6: "    if margin <= -5.5:"
        # We capture including the minus sign via the pattern
        result = extract_line_literal(expression_module, 6, r"<=\s*(-[\d.]+)")
        assert result == pytest.approx(-5.5)
        assert isinstance(result, float)

    def test_float_detected_by_decimal_point(self, expression_module: Path) -> None:
        # Line 6: "    if margin <= -5.5:"
        result = extract_line_literal(expression_module, 6, r"(-5\.\d+)")
        assert isinstance(result, float)

    def test_integer_no_decimal_is_int(self, simple_module: Path) -> None:
        # Line 3: "MAX_RETRIES = 5"
        result = extract_line_literal(simple_module, 3, r"=\s*(\d+)")
        assert result == 5
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# extract_line_literal — error paths
# ---------------------------------------------------------------------------

class TestExtractLineLiteralErrors:
    def test_lineno_zero_raises(self, expression_module: Path) -> None:
        with pytest.raises(ValueError, match="out of range"):
            extract_line_literal(expression_module, 0, r"(\d+)")

    def test_lineno_beyond_end_raises(self, expression_module: Path) -> None:
        with pytest.raises(ValueError, match="out of range"):
            extract_line_literal(expression_module, 9999, r"(\d+)")

    def test_pattern_no_match_raises(self, expression_module: Path) -> None:
        with pytest.raises(ValueError, match="did not match"):
            extract_line_literal(expression_module, 1, r"XYZZY(\d+)")
