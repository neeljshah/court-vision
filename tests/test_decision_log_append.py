"""Tests for vault/Sessions/Decision Log.md append behaviour.

Verifies that vault_session_close.update_decision_log():
  - appends a NEW row for each distinct commit SHA (N tasks → N lines)
  - never replaces or overwrites prior rows
  - is idempotent for the same SHA (re-running adds no duplicate)
  - creates the file with a proper header when it does not exist
"""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_module(tmp_path: Path) -> types.ModuleType:
    """Import vault_session_close with VAULT redirected to tmp_path/vault."""
    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    spec = importlib.util.spec_from_file_location(
        "vault_session_close",
        scripts_dir / "vault_session_close.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    # Override module-level constants BEFORE exec_module runs the body.
    # We patch them after loading because the file assigns them at top-level.
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    # Redirect the DECISION_LOG path to a temp directory.
    mod.DECISION_LOG = tmp_path / "vault" / "Sessions" / "Decision Log.md"
    mod.TODAY = "2026-05-21"
    return mod


def _call_update(mod: types.ModuleType, sha: str, commit_msg: str) -> None:
    """Call update_decision_log() with mocked git output."""
    with (
        patch.object(mod, "_run", side_effect=lambda cmd: _fake_run(cmd, sha, commit_msg)),
        patch.object(mod, "_detect_metric_changes", return_value="no metric changes detected"),
        patch.object(mod, "_detect_affected_domains", return_value=[]),
    ):
        mod.update_decision_log()


def _fake_run(cmd: str, sha: str, commit_msg: str) -> str:
    if "log --oneline" in cmd:
        return f"{sha[:7]} {commit_msg}"
    if "rev-parse --short" in cmd:
        # Return the full SHA so dedup anchors are distinct across test calls.
        return sha
    return ""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDecisionLogAppend:
    def test_creates_file_on_first_call(self, tmp_path: Path) -> None:
        """File is created with header and one row when it does not exist."""
        mod = _load_module(tmp_path)
        _call_update(mod, "abc1234", "feat: initial scaffold")

        log = mod.DECISION_LOG
        assert log.exists(), "Decision Log.md should be created"
        content = log.read_text(encoding="utf-8")
        assert "| Date | Key Decision / Fix | Impact |" in content
        assert "feat: initial scaffold" in content
        assert "abc1234" in content  # SHA anchor present

    def test_two_different_tasks_produce_two_rows(self, tmp_path: Path) -> None:
        """N sequential tasks on the same day produce N distinct rows."""
        mod = _load_module(tmp_path)

        _call_update(mod, "aaa0001", "fix: ball detection threshold")
        _call_update(mod, "bbb0002", "feat: re-ID OSNet upgrade")

        content = mod.DECISION_LOG.read_text(encoding="utf-8")

        # Both summaries must appear.
        assert "fix: ball detection threshold" in content
        assert "feat: re-ID OSNet upgrade" in content

        # Count table data rows (lines starting with '| 2026').
        data_rows = [
            ln for ln in content.splitlines()
            if ln.startswith("| 2026")
        ]
        assert len(data_rows) == 2, (
            f"Expected 2 data rows, got {len(data_rows)}:\n{content}"
        )

    def test_pre_existing_rows_are_preserved(self, tmp_path: Path) -> None:
        """Prior rows from earlier sessions/tasks survive subsequent writes."""
        mod = _load_module(tmp_path)

        _call_update(mod, "aaa0001", "chore: setup CI")
        _call_update(mod, "bbb0002", "fix: homography drift")
        _call_update(mod, "ccc0003", "feat: shot clock")

        content = mod.DECISION_LOG.read_text(encoding="utf-8")

        for summary in ("chore: setup CI", "fix: homography drift", "feat: shot clock"):
            assert summary in content, f"Missing row for: {summary}"

        data_rows = [ln for ln in content.splitlines() if ln.startswith("| 2026")]
        assert len(data_rows) == 3

    def test_same_sha_is_idempotent(self, tmp_path: Path) -> None:
        """Re-running with the identical commit SHA does NOT add a duplicate row."""
        mod = _load_module(tmp_path)

        _call_update(mod, "dup0001", "fix: duplicate guard test")
        _call_update(mod, "dup0001", "fix: duplicate guard test")  # identical SHA

        content = mod.DECISION_LOG.read_text(encoding="utf-8")
        data_rows = [ln for ln in content.splitlines() if ln.startswith("| 2026")]
        assert len(data_rows) == 1, (
            f"Expected 1 row after duplicate run, got {len(data_rows)}:\n{content}"
        )

    def test_fourteen_tasks_produce_fourteen_rows(self, tmp_path: Path) -> None:
        """Regression: 14 bot tasks in one day → 14 distinct table rows."""
        mod = _load_module(tmp_path)

        # Use fully distinct 40-char SHA-like strings.
        shas = [f"{i:040x}" for i in range(14)]
        for i, sha in enumerate(shas):
            _call_update(mod, sha, f"task #{i}: some improvement")

        content = mod.DECISION_LOG.read_text(encoding="utf-8")
        data_rows = [ln for ln in content.splitlines() if ln.startswith("| 2026")]
        assert len(data_rows) == 14, (
            f"Expected 14 rows, got {len(data_rows)}:\n{content}"
        )
