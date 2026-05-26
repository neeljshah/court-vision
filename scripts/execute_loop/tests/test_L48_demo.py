"""test_L48_demo.py — Tests for L48_demo_runner.py.

Run:
    conda run -n basketball_ai python -m pytest scripts/execute_loop/tests/test_L48_demo.py -v
"""
from __future__ import annotations

import os
import sys
import types
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Project root on sys.path + mandatory stubs BEFORE any execute_loop import
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_DIR))

# Stub src.data.nba_api_headers_patch (required transitively by L01/L02)
_api_stub = types.ModuleType("src.data.nba_api_headers_patch")
sys.modules.setdefault("src.data.nba_api_headers_patch", _api_stub)
_src_stub = types.ModuleType("src")
_src_data_stub = types.ModuleType("src.data")
sys.modules.setdefault("src", _src_stub)
sys.modules.setdefault("src.data", _src_data_stub)

# Stub requests so no HTTP is attempted
_req_stub = types.ModuleType("requests")
_req_stub.get = MagicMock(return_value=MagicMock(status_code=404, json=lambda: {}))
_req_stub.post = MagicMock(return_value=MagicMock(status_code=404, json=lambda: {}))
_req_stub.delete = MagicMock(return_value=MagicMock(status_code=404))
_req_stub.Timeout = TimeoutError
_req_stub.RequestException = Exception
sys.modules["requests"] = _req_stub

# Now import the module under test
import scripts.execute_loop.L48_demo_runner as L48  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_live_mode_env(monkeypatch):
    """Ensure SUBMISSION_MODE is unset (paper mode) for every test."""
    monkeypatch.delenv("SUBMISSION_MODE", raising=False)
    for var in [
        "KALSHI_LIVE_ENABLED", "POLYMARKET_LIVE_ENABLED",
        "SPORTTRADE_LIVE_ENABLED", "PROPHET_LIVE_ENABLED",
        "WITHDRAWAL_LIVE_ENABLED", "DK_LIVE_SUBMISSION_ENABLED",
        "FD_LIVE_SUBMISSION_ENABLED",
    ]:
        monkeypatch.delenv(var, raising=False)
    yield


# ---------------------------------------------------------------------------
# Test 1: all 10 stages complete
# ---------------------------------------------------------------------------

def test_demo_runner_completes_all_10_stages():
    runner = L48.DemoRunner(seed=42)
    report = runner.run()
    assert report.paper_mode_verified is True
    assert len(report.stages) == 10
    stage_names = [s.name for s in report.stages]
    expected = [
        "Slate Ingest",
        "FPTS Distribution",
        "Lineup Optimization",
        "Cross-Exchange EV Scan",
        "Kelly Sizing",
        "Risk Budget Check",
        "Paper Submit",
        "Settlement (simulated)",
        "CLV Report",
        "Performance Summary",
    ]
    for name in expected:
        assert name in stage_names, f"Missing stage: {name!r}"


# ---------------------------------------------------------------------------
# Test 2: paper mode assertion — SUBMISSION_MODE=live → graceful failure
# ---------------------------------------------------------------------------

def test_paper_mode_assertion(monkeypatch):
    monkeypatch.setenv("SUBMISSION_MODE", "live")
    runner = L48.DemoRunner(seed=42)
    report = runner.run()
    assert report.paper_mode_verified is False
    assert report.summary.get("demo_failed_paper_check") is True
    assert len(report.stages) == 0  # aborted before any stage


# ---------------------------------------------------------------------------
# Test 3: markdown includes all 10 stage headings
# ---------------------------------------------------------------------------

def test_to_markdown_includes_all_stages():
    runner = L48.DemoRunner(seed=42)
    report = runner.run()
    md = runner.to_markdown(report)
    for name in [
        "Slate Ingest", "FPTS Distribution", "Lineup Optimization",
        "Cross-Exchange EV Scan", "Kelly Sizing", "Risk Budget Check",
        "Paper Submit", "Settlement (simulated)", "CLV Report",
        "Performance Summary",
    ]:
        assert name in md, f"Stage {name!r} missing from markdown"


# ---------------------------------------------------------------------------
# Test 4: markdown has Executive Summary section
# ---------------------------------------------------------------------------

def test_to_markdown_has_summary_section():
    runner = L48.DemoRunner(seed=42)
    report = runner.run()
    md = runner.to_markdown(report)
    assert "## Executive Summary" in md
    assert "Simulated P&L" in md
    assert "Win Rate" in md
    assert "Avg Edge %" in md


# ---------------------------------------------------------------------------
# Test 5: atomic write artifact — file exists; monkeypatch os.replace → original unchanged
# ---------------------------------------------------------------------------

def test_atomic_write_artifact(tmp_path, monkeypatch):
    runner = L48.DemoRunner(seed=42)
    report = runner.run()

    out_path = tmp_path / "demo_test.md"
    artifact = runner.write_artifact(report, path=out_path)

    assert artifact == out_path
    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    assert "## Executive Summary" in content

    # Monkeypatch os.replace to raise → original file should remain unchanged
    original_content = content
    failing_replace = MagicMock(side_effect=OSError("disk full"))
    monkeypatch.setattr(L48.os, "replace", failing_replace)

    with pytest.raises(OSError, match="disk full"):
        runner.write_artifact(report, path=out_path)

    # Original file must still contain original content
    assert out_path.read_text(encoding="utf-8") == original_content


# ---------------------------------------------------------------------------
# Test 6: deterministic seed — two runs with seed=42 produce same headline numbers
# ---------------------------------------------------------------------------

def test_deterministic_seed():
    runner_a = L48.DemoRunner(seed=42)
    runner_b = L48.DemoRunner(seed=42)
    report_a = runner_a.run()
    report_b = runner_b.run()

    assert report_a.summary.get("n_bets_placed") == report_b.summary.get("n_bets_placed")
    assert report_a.summary.get("simulated_pnl_usd") == pytest.approx(
        report_b.summary.get("simulated_pnl_usd"), abs=1e-6
    )
    assert report_a.summary.get("avg_edge_pct") == pytest.approx(
        report_b.summary.get("avg_edge_pct"), abs=1e-6
    )


# ---------------------------------------------------------------------------
# Test 7: main CLI writes artifact to specified path
# ---------------------------------------------------------------------------

def test_main_cli_writes_artifact(tmp_path):
    out_path = tmp_path / "cli_artifact.md"
    rc = L48.main(["--out", str(out_path), "--seed", "42"])
    assert rc == 0
    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    assert "NBA Execute-Loop Demo" in content
    assert "## Executive Summary" in content
    assert "Stage 1: Slate Ingest" in content
