"""Per-file test for scripts.platformkit.autoloop.statcast_refresh_job.

Acceptance criteria:
1. Parquet < 24h old -> skip, run_fn not called.
2. Parquet >= 24h old -> run_fn called, result passed through (season +
   parquet_status).
3. No parquet at all -> treated as due, run_fn called.
4. A non-OK run_season status (e.g. PARTIAL_CAPPED) is NOT an error --
   passed through honestly, status stays "ran".
5. run_fn raising propagates (isolated one level up by
   maintenance_templates.run_all's own try/except -- not re-caught here).
6. _default_run calls savant_backfill.run_season(season, max_seconds=480)
   directly -- never _main()/argparse -- with the CURRENT ET-year season
   (never a frozen literal).
7. sys.argv is untouched by _default_run (the cac9f26f class).
8. Registration: statcast_refresh appears in maintenance_templates._JOB_TABLE.

No real run_season() call in any test below -- it makes live network
requests (season fetch), far too slow for the per-file test gate.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_statcast_refresh_job.py -q
"""
from __future__ import annotations

import os
import sys
import time

import pytest

from scripts.platformkit.autoloop import statcast_refresh_job as SR


def _touch_parquet(tmp_path, age_h):
    p = tmp_path / "savant_full__2026.parquet"
    p.write_text("x", encoding="utf-8")
    os.utime(p, (time.time() - age_h * 3600, time.time() - age_h * 3600))
    return p


def _fake_result(status="OK", season=2026):
    return {"season": season, "status": status, "raw_rows": 1234,
           "days_requested": 90, "days_fetched_this_run": 1,
           "days_available_total": 90, "stopped_reason": None}


def test_fresh_parquet_skips_no_run_call(tmp_path):
    p = _touch_parquet(tmp_path, age_h=1.0)
    calls = []
    out = SR.run_statcast_refresh(
        stamp_path=p, run_fn=lambda: (calls.append("run"), _fake_result())[1])
    assert out["status"] == "skipped"
    assert out["age_h"] == pytest.approx(1.0, abs=0.05)
    assert calls == []


def test_stale_parquet_runs_and_passes_result_through(tmp_path):
    p = _touch_parquet(tmp_path, age_h=30.0)
    calls = []
    out = SR.run_statcast_refresh(
        stamp_path=p, run_fn=lambda: (calls.append("run"), _fake_result())[1])
    assert out["status"] == "ran"
    assert calls == ["run"]
    assert out["season"] == 2026
    assert out["parquet_status"] == "OK"


def test_missing_parquet_treated_as_due(tmp_path):
    p = tmp_path / "savant_full__2026.parquet"
    calls = []
    out = SR.run_statcast_refresh(
        stamp_path=p, run_fn=lambda: (calls.append("run"), _fake_result())[1])
    assert out["status"] == "ran"
    assert out["age_h"] is None
    assert calls == ["run"]


def test_partial_capped_status_written_honestly_not_an_error(tmp_path):
    p = tmp_path / "savant_full__2026.parquet"
    out = SR.run_statcast_refresh(
        stamp_path=p, run_fn=lambda: _fake_result(status="PARTIAL_CAPPED"))
    assert out["status"] == "ran"
    assert out["parquet_status"] == "PARTIAL_CAPPED"


def test_run_raise_propagates_uncaught(tmp_path):
    p = _touch_parquet(tmp_path, age_h=30.0)

    def _boom():
        raise RuntimeError("savant_backfill boom")

    with pytest.raises(RuntimeError, match="savant_backfill boom"):
        SR.run_statcast_refresh(stamp_path=p, run_fn=_boom)
    # stale parquet from before the raise is untouched -- next cycle retries
    assert p.read_text(encoding="utf-8") == "x"


def test_watermarks_param_accepted_and_ignored(tmp_path):
    """Call-shape uniformity with the other maintenance jobs -- watermarks
    is accepted positionally but never read or mutated."""
    p = _touch_parquet(tmp_path, age_h=1.0)
    watermarks = {"unrelated": "untouched"}
    out = SR.run_statcast_refresh(watermarks, stamp_path=p, run_fn=lambda: _fake_result())
    assert out["status"] == "skipped"
    assert watermarks == {"unrelated": "untouched"}


def test_default_run_calls_run_season_directly_with_current_et_season(monkeypatch):
    """_default_run must call run_season() (never _main()/argparse) with the
    CURRENT ET-year season and max_seconds=480 -- verifies the exact args."""
    seen = {}

    class _FakeSB:
        @staticmethod
        def run_season(season, max_seconds=None, cache_dir=None):
            seen.update(season=season, max_seconds=max_seconds)
            return _fake_result(season=season)

    monkeypatch.setitem(sys.modules, "domains.mlb.savant_backfill", _FakeSB)
    result = SR._default_run()
    assert seen == {"season": SR._current_season(), "max_seconds": 480.0}
    assert result["status"] == "OK"


def test_current_season_derived_not_frozen(monkeypatch):
    """Season must track the ET calendar year, not a frozen literal."""
    monkeypatch.setattr(SR, "now_et_day", lambda: "2031-01-05")
    assert SR._current_season() == 2031


def test_default_run_no_argv_touched(monkeypatch):
    """Regression guard for the M16-class argv leak (cac9f26f): calling
    run_season() directly (not _main()) must never read/mutate sys.argv."""
    before = list(sys.argv)
    monkeypatch.setattr(sys, "argv", ["m38_autoloop", "--interval", "86400"])

    class _FakeSB:
        @staticmethod
        def run_season(season, max_seconds=None, cache_dir=None):
            return _fake_result(season=season)

    monkeypatch.setitem(sys.modules, "domains.mlb.savant_backfill", _FakeSB)
    SR._default_run()
    assert sys.argv == ["m38_autoloop", "--interval", "86400"]
    sys.argv = before


def test_registered_in_job_table():
    from scripts.platformkit.autoloop import maintenance_templates as MT
    keys = [row[0] for row in MT._JOB_TABLE]
    assert "statcast_refresh" in keys
    row = next(r for r in MT._JOB_TABLE if r[0] == "statcast_refresh")
    assert row[1] == "scripts.platformkit.autoloop.statcast_refresh_job"
    assert row[2] == "run_statcast_refresh"
    assert "watermarks" in row[3]


def test_failed_run_leaves_stamp_stale_so_next_tick_retries(tmp_path):
    # Opus judge 2026-07-13 BLOCKER: savant_backfill rewrites the parquet even
    # on FAILED_CONSECUTIVE, so a parquet-mtime watermark re-arms without
    # retrying. The gate is now the job's OWN stamp, written only on success.
    p = tmp_path / "statcast_refresh_latest.json"
    out1 = SR.run_statcast_refresh(
        stamp_path=p, run_fn=lambda: _fake_result(status="FAILED_CONSECUTIVE"))
    assert out1["status"] == "ran" and out1["stamped"] is False
    assert not p.exists()  # no stamp -> still due
    out2 = SR.run_statcast_refresh(
        stamp_path=p, run_fn=lambda: _fake_result(status="OK"))
    assert out2["status"] == "ran" and out2["stamped"] is True  # RETRIED
    assert p.exists()
    out3 = SR.run_statcast_refresh(stamp_path=p, run_fn=lambda: _fake_result())
    assert out3["status"] == "skipped"  # success stamp now gates


def test_partial_capped_does_not_stamp(tmp_path):
    p = tmp_path / "statcast_refresh_latest.json"
    out = SR.run_statcast_refresh(
        stamp_path=p, run_fn=lambda: _fake_result(status="PARTIAL_CAPPED"))
    assert out["stamped"] is False and not p.exists()  # continues next tick
