"""The drift checker must see every module that feeds the harness."""
from __future__ import annotations

import ast
from pathlib import Path

from scripts.platformkit.tracking.pod_drift import _is_scoped_module

_ROOT = Path(__file__).resolve().parents[3]
_HARNESS = "scripts/platformkit/tracking_harness.py"


def _platformkit_imports(relative: str) -> set:
    """Modules the file imports from scripts.platformkit, as bare filenames."""
    tree = ast.parse((_ROOT / relative).read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            if parts[:2] == ["scripts", "platformkit"] and len(parts) == 3:
                found.add(parts[2] + ".py")
    return found


def test_every_harness_dependency_is_in_drift_scope() -> None:
    """A harness dependency outside the scope is a silent pod/master divergence.

    The regression: the scope covered tracking_harness.py but none of what it
    imports, so metric_local_profile.py could sit at a different revision on the
    pod than on master and the checker would report no drift. That gap broke the
    pod twice on 2026-09-02 -- an ImportError deploying the harness without its
    dependencies, and a TypeError rolling the harness back without them.
    """
    missing = sorted(
        name for name in _platformkit_imports(_HARNESS)
        if not _is_scoped_module("scripts/platformkit/" + name))
    assert missing == [], (
        "tracking_harness imports these but pod_drift cannot see them: %s" % missing)


def test_the_checker_still_excludes_itself_and_the_junction_helper() -> None:
    """Local-only modules stay out, or the checker reports a permanent drift."""
    assert not _is_scoped_module("scripts/platformkit/tracking/pod_drift.py")
    assert not _is_scoped_module("scripts/platformkit/tracking/worktree_data_links.py")
    assert not _is_scoped_module("scripts/platformkit/tracking/test_pod_drift_scope.py")
    assert _is_scoped_module("domains/tennis/tracking/adapter.py")


def test_all_three_copies_of_the_scope_agree() -> None:
    """SCOPE_GLOBS, HARNESS_DEPENDENCIES and pod_command must list the same set.

    The scope was written in three places. _is_scoped_module guarded the master
    side, SCOPE_GLOBS fed `git ls-files`, and pod_command() carried its own
    hardcoded `find`. Updating one left the checker reporting no drift while
    metric_local_profile.py genuinely differed between pod and master -- the same
    duplicated-fact bug as the SSH port that drifted unnoticed for a day.
    """
    from scripts.platformkit.tracking.pod_drift import (
        HARNESS_DEPENDENCIES,
        SCOPE_GLOBS,
        pod_command,
    )

    command = pod_command()
    for name in HARNESS_DEPENDENCIES:
        assert "scripts/platformkit/" + name in SCOPE_GLOBS, (
            "%s is not in SCOPE_GLOBS, so git ls-files will not offer it" % name)
        assert "-name '%s'" % name in command, (
            "%s is not in the pod find, so it can only ever read as POD-ONLY" % name)
