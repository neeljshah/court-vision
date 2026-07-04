"""Per-file tests for post_restart_verify / post_restart_checks /
post_restart_capture_checks (LANE 4).

Everything is fake/injected -- NO real kills, NO real restart, NO real socket,
NO real HTTP call, NO real filesystem outside tmp_path (module-level path
constants are monkeypatched to tmp_path via setattr, never the real repo
data/ tree). Live-HTTP and kalshi-fetch paths are exercised only through
injected fakes.

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_post_restart_verify.py -q
"""
from __future__ import annotations

import json

import scripts.platformkit.autonomy.post_restart_capture_checks as capture_checks
import scripts.platformkit.autonomy.post_restart_checks as checks
import scripts.platformkit.autonomy.post_restart_verify as verify


# --------------------------------------------------------------------------- #
# (a) supervisor_status
# --------------------------------------------------------------------------- #
def test_supervisor_status_missing_is_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_OPS", tmp_path)
    row = checks.check_supervisor_status(1000.0)
    assert row["status"] == checks.FAIL
    assert "missing" in row["evidence"]


def test_supervisor_status_all_ready_with_new_procs_is_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_OPS", tmp_path)
    doc = {
        "all_ready": True,
        "procs": [{"name": n} for n in list(checks.NEW_PROCS) + ["m1_producer"]],
    }
    (tmp_path / "supervisor_status.json").write_text(json.dumps(doc), encoding="ascii")
    row = checks.check_supervisor_status(1000.0)
    assert row["status"] == checks.PASS


def test_supervisor_status_missing_new_procs_is_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_OPS", tmp_path)
    doc = {"all_ready": True, "procs": [{"name": "m1_producer"}]}
    (tmp_path / "supervisor_status.json").write_text(json.dumps(doc), encoding="ascii")
    row = checks.check_supervisor_status(1000.0)
    assert row["status"] == checks.FAIL
    assert set(row["missing"]) == set(checks.NEW_PROCS)


def test_supervisor_status_not_all_ready_is_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_OPS", tmp_path)
    doc = {"all_ready": False, "procs": [{"name": n} for n in checks.NEW_PROCS]}
    (tmp_path / "supervisor_status.json").write_text(json.dumps(doc), encoding="ascii")
    row = checks.check_supervisor_status(1000.0)
    assert row["status"] == checks.FAIL


# --------------------------------------------------------------------------- #
# (b) ports (HTTP probe injected -- never a real socket)
# --------------------------------------------------------------------------- #
def test_ports_all_200_is_pass():
    def fake_probe(url, timeout=10.0):
        return {"status": 200, "timed_out": False}
    rows = checks.check_ports(http_probe_fn=fake_probe)
    assert len(rows) == 3
    assert all(r["status"] == checks.PASS for r in rows)


def test_ports_timeout_is_fail():
    def fake_probe(url, timeout=10.0):
        return {"status": 0, "timed_out": True}
    rows = checks.check_ports(http_probe_fn=fake_probe)
    assert all(r["status"] == checks.FAIL for r in rows)
    assert all("timed out" in r["evidence"] for r in rows)


def test_ports_non200_is_fail():
    def fake_probe(url, timeout=10.0):
        return {"status": 503, "timed_out": False}
    rows = checks.check_ports(http_probe_fn=fake_probe)
    assert all(r["status"] == checks.FAIL for r in rows)


def test_ports_probe_raises_is_fail():
    def fake_probe(url, timeout=10.0):
        raise RuntimeError("boom")
    rows = checks.check_ports(http_probe_fn=fake_probe)
    assert all(r["status"] == checks.FAIL for r in rows)


# --------------------------------------------------------------------------- #
# (c) new-proc heartbeat freshness
# --------------------------------------------------------------------------- #
def test_new_proc_heartbeat_absent_within_one_tick_is_pending(tmp_path, monkeypatch):
    hb = tmp_path / "m33_http_wedge_reaper.txt"
    fake_procs = {"m33_http_wedge_reaper": {"heartbeat": hb, "cadence_sec": 30.0}}
    monkeypatch.setattr(checks, "NEW_PROCS", fake_procs)
    restart_at = 1000.0
    now = restart_at + 5.0  # well within the 30s cadence
    rows = checks.check_new_procs(now, restart_at)
    assert rows[0]["status"] == checks.PENDING


def test_new_proc_heartbeat_absent_past_one_tick_is_fail(tmp_path, monkeypatch):
    hb = tmp_path / "m33_http_wedge_reaper.txt"
    fake_procs = {"m33_http_wedge_reaper": {"heartbeat": hb, "cadence_sec": 30.0}}
    monkeypatch.setattr(checks, "NEW_PROCS", fake_procs)
    restart_at = 1000.0
    now = restart_at + 90.0  # 3x cadence, well past one tick
    rows = checks.check_new_procs(now, restart_at)
    assert rows[0]["status"] == checks.FAIL


def test_new_proc_heartbeat_fresh_after_restart_is_pass(tmp_path, monkeypatch):
    hb = tmp_path / "m34_freshness_sla.txt"
    hb.write_text("beat", encoding="ascii")
    restart_at = hb.stat().st_mtime - 10.0  # restart happened BEFORE the beat
    fake_procs = {"m34_freshness_sla": {"heartbeat": hb, "cadence_sec": 300.0}}
    monkeypatch.setattr(checks, "NEW_PROCS", fake_procs)
    now = hb.stat().st_mtime + 5.0
    rows = checks.check_new_procs(now, restart_at)
    assert rows[0]["status"] == checks.PASS


def test_new_proc_heartbeat_predates_restart_past_tick_is_fail(tmp_path, monkeypatch):
    hb = tmp_path / "m34_freshness_sla.txt"
    hb.write_text("stale beat from a manual pre-restart run", encoding="ascii")
    mtime = hb.stat().st_mtime
    restart_at = mtime + 10.0  # restart happened AFTER the stale beat
    fake_procs = {"m34_freshness_sla": {"heartbeat": hb, "cadence_sec": 300.0}}
    monkeypatch.setattr(checks, "NEW_PROCS", fake_procs)
    now = restart_at + 1000.0  # well past one 300s tick
    rows = checks.check_new_procs(now, restart_at)
    assert rows[0]["status"] == checks.FAIL
    assert "predates restart" in rows[0]["evidence"]


def test_new_proc_heartbeat_predates_restart_within_tick_is_pending(tmp_path, monkeypatch):
    hb = tmp_path / "m34_freshness_sla.txt"
    hb.write_text("stale beat", encoding="ascii")
    mtime = hb.stat().st_mtime
    restart_at = mtime + 10.0
    fake_procs = {"m34_freshness_sla": {"heartbeat": hb, "cadence_sec": 300.0}}
    monkeypatch.setattr(checks, "NEW_PROCS", fake_procs)
    now = restart_at + 5.0  # within the 300s tick
    rows = checks.check_new_procs(now, restart_at)
    assert rows[0]["status"] == checks.PENDING


# --------------------------------------------------------------------------- #
# (d) capture dirs
# --------------------------------------------------------------------------- #
def test_capture_no_live_game_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_checks, "_LINE_HIST", tmp_path)
    monkeypatch.setattr(capture_checks, "CAPTURE_SPORTS", ["wnba"])
    rows = capture_checks.check_capture_dirs(1000.0, live_game_fn=lambda s: False)
    assert rows[0]["status"] == checks.PENDING
    assert "no live game" in rows[0]["evidence"]


def test_capture_live_game_no_dir_is_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_checks, "_LINE_HIST", tmp_path)
    monkeypatch.setattr(capture_checks, "CAPTURE_SPORTS", ["wnba"])
    rows = capture_checks.check_capture_dirs(1000.0, live_game_fn=lambda s: True)
    assert rows[0]["status"] == checks.FAIL
    assert "no capture dir" in rows[0]["evidence"]


def test_capture_live_game_fresh_tick_is_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_checks, "_LINE_HIST", tmp_path)
    monkeypatch.setattr(capture_checks, "CAPTURE_SPORTS", ["wnba"])
    sport_dir = tmp_path / "wnba"
    sport_dir.mkdir()
    tick = sport_dir / "2026-07-04.jsonl"
    tick.write_text('{"x":1}\n', encoding="ascii")
    now = tick.stat().st_mtime + 5.0
    rows = capture_checks.check_capture_dirs(now, live_game_fn=lambda s: True,
                                             fresh_sec=1800.0)
    assert rows[0]["status"] == checks.PASS


def test_capture_live_game_stale_tick_is_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_checks, "_LINE_HIST", tmp_path)
    monkeypatch.setattr(capture_checks, "CAPTURE_SPORTS", ["wnba"])
    sport_dir = tmp_path / "wnba"
    sport_dir.mkdir()
    tick = sport_dir / "2026-07-04.jsonl"
    tick.write_text('{"x":1}\n', encoding="ascii")
    now = tick.stat().st_mtime + 5000.0
    rows = capture_checks.check_capture_dirs(now, live_game_fn=lambda s: True,
                                             fresh_sec=1800.0)
    assert rows[0]["status"] == checks.FAIL


def test_capture_live_game_lookup_raises_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_checks, "_LINE_HIST", tmp_path)
    monkeypatch.setattr(capture_checks, "CAPTURE_SPORTS", ["wnba"])
    def _raise(_sport):
        raise RuntimeError("espn down")
    rows = capture_checks.check_capture_dirs(1000.0, live_game_fn=_raise)
    assert rows[0]["status"] == checks.PENDING


# --------------------------------------------------------------------------- #
# (e) shadow field
# --------------------------------------------------------------------------- #
def test_shadow_no_live_game_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_checks, "_INGAME_GRADE", tmp_path)
    rows = capture_checks.check_shadow_field(1000.0, live_game_fn=lambda s: False)
    assert rows[0]["status"] == checks.PENDING


def test_shadow_live_game_no_dir_is_pending_known_gap(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_checks, "_INGAME_GRADE", tmp_path)
    rows = capture_checks.check_shadow_field(1000.0, live_game_fn=lambda s: True)
    assert rows[0]["status"] == checks.PENDING
    assert "known gap" in rows[0]["evidence"]


def test_shadow_fresh_tick_with_field_is_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_checks, "_INGAME_GRADE", tmp_path)
    sport_dir = tmp_path / "wnba"
    sport_dir.mkdir()
    tick = sport_dir / "game1.jsonl"
    tick.write_text(json.dumps({"model_prob_wnba_shadow": 0.9815}) + "\n",
                    encoding="ascii")
    now = tick.stat().st_mtime + 5.0
    rows = capture_checks.check_shadow_field(now, live_game_fn=lambda s: True)
    assert rows[0]["status"] == checks.PASS


def test_shadow_fresh_tick_missing_field_is_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_checks, "_INGAME_GRADE", tmp_path)
    sport_dir = tmp_path / "wnba"
    sport_dir.mkdir()
    tick = sport_dir / "game1.jsonl"
    tick.write_text(json.dumps({"model_prob": 0.5}) + "\n", encoding="ascii")
    now = tick.stat().st_mtime + 5.0
    rows = capture_checks.check_shadow_field(now, live_game_fn=lambda s: True)
    assert rows[0]["status"] == checks.FAIL


def test_shadow_stale_tick_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_checks, "_INGAME_GRADE", tmp_path)
    sport_dir = tmp_path / "wnba"
    sport_dir.mkdir()
    tick = sport_dir / "game1.jsonl"
    tick.write_text(json.dumps({"model_prob_wnba_shadow": 0.5}) + "\n", encoding="ascii")
    now = tick.stat().st_mtime + 5000.0
    rows = capture_checks.check_shadow_field(now, live_game_fn=lambda s: True,
                                             fresh_sec=1800.0)
    assert rows[0]["status"] == checks.PENDING


# --------------------------------------------------------------------------- #
# (f) freshness_sla overall
# --------------------------------------------------------------------------- #
def test_freshness_sla_missing_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_OPS", tmp_path)
    row = checks.check_freshness_sla()
    assert row["status"] == checks.PENDING


def test_freshness_sla_green_is_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_OPS", tmp_path)
    (tmp_path / "freshness_sla.json").write_text(
        json.dumps({"overall": "GREEN", "n_daemons": 20, "n_red": 0, "n_na": 0}),
        encoding="ascii")
    row = checks.check_freshness_sla()
    assert row["status"] == checks.PASS


def test_freshness_sla_red_is_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_OPS", tmp_path)
    (tmp_path / "freshness_sla.json").write_text(
        json.dumps({"overall": "RED", "n_daemons": 20, "n_red": 2, "n_na": 0}),
        encoding="ascii")
    row = checks.check_freshness_sla()
    assert row["status"] == checks.FAIL


# --------------------------------------------------------------------------- #
# (g) kalshi pregame n_events
# --------------------------------------------------------------------------- #
def test_kalshi_pregame_events_present_is_pass():
    def fake_fetch(sport):
        return [{"event": "a"}, {"event": "b"}]
    rows = checks.check_kalshi_pregame(fetch_fn=fake_fetch)
    assert len(rows) == len(checks.KALSHI_PREGAME_SPORTS)
    assert all(r["status"] == checks.PASS and r["n_events"] == 2 for r in rows)


def test_kalshi_pregame_zero_events_is_fail():
    def fake_fetch(sport):
        return []
    rows = checks.check_kalshi_pregame(fetch_fn=fake_fetch)
    assert all(r["status"] == checks.FAIL for r in rows)


def test_kalshi_pregame_unavailable_dict_is_pending():
    def fake_fetch(sport):
        return {"reason": "kalshi call failed (URLError)"}
    rows = checks.check_kalshi_pregame(fetch_fn=fake_fetch)
    assert all(r["status"] == checks.PENDING for r in rows)


def test_kalshi_pregame_raises_is_pending_network_error():
    def fake_fetch(sport):
        raise TimeoutError("network down")
    rows = checks.check_kalshi_pregame(fetch_fn=fake_fetch)
    assert all(r["status"] == checks.PENDING for r in rows)


# --------------------------------------------------------------------------- #
# run_all / write_status / render_table orchestration
# --------------------------------------------------------------------------- #
def test_run_all_composes_overall_fail_on_any_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_OPS", tmp_path)
    monkeypatch.setattr(capture_checks, "_LINE_HIST", tmp_path)
    monkeypatch.setattr(capture_checks, "_INGAME_GRADE", tmp_path)

    def fake_http(url, timeout=10.0):
        return {"status": 200, "timed_out": False}

    def fake_kalshi(sport):
        return []  # n_events=0 -> FAIL

    report = verify.run_all(
        now=1000.0, http_probe_fn=fake_http, kalshi_fetch_fn=fake_kalshi,
        live_game_fn=lambda s: False)
    assert report["overall"] == verify.FAIL
    assert report["n_fail"] >= 1


def test_run_all_all_pending_and_pass_is_overall_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_OPS", tmp_path)
    monkeypatch.setattr(capture_checks, "_LINE_HIST", tmp_path)
    monkeypatch.setattr(capture_checks, "_INGAME_GRADE", tmp_path)
    doc = {"all_ready": True, "procs": [{"name": n} for n in checks.NEW_PROCS]}
    (tmp_path / "supervisor_status.json").write_text(json.dumps(doc), encoding="ascii")

    def fake_http(url, timeout=10.0):
        return {"status": 200, "timed_out": False}

    def fake_kalshi(sport):
        return {"reason": "unavailable"}  # PENDING, not FAIL

    report = verify.run_all(
        now=1000.0, http_probe_fn=fake_http, kalshi_fetch_fn=fake_kalshi,
        live_game_fn=lambda s: False)  # no live games -> capture/shadow PENDING
    assert report["overall"] == verify.PASS
    assert report["n_fail"] == 0
    assert report["n_pending"] > 0


def test_write_status_round_trip(tmp_path):
    report = {"generated_at": 123.0, "overall": "PASS", "rows": []}
    out = tmp_path / "post_restart_verify.json"
    ok = verify.write_status(report, out_path=out)
    assert ok is True
    loaded = json.loads(out.read_text(encoding="ascii"))
    assert loaded["overall"] == "PASS"


def test_render_table_contains_header_and_total():
    report = {
        "generated_at": 1000.0, "restart_ts": 900.0,
        "rows": [{"name": "x", "status": "PASS", "evidence": "ok"}],
        "n_pass": 1, "n_fail": 0, "n_pending": 0, "overall": "PASS",
    }
    table = verify.render_table(report)
    assert "POST-RESTART VERIFY" in table
    assert "PASS" in table
    assert "TOTAL: pass=1 fail=0 pending=0  overall=PASS" in table


def test_render_table_is_ascii_only():
    report = {
        "generated_at": 1000.0, "restart_ts": 900.0,
        "rows": [{"name": "x", "status": "FAIL", "evidence": "boom"}],
        "n_pass": 0, "n_fail": 1, "n_pending": 0, "overall": "FAIL",
    }
    table = verify.render_table(report)
    table.encode("ascii")  # raises UnicodeEncodeError if any non-ASCII char sneaks in
