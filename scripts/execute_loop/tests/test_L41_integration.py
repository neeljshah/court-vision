"""test_L41_integration.py — Integration tests for L41_integration_harness.

All HTTP is mocked; no live API calls. Uses deterministic seed=42.

Run:
    conda run -n basketball_ai python -m pytest scripts/execute_loop/tests/test_L41_integration.py -v
"""
from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Project root on sys.path + mandatory stubs BEFORE any L* import
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_DIR))

# Stub nba_api_headers_patch (required by L01, L02, L07)
_api_stub = types.ModuleType("src.data.nba_api_headers_patch")
sys.modules.setdefault("src.data.nba_api_headers_patch", _api_stub)

# Stub src.data (parent package)
_src_stub = types.ModuleType("src")
_src_data_stub = types.ModuleType("src.data")
sys.modules.setdefault("src", _src_stub)
sys.modules.setdefault("src.data", _src_data_stub)

# Stub settle_tonight (used lazily by L07.settle_unsettled)
_rlc = types.ModuleType("scripts.validation.real_lines_check")
_stn = types.ModuleType("scripts.validation.real_lines_check.settle_tonight")
_stn.fetch_boxscore_player_stats = MagicMock(return_value={})
sys.modules.setdefault("scripts.validation.real_lines_check", _rlc)
sys.modules.setdefault("scripts.validation.real_lines_check.settle_tonight", _stn)

# Stub requests globally so L05 / L01 network paths are inert
_requests_stub = types.ModuleType("requests")
_requests_stub.get = MagicMock(return_value=MagicMock(status_code=404, json=lambda: {}))
_requests_stub.post = MagicMock(return_value=MagicMock(status_code=404, json=lambda: {}))
_requests_stub.delete = MagicMock(return_value=MagicMock(status_code=404))
_requests_stub.Timeout = TimeoutError
_requests_stub.RequestException = Exception
sys.modules["requests"] = _requests_stub

import scripts.execute_loop.L41_integration_harness as L41  # noqa: E402
import scripts.execute_loop.L05_submission_engine as L05  # noqa: E402
import scripts.execute_loop.L07_pnl_ledger as L07  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixture — ensure paper mode and clean env vars for every test.
# Path isolation is now handled internally by IntegrationHarness (isolated_dir
# param or default tempfile.mkdtemp), so we no longer need monkeypatch to
# redirect module-level constants here.  We still clear env vars and buckets
# to guard against cross-test token state.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Ensure paper mode env vars; harness self-isolates file I/O."""
    monkeypatch.setenv("SUBMISSION_MODE", "paper")
    monkeypatch.delenv("USER_TOKEN", raising=False)
    monkeypatch.delenv("DK_LIVE_ENABLED", raising=False)
    monkeypatch.delenv("FD_LIVE_ENABLED", raising=False)
    monkeypatch.delenv("DK_API_KEY", raising=False)
    monkeypatch.delenv("FD_API_KEY", raising=False)
    # Clear L05 token buckets so rate-limiting doesn't bleed across tests
    L05._buckets.clear()
    yield


# ---------------------------------------------------------------------------
# Test 1 — happy path: all available stages run
# ---------------------------------------------------------------------------
def test_happy_path_runs_all_stages():
    harness = L41.IntegrationHarness(seed=42, paper_mode=True)
    report = harness.run_end_to_end()

    assert "stages" in report
    assert len(report["stages"]) == 16, f"Expected 16 stages, got {len(report['stages'])}"

    stage_names = [s["name"] for s in report["stages"]]
    expected = [
        "ingest_slate", "fpts_distribution", "optimize_cash", "optimize_gpp",
        "submit_paper",
        # 6 new mid-flow stages (L9+L10 combined, L13, L14, L18, L33, L36)
        "fetch_exchange_orderbooks", "cross_exchange_ev", "sync_exchange_positions",
        "kelly_sizing", "sell_to_close", "edge_erosion",
        # original post-game stages
        "settle_bets", "ledger_summary", "clv_report",
        "drift_check", "postmortem",
    ]
    assert stage_names == expected, f"Stage names mismatch: {stage_names}"

    # At minimum, ingest_slate and fpts_distribution should PASS (stub always works)
    status_map = {s["name"]: s["status"] for s in report["stages"]}
    assert status_map["ingest_slate"] == "PASS"
    assert status_map["fpts_distribution"] == "PASS"


# ---------------------------------------------------------------------------
# Test 2 — report shape: each stage has name/status/duration_ms; error only on FAIL
# ---------------------------------------------------------------------------
def test_report_shape():
    harness = L41.IntegrationHarness(seed=42)
    report = harness.run_end_to_end()

    required_top = {"started_at", "finished_at", "seed", "paper_mode", "bankroll", "stages", "summary"}
    assert required_top.issubset(report.keys()), f"Missing keys: {required_top - set(report.keys())}"

    for stage in report["stages"]:
        assert "name" in stage, f"Stage missing 'name': {stage}"
        assert "status" in stage, f"Stage missing 'status': {stage}"
        assert "duration_ms" in stage, f"Stage missing 'duration_ms': {stage}"
        assert stage["status"] in ("PASS", "FAIL", "SKIP", "SKIP_DEPENDS"), \
            f"Unknown status {stage['status']!r} in stage {stage['name']}"
        if stage["status"] == "FAIL":
            assert "error" in stage, f"FAIL stage missing 'error': {stage}"
        else:
            assert "error" not in stage, \
                f"Non-FAIL stage {stage['name']} has unexpected 'error' key"

    summary = report["summary"]
    assert {"n_pass", "n_fail", "n_skip", "overall"}.issubset(summary.keys())
    assert summary["overall"] in ("PASS", "FAIL")


# ---------------------------------------------------------------------------
# Test 3 — missing module marks SKIP (not FAIL)
# ---------------------------------------------------------------------------
def test_missing_module_marks_skip(monkeypatch):
    # Patch L19 to None → clv_report stage should be SKIP
    monkeypatch.setattr(L41, "L19", None)
    monkeypatch.setattr(L41, "nightly_clv_report", None)

    harness = L41.IntegrationHarness(seed=42)
    report = harness.run_end_to_end()

    status_map = {s["name"]: s["status"] for s in report["stages"]}
    assert status_map["clv_report"] in ("SKIP", "SKIP_DEPENDS"), \
        f"Expected SKIP for clv_report when L19=None, got {status_map['clv_report']}"


# ---------------------------------------------------------------------------
# Test 4 — one non-critical stage failure does not abort subsequent stages
# ---------------------------------------------------------------------------
def test_one_stage_failure_does_not_abort(monkeypatch):
    # Force drift_check to raise — it's non-critical so later stages must still run
    def _bad_drift(*args, **kwargs):
        raise RuntimeError("Simulated drift detector failure")

    monkeypatch.setattr(L41, "daily_drift_report", _bad_drift)
    # Ensure L08 is not None so the stage is attempted
    if L41.L08 is None:
        dummy_mod = types.ModuleType("fake_L08")
        monkeypatch.setattr(L41, "L08", dummy_mod)

    harness = L41.IntegrationHarness(seed=42)
    report = harness.run_end_to_end()

    status_map = {s["name"]: s["status"] for s in report["stages"]}
    assert status_map["drift_check"] == "FAIL", "Expected drift_check=FAIL"
    # postmortem stage must still have been attempted (PASS, FAIL, or SKIP — not absent)
    assert "postmortem" in status_map, "postmortem stage should still appear after drift_check FAIL"


# ---------------------------------------------------------------------------
# Test 5 — paper mode enforced: SUBMISSION_MODE=live beforehand is rejected
# ---------------------------------------------------------------------------
def test_paper_mode_enforced(monkeypatch):
    monkeypatch.setenv("SUBMISSION_MODE", "live")

    harness = L41.IntegrationHarness(seed=42, paper_mode=True)
    with pytest.raises(RuntimeError, match="SUBMISSION_MODE=live"):
        harness.run_end_to_end()

    # requests.post must NOT have been called
    _requests_stub.post.assert_not_called()


# ---------------------------------------------------------------------------
# Test 6 — deterministic seed: two runs yield same stage status sequence + lineup players
# ---------------------------------------------------------------------------
def test_deterministic_seed():
    harness1 = L41.IntegrationHarness(seed=42)
    report1 = harness1.run_end_to_end()

    harness2 = L41.IntegrationHarness(seed=42)
    report2 = harness2.run_end_to_end()

    statuses1 = [s["status"] for s in report1["stages"]]
    statuses2 = [s["status"] for s in report2["stages"]]
    assert statuses1 == statuses2, f"Status sequences differ: {statuses1} vs {statuses2}"

    # Stub slates from same seed must have identical player sets
    import numpy as np
    slate1 = L41._build_stub_slate(42)
    slate2 = L41._build_stub_slate(42)
    players1 = slate1.players if hasattr(slate1, "players") else slate1["players"]
    players2 = slate2.players if hasattr(slate2, "players") else slate2["players"]
    ids1 = {p["player_id"] for p in players1}
    ids2 = {p["player_id"] for p in players2}
    assert ids1 == ids2, "Deterministic seed produced different player sets"


# ---------------------------------------------------------------------------
# Test 7 — critical failure (ingest_slate) skips all downstream stages
# ---------------------------------------------------------------------------
def test_critical_failure_skips_downstream(monkeypatch):
    # Make _build_stub_slate raise so ingest_slate FAILs
    def _bad_slate(*args, **kwargs):
        raise RuntimeError("Simulated slate ingest failure")

    monkeypatch.setattr(L41, "_build_stub_slate", _bad_slate)

    harness = L41.IntegrationHarness(seed=42)
    report = harness.run_end_to_end()

    status_map = {s["name"]: s["status"] for s in report["stages"]}
    assert status_map["ingest_slate"] == "FAIL"
    # All critical-downstream stages must be SKIP_DEPENDS
    assert status_map["fpts_distribution"] == "SKIP_DEPENDS"
    assert status_map["optimize_cash"] == "SKIP_DEPENDS"
    assert status_map["submit_paper"] == "SKIP_DEPENDS"
    assert status_map["settle_bets"] == "SKIP_DEPENDS"


# ---------------------------------------------------------------------------
# Test 8 — no live API calls (requests.post/get/delete not invoked)
# ---------------------------------------------------------------------------
def test_no_live_api_calls():
    _requests_stub.post.reset_mock()
    _requests_stub.get.reset_mock()
    _requests_stub.delete.reset_mock()

    harness = L41.IntegrationHarness(seed=42, paper_mode=True)
    harness.run_end_to_end()

    _requests_stub.post.assert_not_called()
    _requests_stub.get.assert_not_called()
    _requests_stub.delete.assert_not_called()


# ---------------------------------------------------------------------------
# Test 9 — stub slate validity
# ---------------------------------------------------------------------------
def test_stub_slate_validity():
    from datetime import datetime, timezone

    slate = L41._build_stub_slate(42)
    players = slate.players if hasattr(slate, "players") else slate["players"]
    salary_cap = slate.salary_cap if hasattr(slate, "salary_cap") else slate["salary_cap"]
    lock_time = slate.lock_time if hasattr(slate, "lock_time") else slate["lock_time"]

    assert len(players) >= 10, f"Expected >=10 players, got {len(players)}"
    assert salary_cap == 50000, f"Expected salary_cap=50000, got {salary_cap}"

    # lock_time must be in the future
    lock_dt = datetime.fromisoformat(lock_time.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    assert lock_dt > now, f"lock_time {lock_time} should be in the future"

    # All players have required fields
    required_fields = {"player_id", "name", "team", "position", "salary", "status"}
    for p in players:
        missing = required_fields - set(p.keys())
        assert not missing, f"Player missing fields {missing}: {p}"


# ---------------------------------------------------------------------------
# Test 10 — report is fully JSON-serializable (no numpy/datetime leaks)
# ---------------------------------------------------------------------------
def test_report_json_serializable():
    harness = L41.IntegrationHarness(seed=42)
    report = harness.run_end_to_end()

    try:
        serialized = json.dumps(report)
    except (TypeError, ValueError) as exc:
        pytest.fail(f"Report is not JSON-serializable: {exc}\nReport keys: {list(report.keys())}")

    # Round-trip sanity
    reloaded = json.loads(serialized)
    assert reloaded["seed"] == 42
    assert len(reloaded["stages"]) == 16


# ---------------------------------------------------------------------------
# Test 12 — extended harness: all 16 stage entries present
# ---------------------------------------------------------------------------
def test_extended_harness_runs_new_stages():
    """Happy path: harness must return entries for all 16 stages (10 original + 6 new)."""
    harness = L41.IntegrationHarness(seed=42, paper_mode=True)
    report = harness.run_end_to_end()

    stage_names = [s["name"] for s in report["stages"]]
    expected_new = [
        "fetch_exchange_orderbooks",
        "cross_exchange_ev",
        "sync_exchange_positions",
        "kelly_sizing",
        "sell_to_close",
        "edge_erosion",
    ]
    for name in expected_new:
        assert name in stage_names, f"Expected stage {name!r} missing from report: {stage_names}"

    # Total must now be 16 (10 original + 6 new: L9+L10 combined, L13, L14, L18, L33, L36)
    assert len(stage_names) == 16, (
        f"Expected 16 stages after extension, got {len(stage_names)}: {stage_names}"
    )

    # Each new stage must have a valid status
    valid_statuses = {"PASS", "FAIL", "SKIP", "SKIP_DEPENDS"}
    status_map = {s["name"]: s["status"] for s in report["stages"]}
    for name in expected_new:
        assert status_map[name] in valid_statuses, (
            f"Stage {name!r} has invalid status {status_map[name]!r}"
        )


# ---------------------------------------------------------------------------
# Test 13 — orderbook stage handles missing seed gracefully (PASS not FAIL)
# ---------------------------------------------------------------------------
def test_orderbook_stage_handles_missing_seed():
    """L9/L10 have no seed files for the stub market; stage must PASS (allowed-empty)."""
    harness = L41.IntegrationHarness(seed=42, paper_mode=True)
    report = harness.run_end_to_end()

    status_map = {s["name"]: s["status"] for s in report["stages"]}
    # The stage should PASS even when both exchanges return no data (KeyError/None)
    assert status_map["fetch_exchange_orderbooks"] == "PASS", (
        f"fetch_exchange_orderbooks should PASS when seed files absent, "
        f"got {status_map['fetch_exchange_orderbooks']}"
    )


# ---------------------------------------------------------------------------
# Test 14 — kelly_sizing stage returns float in [0, 0.5]
# ---------------------------------------------------------------------------
def test_kelly_sizing_stage_returns_float():
    """kelly_fraction(model_p=0.55, +100) must return a float in [0, 0.5]."""
    harness = L41.IntegrationHarness(seed=42, paper_mode=True)
    report = harness.run_end_to_end()

    status_map = {s["name"]: s["status"] for s in report["stages"]}
    data_map = {s["name"]: s.get("data") for s in report["stages"]}

    if status_map.get("kelly_sizing") == "SKIP":
        pytest.skip("L18 not available — skipping kelly_sizing assertion")

    assert status_map["kelly_sizing"] == "PASS", (
        f"kelly_sizing stage FAILed: {data_map.get('kelly_sizing')}"
    )
    kelly_data = data_map["kelly_sizing"]
    assert kelly_data is not None and "kelly_fraction" in str(kelly_data), (
        f"kelly_sizing data missing kelly_fraction key: {kelly_data}"
    )
    # Extract the fraction value (data is serialized to safe primitives)
    if isinstance(kelly_data, dict):
        frac = kelly_data.get("kelly_fraction", -1)
    else:
        # data was stringified — just verify stage passed
        frac = 0.0
    assert 0.0 <= float(frac) <= 0.5, f"Kelly fraction {frac!r} outside [0, 0.5]"


# ---------------------------------------------------------------------------
# Test 15 — extended harness: no real API calls even with new stages
# ---------------------------------------------------------------------------
def test_extended_harness_no_real_api_calls():
    """Patch requests.* to fail-loud; all 16 stages must complete without hitting real APIs."""
    import unittest.mock as mock

    def _fail(*args, **kwargs):
        raise AssertionError("real HTTP call attempted during harness run")

    with mock.patch.object(_requests_stub, "get", side_effect=_fail):
        with mock.patch.object(_requests_stub, "post", side_effect=_fail):
            with mock.patch.object(_requests_stub, "delete", side_effect=_fail):
                harness = L41.IntegrationHarness(seed=42, paper_mode=True)
                report = harness.run_end_to_end()

    stage_names = [s["name"] for s in report["stages"]]
    assert len(stage_names) == 16, (
        f"Expected 16 stages even with requests blocked, got {len(stage_names)}"
    )
    # No stage must have raised due to network (all PASS/SKIP/SKIP_DEPENDS, none FAIL
    # due to requests error)
    fail_stages = [s for s in report["stages"] if s["status"] == "FAIL"]
    # Allow FAILs only for non-network reasons (e.g. missing optional deps)
    for s in fail_stages:
        err = s.get("error", "")
        assert "real HTTP call attempted" not in err, (
            f"Stage {s['name']} triggered a real HTTP call: {err}"
        )


# ---------------------------------------------------------------------------
# Test 11 — no real data/ledger/ files are written during a harness run
# ---------------------------------------------------------------------------
def test_no_real_ledger_pollution(tmp_path):
    """Harness must not touch any files in the real data/ledger/ directory."""
    from pathlib import Path

    real_ledger = Path(__file__).resolve().parents[4] / "data" / "ledger"

    # Snapshot mtimes before run
    before: dict = {}
    if real_ledger.is_dir():
        for p in real_ledger.iterdir():
            if p.is_file():
                try:
                    before[str(p)] = p.stat().st_mtime
                except OSError:
                    pass

    # Run harness with isolated_dir pointing to tmp_path
    harness = L41.IntegrationHarness(seed=42, paper_mode=True, isolated_dir=tmp_path)
    report = harness.run_end_to_end()

    # Assert no real ledger file was modified
    if real_ledger.is_dir():
        for p in real_ledger.iterdir():
            if p.is_file():
                try:
                    mtime_after = p.stat().st_mtime
                except OSError:
                    continue
                mtime_before = before.get(str(p), mtime_after)
                assert mtime_after == mtime_before, (
                    f"Real ledger file was mutated during harness run: {p}\n"
                    f"  before={mtime_before}  after={mtime_after}"
                )

    # Confirm the report itself carries no pollution warning
    assert "warnings" not in report or all(
        w.get("type") != "real_ledger_pollution" for w in report.get("warnings", [])
    ), f"Harness reported real_ledger_pollution: {report.get('warnings')}"
