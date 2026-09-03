"""S153 -- tell a git worktree checkout apart from the main repo.

The private evidence trees (data/cache/eval_gate/, the 18-row FWER charge ledger)
are NEVER junctioned into a codex worktree, so a test that needs them must SKIP
there. In the main repo the same absence is missing evidence and must FAIL.

Marker: a worktree's `.git` is a FILE (a `gitdir:` pointer); the main repo's is a
DIRECTORY. FOUNDRY_WORKTREE=1 is the explicit override for a runner that copies
rather than links its checkout.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def is_worktree_checkout(root: Path | None = None) -> bool:
    """True iff this checkout is a git worktree (or FOUNDRY_WORKTREE=1 is set)."""
    if os.environ.get("FOUNDRY_WORKTREE") == "1":
        return True
    return (REPO_ROOT if root is None else Path(root)).joinpath(".git").is_file()


if __name__ == "__main__":     # ponytail: self-check, no framework
    assert is_worktree_checkout(REPO_ROOT) is False, "main repo .git must be a directory"
    os.environ["FOUNDRY_WORKTREE"] = "1"
    assert is_worktree_checkout(REPO_ROOT) is True, "env override must force worktree mode"
    print("worktree_marker self-check OK")
