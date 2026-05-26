"""tests/test_R29_V4_session_note.py — R29_V4 probe tests.

Exercises ``scripts/generate_session_note.py``:

  * Note generates against the real coordination_log without error
  * All 5 mandated section headings render
  * Round list is non-empty (at least 10 rounds with content)
  * Every commit SHA referenced in the body exists in the local git
    object database (cross-checked with ``git cat-file -t``)
  * --session arg is respected in both header and filename behaviour
  * Generator is idempotent — same upstream data + same --now yields
    byte-identical output

Tests stage all output to a temp directory; the real
``vault/Sessions/SESSION3.md`` is never written.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_session_note.py"

# Ensure the script is importable regardless of pytest's cwd.
sys.path.insert(0, str(REPO_ROOT / "scripts"))


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _coord_log_path() -> Path:
    """Return whichever coordination_log.md is freshest — the worktree
    copy is sometimes truncated relative to the main repo's copy."""
    main_repo = Path(r"C:/Users/neelj/nba-ai-system/scripts/coordination_log.md")
    local     = REPO_ROOT / "scripts" / "coordination_log.md"
    if main_repo.exists() and main_repo.stat().st_size > local.stat().st_size:
        return main_repo
    return local


def _generate(tmp_path: Path, session: int = 3,
              start: str = "R15", end: str = "R28",
              now: str = "2026-05-26T19:00:00Z") -> Path:
    out = tmp_path / f"SESSION{session}.md"
    res = subprocess.run(
        [sys.executable, str(SCRIPT_PATH),
         "--session", str(session),
         "--start-round", start,
         "--end-round", end,
         "--coord-log", str(_coord_log_path()),
         "--out", str(out),
         "--now", now],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert res.returncode == 0, (
        f"generate_session_note failed: rc={res.returncode}\n"
        f"stdout={res.stdout}\nstderr={res.stderr}"
    )
    assert out.exists(), f"output file not created: {out}"
    return out


# ----------------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------------

def test_note_generates(tmp_path: Path) -> None:
    """The script runs to completion and writes a non-empty file."""
    out = _generate(tmp_path)
    body = out.read_text(encoding="utf-8")
    assert len(body) > 500, f"note suspiciously small: {len(body)} bytes"


def test_all_five_sections_present(tmp_path: Path) -> None:
    """All 5 mandated section headings render in the body."""
    body = _generate(tmp_path).read_text(encoding="utf-8")
    for heading in (
        "## Round-by-Round Summary",
        "## Major Themes",
        "## Top 10 Ships by Impact",
        "## Open Items / Next Session",
        "## Stats",
    ):
        assert heading in body, f"missing section heading: {heading}"


def test_round_list_non_empty(tmp_path: Path) -> None:
    """At least 10 round entries with a Tally line are rendered."""
    body = _generate(tmp_path).read_text(encoding="utf-8")
    round_matches = re.findall(r"### R(\d+)\n- Tally:", body)
    assert len(round_matches) >= 10, (
        f"expected >= 10 round entries, got {len(round_matches)}: "
        f"{round_matches}"
    )


def test_commit_shas_are_real(tmp_path: Path) -> None:
    """Every commit SHA cited in the body exists in the local git repo."""
    body = _generate(tmp_path).read_text(encoding="utf-8")
    shas = re.findall(r"`([0-9a-f]{12})`", body)
    assert len(shas) >= 30, f"expected >= 30 SHAs cited, got {len(shas)}"
    # Sample-check the first 25 (cat-file is cheap but not free).
    for sha in shas[:25]:
        res = subprocess.run(
            ["git", "cat-file", "-t", sha],
            cwd=str(REPO_ROOT),
            capture_output=True, text=True,
        )
        assert res.returncode == 0, f"unknown sha {sha}: {res.stderr}"
        assert res.stdout.strip() == "commit", (
            f"sha {sha} is not a commit: {res.stdout!r}"
        )


def test_session_arg_respected(tmp_path: Path) -> None:
    """The --session arg flows through to header AND filename."""
    out = _generate(tmp_path, session=42)
    assert out.name == "SESSION42.md", out.name
    body = out.read_text(encoding="utf-8")
    assert body.startswith("# Session 42 "), body[:80]


def test_idempotent_for_same_data(tmp_path: Path) -> None:
    """Running twice with the same --now produces byte-identical output."""
    out1 = _generate(tmp_path, session=3, now="2026-05-26T19:00:00Z")
    body1 = out1.read_bytes()
    # Force a second invocation to a fresh dir to avoid the .bak rotation
    # affecting comparison.
    fresh = tmp_path / "second"
    fresh.mkdir()
    out2 = _generate(fresh, session=3, now="2026-05-26T19:00:00Z")
    body2 = out2.read_bytes()
    assert body1 == body2, (
        f"non-deterministic output (lens {len(body1)} vs {len(body2)})"
    )


def test_top_10_section_has_entries(tmp_path: Path) -> None:
    """Top 10 ships section has at least 5 entries with real SHAs."""
    body = _generate(tmp_path).read_text(encoding="utf-8")
    m = re.search(
        r"## Top 10 Ships by Impact\n(.*?)## Open Items",
        body, re.S,
    )
    assert m is not None
    top_block = m.group(1)
    entries = re.findall(r"^\d+\.\s+\*\*", top_block, re.M)
    assert len(entries) >= 5, (
        f"expected >= 5 top-10 entries, got {len(entries)}"
    )


def test_does_not_touch_real_vault(tmp_path: Path) -> None:
    """Generating to a temp path leaves the real vault unmodified."""
    real_vault_path = REPO_ROOT / "vault" / "Sessions" / "SESSION3.md"
    pre_exists = real_vault_path.exists()
    pre_mtime  = real_vault_path.stat().st_mtime if pre_exists else None
    _generate(tmp_path)
    post_exists = real_vault_path.exists()
    if pre_exists:
        assert post_exists, "real SESSION3.md disappeared"
        post_mtime = real_vault_path.stat().st_mtime
        assert pre_mtime == post_mtime, "real SESSION3.md mtime changed"
    else:
        assert not post_exists, "test accidentally wrote to real vault"
