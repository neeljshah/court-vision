"""Tests for scripts.platformkit.improve.pipeline_flag (MF1 kill-switch helper).

Covers:
  1. Absent sentinel  -> pipeline_enabled() returns False.
  2. Present sentinel -> pipeline_enabled() returns True.
  3. Sentinel is removed after being created  -> returns False again.
  4. SENTINEL_PATH is exported and is a pathlib.Path instance.
  5. The module never creates the sentinel itself (SENTINEL_PATH absent after import).

All sentinel I/O is under a tmp directory (monkeypatched via _sentinel kwarg);
no writes ever reach data/cache/improve/.  No network.  ASCII only.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.improve.pipeline_flag import (  # noqa: E402
    SENTINEL_PATH,
    pipeline_enabled,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _sentinel_path(tmp_path: pathlib.Path) -> pathlib.Path:
    """Return a sentinel path under tmp_path (file does NOT exist yet)."""
    return tmp_path / "PIPELINE_ENABLED"


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

def test_absent_sentinel_returns_false(tmp_path: pathlib.Path) -> None:
    """When the sentinel file does not exist, pipeline_enabled() is False."""
    sentinel = _sentinel_path(tmp_path)
    assert not sentinel.exists(), "pre-condition: sentinel must be absent"
    assert pipeline_enabled(_sentinel=sentinel) is False


def test_present_sentinel_returns_true(tmp_path: pathlib.Path) -> None:
    """When the sentinel file exists, pipeline_enabled() is True."""
    sentinel = _sentinel_path(tmp_path)
    sentinel.touch()
    assert sentinel.exists(), "pre-condition: sentinel must exist"
    assert pipeline_enabled(_sentinel=sentinel) is True


def test_removed_sentinel_returns_false(tmp_path: pathlib.Path) -> None:
    """After the sentinel is removed, pipeline_enabled() reverts to False."""
    sentinel = _sentinel_path(tmp_path)
    sentinel.touch()
    assert pipeline_enabled(_sentinel=sentinel) is True
    sentinel.unlink()
    assert pipeline_enabled(_sentinel=sentinel) is False


def test_sentinel_path_exported_as_pathlib_path() -> None:
    """SENTINEL_PATH is a pathlib.Path (not a str/None), exported from the module."""
    assert isinstance(SENTINEL_PATH, pathlib.Path)


def test_module_never_creates_sentinel() -> None:
    """Importing the module must not create data/cache/improve/PIPELINE_ENABLED.

    Verifies the invariant that only a human can flip the flag.
    The real SENTINEL_PATH may or may not exist on this box; the point is that
    merely calling pipeline_enabled() with the real path NEVER creates it.
    """
    initial_exists = SENTINEL_PATH.exists()
    # call once with the real (production) path
    _ = pipeline_enabled()
    # the presence state must be unchanged
    assert SENTINEL_PATH.exists() == initial_exists, (
        "pipeline_enabled() must not create or remove the sentinel"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
