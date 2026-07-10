"""Per-file test for scripts.platformkit.autoloop.execution_cadence_job.

Covers: hourly/weekly cadence gating (due on first run, skipped within
window), per-stage isolation (one stage failing does not block the rest or
the watermark), and run_all()'s single-hook-point shape. All heavy stage
calls (composer/dryrun/reconcile/entry_timing) are injected/mocked -- no
live feed or network calls in this test.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_execution_cadence_job.py -q
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.platformkit.autoloop import execution_cadence_job as ECJ


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_execution_stages_due_on_first_run_calls_all_three():
    watermarks = {}
    calls = []
    out = ECJ.run_execution_stages(
        watermarks,
        compose_fn=lambda: calls.append("compose") or {"count": 1},
        dryrun_fn=lambda: calls.append("dryrun") or {"n_written": 1},
        reconcile_fn=lambda: calls.append("reconcile") or {"n_fills": 1},
    )
    assert out["status"] == "ran"
    assert calls == ["compose", "dryrun", "reconcile"]
    assert ECJ._WM_STAGES in watermarks
    assert "last_run_ts" in watermarks[ECJ._WM_STAGES]


def test_execution_stages_skipped_within_hourly_cadence():
    watermarks = {ECJ._WM_STAGES: {"last_run_ts": _iso(datetime.now(timezone.utc) - timedelta(minutes=5))}}
    calls = []
    out = ECJ.run_execution_stages(
        watermarks,
        compose_fn=lambda: calls.append("compose"),
        dryrun_fn=lambda: calls.append("dryrun"),
        reconcile_fn=lambda: calls.append("reconcile"),
    )
    assert out == {"status": "skipped_cadence"}
    assert calls == []


def test_execution_stages_due_after_hourly_cadence_elapsed():
    watermarks = {ECJ._WM_STAGES: {"last_run_ts": _iso(datetime.now(timezone.utc) - timedelta(hours=2))}}
    calls = []
    out = ECJ.run_execution_stages(
        watermarks,
        compose_fn=lambda: calls.append("compose") or {},
        dryrun_fn=lambda: calls.append("dryrun") or {},
        reconcile_fn=lambda: calls.append("reconcile") or {},
    )
    assert out["status"] == "ran"
    assert calls == ["compose", "dryrun", "reconcile"]


def test_execution_stages_isolates_one_stage_failure():
    watermarks = {}
    calls = []

    def boom():
        raise RuntimeError("composer down")

    out = ECJ.run_execution_stages(
        watermarks, compose_fn=boom,
        dryrun_fn=lambda: calls.append("dryrun") or {},
        reconcile_fn=lambda: calls.append("reconcile") or {},
    )
    assert out["composer"]["status"] == "error"
    assert "composer down" in out["composer"]["error"]
    assert calls == ["dryrun", "reconcile"]  # a failed compose never blocks the rest
    assert ECJ._WM_STAGES in watermarks  # watermark still advances -- no infinite re-fire


def test_entry_timing_refresh_due_then_skipped_within_week():
    watermarks = {}
    calls = []
    out1 = ECJ.run_entry_timing_refresh(
        watermarks, timing_fn=lambda: calls.append(1) or {"policies": {"nba": {}}})
    assert out1["status"] == "ran"
    assert out1["sports_covered"] == ["nba"]
    assert calls == [1]

    out2 = ECJ.run_entry_timing_refresh(watermarks, timing_fn=lambda: calls.append(2) or {})
    assert out2 == {"status": "skipped_cadence"}
    assert calls == [1]  # not called again -- still inside the weekly window


def test_entry_timing_refresh_due_after_weekly_cadence_elapsed():
    watermarks = {ECJ._WM_TIMING: {"last_run_ts": _iso(datetime.now(timezone.utc) - timedelta(days=8))}}
    calls = []
    out = ECJ.run_entry_timing_refresh(
        watermarks, timing_fn=lambda: calls.append(1) or {"policies": {}})
    assert out["status"] == "ran"
    assert calls == [1]


def test_run_all_merges_both_jobs_and_isolates_failure(monkeypatch):
    monkeypatch.setattr(ECJ, "run_execution_stages", lambda wm: {"status": "ran_stub"})

    def boom_timing(wm):
        raise RuntimeError("timing study down")

    monkeypatch.setattr(ECJ, "run_entry_timing_refresh", boom_timing)
    out = ECJ.run_all({})
    assert out["execution_stages"] == {"status": "ran_stub"}
    assert out["entry_timing_refresh"]["status"] == "error"
    assert "timing study down" in out["entry_timing_refresh"]["error"]
