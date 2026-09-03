"""S60: every scripts/**/_*.py that a TRACKED module imports must itself be tracked.

`.gitignore:342` (`scripts/**/_*`) exists to keep scratch throwaways out of git.
When a real module hides behind that rule, a fresh clone -- and the pod's
`git archive` deploy -- imports nothing. This is the regression guard: it fails
if a new private helper becomes an import target while staying untracked.

MEASUREMENT-ONLY. No threshold, no score, no ledger write.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from scripts.platformkit.eval_gate import worktree_marker

ROOT = Path(__file__).resolve().parents[3]


def _git(*args: str) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.splitlines()


def _untracked_helpers() -> dict[str, list[str]]:
    """module stem -> untracked scripts/**/_<stem>.py paths."""
    tracked = set(_git("ls-files", "*.py"))
    by_stem: dict[str, list[str]] = {}
    for p in (ROOT / "scripts").rglob("_*.py"):
        if "__pycache__" in p.parts or p.name == "__init__.py":
            continue
        rel = p.relative_to(ROOT).as_posix()
        if rel in tracked:
            continue
        by_stem.setdefault(p.stem, []).append(rel)
    return by_stem


def _importers(stems: list[str]) -> list[str]:
    args = ["grep", "-n", "-F"]
    for s in stems:
        args += ["-e", s]
    return _git(*args, "--", "*.py")


def test_private_helpers_imported_by_tracked_modules_are_tracked() -> None:
    by_stem = _untracked_helpers()
    if not by_stem:
        helper_glob = ROOT / "scripts" / "**" / "_*.py"
        if worktree_marker.is_worktree_checkout():
            pytest.skip("worktree checkout: untracked private-helper precondition absent: %s" % helper_glob)
        pytest.fail("main-repo checkout: untracked private-helper precondition absent: %s" % helper_glob)

    offenders: list[str] = []
    for hit in _importers(sorted(by_stem)):
        # git grep output: <path>:<lineno>:<line>
        parts = hit.split(":", 2)
        if len(parts) != 3:
            continue
        importer, lineno, line = parts
        stmt = line.strip()
        if not (stmt.startswith("from ") or stmt.startswith("import ")):
            continue
        imp_dir = Path(importer).parent.as_posix()
        for stem, cands in by_stem.items():
            if not re.search(r"\b" + re.escape(stem) + r"\b", stmt):
                continue
            for cand in cands:
                dotted = cand[:-3].replace("/", ".")
                same_dir = Path(cand).parent.as_posix() == imp_dir
                absolute = dotted in stmt
                relative = same_dir and re.search(
                    r"(from\s+\.*|^import\s+)" + re.escape(stem) + r"\b", stmt
                )
                if absolute or relative:
                    offenders.append(f"{cand} <- {importer}:{lineno}: {stmt}")

    assert not offenders, (
        "untracked private helper(s) imported by tracked module(s); add an "
        "explicit `!<path>` negation under .gitignore:342 and `git add` them:\n  "
        + "\n  ".join(sorted(set(offenders)))
    )
