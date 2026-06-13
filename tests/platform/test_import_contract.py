"""test_import_contract.py — Tests for the AST import-direction guard.

Three test cases:

1. GREEN: the current ``kernel/`` tree is clean — zero violations.
2. NEGATIVE (kernel): a temporary kernel module containing ``import nba_api``
   is detected and flagged; the temp file is written under ``tmp_path`` and the
   checker is pointed at a synthetic root so no file ever lands inside the
   real ``kernel/`` directory.
3. NEGATIVE (cross-adapter): a temp ``domains/sport_a/`` module that imports
   ``domains.sport_b`` is flagged; again everything lives under ``tmp_path``.

Temp files never touch the committed tree — they are created under pytest's
``tmp_path`` fixture which cleans up automatically.
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import List

import pytest

from scripts.platformkit.check_import_contract import Violation, check


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _write(path: Path, source: str) -> None:
    """Write *source* to *path*, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source), encoding="utf-8")


def _make_minimal_root(tmp_path: Path) -> Path:
    """Create a minimal fake repo root with a CLAUDE.md marker file."""
    (tmp_path / "CLAUDE.md").write_text("# marker\n", encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Test 1 — GREEN: real kernel/ tree produces zero violations
# ---------------------------------------------------------------------------

def test_kernel_is_clean() -> None:
    """The committed kernel/ tree must contain no import-contract violations."""
    violations: List[Violation] = check()
    assert violations == [], (
        f"Expected zero violations in kernel/ but found {len(violations)}:\n"
        + "\n".join(str(v) for v in violations)
    )


# ---------------------------------------------------------------------------
# Test 2 — NEGATIVE: kernel module importing nba_api is flagged
# ---------------------------------------------------------------------------

def test_kernel_nba_api_import_is_flagged(tmp_path: Path) -> None:
    """A kernel module that imports nba_api must be caught as a violation."""
    root = _make_minimal_root(tmp_path)

    # Build a minimal synthetic kernel tree under tmp_path
    kernel_dir = root / "kernel"
    _write(
        kernel_dir / "__init__.py",
        '"""kernel stub."""\n',
    )
    _write(
        kernel_dir / "bad_module.py",
        """\
        from __future__ import annotations
        import nba_api  # should be caught
        """,
    )

    violations = check(root=root)

    assert len(violations) >= 1, (
        "Expected at least one KERNEL_IMPORT_VIOLATION for 'import nba_api' "
        f"but got zero.  violations={violations}"
    )
    kinds = {v.kind for v in violations}
    assert "KERNEL_IMPORT_VIOLATION" in kinds, (
        f"Expected kind KERNEL_IMPORT_VIOLATION; got kinds={kinds}"
    )
    modules = {v.module for v in violations}
    assert "nba_api" in modules, (
        f"Expected violation for module 'nba_api'; got modules={modules}"
    )


def test_kernel_src_import_is_flagged(tmp_path: Path) -> None:
    """A kernel module that imports from src.* must also be caught."""
    root = _make_minimal_root(tmp_path)
    kernel_dir = root / "kernel"
    _write(kernel_dir / "__init__.py", '"""kernel stub."""\n')
    _write(
        kernel_dir / "bad_src.py",
        """\
        from __future__ import annotations
        from src.prediction import player_props  # banned
        """,
    )

    violations = check(root=root)
    assert any(
        v.kind == "KERNEL_IMPORT_VIOLATION" and v.module.startswith("src")
        for v in violations
    ), f"Expected KERNEL_IMPORT_VIOLATION for src.* import; got {violations}"


def test_kernel_allowlisted_imports_are_clean(tmp_path: Path) -> None:
    """A kernel module using only stdlib + numpy + kernel.* must produce no violations."""
    root = _make_minimal_root(tmp_path)
    kernel_dir = root / "kernel"
    _write(kernel_dir / "__init__.py", '"""kernel stub."""\n')
    _write(
        kernel_dir / "clean_module.py",
        """\
        from __future__ import annotations
        import os
        import sys
        from typing import List
        from dataclasses import dataclass
        import numpy as np
        from kernel.config import stats  # self-import ok
        """,
    )

    violations = check(root=root)
    assert violations == [], (
        f"Expected zero violations for a clean kernel module; got {violations}"
    )


# ---------------------------------------------------------------------------
# Test 3 — NEGATIVE: cross-adapter import is flagged
# ---------------------------------------------------------------------------

def test_cross_adapter_import_is_flagged(tmp_path: Path) -> None:
    """domains/sport_a importing domains.sport_b must be a CROSS_ADAPTER_VIOLATION."""
    root = _make_minimal_root(tmp_path)

    # Build two domain adapters
    domains_dir = root / "domains"
    _write(domains_dir / "__init__.py", '"""domains stub."""\n')

    # sport_a
    _write(domains_dir / "sport_a" / "__init__.py", '"""sport_a stub."""\n')
    _write(
        domains_dir / "sport_a" / "bad_crossref.py",
        """\
        from __future__ import annotations
        # This is the banned cross-adapter reference:
        from domains.sport_b import config  # should be caught
        """,
    )

    # sport_b (must exist so the import makes syntactic sense)
    _write(domains_dir / "sport_b" / "__init__.py", '"""sport_b stub."""\n')
    _write(domains_dir / "sport_b" / "config.py", '"""sport_b config."""\n')

    violations = check(root=root)

    cross = [v for v in violations if v.kind == "CROSS_ADAPTER_VIOLATION"]
    assert len(cross) >= 1, (
        f"Expected at least one CROSS_ADAPTER_VIOLATION; got violations={violations}"
    )
    assert any(
        "sport_b" in v.module for v in cross
    ), f"Expected violation referencing sport_b; got {cross}"


def test_same_domain_import_is_clean(tmp_path: Path) -> None:
    """domains/sport_a importing its own submodule must NOT be a violation."""
    root = _make_minimal_root(tmp_path)
    domains_dir = root / "domains"
    _write(domains_dir / "__init__.py", '"""domains stub."""\n')

    _write(domains_dir / "sport_a" / "__init__.py", '"""sport_a stub."""\n')
    _write(
        domains_dir / "sport_a" / "consumer.py",
        """\
        from __future__ import annotations
        from domains.sport_a import config  # same domain — ok
        from kernel.config import stats     # kernel — ok
        """,
    )
    _write(domains_dir / "sport_a" / "config.py", '"""sport_a config."""\n')

    violations = check(root=root)
    cross = [v for v in violations if v.kind == "CROSS_ADAPTER_VIOLATION"]
    assert cross == [], (
        f"Expected no CROSS_ADAPTER_VIOLATION for same-domain import; got {cross}"
    )


# ---------------------------------------------------------------------------
# Test 4 — No stray files leaked into real kernel/ or domains/ trees
# ---------------------------------------------------------------------------

def test_no_stray_files_in_real_tree() -> None:
    """All negative tests use tmp_path — the real kernel/ and domains/ dirs must
    contain only committed files (no leftover temp files)."""
    real_violations = check()
    # If real tree is still clean after all tests ran, no temp file leaked.
    assert real_violations == [], (
        f"Real tree has violations after test run — possible temp file leak:\n"
        + "\n".join(str(v) for v in real_violations)
    )
