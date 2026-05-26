"""Tests for scripts/e2e_smoke_test.py — R27_T5.

Validates the 12-stage end-to-end smoke harness:

1. produces a result file at the canonical data/cache path
2. reports all 12 stages
3. total runtime is under the 5-min cap (and typically way under)
4. exit code matches failure status (0 iff no FAIL/TIMEOUT)
5. sandbox tmp dirs are cleaned up after each run
6. rerun is idempotent on the same data (same per-stage status distribution)

All tests are safe in any environment — the smoke harness itself uses
sandboxed paths and never touches data/pnl_ledger.csv.
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))
SCRIPTS_DIR = PROJECT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import e2e_smoke_test as smoke  # noqa: E402


# --------------------------------------------------------------------------- #
# Helper — run once + return the summary
# --------------------------------------------------------------------------- #
def _run_once(json_out: str = None) -> dict:
    return smoke.run_smoke(json_out=json_out, quiet=True)


# --------------------------------------------------------------------------- #
# Test 1 — smoke test produces a result file
# --------------------------------------------------------------------------- #
def test_smoke_writes_result_file(tmp_path):
    out_path = str(tmp_path / "smoke_out.json")
    summary = _run_once(json_out=out_path)
    assert os.path.exists(out_path), (
        f"smoke harness did not write json_out to {out_path}"
    )
    with open(out_path, encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload["task"].startswith("R27_T5"), (
        f"unexpected task name: {payload.get('task')!r}"
    )
    assert payload["n_stages"] == 12

    # Also the canonical data/cache/e2e_smoke_<date>.json should exist.
    canonical = summary.get("results_path")
    assert canonical and os.path.exists(canonical), (
        f"canonical results path missing: {canonical}"
    )


# --------------------------------------------------------------------------- #
# Test 2 — all 12 stages are reported
# --------------------------------------------------------------------------- #
def test_all_twelve_stages_reported():
    summary = _run_once()
    names = [s["name"] for s in summary["stages"]]
    assert len(names) == 12, f"expected 12 stages, got {len(names)}: {names}"
    expected = set(smoke.STAGES_ORDER)
    got = set(names)
    assert got == expected, (
        f"stage name mismatch:\n  expected={sorted(expected)}\n  got={sorted(got)}"
    )
    # Every stage row must have status, runtime_sec, name.
    for s in summary["stages"]:
        assert "status" in s and "runtime_sec" in s and "name" in s, (
            f"stage row missing fields: {s}"
        )
        assert s["status"] in ("PASS", "FAIL", "SKIP", "TIMEOUT"), (
            f"{s['name']}: bad status {s['status']!r}"
        )


# --------------------------------------------------------------------------- #
# Test 3 — runtime under cap (overall AND per-stage)
# --------------------------------------------------------------------------- #
def test_runtime_under_cap():
    summary = _run_once()
    assert summary["runtime_sec"] < smoke.OVERALL_TIMEOUT_SEC, (
        f"runtime {summary['runtime_sec']}s exceeds overall cap "
        f"{smoke.OVERALL_TIMEOUT_SEC}s"
    )
    # Practically: on a healthy local checkout this should be << 60s.
    assert summary["runtime_sec"] < 60.0, (
        f"runtime {summary['runtime_sec']}s suspiciously high"
    )
    # No stage should have blown the per-stage cap.
    for s in summary["stages"]:
        if s["status"] == "PASS":
            assert s["runtime_sec"] <= smoke.STAGE_TIMEOUT_SEC, (
                f"{s['name']} PASS but ran {s['runtime_sec']}s > {smoke.STAGE_TIMEOUT_SEC}s"
            )


# --------------------------------------------------------------------------- #
# Test 4 — exit code matches failure status
# --------------------------------------------------------------------------- #
def test_exit_code_matches_failure_status(tmp_path):
    # Invoke the CLI as a subprocess and assert exit code.
    out_path = str(tmp_path / "cli_out.json")
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "e2e_smoke_test.py"),
         "--json-out", out_path, "--quiet"],
        cwd=str(PROJECT_DIR), capture_output=True, text=True, timeout=300,
    )
    assert os.path.exists(out_path), (
        f"CLI did not produce {out_path}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    with open(out_path, encoding="utf-8") as fh:
        payload = json.load(fh)
    expected_rc = 0 if payload["ok"] else 1
    assert proc.returncode == expected_rc, (
        f"exit code {proc.returncode} != expected {expected_rc} "
        f"(ok={payload['ok']}, status={payload['status']}, "
        f"n_failed={payload['n_failed']}, n_timeout={payload['n_timeout']})"
    )


# --------------------------------------------------------------------------- #
# Test 5 — sandbox tmp dirs are cleaned up
# --------------------------------------------------------------------------- #
def test_sandbox_dirs_cleaned_up():
    # Take snapshot of /tmp BEFORE.
    tmp_root = Path(tempfile.gettempdir())
    before = {p.name for p in tmp_root.iterdir() if p.is_dir() and p.name.startswith("r27_t5_smoke_")}
    summary = _run_once()
    after = {p.name for p in tmp_root.iterdir() if p.is_dir() and p.name.startswith("r27_t5_smoke_")}
    new_dirs = after - before
    # All sandbox dirs created during the run must have been removed.
    assert not new_dirs, (
        f"smoke harness leaked sandbox dirs: {sorted(new_dirs)}"
    )
    assert summary["sandbox_cleaned"] is True


# --------------------------------------------------------------------------- #
# Test 6 — rerun is idempotent (same status distribution on same data)
# --------------------------------------------------------------------------- #
def test_idempotent_rerun():
    a = _run_once()
    b = _run_once()
    # Same set of stages reported.
    names_a = [s["name"] for s in a["stages"]]
    names_b = [s["name"] for s in b["stages"]]
    assert names_a == names_b, (
        f"stage order changed between runs:\n  a={names_a}\n  b={names_b}"
    )
    # Per-stage status must match (data didn't change between calls).
    a_map = {s["name"]: s["status"] for s in a["stages"]}
    b_map = {s["name"]: s["status"] for s in b["stages"]}
    for name in names_a:
        assert a_map[name] == b_map[name], (
            f"{name}: run-1 status {a_map[name]} != run-2 status {b_map[name]}"
        )
    # And overall pass/fail outcome matches.
    assert a["ok"] == b["ok"], (
        f"overall ok flag flipped between runs: a={a['ok']} b={b['ok']}"
    )


# --------------------------------------------------------------------------- #
# Test 7 — REFUSE to touch the production pnl_ledger
# --------------------------------------------------------------------------- #
def test_never_touches_production_ledger():
    """The smoke harness must NEVER write to data/pnl_ledger.csv."""
    prod = PROJECT_DIR / "data" / "pnl_ledger.csv"
    prod_size_before = prod.stat().st_size if prod.exists() else -1
    _run_once()
    prod_size_after = prod.stat().st_size if prod.exists() else -1
    assert prod_size_before == prod_size_after, (
        f"production ledger changed size during smoke run: "
        f"{prod_size_before} -> {prod_size_after}"
    )


# --------------------------------------------------------------------------- #
# Test 8 — ship gate: >= 8 stages must PASS on local data
# --------------------------------------------------------------------------- #
def test_ship_gate_min_passes():
    summary = _run_once()
    assert summary["n_passed"] >= summary["ship_gate_min_passes"], (
        f"ship gate: only {summary['n_passed']} PASS, "
        f"need >= {summary['ship_gate_min_passes']}. "
        f"Failed: {summary['failed_stage_names']}"
    )
