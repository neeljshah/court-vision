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


def _git_head_short() -> str:
    """Return the 8-char prefix of HEAD; raise if git unavailable."""
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()[:8]


def test_claude_state_mentions_current_master_commit() -> None:
    """`docs/CLAUDE-state.md` must reference the current HEAD commit prefix."""
    if not DOC_PATH.exists():
        pytest.skip("docs/CLAUDE-state.md is local-only and not present in this checkout")

    try:
        head_short = _git_head_short()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("git not available; cannot verify currency")

    text = DOC_PATH.read_text(encoding="utf-8", errors="replace")
    assert head_short in text, (
        f"docs/CLAUDE-state.md does not mention HEAD {head_short}; "
        "refresh it (R22_O3 pattern) so future sessions inherit the right context."
    )
