"""Tests for scripts/execute_loop/L24_nightly_retrain.py.

Run:
    conda run -n basketball_ai --no-capture-output \
        python -m pytest scripts/execute_loop/tests/test_L24_retrain.py -v

Strategy
--------
- All file-system I/O is redirected to tmp_path via monkeypatching.
- scoreboardv2 is stubbed so no real network calls are made.
- The WF subprocess is mocked so no actual training runs.
- L25.start_shadow is monkeypatched to verify shadow deploy path.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
import types
import importlib
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path before importing the module
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_DIR))

# Stub heavy optional imports so the module loads without the full ML stack
for mod_name in [
    "nba_api",
    "nba_api.stats",
    "nba_api.stats.endpoints",
    "nba_api.live",
    "nba_api.live.nba",
    "nba_api.live.nba.endpoints",
    "nba_api.live.nba.endpoints.scoreboard",
    "src.data.nba_api_headers_patch",
]:
    sys.modules.setdefault(mod_name, types.ModuleType(mod_name))

import scripts.execute_loop.L24_nightly_retrain as L24  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures: redirect all file I/O to tmp_path
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    """Redirect every path constant in L24 to tmp_path subdirectories."""
    models_dir   = tmp_path / "data" / "models"
    ledger_dir   = tmp_path / "data" / "ledger"
    history_path = ledger_dir / "retrain_history.json"
    lock_path    = tmp_path / "data" / ".retrain_lock"
    wf_out_path  = models_dir / "prop_pergame_walk_forward.json"
    wf_script    = tmp_path / "scripts" / "prop_pergame_walk_forward.py"

    models_dir.mkdir(parents=True, exist_ok=True)
    ledger_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(L24, "_MODELS_DIR",   models_dir)
    monkeypatch.setattr(L24, "_LEDGER_DIR",   ledger_dir)
    monkeypatch.setattr(L24, "_HISTORY_PATH", history_path)
    monkeypatch.setattr(L24, "_LOCK_PATH",    lock_path)
    monkeypatch.setattr(L24, "_WF_OUT_PATH",  wf_out_path)
    monkeypatch.setattr(L24, "_WF_SCRIPT",    wf_script)

    return {
        "models_dir":   models_dir,
        "ledger_dir":   ledger_dir,
        "history_path": history_path,
        "lock_path":    lock_path,
        "wf_out_path":  wf_out_path,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]

_GOOD_CANDIDATE_MAE = {s: 1.0 for s in _STATS}   # better than prod (all < 99)
_GOOD_PROD_MAE      = {s: 2.0 for s in _STATS}   # prod baseline


def _write_wf_json(path: Path, *, all_4_folds_pass: bool = True) -> None:
    """Write a synthetic prop_pergame_walk_forward.json."""
    folds_per_stat: dict = {}
    by_stat: dict = {}
    for stat in _STATS:
        # 4 folds where 3-way < 2-way if all_4_folds_pass, else one fold fails
        folds = []
        for i in range(4):
            two_way_mae = 3.0
            if all_4_folds_pass:
                three_way_mae = 2.5  # always better
            else:
                # fold 3 fails (3-way >= 2-way)
                three_way_mae = 2.5 if i < 3 else 3.5
            folds.append({
                "fold": i + 1,
                "two_way":   {"mae": two_way_mae,   "r2": 0.4, "w": [0.5, 0.5]},
                "three_way": {"mae": three_way_mae, "r2": 0.45, "w": [0.4, 0.4, 0.2]},
            })
        folds_per_stat[stat] = folds
        by_stat[stat] = {
            "mae_2way_mean": 3.0,
            "mae_3way_mean": 2.5 if all_4_folds_pass else 3.0,
            "mae_2way_std":  0.1,
            "mae_3way_std":  0.1,
            "r2_2way_mean":  0.4,
            "r2_3way_mean":  0.45,
            "delta_mae_mean": -0.5 if all_4_folds_pass else 0.0,
            "delta_mae_std":  0.05,
            "delta_r2_mean":  0.05,
            "delta_r2_std":   0.01,
        }
    payload = {"folds_per_stat": folds_per_stat, "by_stat": by_stat}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _stub_all_games_final(monkeypatch, final: bool = True):
    """Monkeypatch _all_games_final to return a fixed value."""
    monkeypatch.setattr(L24, "_all_games_final", lambda: final)


def _stub_wf_subprocess(monkeypatch, isolated_paths, *, success: bool = True):
    """Monkeypatch run_walk_forward_candidate to write WF JSON and return MAE."""
    wf_out = isolated_paths["wf_out_path"]

    def _fake_wf():
        if not success:
            raise RuntimeError("Simulated WF failure")
        _write_wf_json(wf_out, all_4_folds_pass=True)
        return {s: 2.5 for s in _STATS}

    monkeypatch.setattr(L24, "run_walk_forward_candidate", _fake_wf)


# ---------------------------------------------------------------------------
# Test 1 — happy path: all FINAL + good WF → status=ok
# ---------------------------------------------------------------------------
def test_happy_path_ok(monkeypatch, isolated_paths):
    """All games FINAL, WF passes 4/4, candidate MAE < prod → status='ok'."""
    wf_out = isolated_paths["wf_out_path"]

    _stub_all_games_final(monkeypatch, final=True)

    # Pre-write WF JSON so compute_production_metrics uses it as "prod"
    _write_wf_json(wf_out, all_4_folds_pass=True)
    # Prod MAE will be 2.5 from by_stat.mae_3way_mean

    def _fake_wf():
        # candidate is 2.0 — strictly better than prod 2.5
        _write_wf_json(wf_out, all_4_folds_pass=True)
        # Override mae_3way_mean to 2.0 so candidate < prod
        data = json.loads(wf_out.read_text())
        for stat in _STATS:
            data["by_stat"][stat]["mae_3way_mean"] = 2.0
        wf_out.write_text(json.dumps(data))
        return {s: 2.0 for s in _STATS}

    monkeypatch.setattr(L24, "run_walk_forward_candidate", _fake_wf)

    # Stub L22 alerting
    monkeypatch.setattr(L24, "_send_alert", lambda *a, **kw: None)

    # Prod snapshot first: it reads WF JSON (mae_3way_mean=2.5)
    run = L24.run_nightly(via_shadow=False, dry_run=True)

    # dry_run=True skips backup and subprocess, parses existing JSON
    assert run.status in ("ok", "gate_warn"), f"Unexpected status: {run.status}"


def test_happy_path_full(monkeypatch, isolated_paths):
    """Full end-to-end: FINAL games + WF pass + 4/4 folds → gate_pass=True."""
    wf_out = isolated_paths["wf_out_path"]

    _stub_all_games_final(monkeypatch, final=True)

    # Prod snapshot returns baseline (2.0), candidate returns 1.5
    def _fake_prod():
        return {s: 2.0 for s in _STATS}

    def _fake_wf():
        _write_wf_json(wf_out, all_4_folds_pass=True)
        # Override to 1.5 so candidate < prod
        data = json.loads(wf_out.read_text())
        for stat in _STATS:
            data["by_stat"][stat]["mae_3way_mean"] = 1.5
        wf_out.write_text(json.dumps(data))
        return {s: 1.5 for s in _STATS}

    monkeypatch.setattr(L24, "compute_production_metrics", _fake_prod)
    monkeypatch.setattr(L24, "run_walk_forward_candidate", _fake_wf)
    monkeypatch.setattr(L24, "_backup_models", lambda ts: isolated_paths["models_dir"] / "_bkp")
    monkeypatch.setattr(L24, "_send_alert", lambda *a, **kw: None)

    # Mock L25 so shadow deploy doesn't fail
    l25_mock = types.ModuleType("scripts.execute_loop.L25_ab_shadow")
    l25_mock.start_shadow = MagicMock(return_value=None)
    sys.modules["scripts.execute_loop.L25_ab_shadow"] = l25_mock

    run = L24.run_nightly(via_shadow=True, dry_run=False)

    assert run.status == "ok", f"Expected ok, got {run.status}. notes: {run.summary_notes}"
    assert run.gate_pass is True
    assert run.wf_4_of_4 is True
    assert run.single_split_better is True
    assert run.deployed is True
    assert run.deploy_mode == "shadow"

    # Verify history was written
    history = L24._load_history()
    assert len(history) == 1
    assert history[0]["run_id"] == run.run_id
    assert history[0]["status"] == "ok"


# ---------------------------------------------------------------------------
# Test 2 — Gate: 4/4 + single-split better on all 7 → gate_pass=True
# ---------------------------------------------------------------------------
def test_gate_pass_all_7_better(monkeypatch, isolated_paths):
    """check_promotion_gate returns True when candidate < prod on all stats."""
    wf_out = isolated_paths["wf_out_path"]
    _write_wf_json(wf_out, all_4_folds_pass=True)

    candidate = {s: 1.0 for s in _STATS}
    prod      = {s: 2.0 for s in _STATS}

    wf_4_of_4, single_split_better, gate_pass = L24.check_promotion_gate(candidate, prod)

    assert wf_4_of_4 is True,         "Expected wf_4_of_4=True"
    assert single_split_better is True, "Expected single_split_better=True"
    assert gate_pass is True,          "Expected gate_pass=True"


# ---------------------------------------------------------------------------
# Test 3 — Gate: 4/4 True but PTS single-split worse → gate_pass=False
# ---------------------------------------------------------------------------
def test_gate_fail_pts_regression(monkeypatch, isolated_paths):
    """gate_pass=False when one stat (PTS) is worse in single-split."""
    wf_out = isolated_paths["wf_out_path"]
    _write_wf_json(wf_out, all_4_folds_pass=True)

    candidate = {s: 1.0 for s in _STATS}
    candidate["pts"] = 5.0  # PTS regresses vs prod=2.0

    prod = {s: 2.0 for s in _STATS}

    wf_4_of_4, single_split_better, gate_pass = L24.check_promotion_gate(candidate, prod)

    assert wf_4_of_4 is True
    assert single_split_better is False, "Expected single_split_better=False (PTS regresses)"
    assert gate_pass is False,           "Expected gate_pass=False"


def test_gate_fail_runs_gate_warn_status(monkeypatch, isolated_paths):
    """run_nightly returns status='gate_warn' and deployed=False when gate fails."""
    wf_out = isolated_paths["wf_out_path"]

    _stub_all_games_final(monkeypatch, final=True)

    def _fake_prod():
        return {s: 2.0 for s in _STATS}

    def _fake_wf():
        _write_wf_json(wf_out, all_4_folds_pass=True)
        # candidate PTS=5 (worse), rest=1.0 (better)
        data = json.loads(wf_out.read_text())
        for stat in _STATS:
            data["by_stat"][stat]["mae_3way_mean"] = 5.0 if stat == "pts" else 1.0
        wf_out.write_text(json.dumps(data))
        return {s: (5.0 if s == "pts" else 1.0) for s in _STATS}

    monkeypatch.setattr(L24, "compute_production_metrics", _fake_prod)
    monkeypatch.setattr(L24, "run_walk_forward_candidate", _fake_wf)
    monkeypatch.setattr(L24, "_backup_models", lambda ts: isolated_paths["models_dir"] / "_bkp")
    monkeypatch.setattr(L24, "_send_alert", lambda *a, **kw: None)

    run = L24.run_nightly(via_shadow=True, dry_run=False)

    assert run.status == "gate_warn", f"Expected gate_warn, got {run.status}"
    assert run.deployed is False
    assert run.gate_pass is False


# ---------------------------------------------------------------------------
# Test 4 — via_shadow=True path: mock L25.start_shadow → deploy_mode="shadow"
# ---------------------------------------------------------------------------
def test_shadow_deploy_mode(monkeypatch, isolated_paths):
    """via_shadow=True calls L25.start_shadow and sets deploy_mode='shadow'."""
    start_shadow_mock = MagicMock(return_value=MagicMock())

    l25_mod = types.ModuleType("scripts.execute_loop.L25_ab_shadow")
    l25_mod.start_shadow = start_shadow_mock
    sys.modules["scripts.execute_loop.L25_ab_shadow"] = l25_mod

    wf_out = isolated_paths["wf_out_path"]

    _stub_all_games_final(monkeypatch, final=True)

    def _fake_prod():
        return {s: 3.0 for s in _STATS}

    def _fake_wf():
        _write_wf_json(wf_out, all_4_folds_pass=True)
        data = json.loads(wf_out.read_text())
        for stat in _STATS:
            data["by_stat"][stat]["mae_3way_mean"] = 2.0
        wf_out.write_text(json.dumps(data))
        return {s: 2.0 for s in _STATS}

    monkeypatch.setattr(L24, "compute_production_metrics", _fake_prod)
    monkeypatch.setattr(L24, "run_walk_forward_candidate", _fake_wf)
    monkeypatch.setattr(L24, "_backup_models", lambda ts: isolated_paths["models_dir"] / "_bkp")
    monkeypatch.setattr(L24, "_send_alert", lambda *a, **kw: None)

    run = L24.run_nightly(via_shadow=True, dry_run=False)

    assert run.deploy_mode == "shadow", f"Expected shadow, got {run.deploy_mode}"
    assert run.deployed is True
    start_shadow_mock.assert_called_once()

    # Verify variant name includes today's date
    call_args = start_shadow_mock.call_args
    variant_name = call_args[0][0] if call_args[0] else call_args[1].get("variant_name", "")
    assert date.today().isoformat() in variant_name


# ---------------------------------------------------------------------------
# Test 5 — Pre-existing lock → status="locked", models dir unchanged
# ---------------------------------------------------------------------------
def test_lock_contention_no_model_writes(monkeypatch, isolated_paths):
    """If .retrain_lock already exists (fresh JSON lock, not stale), return status='locked'."""
    lock_path   = isolated_paths["lock_path"]
    models_dir  = isolated_paths["models_dir"]

    # Create a fresh JSON lock with current pid and hostname so it is NOT stale
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fresh_lock = {
        "pid":        os.getpid(),
        "hostname":   socket.gethostname(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_id":     "test-fresh-lock",
    }
    lock_path.write_text(json.dumps(fresh_lock), encoding="utf-8")

    # Record mtime of models dir before run
    mtime_before = models_dir.stat().st_mtime

    run = L24.run_nightly(via_shadow=True, dry_run=False)

    assert run.status == "locked", f"Expected locked, got {run.status}"

    # models_dir must not have been touched
    mtime_after = models_dir.stat().st_mtime
    assert mtime_after == mtime_before, "Models dir was modified despite lock!"


# ---------------------------------------------------------------------------
# Test 6 — Idempotency: 2nd run on same date returns prior RetrainRun
# ---------------------------------------------------------------------------
def test_idempotency_same_date(monkeypatch, isolated_paths):
    """Second run_nightly on same calendar date returns the prior ok RetrainRun."""
    history_path = isolated_paths["history_path"]

    today = date.today().isoformat()
    prior_run = {
        "run_id":             f"{today}_120000",
        "started_at":         f"{today}T12:00:00+00:00",
        "finished_at":        f"{today}T12:30:00+00:00",
        "prod_mae_before":    {s: 2.0 for s in _STATS},
        "candidate_mae":      {s: 1.8 for s in _STATS},
        "wf_4_of_4":          True,
        "single_split_better": True,
        "gate_pass":          True,
        "deployed":           True,
        "deploy_mode":        "shadow",
        "status":             "ok",
        "summary_notes":      "prior run",
    }
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps([prior_run]), encoding="utf-8")

    run = L24.run_nightly(via_shadow=True, dry_run=False)

    assert run.run_id == prior_run["run_id"], (
        f"Expected prior run_id={prior_run['run_id']}, got {run.run_id}"
    )
    assert run.status == "ok"
    assert run.deployed is True


# ---------------------------------------------------------------------------
# Test 7 — No new data: not all games FINAL → status="no_new_data"
# ---------------------------------------------------------------------------
def test_no_new_data_games_not_final(monkeypatch, isolated_paths):
    """When games are not yet FINAL, returns status='no_new_data'."""
    _stub_all_games_final(monkeypatch, final=False)
    monkeypatch.setattr(L24, "_send_alert", lambda *a, **kw: None)

    run = L24.run_nightly(via_shadow=True, dry_run=False)

    assert run.status == "no_new_data"
    assert run.deployed is False

    # History should have been written
    history = L24._load_history()
    assert any(e["status"] == "no_new_data" for e in history)


# ---------------------------------------------------------------------------
# Test 8 — WF subprocess failure → status="wf_failed"
# ---------------------------------------------------------------------------
def test_wf_failure_sets_status(monkeypatch, isolated_paths):
    """WF subprocess non-zero exit → status='wf_failed', no deploy."""
    _stub_all_games_final(monkeypatch, final=True)

    def _fake_wf_fail():
        raise RuntimeError("Simulated WF subprocess failure rc=1")

    monkeypatch.setattr(L24, "compute_production_metrics", lambda: {s: 2.0 for s in _STATS})
    monkeypatch.setattr(L24, "run_walk_forward_candidate", _fake_wf_fail)
    monkeypatch.setattr(L24, "_backup_models", lambda ts: isolated_paths["models_dir"] / "_bkp")
    monkeypatch.setattr(L24, "_send_alert", lambda *a, **kw: None)

    run = L24.run_nightly(via_shadow=True, dry_run=False)

    assert run.status == "wf_failed", f"Expected wf_failed, got {run.status}"
    assert run.deployed is False
    assert run.gate_pass is False


# ---------------------------------------------------------------------------
# Test 9 — Stale lock is cleared automatically
# ---------------------------------------------------------------------------
def test_stale_lock_cleared(monkeypatch, isolated_paths):
    """JSON lock with created_at 7h ago is treated as stale and cleared so run proceeds."""
    lock_path = isolated_paths["lock_path"]
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # Write a JSON lock with created_at 7 hours ago (exceeds _LOCK_STALE_SECONDS=6h)
    old_created_at = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
    stale_lock = {
        "pid":        99999,
        "hostname":   socket.gethostname(),
        "created_at": old_created_at,
        "run_id":     "test-stale-lock",
    }
    lock_path.write_text(json.dumps(stale_lock), encoding="utf-8")

    _stub_all_games_final(monkeypatch, final=False)
    monkeypatch.setattr(L24, "_send_alert", lambda *a, **kw: None)

    run = L24.run_nightly(via_shadow=True, dry_run=False)

    # Lock was stale — run proceeds (not locked status)
    assert run.status != "locked", "Stale lock should have been cleared"
    assert not lock_path.exists(), "Lock should be released after run"


# ---------------------------------------------------------------------------
# Test 10 — deploy_candidate via_shadow=False without token → returns False
# ---------------------------------------------------------------------------
def test_live_deploy_no_token(monkeypatch, isolated_paths):
    """deploy_candidate(via_shadow=False) without RETRAIN_DEPLOY_TOKEN → False."""
    monkeypatch.delenv("RETRAIN_DEPLOY_TOKEN", raising=False)

    result = L24.deploy_candidate(via_shadow=False)

    assert result is False, "Expected False when RETRAIN_DEPLOY_TOKEN is absent"


# ---------------------------------------------------------------------------
# Test 11 — check_promotion_gate with no WF JSON → wf_4_of_4=False
# ---------------------------------------------------------------------------
def test_gate_no_wf_json(monkeypatch, isolated_paths):
    """When no WF JSON exists, _count_wf_4_of_4 returns False → gate_pass=False."""
    # WF JSON does not exist (isolated_paths ensures clean tmp dir)
    candidate = {s: 1.0 for s in _STATS}
    prod      = {s: 2.0 for s in _STATS}

    wf_4_of_4, single_split_better, gate_pass = L24.check_promotion_gate(candidate, prod)

    assert wf_4_of_4 is False
    assert gate_pass is False


# ---------------------------------------------------------------------------
# Test 12 — compute_production_metrics fallback to baseline
# ---------------------------------------------------------------------------
def test_compute_prod_metrics_fallback(isolated_paths):
    """compute_production_metrics falls back to _BASELINE_MAE when JSON absent."""
    metrics = L24.compute_production_metrics()

    for stat in _STATS:
        assert stat in metrics
        # Baseline values are defined in _BASELINE_MAE
        assert metrics[stat] == pytest.approx(L24._BASELINE_MAE[stat], rel=1e-4)


# ---------------------------------------------------------------------------
# Test 13 — history written even on gate_warn
# ---------------------------------------------------------------------------
def test_history_written_on_gate_warn(monkeypatch, isolated_paths):
    """retrain_history.json is appended even when gate fails."""
    wf_out = isolated_paths["wf_out_path"]

    _stub_all_games_final(monkeypatch, final=True)

    def _fake_prod():
        return {s: 2.0 for s in _STATS}

    def _fake_wf():
        _write_wf_json(wf_out, all_4_folds_pass=False)  # folds fail
        return {s: 3.0 for s in _STATS}  # candidate worse than prod

    monkeypatch.setattr(L24, "compute_production_metrics", _fake_prod)
    monkeypatch.setattr(L24, "run_walk_forward_candidate", _fake_wf)
    monkeypatch.setattr(L24, "_backup_models", lambda ts: isolated_paths["models_dir"] / "_bkp")
    monkeypatch.setattr(L24, "_send_alert", lambda *a, **kw: None)

    run = L24.run_nightly(via_shadow=True, dry_run=False)

    assert run.status in ("gate_warn",)
    history = L24._load_history()
    assert len(history) >= 1
    assert history[-1]["run_id"] == run.run_id


# ===========================================================================
# NEW lock-v2 tests (JSON schema)
# ===========================================================================

def _make_lock(lock_path: Path, *, pid: int, hostname: str, age_hours: float = 0.0) -> None:
    """Write a JSON lock to *lock_path* with the given parameters."""
    created_at = (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat()
    payload = {
        "pid":        pid,
        "hostname":   hostname,
        "created_at": created_at,
        "run_id":     "test-lock",
    }
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 14 — stale by age with live pid → reclaimed
# ---------------------------------------------------------------------------
def test_lock_stale_by_age_reclaimed(monkeypatch, isolated_paths):
    """Lock with created_at 7h ago is reclaimed even if the pid is this process."""
    lock_path = isolated_paths["lock_path"]
    _make_lock(lock_path, pid=os.getpid(), hostname=socket.gethostname(), age_hours=7)

    _stub_all_games_final(monkeypatch, final=False)
    monkeypatch.setattr(L24, "_send_alert", lambda *a, **kw: None)

    run = L24.run_nightly(via_shadow=True, dry_run=False)

    assert run.status != "locked", "7h-old lock should have been reclaimed"


# ---------------------------------------------------------------------------
# Test 15 — fresh live pid → respected (status=locked)
# ---------------------------------------------------------------------------
def test_lock_fresh_live_pid_respected(monkeypatch, isolated_paths):
    """Fresh JSON lock with current pid+host is respected; run returns locked."""
    lock_path = isolated_paths["lock_path"]
    _make_lock(lock_path, pid=os.getpid(), hostname=socket.gethostname(), age_hours=0)

    run = L24.run_nightly(via_shadow=True, dry_run=False)

    assert run.status == "locked", f"Expected locked, got {run.status}"


# ---------------------------------------------------------------------------
# Test 16 — dead pid → reclaimed
# ---------------------------------------------------------------------------
def test_lock_dead_pid_reclaimed(monkeypatch, isolated_paths):
    """Lock held by a definitively dead pid on same host is reclaimed."""
    lock_path = isolated_paths["lock_path"]
    dead_pid = 2_000_000  # astronomically unlikely to exist

    # Verify _pid_alive gives a definitive answer; skip if uncertain on this platform
    alive = L24._pid_alive(dead_pid)
    if alive is None:
        pytest.skip("_pid_alive returned None for dead_pid on this platform — cannot test")

    if alive is True:
        pytest.skip(f"pid={dead_pid} is actually alive on this machine — cannot test")

    _make_lock(lock_path, pid=dead_pid, hostname=socket.gethostname(), age_hours=0)

    _stub_all_games_final(monkeypatch, final=False)
    monkeypatch.setattr(L24, "_send_alert", lambda *a, **kw: None)

    run = L24.run_nightly(via_shadow=True, dry_run=False)

    assert run.status != "locked", "Dead-pid lock should have been reclaimed"


# ---------------------------------------------------------------------------
# Test 17 — corrupt JSON → reclaimed + warning logged
# ---------------------------------------------------------------------------
def test_lock_corrupt_json_reclaimed(monkeypatch, isolated_paths, caplog):
    """Corrupt JSON lock file is reclaimed and a warning is emitted."""
    import logging
    lock_path = isolated_paths["lock_path"]
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("{garbage not json", encoding="utf-8")

    _stub_all_games_final(monkeypatch, final=False)
    monkeypatch.setattr(L24, "_send_alert", lambda *a, **kw: None)

    with caplog.at_level(logging.WARNING, logger="scripts.execute_loop.L24_nightly_retrain"):
        run = L24.run_nightly(via_shadow=True, dry_run=False)

    assert run.status != "locked", "Corrupt-JSON lock should have been reclaimed"
    # A warning about corrupt/empty lock should appear
    assert any("corrupt" in r.message.lower() or "empty" in r.message.lower()
               for r in caplog.records), "Expected a warning about corrupt lock"


# ---------------------------------------------------------------------------
# Test 18 — empty file → reclaimed
# ---------------------------------------------------------------------------
def test_lock_empty_file_reclaimed(monkeypatch, isolated_paths):
    """Empty lock file is treated as corrupt and reclaimed."""
    lock_path = isolated_paths["lock_path"]
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("", encoding="utf-8")

    _stub_all_games_final(monkeypatch, final=False)
    monkeypatch.setattr(L24, "_send_alert", lambda *a, **kw: None)

    run = L24.run_nightly(via_shadow=True, dry_run=False)

    assert run.status != "locked", "Empty lock file should have been reclaimed"


# ---------------------------------------------------------------------------
# Test 19 — atomic write: os.replace raises → tmp cleaned up, target unchanged
# ---------------------------------------------------------------------------
def test_lock_atomic_write_no_partial(monkeypatch, isolated_paths):
    """If os.replace raises, the temp file is cleaned up and target is unchanged."""
    lock_path = isolated_paths["lock_path"]
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    original_replace = os.replace

    def _failing_replace(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", _failing_replace)

    payload = {
        "pid":        os.getpid(),
        "hostname":   socket.gethostname(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_id":     "test-atomic",
    }

    with pytest.raises(OSError, match="simulated replace failure"):
        L24._write_lock_atomic(lock_path, payload)

    # Target lock should not exist (was not there before)
    assert not lock_path.exists(), "Target lock must not be created on failure"

    # No stray .lock.tmp files should remain in parent dir
    tmp_files = list(lock_path.parent.glob("*.lock.tmp"))
    assert tmp_files == [], f"Temp files not cleaned up: {tmp_files}"


# ---------------------------------------------------------------------------
# Test 20 — cross-host lock: age=1h → fresh; age=7h → reclaimed
# ---------------------------------------------------------------------------
def test_lock_cross_host_age_only(monkeypatch, isolated_paths):
    """Cross-host lock: 1h old stays fresh; 7h old is reclaimed by age."""
    lock_path = isolated_paths["lock_path"]
    other_host = "OTHER-HOST-XYZ"
    assert other_host != socket.gethostname(), "Test requires a different hostname"

    now_ts = datetime.now(timezone.utc).timestamp()

    # 1h old cross-host → fresh
    _make_lock(lock_path, pid=12345, hostname=other_host, age_hours=1)
    lock_data_1h = L24._read_lock(lock_path)
    assert lock_data_1h is not None
    stale_1h, reason_1h = L24._is_stale(lock_data_1h, now_ts)
    assert stale_1h is False, f"1h cross-host lock should be fresh, got reason={reason_1h}"

    # 7h old cross-host → stale by age
    _make_lock(lock_path, pid=12345, hostname=other_host, age_hours=7)
    lock_data_7h = L24._read_lock(lock_path)
    assert lock_data_7h is not None
    stale_7h, reason_7h = L24._is_stale(lock_data_7h, now_ts)
    assert stale_7h is True, f"7h cross-host lock should be stale, got reason={reason_7h}"
    assert reason_7h == "age"
