"""Per-file test for scripts.platformkit.autoloop.clv_refresh_job.

Acceptance criteria:
1. Newest clv_reconcile_*.json < 24h old -> skip, neither reconcile_fn nor
   scoreboard_fn is called.
2. Newest clv_reconcile_*.json >= 24h old -> both fns called in order.
3. No clv_reconcile_*.json at all -> treated as due, both fns called.
4. reconcile_fn/scoreboard_fn raising propagates (isolated one level up by
   maintenance_templates.run_all's own try/except -- not re-caught here).
No real reconciler/scoreboard run over full history in any test.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_clv_refresh_job.py -q
"""
from __future__ import annotations

import os
import time

import pytest

from scripts.platformkit.autoloop import clv_refresh_job as CR


def _touch_reconcile(tmp_path, age_h):
    p = tmp_path / "clv_reconcile_moneyline.json"
    p.write_text("{}", encoding="utf-8")
    os.utime(p, (time.time() - age_h * 3600, time.time() - age_h * 3600))
    return p


def test_fresh_file_skips_no_calls(tmp_path):
    _touch_reconcile(tmp_path, age_h=1.0)
    calls = []
    out = CR.run_clv_refresh(
        ops_dir=tmp_path,
        reconcile_fn=lambda: calls.append("reconcile"),
        scoreboard_fn=lambda: calls.append("scoreboard"),
    )
    assert out["status"] == "skipped"
    assert out["age_h"] == pytest.approx(1.0, abs=0.05)
    assert calls == []


def test_stale_file_runs_write_closes_then_reconciler_then_scoreboard(tmp_path):
    _touch_reconcile(tmp_path, age_h=30.0)
    calls = []
    out = CR.run_clv_refresh(
        ops_dir=tmp_path,
        write_closes_fn=lambda: calls.append("write_closes"),
        reconcile_fn=lambda: calls.append("reconcile"),
        scoreboard_fn=lambda: calls.append("scoreboard"),
    )
    assert out["status"] == "ran"
    assert calls == ["write_closes", "reconcile", "scoreboard"]


def test_missing_files_treated_as_due(tmp_path):
    calls = []
    out = CR.run_clv_refresh(
        ops_dir=tmp_path,
        write_closes_fn=lambda: calls.append("write_closes"),
        reconcile_fn=lambda: calls.append("reconcile"),
        scoreboard_fn=lambda: calls.append("scoreboard"),
    )
    assert out["status"] == "ran"
    assert out["age_h"] is None
    assert calls == ["write_closes", "reconcile", "scoreboard"]


def test_reconcile_raise_propagates_uncaught(tmp_path):
    _touch_reconcile(tmp_path, age_h=48.0)

    def _boom():
        raise RuntimeError("reconcile boom")

    with pytest.raises(RuntimeError, match="reconcile boom"):
        CR.run_clv_refresh(ops_dir=tmp_path, write_closes_fn=lambda: None,
                           reconcile_fn=_boom, scoreboard_fn=lambda: None)


def test_write_closes_failure_isolated_reconcile_and_scoreboard_still_run(tmp_path):
    """W1 fix: a write_closes derive failure must NOT block the reconcile/
    scoreboard refresh that follows -- error-isolated, unlike reconcile_fn's
    raise (which IS allowed to propagate, see test above)."""
    _touch_reconcile(tmp_path, age_h=48.0)
    calls = []

    def _boom():
        raise RuntimeError("write_closes boom")

    out = CR.run_clv_refresh(
        ops_dir=tmp_path,
        write_closes_fn=_boom,
        reconcile_fn=lambda: calls.append("reconcile"),
        scoreboard_fn=lambda: calls.append("scoreboard"),
    )
    assert out["status"] == "ran"
    assert calls == ["reconcile", "scoreboard"]


def test_default_write_closes_calls_kx_ticker_close_for_known_sports(monkeypatch):
    from scripts.platformkit.clv import kx_ticker_close as K
    seen = []
    monkeypatch.setattr(K, "write_closes", lambda s: seen.append(s) or {})
    CR._default_write_closes()
    assert seen == list(CR._KX_SPORTS)


def test_watermarks_param_accepted_and_ignored(tmp_path):
    """Call-shape uniformity with the other maintenance jobs -- watermarks
    is accepted positionally but never read or mutated."""
    _touch_reconcile(tmp_path, age_h=1.0)
    watermarks = {"unrelated": "untouched"}
    out = CR.run_clv_refresh(watermarks, ops_dir=tmp_path,
                             reconcile_fn=lambda: None, scoreboard_fn=lambda: None)
    assert out["status"] == "skipped"
    assert watermarks == {"unrelated": "untouched"}


def test_default_callables_pass_empty_argv(monkeypatch):
    """Regression: first live fire ran R.main() bare -> main() fell back to
    sys.argv[1:] = the m38 DAEMON's own args -> wrote clv_reconcile_--interval
    .json instead of the real channels. argv=[] must be passed explicitly."""
    from scripts.platformkit.clv import clv_result_reconciler as R
    from scripts.platformkit.clv import clv_scoreboard as S
    seen = {}
    monkeypatch.setattr(R, "main", lambda argv=None, **kw: seen.setdefault("r", argv))
    monkeypatch.setattr(S, "main", lambda argv=None, **kw: seen.setdefault("s", argv))
    monkeypatch.setattr("sys.argv", ["m38_autoloop", "--interval", "86400"])
    CR._default_reconcile()
    CR._default_scoreboard()
    assert seen["r"] == [] and seen["s"] == []
