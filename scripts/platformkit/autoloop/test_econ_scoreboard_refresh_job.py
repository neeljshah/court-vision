"""Per-file test for scripts.platformkit.autoloop.econ_scoreboard_refresh_job.

Acceptance criteria:
1. All 3 artifacts present and <24h old -> skip, no refresh fn called.
2. Oldest artifact >=24h old -> all 3 refresh fns called.
3. Any artifact missing -> treated as due, all 3 refresh fns called.
4. A refresh fn raising propagates (isolated one level up by
   maintenance_templates.run_all's own try/except -- not re-caught here).

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_econ_scoreboard_refresh_job.py -q
"""
from __future__ import annotations

import os
import time

import pytest

from scripts.platformkit.autoloop import econ_scoreboard_refresh_job as ER


def _touch_all(tmp_path, age_h):
    for name in ER._ARTIFACTS:
        p = tmp_path / name
        p.write_text("{}", encoding="utf-8")
        os.utime(p, (time.time() - age_h * 3600, time.time() - age_h * 3600))


def test_fresh_artifacts_skip_no_calls(tmp_path):
    _touch_all(tmp_path, age_h=1.0)
    calls = []
    out = ER.run_econ_scoreboard_refresh(
        ops_dir=tmp_path,
        after_cost_fn=lambda: calls.append("after_cost"),
        beat_the_line_fn=lambda: calls.append("beat_the_line"),
        execution_quality_fn=lambda: calls.append("execution_quality"),
    )
    assert out["status"] == "skipped"
    assert out["age_h"] == pytest.approx(1.0, abs=0.05)
    assert calls == []


def test_stale_artifacts_run_all_three(tmp_path):
    _touch_all(tmp_path, age_h=30.0)
    calls = []
    out = ER.run_econ_scoreboard_refresh(
        ops_dir=tmp_path,
        after_cost_fn=lambda: calls.append("after_cost"),
        beat_the_line_fn=lambda: calls.append("beat_the_line"),
        execution_quality_fn=lambda: calls.append("execution_quality"),
    )
    assert out["status"] == "ran"
    assert calls == ["after_cost", "beat_the_line", "execution_quality"]


def test_missing_artifact_treated_as_due(tmp_path):
    (tmp_path / "after_cost_scoreboard.json").write_text("{}", encoding="utf-8")
    (tmp_path / "beat_the_line.json").write_text("{}", encoding="utf-8")
    # execution_quality.json missing entirely
    calls = []
    out = ER.run_econ_scoreboard_refresh(
        ops_dir=tmp_path,
        after_cost_fn=lambda: calls.append("after_cost"),
        beat_the_line_fn=lambda: calls.append("beat_the_line"),
        execution_quality_fn=lambda: calls.append("execution_quality"),
    )
    assert out["status"] == "ran"
    assert out["age_h"] is None
    assert calls == ["after_cost", "beat_the_line", "execution_quality"]


def test_refresh_raise_propagates_uncaught(tmp_path):
    _touch_all(tmp_path, age_h=48.0)

    def _boom():
        raise RuntimeError("after_cost boom")

    with pytest.raises(RuntimeError, match="after_cost boom"):
        ER.run_econ_scoreboard_refresh(ops_dir=tmp_path, after_cost_fn=_boom,
                                       beat_the_line_fn=lambda: None,
                                       execution_quality_fn=lambda: None)


def test_watermarks_param_accepted_and_ignored(tmp_path):
    _touch_all(tmp_path, age_h=1.0)
    watermarks = {"unrelated": "untouched"}
    out = ER.run_econ_scoreboard_refresh(
        watermarks, ops_dir=tmp_path, after_cost_fn=lambda: None,
        beat_the_line_fn=lambda: None, execution_quality_fn=lambda: None)
    assert out["status"] == "skipped"
    assert watermarks == {"unrelated": "untouched"}


def test_default_callables_pass_empty_argv(monkeypatch):
    """Same regression class as clv_refresh_job's test_default_callables_pass_empty_argv:
    bare main() falls back to sys.argv[1:] -- the m38 daemon's own args -- unless
    argv=[] is passed explicitly."""
    from scripts.platformkit.econ import after_cost_scoreboard as A
    from scripts.platformkit.econ import beat_the_line as B
    from scripts.platformkit.clv import execution_quality as E
    seen = {}
    monkeypatch.setattr(A, "main", lambda argv=None, **kw: seen.setdefault("a", argv))
    monkeypatch.setattr(B, "main", lambda argv=None, **kw: seen.setdefault("b", argv))
    monkeypatch.setattr(E, "main", lambda argv=None, **kw: seen.setdefault("e", argv))
    monkeypatch.setattr("sys.argv", ["m38_autoloop", "--interval", "86400"])
    ER._default_after_cost()
    ER._default_beat_the_line()
    ER._default_execution_quality()
    assert seen == {"a": [], "b": [], "e": []}
