"""Per-file test for scripts.platformkit.autoloop.pregame_benchmark_job.

Acceptance criteria:
1. Artifact < 168h (7d) old -> skip, run_fn not called.
2. Artifact >= 168h old -> run_fn called, ops-json written (result passed
   through verbatim under pregame_crps_scoreboard).
3. No artifact at all -> treated as due, run_fn called.
4. A benchmark VERDICT (e.g. NOT_TESTABLE/UNDERPOWERED) is NOT an error --
   written honestly to the ops-json, status stays "ran".
5. run_fn raising propagates (isolated one level up by
   maintenance_templates.run_all's own try/except -- not re-caught here);
   no ops-json is written on that path (stale artifact, retried next cycle).
6. _default_run calls run_mlb.run() directly with its own CLI-default
   window (start/end/max_games) -- never _main()/argparse, so no daemon
   argv can leak in (the cac9f26f class); sys.argv is asserted untouched.
7. Registration: pregame_benchmark appears in
   maintenance_templates._JOB_TABLE.

No real run_mlb.run() call in any test below -- the real benchmark measures
in minutes (1m16s wall, 2026-07-12), too slow for the per-file test gate;
that timing was measured directly (not injected) before this job was built.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_pregame_benchmark_job.py -q
"""
from __future__ import annotations

import os
import sys
import time

import pytest

from scripts.platformkit.autoloop import pregame_benchmark_job as PB


def _touch_artifact(tmp_path, age_h):
    p = tmp_path / "pregame_crps_scoreboard_latest.json"
    p.write_text("{}", encoding="utf-8")
    os.utime(p, (time.time() - age_h * 3600, time.time() - age_h * 3600))
    return p


def _fake_result(verdict="UNDERPOWERED", n_scored=300):
    return {"sport": "mlb", "edge_claimed": False, "verdict": verdict,
           "n_scored": n_scored, "paired_delta_95ci": [-0.1, 0.05]}


def test_fresh_artifact_skips_no_run_call(tmp_path):
    p = _touch_artifact(tmp_path, age_h=1.0)
    calls = []
    out = PB.run_pregame_benchmark(
        artifact_path=p, run_fn=lambda: (calls.append("run"), _fake_result())[1])
    assert out["status"] == "skipped"
    assert out["age_h"] == pytest.approx(1.0, abs=0.05)
    assert calls == []


def test_stale_artifact_runs_and_writes_ops_json(tmp_path):
    p = tmp_path / "pregame_crps_scoreboard_latest.json"
    p.write_text("{}", encoding="utf-8")
    os.utime(p, (time.time() - 200 * 3600, time.time() - 200 * 3600))
    calls = []
    out = PB.run_pregame_benchmark(
        artifact_path=p, run_fn=lambda: (calls.append("run"), _fake_result())[1])
    assert out["status"] == "ran"
    assert calls == ["run"]
    assert out["verdict"] == "UNDERPOWERED"
    assert out["n_scored"] == 300
    assert p.exists()
    import json
    doc = json.loads(p.read_text(encoding="ascii"))
    assert doc["pregame_crps_scoreboard"]["verdict"] == "UNDERPOWERED"
    assert doc["pregame_crps_scoreboard"]["edge_claimed"] is False
    assert doc["pregame_crps_scoreboard"]["source_tool"].endswith("run_mlb.py")


def test_missing_artifact_treated_as_due(tmp_path):
    p = tmp_path / "pregame_crps_scoreboard_latest.json"
    calls = []
    out = PB.run_pregame_benchmark(
        artifact_path=p, run_fn=lambda: (calls.append("run"), _fake_result())[1])
    assert out["status"] == "ran"
    assert out["age_h"] is None
    assert calls == ["run"]


def test_not_testable_verdict_written_honestly_not_an_error(tmp_path):
    p = tmp_path / "pregame_crps_scoreboard_latest.json"
    out = PB.run_pregame_benchmark(
        artifact_path=p, run_fn=lambda: _fake_result(verdict="NOT_TESTABLE", n_scored=0))
    assert out["status"] == "ran"
    assert out["verdict"] == "NOT_TESTABLE"
    import json
    doc = json.loads(p.read_text(encoding="ascii"))
    assert doc["pregame_crps_scoreboard"]["verdict"] == "NOT_TESTABLE"


def test_run_raise_propagates_uncaught_no_artifact_written(tmp_path):
    p = _touch_artifact(tmp_path, age_h=200.0)

    def _boom():
        raise RuntimeError("run_mlb boom")

    with pytest.raises(RuntimeError, match="run_mlb boom"):
        PB.run_pregame_benchmark(artifact_path=p, run_fn=_boom)
    # stale artifact from before the raise is untouched -- next cycle retries
    import json
    assert json.loads(p.read_text(encoding="utf-8")) == {}


def test_watermarks_param_accepted_and_ignored(tmp_path):
    """Call-shape uniformity with the other maintenance jobs -- watermarks
    is accepted positionally but never read or mutated."""
    p = _touch_artifact(tmp_path, age_h=1.0)
    watermarks = {"unrelated": "untouched"}
    out = PB.run_pregame_benchmark(watermarks, artifact_path=p, run_fn=lambda: _fake_result())
    assert out["status"] == "skipped"
    assert watermarks == {"unrelated": "untouched"}


def test_default_run_calls_run_mlb_directly_with_cli_defaults(monkeypatch):
    """_default_run must call run_mlb.run() (never _main()/argparse) with
    run_mlb.py's own CLI-default window -- verifies the exact args passed."""
    seen = {}

    class _FakeRM:
        @staticmethod
        def run(start=None, end=None, max_games=None, seed=0):
            seen.update(start=start, end=end, max_games=max_games)
            return _fake_result()

    monkeypatch.setitem(sys.modules, "scripts.platformkit.benchmarks.crps_market.run_mlb", _FakeRM)
    result = PB._default_run()
    assert seen == {"start": "2026-06-18", "end": "2026-07-08", "max_games": 300}
    assert result["verdict"] == "UNDERPOWERED"


def test_default_run_no_argv_touched(monkeypatch):
    """Regression guard for the M16-class argv leak (cac9f26f): calling
    run_mlb.run() directly (not _main()) must never read/mutate sys.argv."""
    before = list(sys.argv)
    monkeypatch.setattr(sys, "argv", ["m38_autoloop", "--interval", "86400"])

    class _FakeRM:
        @staticmethod
        def run(start=None, end=None, max_games=None, seed=0):
            return _fake_result()

    monkeypatch.setitem(sys.modules, "scripts.platformkit.benchmarks.crps_market.run_mlb", _FakeRM)
    PB._default_run()
    assert sys.argv == ["m38_autoloop", "--interval", "86400"]
    sys.argv = before


def test_registered_in_job_table():
    from scripts.platformkit.autoloop import maintenance_templates as MT
    keys = [row[0] for row in MT._JOB_TABLE]
    assert "pregame_benchmark" in keys
    row = next(r for r in MT._JOB_TABLE if r[0] == "pregame_benchmark")
    assert row[1] == "scripts.platformkit.autoloop.pregame_benchmark_job"
    assert row[2] == "run_pregame_benchmark"
    assert "watermarks" in row[3]
