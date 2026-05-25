"""Smoke tests for the live operator runbook + wrapper scripts."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RUNBOOK = REPO / "docs" / "LIVE_OPERATOR_RUNBOOK.md"
MORNING = REPO / "scripts" / "operator_morning.sh"
EOD = REPO / "scripts" / "operator_settle_eod.sh"


def _bash() -> str | None:
    return shutil.which("bash")


def _run_sh(path: Path, *args: str) -> subprocess.CompletedProcess:
    bash = _bash()
    if bash is None:
        pytest.skip("bash not available on this host")
    return subprocess.run(
        [bash, str(path), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        timeout=30,
    )


def test_operator_morning_dry_run_exits_clean():
    res = _run_sh(MORNING, "2026-10-22", "--dry-run")
    assert res.returncode == 0, res.stderr
    assert "predict_slate.py" in res.stdout
    assert "compare_to_lines.py" in res.stdout


def test_operator_settle_eod_dry_run_exits_clean():
    res = _run_sh(EOD, "2026-10-22", "--dry-run")
    assert res.returncode == 0, res.stderr
    assert "settle_bet.py" in res.stdout
    assert "pnl_report.py" in res.stdout
    assert "clv_report.py" in res.stdout


def _wrapper_scripts() -> list[str]:
    refs: set[str] = set()
    for sh in (MORNING, EOD):
        for m in re.finditer(r"scripts/([A-Za-z0-9_./-]+\.py)", sh.read_text(encoding="utf-8")):
            refs.add(m.group(1))
    return sorted(refs)


def test_wrapper_scripts_reference_existing_files():
    missing = [s for s in _wrapper_scripts() if not (REPO / "scripts" / s).exists()]
    assert not missing, f"wrapper scripts reference missing files: {missing}"


def test_runbook_script_references_exist():
    text = RUNBOOK.read_text(encoding="utf-8")
    refs = sorted(set(re.findall(r"scripts/([A-Za-z0-9_./-]+\.py)", text)))
    assert refs, "runbook should reference scripts/*.py"
    missing = [s for s in refs if not (REPO / "scripts" / s).exists()]
    assert not missing, f"runbook references missing scripts: {missing}"
