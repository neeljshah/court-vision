"""Per-file tests for freshness_sla / freshness_sla_runner.

Covers: NA for a name with no table entry (never GREEN), GREEN for a fresh
artifact, RED for a stale/missing artifact, write_status/load_status round
trip, and the runner tick with fake check/write callables (no real daemon
names or filesystem probing beyond tmp_path).

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_freshness_sla.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.autonomy.freshness_sla import (
    GREEN,
    NA,
    RED,
    SlaEntry,
    check_all,
    check_one,
    load_status,
    probe,
    write_status,
)


def test_missing_table_entry_is_na_never_green():
    row = check_one("totally_unknown_daemon_xyz", now=1000.0)
    assert row["status"] == NA
    assert row["reason"] == "no_sla_entry"


def test_green_for_fresh_artifact(tmp_path):
    p = tmp_path / "out.json"
    p.write_text("{}", encoding="utf-8")
    now = p.stat().st_mtime + 10.0
    table = {"svc": SlaEntry(p, 100.0)}
    row = check_one("svc", now=now, table=table)
    assert row["status"] == GREEN
    assert row["age_sec"] == 10.0


def test_red_for_stale_artifact(tmp_path):
    p = tmp_path / "out.json"
    p.write_text("{}", encoding="utf-8")
    now = p.stat().st_mtime + 1000.0
    table = {"svc": SlaEntry(p, 100.0)}
    row = check_one("svc", now=now, table=table)
    assert row["status"] == RED
    assert row["reason"] == "stale"


def test_red_for_missing_artifact(tmp_path):
    p = tmp_path / "does_not_exist.json"
    table = {"svc": SlaEntry(p, 100.0)}
    row = check_one("svc", now=1000.0, table=table)
    assert row["status"] == RED
    assert row["reason"] == "missing"


def test_negative_age_clamped_to_zero(tmp_path):
    p = tmp_path / "out.json"
    p.write_text("{}", encoding="utf-8")
    now = p.stat().st_mtime - 500.0  # clock skew: "now" before mtime
    table = {"svc": SlaEntry(p, 100.0)}
    row = check_one("svc", now=now, table=table)
    assert row["age_sec"] == 0.0
    assert row["status"] == GREEN


def test_check_all_preserves_order_and_mixes_statuses(tmp_path):
    p = tmp_path / "out.json"
    p.write_text("{}", encoding="utf-8")
    now = p.stat().st_mtime + 10.0
    table = {"a": SlaEntry(p, 100.0)}
    rows = check_all(["a", "b_unknown"], now=now, table=table)
    assert [r["name"] for r in rows] == ["a", "b_unknown"]
    assert rows[0]["status"] == GREEN
    assert rows[1]["status"] == NA


def test_write_status_and_load_status_round_trip(tmp_path):
    out = tmp_path / "freshness_sla.json"
    rows = [
        {"name": "a", "status": GREEN},
        {"name": "b", "status": RED},
        {"name": "c", "status": NA},
    ]
    assert write_status(rows, out_path=out, now=500.0) is True
    doc = json.loads(out.read_text(encoding="ascii"))
    assert doc["n_red"] == 1
    assert doc["n_na"] == 1
    assert doc["overall"] == RED
    loaded = load_status(path=out)
    assert [r["name"] for r in loaded] == ["a", "b", "c"]


def test_write_status_overall_green_when_no_red(tmp_path):
    out = tmp_path / "freshness_sla.json"
    rows = [{"name": "a", "status": GREEN}, {"name": "b", "status": NA}]
    write_status(rows, out_path=out, now=500.0)
    doc = json.loads(out.read_text(encoding="ascii"))
    assert doc["overall"] == GREEN


def test_load_status_missing_file_returns_empty(tmp_path):
    assert load_status(path=tmp_path / "nope.json") == []


def test_load_status_garbage_returns_empty(tmp_path):
    p = tmp_path / "garbage.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_status(path=p) == []


def test_probe_convenience_uses_real_table_and_returns_status_string():
    # Every real TABLE-entry daemon reads a status string; an unknown name is NA.
    assert probe("totally_unknown_daemon_xyz") == NA


def test_table_entries_have_positive_staleness():
    from scripts.platformkit.autonomy.freshness_sla import TABLE
    assert len(TABLE) > 0
    for name, entry in TABLE.items():
        assert entry.max_staleness_sec > 0, name


# --------------------------------------------------------------------------- #
# LANE 3: outcome-label artifact SLA rows (soccer_intl/mlb/wnba/npb/kbo)
# --------------------------------------------------------------------------- #
def test_label_artifact_sla_entries_present():
    from scripts.platformkit.autonomy.freshness_sla import TABLE
    for name in ("soccer_intl_finals", "mlb_espn_boxscores", "wnba_espn_scoreboard",
                 "npb_results", "kbo_results"):
        assert name in TABLE, name
        assert TABLE[name].max_staleness_sec > 0


def test_label_artifact_sla_green_when_fresh(tmp_path):
    p = tmp_path / "espn_finals.parquet"
    p.write_text("{}", encoding="utf-8")
    now = p.stat().st_mtime + 10.0
    table = {"soccer_intl_finals": SlaEntry(p, 129600.0)}
    row = check_one("soccer_intl_finals", now=now, table=table)
    assert row["status"] == GREEN


def test_label_artifact_sla_red_when_multi_day_stale(tmp_path):
    p = tmp_path / "espn_finals.parquet"
    p.write_text("{}", encoding="utf-8")
    now = p.stat().st_mtime + 6 * 86400.0  # a 6-day silent gap, the real incident shape
    table = {"soccer_intl_finals": SlaEntry(p, 129600.0)}
    row = check_one("soccer_intl_finals", now=now, table=table)
    assert row["status"] == RED
    assert row["reason"] == "stale"


def test_label_artifact_sla_na_for_unmonitored_name():
    row = check_one("some_future_sport_finals_not_yet_registered", now=1000.0)
    assert row["status"] == NA


# --------------------------------------------------------------------------- #
# LANE 1: manual/CLI ops-report SLA rows (edge_greenlight/clv_scoreboard/
# clv_reconcile/after_cost/beat_the_line)
# --------------------------------------------------------------------------- #
def test_manual_report_sla_entries_present():
    from scripts.platformkit.autonomy.freshness_sla import TABLE
    for name in ("edge_greenlight", "clv_scoreboard", "clv_reconcile_moneyline",
                 "clv_reconcile_paper_pm", "after_cost_scoreboard", "beat_the_line"):
        assert name in TABLE, name
        assert TABLE[name].max_staleness_sec > 0


def test_manual_report_sla_green_when_fresh(tmp_path):
    p = tmp_path / "edge_greenlight.json"
    p.write_text("{}", encoding="utf-8")
    now = p.stat().st_mtime + 10.0
    table = {"edge_greenlight": SlaEntry(p, 172800.0)}
    row = check_one("edge_greenlight", now=now, table=table)
    assert row["status"] == GREEN


def test_manual_report_sla_red_when_multi_day_stale(tmp_path):
    """The real incident shape this lane found: 73-75h stale with nothing
    flagging it -- must go RED, never silently read as live."""
    p = tmp_path / "clv_scoreboard.json"
    p.write_text("{}", encoding="utf-8")
    now = p.stat().st_mtime + 75 * 3600.0  # 75h, matches the real observed staleness
    table = {"clv_scoreboard": SlaEntry(p, 172800.0)}
    row = check_one("clv_scoreboard", now=now, table=table)
    assert row["status"] == RED
    assert row["reason"] == "stale"


def test_m36_already_registered_no_new_procspec_needed_this_lane():
    """LANE 3 wired the bounded finals-refresh into the EXISTING m36 grading
    tick rather than adding a new ProcSpec -- so supervisor.manifest() (the
    real daemon-name source freshness_sla_runner._daemon_names() reads) must
    already include m36 with zero further registration/resync work."""
    from supervisor.manifest import manifest
    names = [s.name for s in manifest("default")]
    assert "m36_ingame_grading_multi" in names


# --------------------------------------------------------------------------- #
# GREENLIGHT-UNCAP wave (2026-07-05): channel-trust + honesty input SLA rows
# (E-SPEC/F-SPEC, GREENLIGHT_UNCAP_SPEC_2026-07-05.md R-d -- 10 keys total,
# 8 new here + clv_reconcile_moneyline/clv_reconcile_paper_pm already present
# from LANE 1 above, unduplicated/unaltered).
# --------------------------------------------------------------------------- #
def test_greenlight_trust_honesty_sla_entries_present():
    from scripts.platformkit.autonomy.freshness_sla import TABLE
    for name in ("execution_quality", "ingame_segment_trust",
                 "ingame_segment_trust_multi", "ingame_clv_verdict",
                 "l4_gate_prereg", "reject_ledger",
                 "clv_reconcile_moneyline", "clv_reconcile_paper_pm",
                 "clv_reconcile_paper_ingame", "clv_reconcile_paper_ingame_prop"):
        assert name in TABLE, name
        assert TABLE[name].max_staleness_sec > 0


def test_greenlight_trust_honesty_sla_paths_match_expected():
    from scripts.platformkit.autonomy.freshness_sla import TABLE, _FRONTEND, _OPS
    expected = {
        "execution_quality": _OPS / "execution_quality.json",
        "ingame_segment_trust": _OPS / "ingame_segment_trust.json",
        "ingame_segment_trust_multi": _OPS / "ingame_segment_trust_multi.json",
        "ingame_clv_verdict": _OPS / "ingame_clv_verdict.json",
        "l4_gate_prereg": _OPS / "l4_gate_prereg.json",
        "reject_ledger": _FRONTEND / "reject_ledger.jsonl",
        "clv_reconcile_moneyline": _OPS / "clv_reconcile_moneyline.json",
        "clv_reconcile_paper_pm": _OPS / "clv_reconcile_paper_pm.json",
        "clv_reconcile_paper_ingame": _OPS / "clv_reconcile_paper_ingame.json",
        "clv_reconcile_paper_ingame_prop": _OPS / "clv_reconcile_paper_ingame_prop.json",
    }
    for name, path in expected.items():
        assert TABLE[name].path == path, name


def test_greenlight_trust_honesty_sla_values_match_spec():
    from scripts.platformkit.autonomy.freshness_sla import TABLE
    day_plus_grace = {
        "execution_quality": 93600.0,
        "ingame_segment_trust": 93600.0,
        "ingame_segment_trust_multi": 93600.0,
        "ingame_clv_verdict": 93600.0,
    }
    two_day_batch = {
        "l4_gate_prereg": 172800.0,
        "reject_ledger": 172800.0,
        "clv_reconcile_moneyline": 172800.0,
        "clv_reconcile_paper_pm": 172800.0,
        "clv_reconcile_paper_ingame": 172800.0,
        "clv_reconcile_paper_ingame_prop": 172800.0,
    }
    for name, sla in {**day_plus_grace, **two_day_batch}.items():
        assert TABLE[name].max_staleness_sec == sla, name


def test_greenlight_trust_honesty_sla_green_when_fresh(tmp_path):
    p = tmp_path / "execution_quality.json"
    p.write_text("{}", encoding="utf-8")
    now = p.stat().st_mtime + 10.0
    table = {"execution_quality": SlaEntry(p, 93600.0)}
    row = check_one("execution_quality", now=now, table=table)
    assert row["status"] == GREEN


def test_greenlight_trust_honesty_sla_red_when_stale(tmp_path):
    p = tmp_path / "l4_gate_prereg.json"
    p.write_text("{}", encoding="utf-8")
    now = p.stat().st_mtime + 3 * 86400.0  # 3 days, past the 48h batch SLA
    table = {"l4_gate_prereg": SlaEntry(p, 172800.0)}
    row = check_one("l4_gate_prereg", now=now, table=table)
    assert row["status"] == RED
    assert row["reason"] == "stale"


def test_greenlight_trust_honesty_sla_red_when_missing(tmp_path):
    p = tmp_path / "reject_ledger.jsonl"
    table = {"reject_ledger": SlaEntry(p, 172800.0)}
    row = check_one("reject_ledger", now=1000.0, table=table)
    assert row["status"] == RED
    assert row["reason"] == "missing"


def test_greenlight_trust_honesty_sla_no_duplicate_moneyline_paper_pm_rows():
    """clv_reconcile_moneyline/clv_reconcile_paper_pm were already registered by
    LANE 1 -- this wave must not have duplicated or altered either row."""
    from scripts.platformkit.autonomy.freshness_sla import TABLE, _OPS
    assert TABLE["clv_reconcile_moneyline"].path == _OPS / "clv_reconcile_moneyline.json"
    assert TABLE["clv_reconcile_moneyline"].max_staleness_sec == 172800.0
    assert TABLE["clv_reconcile_paper_pm"].path == _OPS / "clv_reconcile_paper_pm.json"
    assert TABLE["clv_reconcile_paper_pm"].max_staleness_sec == 172800.0


# --------------------------------------------------------------------------- #
# runner: fake check/write callables, no real supervisor.manifest() names touched
# --------------------------------------------------------------------------- #
def test_runner_tick_calls_check_and_write():
    from scripts.platformkit.autonomy.freshness_sla_runner import tick

    calls = {}

    def fake_check(names, now=None):
        calls["names"] = names
        calls["now"] = now
        return [{"name": n, "status": GREEN} for n in names]

    def fake_write(rows, now=None):
        calls["written"] = rows
        return True

    rows = tick(now=123.0, names=["x", "y"], check_fn=fake_check, write_fn=fake_write)
    assert calls["names"] == ["x", "y"]
    assert calls["now"] == 123.0
    assert len(rows) == 2
    assert calls["written"] == rows


def test_runner_tick_never_raises_when_check_fn_raises():
    from scripts.platformkit.autonomy.freshness_sla_runner import tick

    def boom(names, now=None):
        raise RuntimeError("boom")

    rows = tick(now=0.0, names=["x"], check_fn=boom, write_fn=lambda rows, now=None: True)
    assert rows == []


def test_daemon_names_helper_never_raises():
    from scripts.platformkit.autonomy.freshness_sla_runner import _daemon_names
    names = _daemon_names()
    assert isinstance(names, list)


# --------------------------------------------------------------------------- #
# W3 (2026-07-11): 5 new SlaEntry rows fill 5 of the 17 NA daemon names.
# m1_ui / m1_api_paper / m1_api_boards stay NA on purpose (see TABLE comment).
# --------------------------------------------------------------------------- #
def test_w3_new_entries_present_with_paths_existing_or_declared():
    from scripts.platformkit.autonomy.freshness_sla import TABLE, _FRONTEND, _HB
    expected = {
        "m1_line_daemon": (_HB / "m1_line_daemon.txt", 2700.0),
        "m1_bankroll": (_HB / "m1_bankroll.txt", 1500.0),
        "m5_autonomy_monitor": (_HB / "m5_autonomy_monitor.txt", 300.0),
        "m6_ingame_loop": (_FRONTEND / "ingame" / "_heartbeat.json", 300.0),
        "m41_public_splits": (_HB / "m41_public_splits.txt", 190000.0),
    }
    for name, (path, sla) in expected.items():
        assert TABLE[name].path == path, name
        assert TABLE[name].max_staleness_sec == sla, name


def test_w3_skipped_names_stay_na():
    for name in ("m1_ui", "m1_api_paper", "m1_api_boards"):
        row = check_one(name, now=1000.0)
        assert row["status"] == NA, name


def test_w3_real_table_na_count_drops_to_12():
    """Real freshness pass against the actual supervisor daemon-name list: the
    17 pre-W3 NA rows drop to exactly 12 (17 - 5 new entries; m19-m27 stay
    M29-covered, m1_ui/m1_api_paper/m1_api_boards stay honest NA)."""
    from scripts.platformkit.autonomy.freshness_sla_runner import _daemon_names
    rows = check_all(_daemon_names())
    n_na = sum(1 for r in rows if r["status"] == NA)
    assert n_na == 12, [r["name"] for r in rows if r["status"] == NA]
