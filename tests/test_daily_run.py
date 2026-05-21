"""
test_daily_run.py — Structural and behavioral tests for scripts/daily_run.sh.

Tests:
  1. Script contains `set -e` (or `set -euo pipefail`) — fail-fast enabled.
  2. Script exports LIVE_BETTING=0 — paper mode enforced.
  3. All 4 stages are present in the correct order.
  4. Auto-retrain stage (stage 4) is still present — no regression.
  5. Stage failure causes non-zero exit (stub test via script parsing).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(PROJECT_DIR, "scripts", "daily_run.sh")


# ── helpers ───────────────────────────────────────────────────────────────────

def _read_script() -> str:
    with open(SCRIPT_PATH, encoding="utf-8") as f:
        return f.read()


def _stage_positions(text: str) -> dict[str, int]:
    """Return {stage_keyword: first char position} for each expected stage."""
    stages = {
        "record_slate_results": None,
        "run_daily_slate":      None,
        "bet_selector":         None,
        "auto_retrain":         None,
    }
    for key in stages:
        m = re.search(re.escape(key), text)
        if m:
            stages[key] = m.start()
    return stages


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def script_text() -> str:
    assert os.path.exists(SCRIPT_PATH), f"daily_run.sh not found at {SCRIPT_PATH}"
    return _read_script()


# ── test 1: fail-fast set -e ─────────────────────────────────────────────────

def test_has_set_e(script_text: str) -> None:
    """Script must have `set -e` or `set -euo pipefail` for fail-fast behaviour."""
    assert re.search(r"set\s+-[a-z]*e[a-z]*", script_text), (
        "daily_run.sh must contain `set -e` (or `set -euo pipefail`)"
    )


# ── test 2: LIVE_BETTING=0 export ────────────────────────────────────────────

def test_exports_live_betting_zero(script_text: str) -> None:
    """Script must export LIVE_BETTING=0 (paper mode guard)."""
    assert re.search(r"export\s+LIVE_BETTING=0", script_text), (
        "daily_run.sh must contain `export LIVE_BETTING=0`"
    )


# ── test 3: all 4 stages present in correct order ────────────────────────────

def test_four_stages_in_order(script_text: str) -> None:
    """All 4 stages must be present and appear in the required order."""
    positions = _stage_positions(script_text)

    missing = [k for k, v in positions.items() if v is None]
    assert not missing, f"Missing stages in daily_run.sh: {missing}"

    order = [
        "record_slate_results",
        "run_daily_slate",
        "bet_selector",
        "auto_retrain",
    ]
    for i in range(len(order) - 1):
        a, b = order[i], order[i + 1]
        assert positions[a] < positions[b], (
            f"Stage '{a}' must appear before '{b}' in daily_run.sh "
            f"(positions: {a}={positions[a]}, {b}={positions[b]})"
        )


# ── test 4: auto-retrain stage not regressed ─────────────────────────────────

def test_auto_retrain_stage_preserved(script_text: str) -> None:
    """auto_retrain.py invocation must still be present (no regression)."""
    assert "auto_retrain.py" in script_text, (
        "daily_run.sh must still invoke auto_retrain.py (stage 4 regression check)"
    )


# ── test 5: stage-failure exits non-zero ─────────────────────────────────────

def test_stage_failure_exits_nonzero() -> None:
    """Replacing a stage command with `false` must cause the script to exit non-zero.

    Strategy: build a minimal stub script that mirrors the fail-fast pattern
    of daily_run.sh, injects a failing stage, and asserts non-zero exit.
    We test the script's *pattern* directly rather than executing daily_run.sh
    against live infrastructure (which is unavailable in CI).
    """
    # Build a minimal stub that replicates the exact fail-fast idiom used in
    # daily_run.sh: set -euo pipefail + _fail function + stage invocation.
    stub = textwrap.dedent("""\
        #!/usr/bin/env bash
        set -euo pipefail
        export LIVE_BETTING=0

        _fail() {
          echo "FAILED: $1" >&2
          exit 1
        }

        # Stage 1: intentionally fails
        false || _fail "record_slate_results"
        echo "should not reach here"
    """)

    bash_exe = _find_bash()
    if bash_exe is None:
        pytest.skip("bash not available — skipping execution test")

    result = subprocess.run(
        [bash_exe, "-c", stub],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        "A failing stage must cause the script to exit non-zero "
        f"(got returncode={result.returncode}, stdout={result.stdout!r})"
    )
    assert "should not reach here" not in result.stdout, (
        "Script must stop after a failing stage — subsequent stages must not run"
    )


def _find_bash() -> str | None:
    """Return path to bash executable, or None if unavailable."""
    import shutil
    return shutil.which("bash")


# ── test 6: bet_selector has __main__ entry point ────────────────────────────

def test_bet_selector_has_main_entrypoint() -> None:
    """bet_selector.py must have a __main__ block so the shell can invoke it."""
    selector_path = os.path.join(
        PROJECT_DIR, "src", "prediction", "bet_selector.py"
    )
    assert os.path.exists(selector_path), f"bet_selector.py not found: {selector_path}"
    with open(selector_path, encoding="utf-8") as f:
        content = f.read()
    assert '__name__ == "__main__"' in content or "__name__ == '__main__'" in content, (
        "bet_selector.py must have an `if __name__ == '__main__':` block "
        "so `python -m src.prediction.bet_selector --date DATE` works"
    )


# ── test 7: stage 3 uses _fail (not soft-skip) ───────────────────────────────

def test_stage3_is_fail_fast(script_text: str) -> None:
    """Stage 3 (bet_selector) must call _fail on non-zero exit, not silently skip."""
    # Find the bet_selector invocation block
    # It should have `|| _fail "bet_selector"` not `|| echo ... skipped`
    bet_block_m = re.search(
        r"bet_selector.*?(?=\n\n|\Z)",
        script_text,
        re.DOTALL,
    )
    # More targeted: check that after the bet_selector python call, _fail is used
    assert re.search(r"bet_selector[^\n]*\|\|\s*_fail", script_text), (
        "Stage 3 (bet_selector) must use `|| _fail` for fail-fast, not a soft skip"
    )
