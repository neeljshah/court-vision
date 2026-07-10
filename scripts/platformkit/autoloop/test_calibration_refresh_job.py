"""Per-file test for scripts.platformkit.autoloop.calibration_refresh_job.

Acceptance criteria:
1. Artifact < 72h old -> skip, build_fn not called.
2. Artifact >= 72h old -> build_fn called.
3. No artifact at all -> treated as due, build_fn called.
4. build_fn raising propagates (isolated one level up by
   maintenance_templates.run_all's own try/except -- not re-caught here).
No real scoreboard build (sub-tuners/parquet loads) in any test.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_calibration_refresh_job.py -q
"""
from __future__ import annotations

import os
import time

import pytest

from scripts.platformkit.autoloop import calibration_refresh_job as CJ


def _touch_artifact(tmp_path, age_h):
    p = tmp_path / "calibration_scoreboard_latest.json"
    p.write_text("{}", encoding="utf-8")
    os.utime(p, (time.time() - age_h * 3600, time.time() - age_h * 3600))
    return p


def test_fresh_artifact_skips_no_build_call(tmp_path):
    p = _touch_artifact(tmp_path, age_h=1.0)
    calls = []
    out = CJ.run_calibration_refresh(
        artifact_path=p, build_fn=lambda: calls.append("build"))
    assert out["status"] == "skipped"
    assert out["age_h"] == pytest.approx(1.0, abs=0.05)
    assert calls == []


def test_stale_artifact_runs_build(tmp_path):
    p = _touch_artifact(tmp_path, age_h=100.0)
    calls = []
    out = CJ.run_calibration_refresh(
        artifact_path=p, build_fn=lambda: calls.append("build"))
    assert out["status"] == "ran"
    assert calls == ["build"]


def test_missing_artifact_treated_as_due(tmp_path):
    p = tmp_path / "calibration_scoreboard_latest.json"
    calls = []
    out = CJ.run_calibration_refresh(
        artifact_path=p, build_fn=lambda: calls.append("build"))
    assert out["status"] == "ran"
    assert out["age_h"] is None
    assert calls == ["build"]


def test_build_raise_propagates_uncaught(tmp_path):
    p = _touch_artifact(tmp_path, age_h=100.0)

    def _boom():
        raise RuntimeError("build boom")

    with pytest.raises(RuntimeError, match="build boom"):
        CJ.run_calibration_refresh(artifact_path=p, build_fn=_boom)


def test_watermarks_param_accepted_and_ignored(tmp_path):
    """Call-shape uniformity with the other maintenance jobs -- watermarks
    is accepted positionally but never read or mutated."""
    p = _touch_artifact(tmp_path, age_h=1.0)
    watermarks = {"unrelated": "untouched"}
    out = CJ.run_calibration_refresh(watermarks, artifact_path=p, build_fn=lambda: None)
    assert out["status"] == "skipped"
    assert watermarks == {"unrelated": "untouched"}
