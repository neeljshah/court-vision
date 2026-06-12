"""Tests for kernel.paths.repo_root()."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Case 1: marker discovery — repo_root() resolves to the real repo root
# ---------------------------------------------------------------------------

def test_marker_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    """repo_root() walks parents until it finds a marker file (CLAUDE.md/.git/pyproject.toml).

    With COURTVISION_ROOT unset the function must return a Path that exists and
    contains at least one of the marker files.
    """
    monkeypatch.delenv("COURTVISION_ROOT", raising=False)

    from kernel.paths import repo_root, _MARKERS

    root = repo_root()

    assert isinstance(root, Path), "repo_root() must return a Path"
    assert root.is_dir(), f"repo_root() returned a non-directory: {root}"
    assert any((root / m).exists() for m in _MARKERS), (
        f"repo_root() returned {root!r} but none of {_MARKERS} exist there"
    )
    # Sanity: CLAUDE.md specifically should be present in this repo
    assert (root / "CLAUDE.md").exists(), (
        f"Expected CLAUDE.md at {root} — verify this is the right repo root"
    )


# ---------------------------------------------------------------------------
# Case 2: env override — COURTVISION_ROOT wins, no filesystem walk needed
# ---------------------------------------------------------------------------

def test_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """When COURTVISION_ROOT is set, repo_root() must return exactly Path(env_value).

    The returned path need not contain any markers; the env var is taken as-is.
    This also demonstrates that the override path is honored without any walk.
    """
    target = str(tmp_path)
    monkeypatch.setenv("COURTVISION_ROOT", target)

    # Re-import to avoid any cached state (module-level cache would be a bug anyway)
    from kernel.paths import repo_root

    result = repo_root()

    assert result == Path(target), (
        f"Expected Path({target!r}), got {result!r}"
    )


# ---------------------------------------------------------------------------
# Case 3: override-then-unset — env branch is mutually exclusive from the walk
# ---------------------------------------------------------------------------

def test_env_branch_honored_exclusively(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Setting COURTVISION_ROOT to a directory with NO markers still returns that path.

    This confirms the env branch is a bypass: when the env var is present the
    filesystem-walk branch is never reached, even for a path that would cause
    RuntimeError if the walk ran (empty tmp directory has no markers).
    """
    monkeypatch.setenv("COURTVISION_ROOT", str(tmp_path))

    from kernel.paths import repo_root, _MARKERS

    result = repo_root()

    # tmp_path has no markers — if the walk ran we'd get RuntimeError or a wrong path
    assert result == tmp_path
    assert not any((tmp_path / m).exists() for m in _MARKERS), (
        "Precondition: tmp_path must not contain any markers for this test to be meaningful"
    )
