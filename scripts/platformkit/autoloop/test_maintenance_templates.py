"""Per-file test for scripts.platformkit.autoloop.maintenance_templates.

Acceptance criteria:
1. validate_new_stores: mtime-trigger (missing pairing / stale validation
   fires; a fresh pairing is watermark-skipped) + failure isolation (one
   bad store never blocks the next).
2. weighting_refresh: per-sport mtime-trigger against that sport's OWN
   watermark (not a shared global one) + failure isolation across sports.
3. replication_watch: REPORTS only (never calls a fit/run function) and is
   idempotent -- a corpus file already seen is never re-reported.
4. run_all: one job raising never blocks the rest of the table (checked at
   the real table's first entry AND generically at a fake table's middle
   entry); out[] keys match a golden list (table-driven refactor must not
   add/drop/rename a job key).

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_maintenance_templates.py -q
"""
from __future__ import annotations

import json
import os
import time
from unittest import mock

from scripts.platformkit.autoloop import maintenance_templates as MT


# 1. validate_new_stores ------------------------------------------------------
def test_validate_new_stores_mtime_trigger_and_skip(tmp_path):
    fresh = tmp_path / "fresh.jsonl"
    fresh.write_text("{}\n", encoding="utf-8")
    (tmp_path / "fresh_validation.json").write_text("{}", encoding="utf-8")
    os.utime(tmp_path / "fresh_validation.json", (time.time() + 10, time.time() + 10))

    stale = tmp_path / "stale.jsonl"
    stale.write_text("{}\n", encoding="utf-8")
    # no stale_validation.json at all -- missing pairing must fire

    calls = []
    result = MT.run_validate_new_stores(claims_dir=tmp_path,
                                        validate_fn=lambda s: calls.append(s))
    assert result["stores_scanned"] == 2
    assert result["stores_validated"] == 1
    assert any("stale" in c for c in calls)
    assert not any("fresh" in c for c in calls)


def test_validate_new_stores_failure_isolation(tmp_path):
    (tmp_path / "bad.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "good.jsonl").write_text("{}\n", encoding="utf-8")

    def flaky(stem_or_path):
        if "bad" in stem_or_path:
            raise ValueError("boom")

    result = MT.run_validate_new_stores(claims_dir=tmp_path, validate_fn=flaky)
    assert result["stores_scanned"] == 2
    assert result["stores_validated"] == 1
    assert result["stores_failed"] == 1
    assert "bad" in result["failed_stores"][0]


# 2. weighting_refresh ---------------------------------------------------------
def test_weighting_refresh_per_sport_watermark(tmp_path):
    (tmp_path / "nba_x_validation.json").write_text("{}", encoding="utf-8")
    (tmp_path / "mlb_y_validation.json").write_text("{}", encoding="utf-8")

    calls = []
    watermarks: dict = {}
    result = MT.run_weighting_refresh(
        watermarks, claims_dir=tmp_path,
        cli_run_fn=lambda sport: calls.append(sport) or [],
        append_fn=lambda results: None,
    )
    assert sorted(result["sports_refreshed"]) == ["mlb", "nba"]
    assert sorted(calls) == ["mlb", "nba"]
    assert "M02_weighting_refresh__nba" in watermarks
    assert "M02_weighting_refresh__mlb" in watermarks

    # second run, nothing changed on disk -> neither sport is due again
    calls.clear()
    result2 = MT.run_weighting_refresh(
        watermarks, claims_dir=tmp_path,
        cli_run_fn=lambda sport: calls.append(sport) or [],
        append_fn=lambda results: None,
    )
    assert result2["sports_refreshed"] == []
    assert calls == []

    # bump only nba's validation mtime -> only nba is due, mlb untouched
    os.utime(tmp_path / "nba_x_validation.json", (time.time() + 10, time.time() + 10))
    result3 = MT.run_weighting_refresh(
        watermarks, claims_dir=tmp_path,
        cli_run_fn=lambda sport: calls.append(sport) or [],
        append_fn=lambda results: None,
    )
    assert result3["sports_refreshed"] == ["nba"]


def test_weighting_refresh_failure_isolation(tmp_path):
    (tmp_path / "nba_x_validation.json").write_text("{}", encoding="utf-8")
    (tmp_path / "mlb_y_validation.json").write_text("{}", encoding="utf-8")

    def flaky_cli(sport):
        if sport == "mlb":
            raise RuntimeError("cli boom")
        return []

    watermarks: dict = {}
    result = MT.run_weighting_refresh(
        watermarks, claims_dir=tmp_path, cli_run_fn=flaky_cli, append_fn=lambda r: None,
    )
    assert result["sports_refreshed"] == ["nba"]
    assert result["sports_failed"] == [{"sport": "mlb", "error": "cli boom"}]
    assert "M02_weighting_refresh__nba" in watermarks
    assert "M02_weighting_refresh__mlb" not in watermarks  # failed -> not watermarked


# 3. replication_watch (report-only, idempotent) -------------------------------
def test_replication_watch_reports_only_and_is_idempotent(tmp_path):
    lineups = tmp_path / "lineups"
    lineups.mkdir()
    (lineups / "stints_2025_26.parquet").write_bytes(b"x")

    ledger = tmp_path / "prereg_hypothesis_ledger.jsonl"
    ledger.write_text(
        json.dumps({"hypothesis": "h1", "sport": "nba", "verdict": "SURVIVES_PREREG",
                   "computed_at": "2026-07-01T00:00:00Z"}) + "\n"
        + json.dumps({"hypothesis": "h2", "sport": "nba", "verdict": "NULL",
                     "computed_at": "2026-07-01T00:00:00Z"}) + "\n",
        encoding="utf-8",
    )
    import re
    patterns = [(lineups, re.compile(r"^stints_\d{4}_\d{2}\.parquet$"), "nba")]

    queued = []
    watermarks: dict = {}
    result = MT.run_replication_watch(watermarks, corpus_patterns=patterns,
                                      ledger_path=ledger, queue_fn=queued.append)
    assert result["new_reports"] == 1
    assert queued[0]["kind"] == "REPLICATION_OPPORTUNITY"
    assert queued[0]["survives_prereg_hypotheses"] == ["h1"]
    assert "run" not in queued[0] and "fit" not in queued[0]

    # second call, same file -> idempotent, no re-report
    queued.clear()
    result2 = MT.run_replication_watch(watermarks, corpus_patterns=patterns,
                                       ledger_path=ledger, queue_fn=queued.append)
    assert result2["new_reports"] == 0
    assert queued == []


def test_replication_watch_never_calls_a_run_or_fit_function():
    """No callable resembling 'run a replication' is ever invoked -- the
    function signature itself has no such hook, verified structurally."""
    import inspect
    sig = inspect.signature(MT.run_replication_watch)
    assert set(sig.parameters) == {"watermarks", "corpus_patterns", "ledger_path", "queue_fn"}


# 4. run_all isolation ----------------------------------------------------------
_GOLDEN_KEYS = {
    "validate_new_stores", "weighting_refresh", "replication_watch",
    "census_drift", "scoreboard_history", "ingame_benchmarks", "mechanism_reval",
    "utilization_drift", "frontier_probe", "shadow_settle", "propose_gate",
    "milb_refresh", "benchmark_refresh", "clv_refresh", "calibration_refresh",
    "log_reaper", "eval_gate", "pregame_benchmark", "statcast_refresh",
    "replication_cadence", "false_discovery_accounting", "mlb_results_refresh",
    "weekly_scoreboard_cadence", "k_nightly_refresh", "k_escalation_intake",
    "auto_validate", "card_grade",
}


@mock.patch("scripts.platformkit.autoloop.card_grade_job.run_card_grade",
            return_value={"grade": {"status": "skipped"}, "edge_claimed": False})
def test_run_all_isolates_one_failing_job(_cg_mock, tmp_path):
    # card_grade mocked via decorator: the with-stack below is already at
    # CPython's 20-nested-block cap, one more with-item is a SyntaxError.
    with mock.patch.object(MT, "run_validate_new_stores", side_effect=RuntimeError("x")), \
        mock.patch.object(MT, "run_weighting_refresh", return_value={"sports_refreshed": []}), \
        mock.patch.object(MT, "run_replication_watch", return_value={"new_reports": 0}), \
        mock.patch("scripts.platformkit.scoreboard_history.append_rows",
                   return_value={"status": "ok", "appended": 0}), \
        mock.patch("scripts.platformkit.autoloop.ingame_benchmark_job.run_ingame_benchmarks",
                   return_value={"mlb_state_bucket_benchmark": {"status": "skipped"}}), \
        mock.patch("scripts.platformkit.autoloop.mechanism_reval_job.run_mechanism_reval",
                   return_value={}), \
        mock.patch("scripts.platformkit.autoloop.utilization_drift_job.run_utilization_drift",
                   return_value={}), \
        mock.patch("scripts.platformkit.data_frontier.frontier_probe_job.run_probe_cycle",
                   return_value={"status": "skipped_cadence"}), \
        mock.patch("scripts.platformkit.autoloop.shadow_settle_job.run_shadow_settle",
                   return_value={"status": "skipped"}), \
        mock.patch("scripts.platformkit.autoloop.clv_refresh_job.run_clv_refresh",
                   return_value={"status": "skipped", "age_h": 1.0}), \
        mock.patch("scripts.platformkit.autoloop.calibration_refresh_job.run_calibration_refresh",
                   return_value={"status": "skipped", "age_h": 1.0}), \
        mock.patch("scripts.platformkit.autoloop.eval_gate_job.run_eval_gate",
                   return_value={"status": "skipped", "age_h": 1.0}), \
        mock.patch("scripts.platformkit.autoloop.pregame_benchmark_job.run_pregame_benchmark",
                   return_value={"status": "skipped", "age_h": 1.0}), \
        mock.patch("scripts.platformkit.autoloop.statcast_refresh_job.run_statcast_refresh",
                   return_value={"status": "skipped", "age_h": 1.0}), \
        mock.patch("scripts.platformkit.autoloop.replication_job.run_replication_cadence",
                   return_value={"status": "no_pending"}), \
        mock.patch("scripts.platformkit.autoloop.false_discovery_job.run_false_discovery_accounting",
                   return_value={"status": "ran", "dates_appended": []}), \
        mock.patch("scripts.platformkit.autoloop.mlb_results_refresh_job.run_mlb_results_refresh",
                   return_value={"status": "skipped", "age_h": 1.0}), \
        mock.patch("scripts.platformkit.autoloop.scoreboard_job.run_scoreboard",
                   return_value={"status": "skipped", "week": "2026-W28"}), \
        mock.patch("scripts.platformkit.omni.k_refresh_job.run_k_refresh",
                   return_value={"status": "no_games"}), \
        mock.patch("scripts.platformkit.omni.escalation_intake.run_escalation_intake",
                   return_value={"screened": 0}):
        out = MT.run_all({}, queue_fn=lambda row: None)
    assert out["validate_new_stores"]["status"] == "error"
    assert out["weighting_refresh"] == {"sports_refreshed": []}
    assert out["replication_watch"] == {"new_reports": 0}
    assert out["ingame_benchmarks"] == {"mlb_state_bucket_benchmark": {"status": "skipped"}}
    assert out["mechanism_reval"] == {}
    assert out["utilization_drift"] == {}
    assert out["frontier_probe"] == {"status": "skipped_cadence"}
    assert out["shadow_settle"] == {"status": "skipped"}
    assert out["clv_refresh"] == {"status": "skipped", "age_h": 1.0}
    assert out["calibration_refresh"] == {"status": "skipped", "age_h": 1.0}
    assert out["eval_gate"] == {"status": "skipped", "age_h": 1.0}
    assert out["pregame_benchmark"] == {"status": "skipped", "age_h": 1.0}
    assert out["statcast_refresh"] == {"status": "skipped", "age_h": 1.0}
    assert out["replication_cadence"] == {"status": "no_pending"}
    assert out["false_discovery_accounting"] == {"status": "ran", "dates_appended": []}
    assert out["mlb_results_refresh"] == {"status": "skipped", "age_h": 1.0}
    assert out["weekly_scoreboard_cadence"] == {"status": "skipped", "week": "2026-W28"}
    # golden key list: table-driven refactor must not add/drop/rename a job key
    assert set(out.keys()) == _GOLDEN_KEYS


def test_run_all_job_table_isolates_a_middle_entry_failure():
    """A raise from an entry in the MIDDLE of _JOB_TABLE (not just the first)
    must not stop later entries from running -- proves the dispatch loop
    itself isolates, not just the first try/except by coincidence."""
    calls = []

    def _ok(key):
        def _fn(*_a, **_kw):
            calls.append(key)
            return {"status": "ok"}
        return _fn

    def _boom(*_a, **_kw):
        raise RuntimeError("boom")

    fake_table = [
        ("first", MT.__name__, "_fake_first", ()),
        ("middle_fails", MT.__name__, "_fake_middle", ()),
        ("last", MT.__name__, "_fake_last", ()),
    ]
    with mock.patch.object(MT, "_JOB_TABLE", fake_table), \
        mock.patch.object(MT, "_fake_first", _ok("first"), create=True), \
        mock.patch.object(MT, "_fake_middle", _boom, create=True), \
        mock.patch.object(MT, "_fake_last", _ok("last"), create=True):
        out = MT.run_all({})
    assert out["first"] == {"status": "ok"}
    assert out["middle_fails"]["status"] == "error"
    assert out["last"] == {"status": "ok"}
    assert calls == ["first", "last"]
