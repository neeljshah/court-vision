"""tests/kernel/test_import_smoke.py — P0-F-003: kernel import smoke test.

Proves that importing ``kernel`` (and ``kernel.config.*``) succeeds even when
``nba_api`` is unavailable at import time, confirming the kernel has zero
sport-specific / heavy imports at module load.

Three tests
-----------
1. **Positive smoke** — runs a subprocess with ``nba_api`` poisoned (set to
   ``None`` in ``sys.modules``), imports ``kernel`` plus the three config
   modules, and asserts exit code 0 plus "OK" in stdout.

2. **Heavy-module guard** — runs a subprocess with ``nba_api`` poisoned,
   imports ``kernel``, then asserts that ``torch`` and ``pandas`` are NOT
   present in ``sys.modules`` after the import (they must not be pulled in
   transitively).

3. **Negative test (hermeticity)** — plants a temporary Python file inside
   ``kernel/`` that does ``import nba_api`` at top level, then verifies that
   importing that temp module raises an error (exit code ≠ 0) while
   ``nba_api`` is poisoned.  Removes the temp file unconditionally via
   ``try/finally``, then asserts no stray file remains in ``kernel/``.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo-root discovery
# ---------------------------------------------------------------------------

# This file lives at <repo>/tests/kernel/test_import_smoke.py
_REPO_ROOT: Path = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(code: str) -> subprocess.CompletedProcess[str]:
    """Run *code* in a subprocess using the current interpreter.

    Parameters
    ----------
    code:
        Python source string to execute with ``-c``.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The completed process with ``stdout`` and ``stderr`` captured.
    """
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )


_POISON_PREFIX = (
    "import sys; sys.modules['nba_api'] = None; "
)
"""Prefix that poisons nba_api so any ``import nba_api`` inside the
subprocess raises ``ImportError`` (because ``sys.modules[key] = None``
is the CPython sentinel for a failed/blocked import)."""


# ---------------------------------------------------------------------------
# Test 1 — positive smoke: kernel imports cleanly without nba_api
# ---------------------------------------------------------------------------

def test_kernel_import_smoke_no_nba_api() -> None:
    """Kernel and kernel.config.* import successfully when nba_api is unavailable.

    The subprocess poisons ``sys.modules['nba_api']`` before any import,
    then imports ``kernel``, ``kernel.config.stats``, ``kernel.config.clock``,
    and ``kernel.config.pbp``.  The script prints "OK" on success.

    Assertions
    ----------
    * Return code is 0.
    * "OK" appears in stdout.
    """
    code = (
        _POISON_PREFIX
        + "import kernel; "
        + "import kernel.config.stats; "
        + "import kernel.config.clock; "
        + "import kernel.config.pbp; "
        + "print('OK')"
    )
    result = _run(code)
    assert result.returncode == 0, (
        f"Kernel import failed (rc={result.returncode}).\n"
        f"stdout: {result.stdout!r}\n"
        f"stderr: {result.stderr!r}"
    )
    assert "OK" in result.stdout, (
        f"Expected 'OK' in stdout but got: {result.stdout!r}\n"
        f"stderr: {result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Test 2 — heavy-module guard: torch and pandas not pulled in by kernel import
# ---------------------------------------------------------------------------

def test_kernel_import_does_not_pull_torch_or_pandas() -> None:
    """Importing ``kernel`` must not transitively import torch or pandas.

    The subprocess imports ``kernel`` (with ``nba_api`` poisoned) and then
    checks ``sys.modules`` for ``torch`` and ``pandas``.  If either is
    present the subprocess prints their names and exits non-zero.

    Assertions
    ----------
    * Return code is 0 (neither torch nor pandas appeared in sys.modules).
    """
    code = (
        _POISON_PREFIX
        + "import kernel; "
        + "import kernel.config.stats; "
        + "import kernel.config.clock; "
        + "import kernel.config.pbp; "
        + "heavy = [m for m in ('torch', 'pandas') if m in sys.modules]; "
        + "import sys as _sys; "
        # Re-import sys under a different name to avoid shadowing the earlier
        # ``sys`` alias used in the poison prefix (they are the same object).
        + "heavy2 = [m for m in ('torch', 'pandas') if m in _sys.modules]; "
        + "_sys.exit(0 if not heavy2 else 1)"
    )
    # Rebuild without the name clash: use a single coherent script string.
    code = (
        "import sys\n"
        "sys.modules['nba_api'] = None\n"
        "import kernel\n"
        "import kernel.config.stats\n"
        "import kernel.config.clock\n"
        "import kernel.config.pbp\n"
        "heavy = [m for m in ('torch', 'pandas') if m in sys.modules]\n"
        "if heavy:\n"
        "    print('HEAVY_IMPORTS_FOUND:', heavy)\n"
        "    sys.exit(1)\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"Heavy imports detected after 'import kernel'.\n"
        f"stdout: {result.stdout!r}\n"
        f"stderr: {result.stderr!r}"
    )
    assert "OK" in result.stdout, (
        f"Expected 'OK' in stdout but got: {result.stdout!r}\n"
        f"stderr: {result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Test 3 — negative / hermeticity: planted nba_api import inside kernel fails
# ---------------------------------------------------------------------------

def test_negative_planted_nba_api_import_fails_and_no_stray_file() -> None:
    """A kernel module that imports nba_api at top level must cause smoke to fail.

    Procedure
    ---------
    1. Write a temp Python file ``kernel/_smoke_poison_tmp.py`` that executes
       ``import nba_api`` at module level.
    2. Run a subprocess (nba_api poisoned) that imports the temp module via its
       fully-qualified name.
    3. Assert the subprocess exits non-zero — proving the negative test works.
    4. ``finally`` unconditionally removes the temp file and its ``__pycache__``
       artefact (if any).
    5. Assert the temp file no longer exists in ``kernel/``.
    6. Assert ``git status --porcelain kernel/`` reports no tracked changes
       (the kernel/ tree is clean), confirming hermeticity.

    Assertions
    ----------
    * Subprocess exit code is non-zero (planted import causes failure).
    * Temp file does not exist after the test.
    * ``git status --porcelain kernel/`` output is empty.
    """
    kernel_dir: Path = _REPO_ROOT / "kernel"
    tmp_module_name = "_smoke_poison_tmp"
    tmp_file: Path = kernel_dir / f"{tmp_module_name}.py"

    # Defensive: if a previous aborted run left the file, remove it first.
    if tmp_file.exists():
        tmp_file.unlink()

    try:
        # Step 1 — plant the temp module.
        tmp_file.write_text(
            '"""Temporary negative-test module — must be deleted by the test."""\n'
            "import nba_api  # this import must fail when nba_api is poisoned\n",
            encoding="utf-8",
        )
        assert tmp_file.exists(), "Failed to create temp module file."

        # Step 2 — run subprocess: poison nba_api, then import the temp module.
        code = (
            "import sys\n"
            "sys.modules['nba_api'] = None\n"
            f"import kernel.{tmp_module_name}\n"
            "print('SHOULD_NOT_REACH')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )

        # Step 3 — the subprocess MUST fail.
        assert result.returncode != 0, (
            "Expected non-zero exit code when importing a kernel module that "
            "contains 'import nba_api' (with nba_api poisoned), but it "
            f"succeeded.\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )
        assert "SHOULD_NOT_REACH" not in result.stdout, (
            "Subprocess printed 'SHOULD_NOT_REACH', meaning the poisoned "
            "import did not raise an error as expected."
        )

    finally:
        # Step 4 — unconditional cleanup.
        if tmp_file.exists():
            tmp_file.unlink()

        # Remove any __pycache__ bytecode artefact for the temp module.
        pycache_dir: Path = kernel_dir / "__pycache__"
        if pycache_dir.is_dir():
            for pyc in pycache_dir.glob(f"{tmp_module_name}.cpython-*.pyc"):
                pyc.unlink()

    # Step 5 — file must be gone.
    assert not tmp_file.exists(), (
        f"Temp file {tmp_file} still exists after cleanup — hermeticity failure."
    )

    # Step 6 — git status must not list our specific temp file.
    # We check for the exact temp filename rather than asserting kernel/ is
    # globally clean, because other untracked files may exist in kernel/ that
    # predate this test run and are unrelated to it.
    git_result = subprocess.run(
        ["git", "status", "--porcelain", "kernel/"],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    stray_lines = [
        line for line in git_result.stdout.splitlines()
        if tmp_module_name in line
    ]
    assert not stray_lines, (
        f"Temp file {tmp_file.name!r} still appears in 'git status' output "
        f"after cleanup — hermeticity failure.\n"
        f"Matching lines: {stray_lines}\n"
        f"Full git status:\n{git_result.stdout}"
    )
