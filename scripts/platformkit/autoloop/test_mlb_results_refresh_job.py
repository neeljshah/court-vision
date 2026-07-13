"""Per-file test for scripts.platformkit.autoloop.mlb_results_refresh_job.

Acceptance criteria:
1. Stamp < 24h old -> skip, run_fn not called.
2. Stamp >= 24h old (or missing) -> run_fn called, stamp written with the
   post-run row count.
3. row_count shrinks after the run -> NO stamp (corruption guard); status
   stays "ran", stamped is False.
4. run_fn raises -> caught, NOT re-raised (unlike M20's uncaught-propagate
   convention -- ingest_current shells out to curl per season, a transient
   network failure must not crash the autoloop tick); no stamp, no crash.
5. No parquet at all after the run -> no stamp (nothing to compare/report).
6. watermarks param accepted and ignored (call-shape uniformity).
7. _default_run calls ingest_current.build_current() directly (never
   _main()) with no end_date override.
8. Registration: mlb_results_refresh appears in maintenance_templates._JOB_TABLE.

No real build_current()/curl call in any test below -- real network fetch,
far too slow (and non-hermetic) for the per-file test gate.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_mlb_results_refresh_job.py -q
"""
from __future__ import annotations

import os
import sys
import time

import pytest

from scripts.platformkit.autoloop import mlb_results_refresh_job as RR


def _touch_stamp(tmp_path, age_h):
    p = tmp_path / "mlb_results_refresh_latest.json"
    p.write_text("{}", encoding="ascii")
    os.utime(p, (time.time() - age_h * 3600, time.time() - age_h * 3600))
    return p


def test_fresh_stamp_skips_no_run_call(tmp_path):
    sp = _touch_stamp(tmp_path, age_h=1.0)
    calls = []
    out = RR.run_mlb_results_refresh(
        stamp_path=sp, run_fn=lambda: calls.append("run"))
    assert out["status"] == "skipped"
    assert out["age_h"] == pytest.approx(1.0, abs=0.05)
    assert calls == []


def test_stale_stamp_runs_and_writes_stamp_on_success(tmp_path):
    sp = tmp_path / "mlb_results_refresh_latest.json"
    pq = tmp_path / "games_current.parquet"
    pq.write_text("x", encoding="utf-8")
    counts = iter([100, 111])  # before, after
    out = RR.run_mlb_results_refresh(
        stamp_path=sp, parquet_path=pq,
        row_count_fn=lambda p: next(counts),
        run_fn=lambda: None)
    assert out["status"] == "ran"
    assert out["stamped"] is True
    assert out["rows_before"] == 100 and out["rows_after"] == 111
    assert sp.exists()


def test_missing_stamp_treated_as_due(tmp_path):
    sp = tmp_path / "mlb_results_refresh_latest.json"
    pq = tmp_path / "games_current.parquet"
    calls = []
    out = RR.run_mlb_results_refresh(
        stamp_path=sp, parquet_path=pq,
        row_count_fn=lambda p: (calls.append("count"), None)[1],
        run_fn=lambda: calls.append("run"))
    assert out["age_h"] is None
    assert "run" in calls


def test_row_shrink_is_not_stamped(tmp_path):
    sp = tmp_path / "mlb_results_refresh_latest.json"
    pq = tmp_path / "games_current.parquet"
    counts = iter([500, 480])  # shrank -- corruption guard trips
    out = RR.run_mlb_results_refresh(
        stamp_path=sp, parquet_path=pq,
        row_count_fn=lambda p: next(counts),
        run_fn=lambda: None)
    assert out["status"] == "ran"
    assert out["stamped"] is False
    assert out["reason"] == "row_shrink"
    assert not sp.exists()


def test_run_raise_caught_not_crashed(tmp_path):
    sp = tmp_path / "mlb_results_refresh_latest.json"
    pq = tmp_path / "games_current.parquet"

    def _boom():
        raise RuntimeError("curl: network unreachable")

    out = RR.run_mlb_results_refresh(
        stamp_path=sp, parquet_path=pq,
        row_count_fn=lambda p: 100, run_fn=_boom)
    assert out["status"] == "ran"
    assert out["stamped"] is False
    assert out["reason"] == "error"
    assert "network unreachable" in out["error"]
    assert not sp.exists()


def test_no_parquet_after_run_not_stamped(tmp_path):
    sp = tmp_path / "mlb_results_refresh_latest.json"
    pq = tmp_path / "games_current.parquet"
    out = RR.run_mlb_results_refresh(
        stamp_path=sp, parquet_path=pq,
        row_count_fn=lambda p: None, run_fn=lambda: None)
    assert out["status"] == "ran"
    assert out["stamped"] is False
    assert out["reason"] == "no_parquet_after_run"
    assert not sp.exists()


def test_watermarks_param_accepted_and_ignored(tmp_path):
    sp = _touch_stamp(tmp_path, age_h=1.0)
    watermarks = {"unrelated": "untouched"}
    out = RR.run_mlb_results_refresh(watermarks, stamp_path=sp, run_fn=lambda: None)
    assert out["status"] == "skipped"
    assert watermarks == {"unrelated": "untouched"}


def test_default_run_calls_build_current_directly_no_end_date_override(monkeypatch):
    """_default_run must call build_current() (never _main()) and must NOT
    pass an end_date override -- it inherits build_current's own yesterday
    default rather than duplicating that date logic here."""
    seen = {}

    class _FakeIC:
        @staticmethod
        def build_current(**kwargs):
            seen.update(kwargs)
            return None

    monkeypatch.setitem(sys.modules, "domains.mlb.ingest_current", _FakeIC)
    RR._default_run()
    assert seen == {}


def test_registered_in_job_table():
    from scripts.platformkit.autoloop import maintenance_templates as MT
    keys = [row[0] for row in MT._JOB_TABLE]
    assert "mlb_results_refresh" in keys
    row = next(r for r in MT._JOB_TABLE if r[0] == "mlb_results_refresh")
    assert row[1] == "scripts.platformkit.autoloop.mlb_results_refresh_job"
    assert row[2] == "run_mlb_results_refresh"
    assert "watermarks" in row[3]
