"""
Tests for vps_setup.sh and vps_deploy.sh.

Cases:
  1. test_dry_run_prints_commands      — exit 0 and stdout contains "[dry-run]"
  2. test_dry_run_contains_cron_entry  — stdout contains the cron schedule "13 * * *"
  3. test_dry_run_contains_conda_init  — stdout contains "miniconda" or "conda"
  4. test_deploy_script_is_executable  — vps_deploy.sh passes bash -n syntax check
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# Resolve script paths relative to the repo root (two levels up from tests/)
REPO_ROOT = Path(__file__).resolve().parent.parent
VPS_SETUP = REPO_ROOT / "scripts" / "vps_setup.sh"
VPS_DEPLOY = REPO_ROOT / "scripts" / "vps_deploy.sh"


def _run_dry(script: Path, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    """Run a bash script with --dry-run; capture stdout+stderr."""
    cmd = ["bash", str(script)] + (extra_args or [])
    return subprocess.run(cmd, capture_output=True, text=True)


# ─────────────────────────────────────────────────────────────────
# Case 1 — dry-run exits 0 and prints [dry-run] markers
# ─────────────────────────────────────────────────────────────────

def test_dry_run_prints_commands():
    """bash scripts/vps_setup.sh --dry-run exits 0 and emits [dry-run] lines."""
    result = _run_dry(VPS_SETUP, ["--dry-run"])
    assert result.returncode == 0, f"Non-zero exit: {result.stderr}"
    assert "[dry-run]" in result.stdout, "Expected [dry-run] markers in stdout"


# ─────────────────────────────────────────────────────────────────
# Case 2 — cron schedule is present in dry-run output
# ─────────────────────────────────────────────────────────────────

def test_dry_run_contains_cron_entry():
    """Dry-run output includes the 13:00 UTC cron schedule."""
    result = _run_dry(VPS_SETUP, ["--dry-run"])
    assert result.returncode == 0, f"Non-zero exit: {result.stderr}"
    assert "13 * * *" in result.stdout, (
        "Expected cron schedule '13 * * *' in stdout; got:\n" + result.stdout
    )


# ─────────────────────────────────────────────────────────────────
# Case 3 — conda/miniconda reference is present in dry-run output
# ─────────────────────────────────────────────────────────────────

def test_dry_run_contains_conda_init():
    """Dry-run output references miniconda or conda setup."""
    result = _run_dry(VPS_SETUP, ["--dry-run"])
    assert result.returncode == 0, f"Non-zero exit: {result.stderr}"
    output_lower = result.stdout.lower()
    assert "miniconda" in output_lower or "conda" in output_lower, (
        "Expected 'miniconda' or 'conda' in stdout; got:\n" + result.stdout
    )


# ─────────────────────────────────────────────────────────────────
# Case 4 — vps_deploy.sh is syntactically valid bash
# ─────────────────────────────────────────────────────────────────

def test_deploy_script_is_executable():
    """vps_deploy.sh passes bash -n syntax check (no execution needed)."""
    result = subprocess.run(
        ["bash", "-n", str(VPS_DEPLOY)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"bash -n syntax check failed for vps_deploy.sh:\n{result.stderr}"
    )
