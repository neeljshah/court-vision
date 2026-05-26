"""tests/test_daily_workflow.py — R26_S3 orchestrator coverage.

Each test drives the orchestrator into a tmp_path so the production
vault + dashboard cache files are never touched. We seed a fake
``live_rec_tracker.run_engine`` (via a monkeypatched module attr) so
the evening stage produces a real snapshot file on disk without any
network / real engine dependency.

Coverage matrix (>= 8 tests):
  1. evening stage produces a snapshot file
  2. morning stage produces settle + reconcile + report results
  3. --dry-run leaves no side effects
  4. one failing step does not abort the others
  5. --summary parses the log correctly
  6. idempotent — running twice doesn't double-snapshot
  7. subprocess-safe — no shell strings, all args list-form (no os.system)
  8. critical alert fires on a step failure
  9. cron-helper: parse_log handles missing + malformed lines safely
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts import daily_workflow as dw  # noqa: E402


# --------------------------------------------------------------------------- #
# Shared fixtures                                                              #
# --------------------------------------------------------------------------- #
DATE = "2099-01-15"   # synthetic future date — never collides with real data
YEST = "2099-01-14"


def _fake_run_engine(*, bankroll, top, date, min_edge):
    """Stand-in for scripts.live_recommendation_engine.run_engine.

    Returns a deterministic single-rec payload so the snapshot file is
    populated. We never call the real engine in tests.
    """
    return {
        "date": date,
        "bankroll": bankroll,
        "top": top,
        "min_edge": min_edge,
        "engine_version": "test",
        "reason": "synthetic",
        "n_recs": 1,
        "recommendations": [{
            "player": "Alice Adams", "stat": "pts", "line": 18.5,
            "side": "OVER", "book": "bov", "odds": -110,
            "edge": 0.07, "stake_dollars": 25.0,
        }],
    }


@pytest.fixture
def fake_engine(monkeypatch):
    """Inject _fake_run_engine into the live_recommendation_engine module."""
    from scripts import live_recommendation_engine as lre  # noqa: PLC0415
    monkeypatch.setattr(lre, "run_engine", _fake_run_engine)
    yield


@pytest.fixture
def stub_dashboard():
    """Stub the dashboard collector so we don't import pandas + the
    full operator_dashboard helpers in a unit test."""
    return lambda **kw: "<html><body>STUB DASHBOARD</body></html>"


@pytest.fixture
def alert_recorder():
    """In-memory alert recorder so tests can assert alerts fired."""
    captured: List[Dict[str, Any]] = []

    def _fake_alert(message, level="info", tag=None, source=None,
                    fields=None, **_):
        captured.append({"message": message, "level": level, "tag": tag,
                          "fields": fields or []})
        return {"discord_sent": False, "file_written": True,
                "vault_appended": True}

    _fake_alert.captured = captured  # type: ignore[attr-defined]
    return _fake_alert


# --------------------------------------------------------------------------- #
# Test 1: evening produces a snapshot                                          #
# --------------------------------------------------------------------------- #
def test_evening_stage_produces_snapshot(tmp_path, fake_engine,
                                          stub_dashboard, alert_recorder):
    snap_dir = tmp_path / "snap"
    cache    = tmp_path / "cache.html"
    log_path = tmp_path / "log.md"

    res = dw.run_evening(
        bankroll=1000.0, top=10, min_edge=0.05,
        snapshot_dir=snap_dir, dashboard_cache=cache,
        log_path=log_path, dry_run=False, today=DATE,
        alert_fn=alert_recorder, collect_fn=stub_dashboard,
    )
    assert res["n_critical_failures"] == 0
    snap_files = list(snap_dir.glob("rec_snapshot_*.json"))
    assert len(snap_files) == 1
    payload = json.loads(snap_files[0].read_text(encoding="utf-8"))
    assert payload["date"] == DATE
    assert payload["n_recs"] == 1
    assert cache.exists()
    assert "STUB DASHBOARD" in cache.read_text(encoding="utf-8")
    # Log entry was appended.
    assert log_path.exists()
    assert "stage=evening" in log_path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Test 2: morning produces settle + reconcile + report results                #
# --------------------------------------------------------------------------- #
def test_morning_stage_settle_reconcile_report(tmp_path, fake_engine,
                                                 stub_dashboard, alert_recorder,
                                                 monkeypatch):
    snap_dir = tmp_path / "snap"
    cache    = tmp_path / "cache.html"
    log_path = tmp_path / "log.md"
    settled  = tmp_path / "rec_settled.parquet"
    qb_dir   = tmp_path / "qb"  # empty — all recs will be "ungraded"

    # First make a yesterday snapshot via evening (so morning has data to settle).
    dw.run_evening(
        snapshot_dir=snap_dir, dashboard_cache=cache,
        log_path=log_path, dry_run=False, today=YEST,
        alert_fn=alert_recorder, collect_fn=stub_dashboard,
    )
    # Now morning.
    res = dw.run_morning(
        snapshot_dir=snap_dir, settled_path=settled, qb_dir=qb_dir,
        dashboard_cache=cache, log_path=log_path,
        reconcile_days=1, report_days=1,
        dry_run=False, yesterday=YEST,
        alert_fn=alert_recorder, collect_fn=stub_dashboard,
    )
    assert res["stage"] == "morning"
    # We expect settle_recs, reconcile_settlements, report_recs, refresh_dashboard, alert_morning
    step_names = [s["name"] for s in res["steps"]]
    assert "settle_recs" in step_names
    assert "reconcile_settlements" in step_names
    assert "report_recs" in step_names
    assert "refresh_dashboard" in step_names
    assert "alert_morning" in step_names

    # The morning alert message contains the summary fields.
    msgs = [a["message"] for a in alert_recorder.captured]
    morning_msg = [m for m in msgs if m.startswith("R26_S3 morning summary")]
    assert len(morning_msg) == 1
    assert YEST in morning_msg[0]


# --------------------------------------------------------------------------- #
# Test 3: --dry-run produces no side effects                                  #
# --------------------------------------------------------------------------- #
def test_dry_run_produces_no_side_effects(tmp_path, fake_engine,
                                            stub_dashboard, alert_recorder):
    snap_dir = tmp_path / "snap"
    cache    = tmp_path / "cache.html"
    log_path = tmp_path / "log.md"

    res = dw.run_evening(
        snapshot_dir=snap_dir, dashboard_cache=cache,
        log_path=log_path, dry_run=True, today=DATE,
        alert_fn=alert_recorder, collect_fn=stub_dashboard,
    )
    assert res["dry_run"] is True
    assert res["n_critical_failures"] == 0
    # No snapshot, no cache, no log file.
    assert not snap_dir.exists() or not any(snap_dir.iterdir())
    assert not cache.exists()
    assert not log_path.exists()
    # The alert recorder was NEVER called.
    assert alert_recorder.captured == []


# --------------------------------------------------------------------------- #
# Test 4: one step failure doesn't abort the others                            #
# --------------------------------------------------------------------------- #
def test_failure_does_not_abort_workflow(tmp_path, fake_engine,
                                          alert_recorder):
    snap_dir = tmp_path / "snap"
    cache    = tmp_path / "cache.html"
    log_path = tmp_path / "log.md"

    def _broken_dashboard(**kw):
        raise RuntimeError("synthetic dashboard failure")

    res = dw.run_evening(
        snapshot_dir=snap_dir, dashboard_cache=cache,
        log_path=log_path, dry_run=False, today=DATE,
        alert_fn=alert_recorder, collect_fn=_broken_dashboard,
    )
    # The broken dashboard step failed, BUT the snapshot AND the alert
    # steps still ran.
    by_name = {s["name"]: s for s in res["steps"]}
    assert by_name["snapshot_recs"]["ok"] is True
    assert by_name["refresh_dashboard"]["ok"] is False
    assert by_name["alert_evening"]["ok"] is True
    assert res["n_critical_failures"] == 1


# --------------------------------------------------------------------------- #
# Test 5: --summary parses the log correctly                                  #
# --------------------------------------------------------------------------- #
def test_summary_parses_log_correctly(tmp_path, fake_engine,
                                       stub_dashboard, alert_recorder):
    log_path = tmp_path / "log.md"
    snap_dir = tmp_path / "snap"
    cache    = tmp_path / "cache.html"

    # Run evening twice → expect 2 log entries.
    for _ in range(2):
        dw.run_evening(
            snapshot_dir=snap_dir, dashboard_cache=cache,
            log_path=log_path, dry_run=False, today=DATE,
            alert_fn=alert_recorder, collect_fn=stub_dashboard,
        )
    s = dw.summary(log_path=log_path, days=7)
    assert s["n_total"] == 2
    assert s["n_in_window"] == 2
    assert all(r["stage"] == "evening" for r in s["runs"])
    # Each run has the right step names.
    for r in s["runs"]:
        names = [st["name"] for st in r["steps"]]
        assert "snapshot_recs" in names
        assert "refresh_dashboard" in names
        assert "alert_evening" in names


# --------------------------------------------------------------------------- #
# Test 6: idempotent — running evening twice doesn't double-write a snapshot  #
# --------------------------------------------------------------------------- #
def test_evening_idempotent(tmp_path, fake_engine,
                              stub_dashboard, alert_recorder):
    snap_dir = tmp_path / "snap"
    cache    = tmp_path / "cache.html"
    log_path = tmp_path / "log.md"

    for _ in range(2):
        dw.run_evening(
            snapshot_dir=snap_dir, dashboard_cache=cache,
            log_path=log_path, dry_run=False, today=DATE,
            alert_fn=alert_recorder, collect_fn=stub_dashboard,
        )
    # The snapshot file name is deterministic by date, so only ONE file
    # exists — the second call overwrites.
    files = sorted(snap_dir.glob("rec_snapshot_*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["n_recs"] == 1


# --------------------------------------------------------------------------- #
# Test 7: subprocess calls are properly args-quoted (no shell=True anywhere)   #
# --------------------------------------------------------------------------- #
def test_no_shell_injection_surface():
    """daily_workflow.py drives steps via direct Python imports, NOT via
    shell-string subprocess calls — there is no shell-injection surface to
    begin with. Assert that no os.system or shell=True call sneaks into
    executable code (we strip docstrings + comments before scanning so the
    file is allowed to mention these phrases in its own documentation)."""
    import re as _re
    src = Path(dw.__file__).read_text(encoding="utf-8")
    # Strip triple-quoted docstrings (both " and ' flavors).
    no_doc = _re.sub(r'"""[\s\S]*?"""', "", src)
    no_doc = _re.sub(r"'''[\s\S]*?'''", "", no_doc)
    # Strip line comments.
    no_doc = "\n".join(
        line.split("#", 1)[0] for line in no_doc.splitlines()
    )
    assert "os.system(" not in no_doc
    assert "shell=True" not in no_doc
    assert "commands.getoutput" not in no_doc


# --------------------------------------------------------------------------- #
# Test 8: critical alert fires on step failure                                 #
# --------------------------------------------------------------------------- #
def test_critical_alert_fires_on_failure(tmp_path, fake_engine, alert_recorder):
    snap_dir = tmp_path / "snap"
    cache    = tmp_path / "cache.html"
    log_path = tmp_path / "log.md"

    def _broken_dashboard(**kw):
        raise RuntimeError("synthetic dashboard failure")

    dw.run_evening(
        snapshot_dir=snap_dir, dashboard_cache=cache,
        log_path=log_path, dry_run=False, today=DATE,
        alert_fn=alert_recorder, collect_fn=_broken_dashboard,
    )
    # We expect 2 alerts: one info ("evening recs ready") AND one critical
    # (refresh_dashboard failed).
    levels = [a["level"] for a in alert_recorder.captured]
    assert "critical" in levels
    crits = [a for a in alert_recorder.captured if a["level"] == "critical"]
    assert any("refresh_dashboard" in (a["message"] or "") for a in crits)


# --------------------------------------------------------------------------- #
# Test 9: parse_log tolerates missing + malformed lines                        #
# --------------------------------------------------------------------------- #
def test_parse_log_handles_missing_and_garbage(tmp_path):
    # No file at all.
    assert dw.parse_log(tmp_path / "nope.md") == []
    # File with only garbage lines + a partial valid block.
    log = tmp_path / "log.md"
    log.write_text(
        "# garbage\n"
        "this line means nothing\n"
        "## 2099-01-15T10:00:00Z stage=evening\n"
        "- duration: 1.2s\n"
        "- critical_failures: 0\n"
        "- steps:\n"
        "  - snapshot_recs: OK (0.3s)\n"
        "  - refresh_dashboard: FAIL (0.1s) — oops\n"
        "  - alert_evening: OK (0.0s)\n"
        "\n"
        "totally invalid line should be tolerated\n",
        encoding="utf-8",
    )
    records = dw.parse_log(log)
    assert len(records) == 1
    rec = records[0]
    assert rec["stage"] == "evening"
    assert rec["duration"] == "1.2s"
    assert rec["critical_failures"] == 0
    names = [s["name"] for s in rec["steps"]]
    assert names == ["snapshot_recs", "refresh_dashboard", "alert_evening"]
    fail = next(s for s in rec["steps"] if s["name"] == "refresh_dashboard")
    assert fail["ok"] is False
    assert fail["error"] == "oops"


# --------------------------------------------------------------------------- #
# Test 10: run_all chains evening + morning into one combined record           #
# --------------------------------------------------------------------------- #
def test_run_all_chains_both_stages(tmp_path, fake_engine,
                                      stub_dashboard, alert_recorder):
    snap_dir = tmp_path / "snap"
    cache    = tmp_path / "cache.html"
    log_path = tmp_path / "log.md"
    settled  = tmp_path / "rec_settled.parquet"
    qb_dir   = tmp_path / "qb"

    res = dw.run_all(
        bankroll=1000.0, top=10, min_edge=0.05,
        snapshot_dir=snap_dir, dashboard_cache=cache,
        log_path=log_path, dry_run=False,
        today=DATE, yesterday=YEST,
        settled_path=settled, qb_dir=qb_dir,
        reconcile_days=1, report_days=1,
        alert_fn=alert_recorder, collect_fn=stub_dashboard,
    )
    assert res["stage"] == "all"
    assert "evening" in res and "morning" in res
    assert res["evening"]["stage"] == "evening"
    assert res["morning"]["stage"] == "morning"
    # Both stage logs landed in the same file (two ## headers).
    text = log_path.read_text(encoding="utf-8")
    assert text.count("stage=evening") == 1
    assert text.count("stage=morning") == 1
