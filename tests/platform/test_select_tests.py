"""test_select_tests.py — Unit tests for scripts/platformkit/select_tests.py.

Covers all 6 rules:
  1. Changed test file selects itself.
  2. Convention: src/.../foo.py → tests/**/test_foo*.py.
  3. Reverse import map (transitive AST imports).
  4. Fallback: script stem grep in tests/.
  5. Always-include floor: tests/platform/ + smoke list.
  6. >200 files → sentinel="ALL".

Python 3.9 compatible. No network. Pure pathlib / stdlib.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "platformkit"))

import select_tests  # noqa: E402


# ---------------------------------------------------------------------------
# Helper: build a minimal fake repo tree in tmp_path
# ---------------------------------------------------------------------------

def _make_repo(tmp_path: Path) -> Path:
    """Create a minimal fake repo layout under tmp_path."""
    # src module
    src = tmp_path / "src" / "mymodule"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    (src / "foo.py").write_text("def bar(): pass\n")

    # tests
    tp = tmp_path / "tests" / "platform"
    tp.mkdir(parents=True)
    (tp / "test_platform_smoke.py").write_text("def test_ok(): pass\n")

    tests = tmp_path / "tests"
    (tests / "test_foo.py").write_text("import mymodule.foo\n\ndef test_foo(): pass\n")
    (tests / "test_other.py").write_text("def test_other(): pass\n")

    # scripts dir (for rule 4)
    scripts = tmp_path / "scripts" / "platformkit"
    scripts.mkdir(parents=True)
    (scripts / "my_script.py").write_text("# does stuff\n")

    # a test that references the script by name
    (tests / "test_my_script.py").write_text(
        "import subprocess\n"
        "def test_runs():\n"
        "    subprocess.run(['python', 'scripts/platformkit/my_script.py'])\n"
    )

    return tmp_path


# ---------------------------------------------------------------------------
# Rule 1: changed test file selects itself
# ---------------------------------------------------------------------------

def test_rule1_changed_test_selects_itself(tmp_path):
    repo = _make_repo(tmp_path)
    test_file = "tests/test_foo.py"
    result = select_tests.select([test_file], repo_root=repo)

    assert result["sentinel"] is None
    assert any("test_foo" in t for t in result["tests"]), (
        f"Expected test_foo.py in selection; got {result['tests']}"
    )
    assert "rule1_self" in result["rules_fired"]


def test_rule1_multiple_changed_tests(tmp_path):
    repo = _make_repo(tmp_path)
    result = select_tests.select(
        ["tests/test_foo.py", "tests/test_other.py"],
        repo_root=repo,
    )
    tests_norm = [t.replace("\\", "/") for t in result["tests"]]
    assert any("test_foo" in t for t in tests_norm)
    assert any("test_other" in t for t in tests_norm)


# ---------------------------------------------------------------------------
# Rule 2: convention test_<stem>*.py for src files
# ---------------------------------------------------------------------------

def test_rule2_convention_src_to_test(tmp_path):
    repo = _make_repo(tmp_path)
    result = select_tests.select(["src/mymodule/foo.py"], repo_root=repo)

    assert result["sentinel"] is None
    tests_norm = [t.replace("\\", "/") for t in result["tests"]]
    assert any("test_foo" in t for t in tests_norm), (
        f"Expected test_foo.py via convention; got {tests_norm}"
    )
    assert any("rule2_convention" in r for r in result["rules_fired"])


def test_rule2_no_match_still_returns_floor(tmp_path):
    repo = _make_repo(tmp_path)
    # src file whose stem has no matching test_<stem>*.py
    result = select_tests.select(["src/mymodule/__init__.py"], repo_root=repo)
    # Floor (tests/platform/) must always be included
    tests_norm = [t.replace("\\", "/") for t in result["tests"]]
    assert any("tests/platform" in t for t in tests_norm)


# ---------------------------------------------------------------------------
# Rule 3: reverse import map
# ---------------------------------------------------------------------------

def test_rule3_import_map_includes_importing_test(tmp_path):
    """tests/test_foo.py imports mymodule.foo → must be selected when foo.py changes."""
    repo = _make_repo(tmp_path)
    result = select_tests.select(["src/mymodule/foo.py"], repo_root=repo)
    tests_norm = [t.replace("\\", "/") for t in result["tests"]]
    # test_foo.py imports mymodule.foo, so rule 3 (or rule 2) must catch it
    assert any("test_foo" in t for t in tests_norm), (
        f"test_foo.py should be selected (imports foo); got {tests_norm}"
    )


def test_rule3_unrelated_test_not_selected(tmp_path):
    """tests/test_other.py has no import of mymodule.foo — should only appear via floor."""
    repo = _make_repo(tmp_path)
    # Patch: test_other.py has no platform floor path, so unless it's in floor, it won't appear.
    result = select_tests.select(["src/mymodule/foo.py"], repo_root=repo)
    tests_norm = [t.replace("\\", "/") for t in result["tests"]]
    # test_other.py is not in tests/platform/ and has no import of foo
    # It MUST NOT be selected for this targeted change
    assert not any("test_other" in t and "platform" not in t for t in tests_norm), (
        f"test_other.py should NOT be selected; got {tests_norm}"
    )


# ---------------------------------------------------------------------------
# Rule 4: script-path grep fallback
# ---------------------------------------------------------------------------

def test_rule4_grep_fallback_for_script(tmp_path):
    """A test referencing a script path via subprocess string should be selected."""
    repo = _make_repo(tmp_path)
    result = select_tests.select(
        ["scripts/platformkit/my_script.py"],
        repo_root=repo,
    )
    tests_norm = [t.replace("\\", "/") for t in result["tests"]]
    assert any("test_my_script" in t for t in tests_norm), (
        f"Expected test_my_script.py via grep fallback; got {tests_norm}"
    )
    assert any("rule4_grep" in r for r in result["rules_fired"])


# ---------------------------------------------------------------------------
# Rule 5: always-include floor (tests/platform/ + smoke)
# ---------------------------------------------------------------------------

def test_rule5_floor_always_included(tmp_path):
    repo = _make_repo(tmp_path)
    # Even for empty input, floor must appear
    result = select_tests.select([], repo_root=repo)
    tests_norm = [t.replace("\\", "/") for t in result["tests"]]
    assert any("tests/platform" in t for t in tests_norm), (
        f"Floor (tests/platform/) must always be included; got {tests_norm}"
    )
    assert "rule5_floor" in result["rules_fired"]


def test_rule5_floor_included_with_src_change(tmp_path):
    repo = _make_repo(tmp_path)
    result = select_tests.select(["src/mymodule/foo.py"], repo_root=repo)
    tests_norm = [t.replace("\\", "/") for t in result["tests"]]
    assert any("tests/platform" in t for t in tests_norm)


def test_rule5_real_repo_floor_present():
    """On the actual repo, tests/platform/ files are always in the floor."""
    result = select_tests.select([], repo_root=ROOT)
    tests_norm = [t.replace("\\", "/") for t in result["tests"]]
    assert any("tests/platform" in t for t in tests_norm), (
        f"Real repo floor missing; got {tests_norm[:5]}"
    )


# ---------------------------------------------------------------------------
# Rule 6: >200 files → sentinel="ALL"
# ---------------------------------------------------------------------------

def test_rule6_all_sentinel_when_too_many(tmp_path):
    """When selection exceeds 200 files, sentinel must be 'ALL'."""
    # Create 201 fake test files in tests/
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True)
    tp = tests_dir / "platform"
    tp.mkdir(parents=True)
    (tp / "test_platform_smoke.py").write_text("def test_ok(): pass\n")

    for i in range(202):
        (tests_dir / f"test_gen_{i:04d}.py").write_text(
            f"import gen_src_{i}\ndef test_{i}(): pass\n"
        )

    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)

    # A single src change that matches ALL the generated tests (via rule 2 convention).
    # We can't fake 202 convention hits easily, so we monkeypatch _MAX_TESTS instead.
    import select_tests as st
    original_max = st._MAX_TESTS
    try:
        st._MAX_TESTS = 0  # force any non-empty selection to trigger ALL
        result = st.select(["src/anything.py"], repo_root=tmp_path)
        assert result["sentinel"] == "ALL", f"Expected ALL sentinel; got {result}"
        assert result["tests"] == []
        assert "too broad" in result["reason"].lower() or "ALL" in result["reason"]
    finally:
        st._MAX_TESTS = original_max


def test_rule6_sentinel_none_when_few(tmp_path):
    repo = _make_repo(tmp_path)
    result = select_tests.select(["src/mymodule/foo.py"], repo_root=repo)
    assert result["sentinel"] is None


# ---------------------------------------------------------------------------
# Integration: W002-like file set (scripts/platformkit/capture/ledger_*.py)
# ---------------------------------------------------------------------------

def test_w002_like_ledger_selection():
    """W002 changed scripts/platformkit/capture/ledger_*.py.
    Selection must: include tests/platform/, NOT select the entire test tree.
    """
    changed = [
        "scripts/platformkit/capture/ledger_schema.py",
        "scripts/platformkit/capture/ledger_writer.py",
    ]
    result = select_tests.select(changed, repo_root=ROOT)

    # Must not be the full suite
    assert result["sentinel"] is None, (
        f"W002-like set should NOT trigger ALL sentinel; reason: {result['reason']}"
    )

    tests_norm = [t.replace("\\", "/") for t in result["tests"]]

    # Must include tests/platform/ floor
    assert any("tests/platform" in t for t in tests_norm), (
        f"Floor missing from W002 selection; got {tests_norm[:10]}"
    )

    # Must NOT be the full test tree (expected << 200)
    assert len(result["tests"]) < 200, (
        f"W002-like set selected too many files: {len(result['tests'])}"
    )

    # Must NOT be empty (floor ensures non-empty)
    assert len(result["tests"]) > 0


# ---------------------------------------------------------------------------
# select() return shape
# ---------------------------------------------------------------------------

def test_select_return_shape_no_sentinel(tmp_path):
    repo = _make_repo(tmp_path)
    result = select_tests.select([], repo_root=repo)
    assert "tests" in result
    assert "sentinel" in result
    assert "reason" in result
    assert "rules_fired" in result
    assert isinstance(result["tests"], list)
    assert isinstance(result["rules_fired"], list)


def test_select_output_is_sorted(tmp_path):
    repo = _make_repo(tmp_path)
    result = select_tests.select(["src/mymodule/foo.py"], repo_root=repo)
    assert result["tests"] == sorted(result["tests"])


def test_select_output_no_duplicates(tmp_path):
    repo = _make_repo(tmp_path)
    result = select_tests.select(
        ["src/mymodule/foo.py", "src/mymodule/foo.py"],
        repo_root=repo,
    )
    assert len(result["tests"]) == len(set(result["tests"]))


def test_select_handles_nonexistent_file_gracefully(tmp_path):
    repo = _make_repo(tmp_path)
    result = select_tests.select(["src/nonexistent/ghost.py"], repo_root=repo)
    # Should not raise; floor still included
    assert result["sentinel"] is None or result["sentinel"] == "ALL"
    if result["sentinel"] is None:
        tests_norm = [t.replace("\\", "/") for t in result["tests"]]
        assert any("tests/platform" in t for t in tests_norm)
