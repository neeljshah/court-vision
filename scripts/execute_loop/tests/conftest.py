"""conftest.py — Shared pytest fixtures for execute_loop tests.

Provides an autouse fixture that keeps the ``scripts.execute_loop`` package's
submodule attributes in sync with ``sys.modules`` before and after each test.

Background
----------
Python's ``import a.b.c as X`` binds X to ``getattr(a.b, "c")`` — the parent
package's attribute — NOT to ``sys.modules["a.b.c"]``.  Tests that mock
``sys.modules["scripts.execute_loop.Lxx"]`` via monkeypatch.setitem therefore
need the parent package attribute to be consistent with sys.modules at the
START of each test.

This fixture performs a sync before (and after) each test so that any stale
package attributes left by previous imports are cleared.  Combined with each
individual test module's own ``_reset_singleton``-style cleanup (which removes
entries from sys.modules), this fixture ensures full isolation.
"""
from __future__ import annotations

import sys
from typing import Any, Optional

import pytest

_EL_PKG = "scripts.execute_loop"
_EL_PREFIX = _EL_PKG + "."


def _is_el_submod_key(key: str) -> bool:
    """True if key is a direct-child execute_loop submodule sys.modules key."""
    if not key.startswith(_EL_PREFIX):
        return False
    rest = key[len(_EL_PREFIX):]
    return "." not in rest and rest.startswith("L") and len(rest) > 1 and rest[1:3].isdigit()


def _sync_el_pkg_attrs() -> None:
    """Make scripts.execute_loop package attrs match sys.modules for Lxx submodules.

    - Removes package attrs whose sys.modules entry is absent.
    - Updates package attrs whose sys.modules entry differs.
    - Adds package attrs for sys.modules entries missing from the package.
    """
    pkg = sys.modules.get(_EL_PKG)
    if pkg is None:
        return
    pkg_dict = getattr(pkg, "__dict__", {})

    # Remove stale attrs (present in pkg but absent/different in sys.modules)
    for attr in [a for a in pkg_dict if _is_el_submod_key(_EL_PREFIX + a)]:
        full_key = _EL_PREFIX + attr
        if full_key not in sys.modules:
            pkg_dict.pop(attr, None)
        elif pkg_dict.get(attr) is not sys.modules[full_key]:
            pkg_dict[attr] = sys.modules[full_key]

    # Add/update missing attrs from sys.modules
    for full_key in list(sys.modules):
        if not _is_el_submod_key(full_key):
            continue
        attr = full_key[len(_EL_PREFIX):]
        if pkg_dict.get(attr) is not sys.modules[full_key]:
            pkg_dict[attr] = sys.modules[full_key]


@pytest.fixture(autouse=True)
def ensure_el_pkg_attrs_consistent():
    """Sync execute_loop package attrs with sys.modules before + after each test.

    This ensures that any stale cached package attribute from a previous test's
    imports does not leak into the current test's ``import scripts.execute_loop.Lxx``
    call inside test-subject code.
    """
    _sync_el_pkg_attrs()
    yield
    _sync_el_pkg_attrs()
