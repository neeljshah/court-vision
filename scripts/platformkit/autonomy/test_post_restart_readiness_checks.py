"""Per-file tests for post_restart_readiness_checks (RESTART-READINESS LANE 3).

Everything is fake/injected -- NO real network call, NO real PID/socket, NO real
filesystem outside tmp_path (module-level path constants monkeypatched to tmp_path
via setattr, never the real repo data/ tree).

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_post_restart_readiness_checks.py -q
"""
from __future__ import annotations

import json

import scripts.platformkit.autonomy.post_restart_checks as checks
import scripts.platformkit.autonomy.post_restart_readiness_checks as ready


# --------------------------------------------------------------------------- #
# (k) grade-writer frac-clamp
# --------------------------------------------------------------------------- #
def test_clamp_no_live_game_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(ready, "_INGAME_GRADE", tmp_path)
    row = ready.check_grade_writer_clamp(1000.0, live_game_fn=lambda s: False)
    assert row["status"] == checks.PENDING


def test_clamp_live_no_row_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(ready, "_INGAME_GRADE", tmp_path)
    row = ready.check_grade_writer_clamp(1000.0, live_game_fn=lambda s: True)
    assert row["status"] == checks.PENDING


def test_clamp_before_inning_9_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(ready, "_INGAME_GRADE", tmp_path)
    sport_dir = tmp_path / "mlb"
    sport_dir.mkdir()
    doc = {"state_summary": "inning=6 half=bottom", "model_prob": 0.6}
    tick = sport_dir / "g1.jsonl"
    tick.write_text(json.dumps(doc) + "\n", encoding="ascii")
    now = tick.stat().st_mtime + 5.0
    row = ready.check_grade_writer_clamp(now, live_game_fn=lambda s: True)
    assert row["status"] == checks.PENDING
    assert "inning 9" in row["evidence"]


def test_clamp_inning_9_with_model_prob_is_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(ready, "_INGAME_GRADE", tmp_path)
    sport_dir = tmp_path / "mlb"
    sport_dir.mkdir()
    doc = {"state_summary": "inning=9 half=bottom", "model_prob": 0.71}
    tick = sport_dir / "g1.jsonl"
    tick.write_text(json.dumps(doc) + "\n", encoding="ascii")
    now = tick.stat().st_mtime + 5.0
    row = ready.check_grade_writer_clamp(now, live_game_fn=lambda s: True)
    assert row["status"] == checks.PASS


def test_clamp_inning_11_null_model_prob_is_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(ready, "_INGAME_GRADE", tmp_path)
    sport_dir = tmp_path / "mlb"
    sport_dir.mkdir()
    doc = {"state_summary": "inning=11 half=top", "model_prob": None}
    tick = sport_dir / "g1.jsonl"
    tick.write_text(json.dumps(doc) + "\n", encoding="ascii")
    now = tick.stat().st_mtime + 5.0
    row = ready.check_grade_writer_clamp(now, live_game_fn=lambda s: True)
    assert row["status"] == checks.FAIL


def test_clamp_stale_row_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(ready, "_INGAME_GRADE", tmp_path)
    sport_dir = tmp_path / "mlb"
    sport_dir.mkdir()
    doc = {"state_summary": "inning=10 half=top", "model_prob": None}
    tick = sport_dir / "g1.jsonl"
    tick.write_text(json.dumps(doc) + "\n", encoding="ascii")
    now = tick.stat().st_mtime + 5000.0
    row = ready.check_grade_writer_clamp(now, live_game_fn=lambda s: True, fresh_sec=1800.0)
    assert row["status"] == checks.PENDING


# --------------------------------------------------------------------------- #
# (l) kalshi pacing counters
# --------------------------------------------------------------------------- #
def test_pacing_missing_heartbeat_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(ready, "_CAPTURE_HEARTBEAT", tmp_path / "missing.json")
    row = ready.check_kalshi_pacing_counters(1000.0)
    assert row["status"] == checks.PENDING


def test_pacing_counters_present_is_pass(tmp_path, monkeypatch):
    hb = tmp_path / "_capture_heartbeat.json"
    hb.write_text(json.dumps({"n_requests_total": 12, "n_429_total": 1}), encoding="ascii")
    monkeypatch.setattr(ready, "_CAPTURE_HEARTBEAT", hb)
    row = ready.check_kalshi_pacing_counters(hb.stat().st_mtime - 100.0)
    assert row["status"] == checks.PASS


def test_pacing_counters_absent_predates_restart_is_pending(tmp_path, monkeypatch):
    hb = tmp_path / "_capture_heartbeat.json"
    hb.write_text(json.dumps({"as_of": "x"}), encoding="ascii")
    monkeypatch.setattr(ready, "_CAPTURE_HEARTBEAT", hb)
    row = ready.check_kalshi_pacing_counters(hb.stat().st_mtime + 100.0)
    assert row["status"] == checks.PENDING


def test_pacing_counters_absent_post_restart_is_fail(tmp_path, monkeypatch):
    hb = tmp_path / "_capture_heartbeat.json"
    hb.write_text(json.dumps({"as_of": "x"}), encoding="ascii")
    monkeypatch.setattr(ready, "_CAPTURE_HEARTBEAT", hb)
    row = ready.check_kalshi_pacing_counters(hb.stat().st_mtime - 100.0)
    assert row["status"] == checks.FAIL


# --------------------------------------------------------------------------- #
# (m) enrichment persistence
# --------------------------------------------------------------------------- #
def test_persistence_no_live_game_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(ready, "_INGAME_GRADE", tmp_path)
    row = ready.check_enrichment_persistence(1000.0, live_game_fn=lambda s: False)
    assert row["status"] == checks.PENDING


def test_persistence_live_game_fresh_row_with_key_is_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(ready, "_INGAME_GRADE", tmp_path)
    sport_dir = tmp_path / "wnba"
    sport_dir.mkdir()
    doc = {"espn_wp": 0.5, "model_prob": 0.6}
    tick = sport_dir / "g1.jsonl"
    tick.write_text(json.dumps(doc) + "\n", encoding="ascii")
    now = tick.stat().st_mtime + 5.0
    row = ready.check_enrichment_persistence(
        now, live_game_fn=lambda s: s == "wnba", sports=["wnba"])
    assert row["status"] == checks.PASS


def test_persistence_live_game_no_enrichment_key_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(ready, "_INGAME_GRADE", tmp_path)
    sport_dir = tmp_path / "wnba"
    sport_dir.mkdir()
    tick = sport_dir / "g1.jsonl"
    tick.write_text(json.dumps({"model_prob": 0.6}) + "\n", encoding="ascii")
    now = tick.stat().st_mtime + 5.0
    row = ready.check_enrichment_persistence(
        now, live_game_fn=lambda s: s == "wnba", sports=["wnba"])
    assert row["status"] == checks.PENDING


# --------------------------------------------------------------------------- #
# (n) sidecar retention
# --------------------------------------------------------------------------- #
def test_sidecar_retention_plans_cleanly():
    row = ready.check_sidecar_retention()
    assert row["status"] in (checks.PASS, checks.FAIL)  # never PENDING
    # Real DEFAULT_POLICY must plan cleanly (read-only; asserts the actual module).
    assert row["status"] == checks.PASS, row["evidence"]


def test_sidecar_retention_empty_policy_is_fail(monkeypatch):
    import scripts.platformkit.ingame.sidecar_retention as sr
    monkeypatch.setattr(sr, "DEFAULT_POLICY", [])
    row = ready.check_sidecar_retention()
    assert row["status"] == checks.FAIL


# --------------------------------------------------------------------------- #
# (o) supervisor beat-thread
# --------------------------------------------------------------------------- #
def test_beat_thread_missing_status_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(ready, "_OPS", tmp_path)
    row = ready.check_supervisor_beat_thread(1000.0, 900.0)
    assert row["status"] == checks.PENDING


def test_beat_thread_predates_restart_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(ready, "_OPS", tmp_path)
    doc = {"boot_initiator": None, "updated_at": 500.0}
    (tmp_path / "supervisor_status.json").write_text(json.dumps(doc), encoding="ascii")
    restart_at = (tmp_path / "supervisor_status.json").stat().st_mtime + 1000.0
    row = ready.check_supervisor_beat_thread(restart_at + 10.0, restart_at)
    assert row["status"] == checks.PENDING


def test_beat_thread_stamped_and_fresh_is_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(ready, "_OPS", tmp_path)
    doc = {"boot_initiator": "boot_ps1", "updated_at": 2000.0}
    (tmp_path / "supervisor_status.json").write_text(json.dumps(doc), encoding="ascii")
    restart_at = (tmp_path / "supervisor_status.json").stat().st_mtime - 100.0
    row = ready.check_supervisor_beat_thread(2050.0, restart_at)
    assert row["status"] == checks.PASS


def test_beat_thread_missing_initiator_post_restart_is_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(ready, "_OPS", tmp_path)
    doc = {"boot_initiator": None, "updated_at": 2000.0}
    (tmp_path / "supervisor_status.json").write_text(json.dumps(doc), encoding="ascii")
    restart_at = (tmp_path / "supervisor_status.json").stat().st_mtime - 100.0
    row = ready.check_supervisor_beat_thread(2050.0, restart_at)
    assert row["status"] == checks.FAIL


def test_beat_thread_stale_updated_at_is_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(ready, "_OPS", tmp_path)
    doc = {"boot_initiator": "boot_ps1", "updated_at": 1000.0}
    (tmp_path / "supervisor_status.json").write_text(json.dumps(doc), encoding="ascii")
    restart_at = (tmp_path / "supervisor_status.json").stat().st_mtime - 100.0
    row = ready.check_supervisor_beat_thread(1000.0 + 400.0, restart_at)
    assert row["status"] == checks.FAIL


# --------------------------------------------------------------------------- #
# (p) npb/kbo live-state bridge
# --------------------------------------------------------------------------- #
def test_npb_kbo_bridge_wired_is_pass():
    row = ready.check_npb_kbo_live_state_bridge()
    assert row["status"] == checks.PASS, row["evidence"]


def test_npb_kbo_bridge_missing_dispatch_is_fail(monkeypatch):
    import scripts.platformkit.ingame.npb_kbo_live_state as nk
    monkeypatch.setattr(nk, "_DISPATCH", {"npb": lambda *a, **k: []})
    row = ready.check_npb_kbo_live_state_bridge()
    assert row["status"] == checks.FAIL
    assert "kbo" in row["evidence"]


# --------------------------------------------------------------------------- #
# (q) autoloop maintenance jobs armed (E3)
# --------------------------------------------------------------------------- #
_M07_M12 = {
    "mechanism_reval": {"status": "ok"}, "utilization_drift": {"status": "ok"},
    "shadow_settle": {"status": "ok"}, "propose_gate": {"status": "ok"},
    "frontier_probe": {"status": "ok"}, "milb_refresh": {"status": "ok"},
}


def test_autoloop_maintenance_missing_report_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(ready, "_AUTOLOOP_REPORT", tmp_path / "missing.json")
    row = ready.check_autoloop_maintenance_jobs(1000.0)
    assert row["status"] == checks.PENDING


def test_autoloop_maintenance_predates_restart_is_pending(tmp_path, monkeypatch):
    rpt = tmp_path / "autoloop_report.json"
    rpt.write_text(json.dumps({"maintenance": {}}), encoding="ascii")
    monkeypatch.setattr(ready, "_AUTOLOOP_REPORT", rpt)
    row = ready.check_autoloop_maintenance_jobs(rpt.stat().st_mtime + 100.0)
    assert row["status"] == checks.PENDING


def test_autoloop_maintenance_post_restart_missing_keys_is_fail(tmp_path, monkeypatch):
    rpt = tmp_path / "autoloop_report.json"
    rpt.write_text(json.dumps({"maintenance": {}}), encoding="ascii")
    monkeypatch.setattr(ready, "_AUTOLOOP_REPORT", rpt)
    row = ready.check_autoloop_maintenance_jobs(rpt.stat().st_mtime - 100.0)
    assert row["status"] == checks.FAIL


def test_autoloop_maintenance_post_restart_error_status_is_fail(tmp_path, monkeypatch):
    rpt = tmp_path / "autoloop_report.json"
    maintenance = dict(_M07_M12)
    maintenance["propose_gate"] = {"status": "error", "error": "boom"}
    rpt.write_text(json.dumps({"maintenance": maintenance, "execution": {}}), encoding="ascii")
    monkeypatch.setattr(ready, "_AUTOLOOP_REPORT", rpt)
    row = ready.check_autoloop_maintenance_jobs(rpt.stat().st_mtime - 100.0)
    assert row["status"] == checks.FAIL
    assert "propose_gate" in row["evidence"]


def test_autoloop_maintenance_post_restart_clean_is_pass(tmp_path, monkeypatch):
    rpt = tmp_path / "autoloop_report.json"
    doc = {"maintenance": _M07_M12, "execution": {"execution_stages": {"status": "ran"}}}
    rpt.write_text(json.dumps(doc), encoding="ascii")
    monkeypatch.setattr(ready, "_AUTOLOOP_REPORT", rpt)
    row = ready.check_autoloop_maintenance_jobs(rpt.stat().st_mtime - 100.0)
    assert row["status"] == checks.PASS
