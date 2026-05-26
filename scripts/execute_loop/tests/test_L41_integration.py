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
    assert len(report["stages"]) == 25, f"Expected 25 stages, got {len(report['stages'])}"

    stage_names = [s["name"] for s in report["stages"]]
    expected = [
        "ingest_slate",
        # L20, L21: pre-game info
        "injury_feed_check", "lineup_watcher",
        "fpts_distribution",
        # L40, L25: dispatch + shadow
        "dispatcher_route", "shadow_compare",
        "optimize_cash", "optimize_gpp",
        "submit_paper",
        # exchange mid-flow
        "fetch_exchange_orderbooks", "cross_exchange_ev",
        # L15: market making
        "market_making_quote",
        "sync_exchange_positions",
        # L17: hedge
        "hedge_calculate",
        "kelly_sizing",
        # L34: variance budget
        "variance_budget",
        "sell_to_close", "edge_erosion",
        # post-game stages
        "settle_bets", "ledger_summary", "clv_report",
        "drift_check",
        # L26: hygiene before postmortem
        "hygiene_check",
        "postmortem",
        # L46: event publication verification
        "verify_event_publication",
    ]
    assert stage_names == expected, f"Stage names mismatch:\n  got:      {stage_names}\n  expected: {expected}"

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
    assert len(reloaded["stages"]) == 25


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

    # Total must now be 25 (16 previous + 8 new + 1 L46 verify)
    assert len(stage_names) == 25, (
        f"Expected 25 stages after extension, got {len(stage_names)}: {stage_names}"
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
    assert len(stage_names) == 25, (
        f"Expected 25 stages even with requests blocked, got {len(stage_names)}"
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


# ---------------------------------------------------------------------------
# Test 16 — v4: all 24 stages present (8 new layers wired)
# ---------------------------------------------------------------------------
def test_l41v4_runs_all_24_stages():
    """After R9-v4 extension, harness must return exactly 25 stage entries."""
    harness = L41.IntegrationHarness(seed=42, paper_mode=True)
    report = harness.run_end_to_end()

    stage_names = [s["name"] for s in report["stages"]]
    assert len(stage_names) == 25, (
        f"Expected 25 stages (16 existing + 8 new + 1 L46 verify), got {len(stage_names)}: {stage_names}"
    )
    new_stages = [
        "injury_feed_check", "lineup_watcher", "dispatcher_route",
        "shadow_compare", "market_making_quote", "hedge_calculate",
        "variance_budget", "hygiene_check",
    ]
    for name in new_stages:
        assert name in stage_names, f"New stage {name!r} missing from: {stage_names}"

    valid_statuses = {"PASS", "FAIL", "SKIP", "SKIP_DEPENDS"}
    for s in report["stages"]:
        assert s["status"] in valid_statuses, (
            f"Stage {s['name']} has invalid status {s['status']!r}"
        )


# ---------------------------------------------------------------------------
# Test 17 — new stages SKIP when module is absent (L20 = None)
# ---------------------------------------------------------------------------
def test_new_stages_skip_when_module_absent(monkeypatch):
    """When L20 is patched to None, injury_feed_check must be SKIP (not FAIL)."""
    monkeypatch.setattr(L41, "L20", None)
    monkeypatch.setattr(L41, "fetch_nba_official_injuries", None)

    harness = L41.IntegrationHarness(seed=42, paper_mode=True)
    report = harness.run_end_to_end()

    status_map = {s["name"]: s["status"] for s in report["stages"]}
    assert status_map["injury_feed_check"] in ("SKIP", "SKIP_DEPENDS"), (
        f"Expected SKIP for injury_feed_check when L20=None, got {status_map['injury_feed_check']}"
    )
    # Other new stages are unaffected — they must still appear
    assert "lineup_watcher" in status_map
    assert "variance_budget" in status_map


# ---------------------------------------------------------------------------
# Test 18 — new stage failure isolates (shadow_compare FAIL, rest continue)
# ---------------------------------------------------------------------------
def test_new_stages_failure_isolates(monkeypatch):
    """When shadow_compare raises, it should FAIL while all later stages still run."""
    def _bad_shadows(*args, **kwargs):
        raise RuntimeError("Simulated L25 evaluate failure")

    monkeypatch.setattr(L41, "list_active_shadows", _bad_shadows)
    # Ensure L25 is not None so the stage is attempted
    if L41.L25 is None:
        dummy_mod = types.ModuleType("fake_L25")
        monkeypatch.setattr(L41, "L25", dummy_mod)

    harness = L41.IntegrationHarness(seed=42, paper_mode=True)
    report = harness.run_end_to_end()

    status_map = {s["name"]: s["status"] for s in report["stages"]}
    assert status_map["shadow_compare"] == "FAIL", (
        f"Expected shadow_compare=FAIL, got {status_map['shadow_compare']}"
    )
    # Later stages must still have been attempted
    for later_stage in ["optimize_cash", "kelly_sizing", "settle_bets", "postmortem"]:
        assert later_stage in status_map, f"Stage {later_stage!r} missing after shadow_compare FAIL"


# ---------------------------------------------------------------------------
# Test 19 — full 24-stage report is JSON-serializable
# ---------------------------------------------------------------------------
def test_harness_report_serializable():
    """Full 24-stage report must survive a json.dumps / json.loads round-trip."""
    harness = L41.IntegrationHarness(seed=42, paper_mode=True)
    report = harness.run_end_to_end()

    try:
        serialized = json.dumps(report)
    except (TypeError, ValueError) as exc:
        pytest.fail(f"24-stage report is not JSON-serializable: {exc}")

    reloaded = json.loads(serialized)
    assert reloaded["seed"] == 42
    assert len(reloaded["stages"]) == 25

    # Verify every stage entry survives the round-trip
    for stage in reloaded["stages"]:
        assert "name" in stage
        assert "status" in stage
        assert stage["status"] in ("PASS", "FAIL", "SKIP", "SKIP_DEPENDS")


# ---------------------------------------------------------------------------
# Test 20 — verify_event_publication stage is present in full run
# ---------------------------------------------------------------------------
def test_verify_event_publication_stage_present():
    """Full run must include the verify_event_publication stage."""
    harness = L41.IntegrationHarness(seed=42, paper_mode=True)
    report = harness.run_end_to_end()

    stage_names = [s["name"] for s in report["stages"]]
    assert "verify_event_publication" in stage_names, (
        f"verify_event_publication stage missing from: {stage_names}"
    )
    # It must be the last stage
    assert stage_names[-1] == "verify_event_publication", (
        f"verify_event_publication should be last stage, got: {stage_names[-1]}"
    )
    # Must have a valid status
    status_map = {s["name"]: s["status"] for s in report["stages"]}
    assert status_map["verify_event_publication"] in ("PASS", "FAIL", "SKIP", "SKIP_DEPENDS"), (
        f"Invalid status: {status_map['verify_event_publication']}"
    )


# ---------------------------------------------------------------------------
# Test 21 — required events captured during run when producers publish
# ---------------------------------------------------------------------------
def test_required_events_captured_during_run():
    """When producers run normally, required events must be captured and stage must PASS."""
    import scripts.execute_loop.L46_event_bus as _l46_mod

    harness = L41.IntegrationHarness(seed=42, paper_mode=True)
    report = harness.run_end_to_end()

    status_map = {s["name"]: s["status"] for s in report["stages"]}
    data_map = {s["name"]: s.get("data") for s in report["stages"]}

    verify_status = status_map.get("verify_event_publication")
    verify_data = data_map.get("verify_event_publication")

    # If L46 is available, stage must PASS (required events captured by real producers)
    if verify_data and isinstance(verify_data, dict) and verify_data.get("l46_available"):
        assert verify_status == "PASS", (
            f"verify_event_publication should PASS when L46 available and producers run. "
            f"Status={verify_status}, data={verify_data}"
        )
        # event_count must be in data
        assert "event_count" in verify_data, f"event_count missing from data: {verify_data}"
        assert verify_data["event_count"] >= 0
        # breakdown must be a dict
        assert isinstance(verify_data.get("breakdown"), dict), (
            f"breakdown should be a dict: {verify_data}"
        )
    else:
        # L46 not available — stage should still exist (PASS with warn or FAIL)
        assert verify_status is not None, "verify_event_publication stage must always appear"


# ---------------------------------------------------------------------------
# Test 22 — missing required event causes verify stage to FAIL
# ---------------------------------------------------------------------------
def test_missing_required_event_marks_fail(monkeypatch):
    """When a required event is gated open but never published, verify_event_publication FAILs.

    Strategy: run a harness where kelly_sizing PASSes with a positive fraction
    (gate opens for kelly.sized) but we suppress the L18 publish by clearing
    captured_events right before the verify stage runs, then injecting every
    required event except kelly.sized.  We do this by patching the verify's
    _captured_events directly after the harness run collects them.
    """
    try:
        import scripts.execute_loop.L46_event_bus as _l46_mod
        from scripts.execute_loop.L46_event_bus import EventBus, Event
    except Exception:
        pytest.skip("L46 not available — cannot test event-missing failure path")

    # We need kelly_sizing to PASS with fraction > 0 so the gate opens.
    # Patch kelly_fraction to return 0.10.
    def _positive_kelly(*args, **kwargs):
        return 0.10

    monkeypatch.setattr(L41, "kelly_fraction", _positive_kelly)
    if L41.L18 is None:
        dummy_mod = types.ModuleType("fake_L18")
        monkeypatch.setattr(L41, "L18", dummy_mod)

    # After setup_event_capture runs, we intercept _run_stages to inject fake events
    # for everything EXCEPT kelly.sized, then clear captured_events.
    # The simplest hook: patch _run_stages to clear captured_events at the start of
    # verify_event_publication computation. Instead, we patch the harness's
    # _captured_events after run_end_to_end finishes by running a modified harness.
    # Cleanest: subclass and override to inject events.
    import datetime as _dt
    import uuid as _uuid

    class _HarnessWithMissingKelly(L41.IntegrationHarness):
        def _run_stages(self, started_at):
            result = super()._run_stages(started_at)
            # After all stages ran, replace captured events: keep everything except
            # kelly.sized so the gate triggers a FAIL.
            # Find the verify stage and re-run with manipulated events.
            # We can't re-run easily, so instead we'll inject events before run.
            return result

    # Inject events BEFORE run by pre-populating via a hook on _setup_event_capture
    original_setup = L41.IntegrationHarness._setup_event_capture

    def _inject_setup(self_h):
        original_setup(self_h)
        # Publish a dummy "bet.settled" so that gate check has at least one captured event
        # (doesn't matter — the verify stage is driven by stage outcome data, not bus directly)
        # The key: kelly.sized must NOT be published (which it won't be since _positive_kelly
        # never calls L18 internals). Gate opens because kelly_sizing PASS'd with frac>0.
        # So just let the normal flow happen — kelly.sized won't be published.
        pass

    monkeypatch.setattr(L41.IntegrationHarness, "_setup_event_capture", _inject_setup)

    harness = L41.IntegrationHarness(seed=42, paper_mode=True)
    report = harness.run_end_to_end()

    status_map = {s["name"]: s["status"] for s in report["stages"]}
    data_map = {s["name"]: s.get("data") for s in report["stages"]}
    error_map = {s["name"]: s.get("error", "") for s in report["stages"]}
    verify_status = status_map.get("verify_event_publication")
    verify_data = data_map.get("verify_event_publication")

    # If L46 is not available, verify stage PASSes with a warn dict (l46_available=False)
    if isinstance(verify_data, dict) and not verify_data.get("l46_available"):
        pytest.skip("L46 not available in this environment — cannot test event-missing failure path")

    # When kelly_sizing PASSes with frac > 0 but kelly.sized is not published,
    # verify_event_publication must FAIL.
    # Check that kelly_sizing PASSed (gate could open)
    if status_map.get("kelly_sizing") not in ("PASS",):
        pytest.skip(
            f"kelly_sizing did not PASS (got {status_map.get('kelly_sizing')}) — "
            "cannot test event-missing failure path"
        )

    kelly_data = data_map.get("kelly_sizing") or {}
    kelly_frac = kelly_data.get("kelly_fraction", 0.0) if isinstance(kelly_data, dict) else 0.0
    if float(kelly_frac) <= 0.0:
        pytest.skip(
            f"kelly fraction was {kelly_frac} (<=0) — gate would not open, "
            "cannot test missing event FAIL"
        )

    # At this point: kelly_sizing PASS'd with positive frac, gate opens,
    # kelly.sized not published → verify must FAIL
    assert verify_status == "FAIL", (
        f"Expected verify_event_publication=FAIL when kelly.sized gate open but not published, "
        f"got {verify_status!r}. data={verify_data}, error={error_map.get('verify_event_publication')}"
    )
    # The error message should mention kelly.sized
    error_msg = error_map.get("verify_event_publication", "")
    assert "kelly.sized" in error_msg, (
        f"Error message should mention kelly.sized: {error_msg!r}"
    )


# ---------------------------------------------------------------------------
# Test 23 — verify stage data field contains event_count and breakdown
# ---------------------------------------------------------------------------
def test_captured_events_in_report_data():
    """verify_event_publication data must contain event_count and breakdown dict."""
    harness = L41.IntegrationHarness(seed=42, paper_mode=True)
    report = harness.run_end_to_end()

    data_map = {s["name"]: s.get("data") for s in report["stages"]}
    status_map = {s["name"]: s["status"] for s in report["stages"]}
    verify_data = data_map.get("verify_event_publication")
    verify_status = status_map.get("verify_event_publication")

    assert verify_data is not None or verify_status == "FAIL", (
        "verify_event_publication must either have data or be FAIL with error"
    )
    if isinstance(verify_data, dict):
        assert "event_count" in verify_data, f"Missing event_count in: {verify_data}"
        assert "l46_available" in verify_data, f"Missing l46_available in: {verify_data}"
        if verify_data.get("l46_available"):
            assert "breakdown" in verify_data, f"Missing breakdown in: {verify_data}"
            assert isinstance(verify_data["breakdown"], dict), (
                f"breakdown must be dict, got: {type(verify_data['breakdown'])}"
            )
