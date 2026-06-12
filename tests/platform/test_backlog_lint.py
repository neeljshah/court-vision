"""test_backlog_lint.py — Acceptance tests for scripts/platform_harness/backlog_lint.py.

Python 3.9 compatible. No network. Runs in < 30 s.

Test matrix
-----------
1.  Real BUILD_BACKLOG.md parses with zero schema errors (or reports real issues).
2.  Fixture: missing title is a schema error.
3.  Fixture: missing done_criteria is a schema error.
4.  Fixture: dangling depends_on (unknown id and not a range dep) is a schema error.
5.  Fixture: valid dep between two tasks in the same fixture is not an error.
6.  Fixture: range dep (contains '..') is never a schema error.
7.  Fixture: edge phrase in 'do' is an edge warning.
8.  Fixture: edge phrase in 'done_criteria' is an edge warning.
9.  Fixture: edge phrase in 'title' is an edge warning.
10. Fixture: multiple edge patterns each fire independently.
11. Fixture: shared file in same parallel_group is a collision warning.
12. Fixture: disjoint files in same parallel_group → no collision.
13. Fixture: same file in DIFFERENT parallel_groups → no collision.
14. Fixture: clean task produces zero errors/warnings/collisions.
15. Fixture: gate-style task (empty files, no do, no change_kind) is not an error.
16. Fixture: duplicate task id → promoted schema error.
17. SchemaError / EdgeWarning / CollisionWarning string format contracts.
18. CLI: clean fixture exits 0 with PASS in stdout.
19. CLI: fixture with schema error exits 1 with FAIL in stdout.
20. CLI: structured section headers always present.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path
from typing import List, Tuple

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "platform_harness"))

from backlog_lint import (  # noqa: E402
    CollisionWarning,
    EdgeWarning,
    SchemaError,
    lint_file_collisions,
    lint_honest_edge,
    lint_schema,
    run_lint,
)
import backlog as _backlog  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ENVPY = str(Path(sys.executable))

# A minimal, fully valid task with one non-empty file
VALID_TASK_YAML = textwrap.dedent("""\
    ```yaml
    id: P0-Z-001
    title: A perfectly valid task
    phase: 0   epic: P0-Z   depends_on: []   size: S   parallel_group: pz   owner_model: sonnet   review: auto
    change_kind: new
    files: [scripts/platform_harness/some_module.py]
    do: Write the module.
    done_criteria: python -m pytest tests/platform/test_some_module.py -q
    ```
""")

# A gate-style task: no do, no change_kind, empty files — valid per backlog convention
GATE_TASK_YAML = textwrap.dedent("""\
    ```yaml
    id: X-P1-GATE
    title: Wave gate — GATES + PHASE-TAG (platform-xp1)
    depends_on: [X-P1-001..016]   owner_model: opus   review: auto   size: S
    done_criteria: GATES green; check_import_contract green on the now-populated kernel/.
    ```
""")


def _make_backlog(tasks_yaml: str, tmp_path: Path) -> Path:
    """Wrap raw ```yaml blocks in a minimal BUILD_BACKLOG.md and return the path."""
    content = "# BUILD_BACKLOG.md — test fixture\n\n" + tasks_yaml
    p = tmp_path / "BUILD_BACKLOG.md"
    p.write_text(content, encoding="utf-8")
    return p


def _lint_fixture(yaml_text: str, tmp_path: Path) -> Tuple[
    dict,
    List[SchemaError],
    List[EdgeWarning],
    List[CollisionWarning],
]:
    """Parse and lint a single fixture string; return (tasks, schema_errors, edge_warnings, collisions)."""
    path = _make_backlog(yaml_text, tmp_path)
    schema_errors, edge_warnings, collisions = run_lint(path)
    tasks, _ = _backlog.parse(path)
    return tasks, schema_errors, edge_warnings, collisions


# ---------------------------------------------------------------------------
# 1. Real BUILD_BACKLOG.md — schema must be clean
# ---------------------------------------------------------------------------

class TestRealBacklog:
    def test_real_backlog_schema_pass(self) -> None:
        """Real BUILD_BACKLOG.md must have zero schema errors.

        Failures are reported in detail so the CI output is actionable.
        Edge warnings and collisions are informational and do not fail this test.
        """
        schema_errors, _, _ = run_lint()
        if schema_errors:
            msgs = "\n".join(f"  {e}" for e in schema_errors)
            pytest.fail(
                f"Real BUILD_BACKLOG.md has {len(schema_errors)} schema error(s):\n{msgs}"
            )

    def test_real_backlog_yields_tasks(self) -> None:
        """Underlying parse must yield the expected task floor."""
        tasks, _ = _backlog.parse()
        assert len(tasks) >= 75, f"Expected >= 75 tasks (H0 baseline), got {len(tasks)}"

    def test_real_backlog_returns_typed_lists(self) -> None:
        schema_errors, edge_warnings, collisions = run_lint()
        assert isinstance(schema_errors, list)
        assert isinstance(edge_warnings, list)
        assert isinstance(collisions, list)


# ---------------------------------------------------------------------------
# 2–3. Missing required fields → schema error
# ---------------------------------------------------------------------------

class TestMissingRequiredField:
    def test_missing_title_is_error(self, tmp_path: Path) -> None:
        yaml = textwrap.dedent("""\
            ```yaml
            id: P0-Z-002
            phase: 0   epic: P0-Z   depends_on: []   size: S
            change_kind: new
            files: [scripts/platform_harness/x.py]
            do: Do something.
            done_criteria: pytest tests/ -q
            ```
        """)
        _, schema_errors, _, _ = _lint_fixture(yaml, tmp_path)
        ids = [e.task_id for e in schema_errors]
        assert "P0-Z-002" in ids, f"Expected P0-Z-002 in errors; got {schema_errors}"
        msgs = " ".join(e.message for e in schema_errors if e.task_id == "P0-Z-002")
        assert "title" in msgs.lower(), f"Error message should mention 'title': {msgs}"

    def test_missing_done_criteria_is_error(self, tmp_path: Path) -> None:
        yaml = textwrap.dedent("""\
            ```yaml
            id: P0-Z-003
            title: Task missing done_criteria
            phase: 0   epic: P0-Z   depends_on: []   size: S
            change_kind: new
            files: [scripts/platform_harness/z.py]
            do: Do something useful.
            ```
        """)
        _, schema_errors, _, _ = _lint_fixture(yaml, tmp_path)
        ids = [e.task_id for e in schema_errors]
        assert "P0-Z-003" in ids, f"Expected P0-Z-003 in errors; got {schema_errors}"
        msgs = " ".join(e.message for e in schema_errors if e.task_id == "P0-Z-003")
        assert "done_criteria" in msgs.lower(), f"Error should name 'done_criteria': {msgs}"

    def test_optional_do_field_not_required(self, tmp_path: Path) -> None:
        """'do' is optional — its absence must not be a schema error."""
        yaml = textwrap.dedent("""\
            ```yaml
            id: P0-Z-004
            title: Task without do field
            phase: 0   epic: P0-Z   depends_on: []   size: S
            change_kind: new
            files: [scripts/platform_harness/y.py]
            done_criteria: pytest tests/ -q
            ```
        """)
        _, schema_errors, _, _ = _lint_fixture(yaml, tmp_path)
        ids = [e.task_id for e in schema_errors]
        assert "P0-Z-004" not in ids, f"'do' is optional; should not error: {schema_errors}"


# ---------------------------------------------------------------------------
# 4–6. depends_on validation
# ---------------------------------------------------------------------------

class TestDependsOnValidation:
    def test_dangling_dep_is_error(self, tmp_path: Path) -> None:
        yaml = textwrap.dedent("""\
            ```yaml
            id: P0-Z-010
            title: Task with dangling dep
            phase: 0   epic: P0-Z   depends_on: [NONEXISTENT-999]   size: S
            change_kind: new
            files: [scripts/platform_harness/dangle.py]
            do: Do something.
            done_criteria: pytest tests/ -q
            ```
        """)
        _, schema_errors, _, _ = _lint_fixture(yaml, tmp_path)
        ids = [e.task_id for e in schema_errors]
        assert "P0-Z-010" in ids, f"Expected P0-Z-010 in errors; got {schema_errors}"
        msgs = " ".join(e.message for e in schema_errors if e.task_id == "P0-Z-010")
        assert "NONEXISTENT-999" in msgs, f"Error should name the bad dep: {msgs}"

    def test_valid_dep_between_two_tasks_no_error(self, tmp_path: Path) -> None:
        yaml = textwrap.dedent("""\
            ```yaml
            id: P0-Z-011
            title: Root task
            phase: 0   epic: P0-Z   depends_on: []   size: S
            change_kind: new
            files: [scripts/platform_harness/root.py]
            do: Do something.
            done_criteria: pytest tests/ -q
            ```

            ```yaml
            id: P0-Z-012
            title: Child task with valid dep
            phase: 0   epic: P0-Z   depends_on: [P0-Z-011]   size: S
            change_kind: new
            files: [scripts/platform_harness/child.py]
            do: Do something dependent.
            done_criteria: pytest tests/ -q
            ```
        """)
        _, schema_errors, _, _ = _lint_fixture(yaml, tmp_path)
        dep_errors = [e for e in schema_errors if e.task_id == "P0-Z-012"]
        assert dep_errors == [], f"Valid dep should not produce error: {dep_errors}"

    def test_range_dep_not_an_error(self, tmp_path: Path) -> None:
        yaml = textwrap.dedent("""\
            ```yaml
            id: P0-Z-013
            title: Task with range dep
            phase: 0   epic: P0-Z   depends_on: [X-P1-001..016]   size: S
            change_kind: new
            files: [scripts/platform_harness/range_dep.py]
            do: Depends on a range.
            done_criteria: pytest tests/ -q
            ```
        """)
        _, schema_errors, _, _ = _lint_fixture(yaml, tmp_path)
        range_errors = [e for e in schema_errors if e.task_id == "P0-Z-013"]
        assert range_errors == [], f"Range dep must not be a schema error: {range_errors}"

    def test_epic_dep_resolved_no_error(self, tmp_path: Path) -> None:
        """An epic id reference (all tasks in that epic done) is valid."""
        yaml = textwrap.dedent("""\
            ```yaml
            id: P0-Z-014
            title: Epic-level root
            phase: 0   epic: P0-Z   depends_on: []   size: S
            change_kind: new
            files: [scripts/platform_harness/epic_root.py]
            do: Seed epic.
            done_criteria: pytest tests/ -q
            ```

            ```yaml
            id: P0-Z-015
            title: Task depending on whole epic P0-Z
            phase: 0   epic: P0-Z   depends_on: [P0-Z]   size: S
            change_kind: new
            files: [scripts/platform_harness/epic_child.py]
            do: Depends on P0-Z epic.
            done_criteria: pytest tests/ -q
            ```
        """)
        _, schema_errors, _, _ = _lint_fixture(yaml, tmp_path)
        dep_errors = [e for e in schema_errors if e.task_id == "P0-Z-015"]
        assert dep_errors == [], f"Epic dep should not be an error: {dep_errors}"


# ---------------------------------------------------------------------------
# 7–10. Honest-edge detection
# ---------------------------------------------------------------------------

class TestEdgePhrases:
    def test_edge_in_do_field(self, tmp_path: Path) -> None:
        yaml = textwrap.dedent("""\
            ```yaml
            id: P0-Z-030
            title: A legitimate task
            phase: 0   epic: P0-Z   depends_on: []   size: S
            change_kind: new
            files: [scripts/platform_harness/e.py]
            do: This feature proves our model has a proven edge over the books.
            done_criteria: pytest tests/ -q
            ```
        """)
        _, _, edge_warnings, _ = _lint_fixture(yaml, tmp_path)
        ids = [w.task_id for w in edge_warnings]
        assert "P0-Z-030" in ids, f"Expected P0-Z-030 edge warning; got {edge_warnings}"
        fields = [w.field for w in edge_warnings if w.task_id == "P0-Z-030"]
        assert "do" in fields, f"Warning should name field 'do': {fields}"

    def test_edge_in_done_criteria(self, tmp_path: Path) -> None:
        yaml = textwrap.dedent("""\
            ```yaml
            id: P0-Z-031
            title: A task
            phase: 0   epic: P0-Z   depends_on: []   size: S
            change_kind: new
            files: [scripts/platform_harness/f.py]
            do: Build a signal.
            done_criteria: model is profitable and edge exists on held-out data
            ```
        """)
        _, _, edge_warnings, _ = _lint_fixture(yaml, tmp_path)
        ids = [w.task_id for w in edge_warnings]
        assert "P0-Z-031" in ids, f"Expected P0-Z-031 edge warning; got {edge_warnings}"
        fields = [w.field for w in edge_warnings if w.task_id == "P0-Z-031"]
        assert "done_criteria" in fields, f"Warning should name 'done_criteria': {fields}"

    def test_edge_in_title(self, tmp_path: Path) -> None:
        yaml = textwrap.dedent("""\
            ```yaml
            id: P0-Z-032
            title: Build profitable signal that beats the close
            phase: 0   epic: P0-Z   depends_on: []   size: S
            change_kind: new
            files: [scripts/platform_harness/g.py]
            do: Build something.
            done_criteria: pytest tests/ -q
            ```
        """)
        _, _, edge_warnings, _ = _lint_fixture(yaml, tmp_path)
        ids = [w.task_id for w in edge_warnings]
        assert "P0-Z-032" in ids, f"Expected P0-Z-032 edge warning; got {edge_warnings}"
        fields = [w.field for w in edge_warnings if w.task_id == "P0-Z-032"]
        assert "title" in fields, f"Warning should name 'title': {fields}"

    def test_multiple_edge_patterns_all_fire(self, tmp_path: Path) -> None:
        yaml = textwrap.dedent("""\
            ```yaml
            id: P0-Z-033
            title: Guaranteed profitable edge
            phase: 0   epic: P0-Z   depends_on: []   size: S
            change_kind: new
            files: [scripts/platform_harness/h.py]
            do: Something clean.
            done_criteria: edge is proven on held-out data
            ```
        """)
        _, _, edge_warnings, _ = _lint_fixture(yaml, tmp_path)
        ids = [w.task_id for w in edge_warnings]
        count = ids.count("P0-Z-033")
        assert count >= 2, (
            f"Multiple edge patterns should each fire separately; got {edge_warnings}"
        )

    def test_clean_task_no_edge_warning(self, tmp_path: Path) -> None:
        _, _, edge_warnings, _ = _lint_fixture(VALID_TASK_YAML, tmp_path)
        ids = [w.task_id for w in edge_warnings]
        assert "P0-Z-001" not in ids, f"Clean task must not trigger edge warning: {edge_warnings}"


# ---------------------------------------------------------------------------
# 11–13. File-collision detection
# ---------------------------------------------------------------------------

class TestFileCollision:
    def test_shared_file_same_group_is_collision(self, tmp_path: Path) -> None:
        yaml = textwrap.dedent("""\
            ```yaml
            id: P0-Z-040
            title: Task A
            phase: 0   epic: P0-Z   depends_on: []   size: S   parallel_group: wave_x
            change_kind: new
            files: [scripts/platform_harness/shared.py, scripts/platform_harness/a_only.py]
            do: Write A.
            done_criteria: pytest tests/ -q
            ```

            ```yaml
            id: P0-Z-041
            title: Task B
            phase: 0   epic: P0-Z   depends_on: []   size: S   parallel_group: wave_x
            change_kind: new
            files: [scripts/platform_harness/shared.py, scripts/platform_harness/b_only.py]
            do: Write B.
            done_criteria: pytest tests/ -q
            ```
        """)
        _, _, _, collisions = _lint_fixture(yaml, tmp_path)
        assert len(collisions) >= 1, f"Expected >= 1 collision; got {collisions}"
        fp_set = {c.file_path for c in collisions}
        assert "scripts/platform_harness/shared.py" in fp_set, (
            f"Shared file should appear in collisions: {collisions}"
        )
        # Non-shared files must NOT appear
        assert "scripts/platform_harness/a_only.py" not in fp_set
        assert "scripts/platform_harness/b_only.py" not in fp_set

    def test_disjoint_files_same_group_no_collision(self, tmp_path: Path) -> None:
        yaml = textwrap.dedent("""\
            ```yaml
            id: P0-Z-042
            title: Task C
            phase: 0   epic: P0-Z   depends_on: []   size: S   parallel_group: wave_y
            change_kind: new
            files: [scripts/platform_harness/c.py]
            do: Write C.
            done_criteria: pytest tests/ -q
            ```

            ```yaml
            id: P0-Z-043
            title: Task D
            phase: 0   epic: P0-Z   depends_on: []   size: S   parallel_group: wave_y
            change_kind: new
            files: [scripts/platform_harness/d.py]
            do: Write D.
            done_criteria: pytest tests/ -q
            ```
        """)
        _, _, _, collisions = _lint_fixture(yaml, tmp_path)
        assert collisions == [], f"Disjoint files must not collide: {collisions}"

    def test_same_file_different_groups_no_collision(self, tmp_path: Path) -> None:
        yaml = textwrap.dedent("""\
            ```yaml
            id: P0-Z-044
            title: Task E group 1
            phase: 0   epic: P0-Z   depends_on: []   size: S   parallel_group: wave_e1
            change_kind: new
            files: [scripts/platform_harness/shared2.py]
            do: Write E.
            done_criteria: pytest tests/ -q
            ```

            ```yaml
            id: P0-Z-045
            title: Task F group 2
            phase: 0   epic: P0-Z   depends_on: []   size: S   parallel_group: wave_e2
            change_kind: new
            files: [scripts/platform_harness/shared2.py]
            do: Write F.
            done_criteria: pytest tests/ -q
            ```
        """)
        _, _, _, collisions = _lint_fixture(yaml, tmp_path)
        assert collisions == [], (
            "Same file in DIFFERENT groups is sequenced by dependency — not a collision"
        )


# ---------------------------------------------------------------------------
# 14. Clean task
# ---------------------------------------------------------------------------

class TestCleanTask:
    def test_clean_task_produces_no_issues(self, tmp_path: Path) -> None:
        tasks, schema_errors, edge_warnings, collisions = _lint_fixture(
            VALID_TASK_YAML, tmp_path
        )
        assert len(tasks) == 1
        assert schema_errors == [], f"Clean task must not have schema errors: {schema_errors}"
        assert edge_warnings == [], f"Clean task must not have edge warnings: {edge_warnings}"
        assert collisions == [], f"Single task cannot collide with itself: {collisions}"


# ---------------------------------------------------------------------------
# 15. Gate-style task (no do, no change_kind, empty files) is valid
# ---------------------------------------------------------------------------

class TestGateStyleTask:
    def test_gate_task_no_schema_error(self, tmp_path: Path) -> None:
        """Gate tasks legitimately omit do, change_kind, and files."""
        tasks, schema_errors, _, _ = _lint_fixture(GATE_TASK_YAML, tmp_path)
        assert len(tasks) == 1
        gate_errors = [e for e in schema_errors if e.task_id == "X-P1-GATE"]
        assert gate_errors == [], f"Gate task should have no schema errors: {gate_errors}"


# ---------------------------------------------------------------------------
# 16. Duplicate id → promoted to schema error
# ---------------------------------------------------------------------------

class TestDuplicateId:
    def test_duplicate_id_reported_in_schema_errors(self, tmp_path: Path) -> None:
        yaml = textwrap.dedent("""\
            ```yaml
            id: P0-Z-060
            title: First occurrence
            phase: 0   epic: P0-Z   depends_on: []   size: S
            change_kind: new
            files: [scripts/platform_harness/dup1.py]
            do: First.
            done_criteria: pytest tests/ -q
            ```

            ```yaml
            id: P0-Z-060
            title: Duplicate id — second occurrence
            phase: 0   epic: P0-Z   depends_on: []   size: S
            change_kind: new
            files: [scripts/platform_harness/dup2.py]
            do: Second.
            done_criteria: pytest tests/ -q
            ```
        """)
        _, schema_errors, _, _ = _lint_fixture(yaml, tmp_path)
        # backlog.parse() produces "Duplicate id: 'P0-Z-060'" which run_lint promotes
        combined_text = " ".join(str(e) for e in schema_errors)
        assert "P0-Z-060" in combined_text, (
            f"Duplicate id P0-Z-060 should appear in schema errors: {schema_errors}"
        )


# ---------------------------------------------------------------------------
# 17. Result type string formatting
# ---------------------------------------------------------------------------

class TestResultFormatting:
    def test_schema_error_str_contains_required_parts(self) -> None:
        e = SchemaError("P0-Z-099", "required field 'title' is missing or empty")
        s = str(e)
        assert "SCHEMA_ERROR" in s
        assert "P0-Z-099" in s
        assert "title" in s

    def test_edge_warning_str_contains_required_parts(self) -> None:
        w = EdgeWarning(
            task_id="P0-Z-098",
            field="do",
            pattern="proven_edge",
            excerpt="has a proven edge",
        )
        s = str(w)
        assert "HONEST_EDGE_WARN" in s
        assert "P0-Z-098" in s
        assert "proven_edge" in s
        assert "do" in s

    def test_collision_warning_str_contains_required_parts(self) -> None:
        c = CollisionWarning("wave_a", "src/foo.py", ("T1", "T2"))
        s = str(c)
        assert "FILE_COLLISION" in s
        assert "wave_a" in s
        assert "src/foo.py" in s
        assert "T1" in s
        assert "T2" in s


# ---------------------------------------------------------------------------
# 18–20. CLI exit codes and output structure
# ---------------------------------------------------------------------------

class TestCLI:
    def test_cli_clean_fixture_exits_0(self, tmp_path: Path) -> None:
        path = _make_backlog(VALID_TASK_YAML, tmp_path)
        result = subprocess.run(
            [_ENVPY,
             str(ROOT / "scripts" / "platform_harness" / "backlog_lint.py"),
             "--path", str(path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Expected exit 0 for clean fixture.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "PASS" in result.stdout

    def test_cli_schema_error_exits_1(self, tmp_path: Path) -> None:
        # Missing title → schema error
        bad_yaml = textwrap.dedent("""\
            ```yaml
            id: P0-Z-099
            phase: 0   epic: P0-Z   depends_on: []   size: S
            change_kind: new
            files: [scripts/platform_harness/bad.py]
            do: Something.
            done_criteria: pytest tests/ -q
            ```
        """)
        path = _make_backlog(bad_yaml, tmp_path)
        result = subprocess.run(
            [_ENVPY,
             str(ROOT / "scripts" / "platform_harness" / "backlog_lint.py"),
             "--path", str(path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1, (
            f"Expected exit 1 for schema error.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "FAIL" in result.stdout

    def test_cli_outputs_three_structured_sections(self, tmp_path: Path) -> None:
        path = _make_backlog(VALID_TASK_YAML, tmp_path)
        result = subprocess.run(
            [_ENVPY,
             str(ROOT / "scripts" / "platform_harness" / "backlog_lint.py"),
             "--path", str(path)],
            capture_output=True,
            text=True,
        )
        assert "SCHEMA ERRORS" in result.stdout, "Missing SCHEMA ERRORS section header"
        assert "HONEST-EDGE" in result.stdout, "Missing HONEST-EDGE section header"
        assert "FILE-COLLISION" in result.stdout, "Missing FILE-COLLISION section header"
        assert "RESULT:" in result.stdout, "Missing RESULT summary line"

    def test_cli_edge_warning_does_not_cause_nonzero_exit(self, tmp_path: Path) -> None:
        """Edge warnings are soft — CLI must still exit 0 when schema is clean."""
        edge_yaml = textwrap.dedent("""\
            ```yaml
            id: P0-Z-070
            title: Build profitable model
            phase: 0   epic: P0-Z   depends_on: []   size: S
            change_kind: new
            files: [scripts/platform_harness/soft.py]
            do: Something.
            done_criteria: pytest tests/ -q
            ```
        """)
        path = _make_backlog(edge_yaml, tmp_path)
        result = subprocess.run(
            [_ENVPY,
             str(ROOT / "scripts" / "platform_harness" / "backlog_lint.py"),
             "--path", str(path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Edge warning must not produce nonzero exit.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "PASS" in result.stdout
        assert "HONEST-EDGE WARNINGS: 1" in result.stdout
