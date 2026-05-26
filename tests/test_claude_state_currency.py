"""tests/test_claude_state_currency.py — R22_O3.

Currency gate for `docs/CLAUDE-state.md`. The doc is the central state
reference loaded on demand by Claude sessions. If it drifts behind the
master commit it stops being useful, so this test fails loudly when the
doc no longer mentions the current HEAD commit prefix.

The doc is a local-only artifact (gitignored on fresh clones); when
absent (e.g. CI fresh clone), the test is skipped rather than failed.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = REPO_ROOT / "docs" / "CLAUDE-state.md"


def _git_rev_short(rev: str) -> str:
    """Return the 8-char prefix of the given rev; raise if git unavailable."""
    out = subprocess.run(
        ["git", "rev-parse", rev],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()[:8]


def test_claude_state_mentions_current_master_commit() -> None:
    """`docs/CLAUDE-state.md` must reference the HEAD commit prefix.

    Because the doc is necessarily written BEFORE the commit that lands it,
    the doc records the *prior* HEAD at write time. To stay green across
    the commit boundary, we accept either HEAD or HEAD~1 (the snapshot the
    doc was refreshed against). Any older mismatch means the doc drifted.
    """
    if not DOC_PATH.exists():
        pytest.skip("docs/CLAUDE-state.md is local-only and not present in this checkout")

    try:
        head_short = _git_rev_short("HEAD")
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("git not available; cannot verify currency")

    try:
        parent_short = _git_rev_short("HEAD~1")
    except (subprocess.CalledProcessError, FileNotFoundError):
        parent_short = ""

    text = DOC_PATH.read_text(encoding="utf-8", errors="replace")
    acceptable = [s for s in (head_short, parent_short) if s]
    assert any(s in text for s in acceptable), (
        f"docs/CLAUDE-state.md does not mention HEAD ({head_short}) "
        f"or HEAD~1 ({parent_short}); refresh it (R22_O3 pattern)."
    )
