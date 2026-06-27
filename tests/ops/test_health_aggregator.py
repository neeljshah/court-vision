"""Offline tests for ops.health_aggregator + ops.runbook + ops.metrics_rollup.

Injects fake heartbeat files and a fake clock via the liveness snapshot's
_registry_path / _hb_dir hooks and the well-known frontend heartbeat paths.
Never spawns a real process, binds a real port, or writes a production path.

Per-file run only:
    python -m pytest tests/ops/test_health_aggregator.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ops import health_aggregator as agg
from ops import metrics_rollup as mr
from ops import runbook as rb
from ops import service_registry as sr


# --------------------------------------------------------------------------- #
# Helpers: build a fake liveness snapshot keyed by component (monkeypatched in).
# --------------------------------------------------------------------------- #
def _fake_snapshot(live_map):
    """live_map: {component: (live, age_sec)} -> snapshot dict."""
    out = {}
    for comp, (live, age) in live_map.items():
        out[comp] = {"live": live, "age_sec": age, "path": "/fake/%s" % comp}
    return out


@pytest.fixture
def all_live(monkeypatch):
    """Every heartbeat-backed component is fresh."""
    snap = _fake_snapshot({
        "predict_service_scheduler": (True, 5.0),
        "ingame_live_loop": (True, 10.0),
        "line_daemon": (True, 12.0),
        "paper_loop": (True, 20.0),
    })
    monkeypatch.setattr(agg._liveness, "liveness_snapshot", lambda **k: snap)
    return snap


# --------------------------------------------------------------------------- #
# service_registry derives from the manifest
# --------------------------------------------------------------------------- #
class TestServiceRegistry:
    def test_descriptors_mirror_manifest(self):
        descs = sr.service_descriptors("default")
        names = {d.name for d in descs}
        assert "m1_producer" in names
        assert "m1_api_paper" in names
        assert "m6_ingame_loop" in names

    def test_critical_set(self):
        crit = set(sr.critical_names("default"))
        assert crit == {"m1_producer", "m1_api_paper"}

    def test_backend_profile_drops_ui(self):
        names = {d.name for d in sr.service_descriptors("backend")}
        assert "m1_ui" not in names

    def test_m7_has_liveness_component_autoderived(self):
        """BUG 2 regression: m7_ingame_refresh must carry a liveness component
        (auto-derived from its heartbeat filename stem) so a dead m7 is visible.
        Previously it was absent from the hand-maintained dict -> live=None ->
        never shown down."""
        descs = {d.name: d for d in sr.service_descriptors("default")}
        assert "m7_ingame_refresh" in descs
        m7 = descs["m7_ingame_refresh"]
        assert m7.liveness_component == "m7_ingame_refresh"

    def test_hb_stem_derivation(self):
        """The component name is derived from the heartbeat path stem (posix+win)."""
        assert sr._hb_stem("data/cache/daemon_heartbeats/m7_ingame_refresh.txt") == \
            "m7_ingame_refresh"
        assert sr._hb_stem("data\\cache\\hb\\new_daemon.txt") == "new_daemon"
        assert sr._hb_stem(None) is None


# --------------------------------------------------------------------------- #
# aggregate() overall rollup
# --------------------------------------------------------------------------- #
class TestAggregateOverall:
    def test_all_live_is_ok(self, all_live):
        status = agg.aggregate(now=1000.0)
        assert status["overall"] == "ok"
        assert any(s["name"] == "m1_producer" and s["live"] for s in status["services"])

    def test_noncritical_down_is_degraded(self, monkeypatch):
        snap = _fake_snapshot({
            "predict_service_scheduler": (True, 5.0),
            "ingame_live_loop": (True, 10.0),
            "line_daemon": (False, None),   # non-critical down
            "paper_loop": (True, 20.0),
        })
        monkeypatch.setattr(agg._liveness, "liveness_snapshot", lambda **k: snap)
        status = agg.aggregate(now=1000.0)
        assert status["overall"] == "degraded"

    def test_critical_down_is_down(self, monkeypatch):
        snap = _fake_snapshot({
            "predict_service_scheduler": (False, None),  # CRITICAL down
            "ingame_live_loop": (True, 10.0),
            "line_daemon": (True, 12.0),
            "paper_loop": (True, 20.0),
        })
        monkeypatch.setattr(agg._liveness, "liveness_snapshot", lambda **k: snap)
        status = agg.aggregate(now=1000.0)
        assert status["overall"] == "down"
        notes = " ".join(status["notes"]).lower()
        assert "m1_producer" in notes

    def test_stale_m7_is_degraded_and_named(self, monkeypatch):
        """BUG 2 regression: a stale/dead m7_ingame_refresh must surface as a
        non-critical DOWN -> overall degraded, and be NAMED in the doctor."""
        snap = _fake_snapshot({
            "predict_service_scheduler": (True, 5.0),
            "ingame_live_loop": (True, 10.0),
            "line_daemon": (True, 12.0),
            "paper_loop": (True, 20.0),
            "m7_ingame_refresh": (False, None),  # dead m7
        })
        monkeypatch.setattr(agg._liveness, "liveness_snapshot", lambda **k: snap)
        status = agg.aggregate(now=1000.0)
        assert status["overall"] == "degraded"
        row = next(s for s in status["services"] if s["name"] == "m7_ingame_refresh")
        assert row["live"] is False
        diag = rb.doctor(now=1000.0, status=status)
        names = {p["service"] for p in diag["problems"]}
        assert "m7_ingame_refresh" in names
        m7p = next(p for p in diag["problems"] if p["service"] == "m7_ingame_refresh")
        assert m7p["remedy"] and "boot.ps1" in m7p["remedy"]
        assert m7p["severity"] == "warning"  # non-critical

    def test_healthy_m7_not_flagged_within_hourly_window(self, monkeypatch):
        """A m7 that beat 20 min ago is HEALTHY (hourly cadence) -- not stale.
        Guards against the 300s-window flicker the manifest retune fixed."""
        snap = _fake_snapshot({
            "predict_service_scheduler": (True, 5.0),
            "ingame_live_loop": (True, 10.0),
            "line_daemon": (True, 12.0),
            "paper_loop": (True, 20.0),
            "m7_ingame_refresh": (True, 1200.0),  # 20 min ago -> still alive
        })
        monkeypatch.setattr(agg._liveness, "liveness_snapshot", lambda **k: snap)
        status = agg.aggregate(now=1000.0)
        row = next(s for s in status["services"] if s["name"] == "m7_ingame_refresh")
        assert row["live"] is True
        assert row["fresh"] in (None, "fresh")  # not stale at 20 min
        diag = rb.doctor(now=1000.0, status=status)
        assert "m7_ingame_refresh" not in {p["service"] for p in diag["problems"]}

    def test_stale_feed_flips_row_and_overall_not_ok(self, monkeypatch):
        """CORE INVARIANT: a source past its SLA (heartbeat live but data old)
        flips its row off "ok" (fresh="stale") AND drives overall to NOT-ok.
        A feed past its SLA can never read green."""
        # line_daemon source SLA is 300s; beat 5000s ago -> data is STALE even
        # though the process heartbeat we inject still reads live=True.
        snap = _fake_snapshot({
            "predict_service_scheduler": (True, 5.0),
            "ingame_live_loop": (True, 10.0),
            "line_daemon": (True, 5000.0),   # live process, STALE data feed
            "paper_loop": (True, 20.0),
        })
        monkeypatch.setattr(agg._liveness, "liveness_snapshot", lambda **k: snap)
        status = agg.aggregate(now=1000.0)
        assert status["overall"] != "ok"          # freshness GATES the rollup
        assert status["overall"] == "degraded"
        row = next(s for s in status["services"] if s["name"] == "m1_line_daemon")
        assert row["fresh"] == "stale"
        assert row["live"] is True                 # heartbeat alone said "fine"
        # the doctor names it with a remedy
        diag = rb.doctor(now=1000.0, status=status)
        names = {p["service"] for p in diag["problems"]}
        assert "m1_line_daemon" in names
        prob = next(p for p in diag["problems"] if p["service"] == "m1_line_daemon")
        assert prob["remedy"]

    def test_fresh_feed_stays_ok(self, monkeypatch):
        """A source comfortably within its SLA keeps fresh="fresh" and overall ok."""
        snap = _fake_snapshot({
            "predict_service_scheduler": (True, 5.0),
            "ingame_live_loop": (True, 10.0),
            "line_daemon": (True, 12.0),     # well within the 300s SLA
            "paper_loop": (True, 20.0),
        })
        monkeypatch.setattr(agg._liveness, "liveness_snapshot", lambda **k: snap)
        status = agg.aggregate(now=1000.0)
        assert status["overall"] == "ok"
        row = next(s for s in status["services"] if s["name"] == "m1_line_daemon")
        assert row["fresh"] in (None, "fresh")

    def test_critical_feed_not_reporting_is_down(self, monkeypatch):
        """A CRITICAL service whose data source has stopped reporting (fresh down)
        drives overall to "down". Here we force fresh="down" via a stale-but-live
        heartbeat past predict_service's 120s SLA -> at least degraded; with a
        dead heartbeat (live False) it is fully down."""
        snap = _fake_snapshot({
            "predict_service_scheduler": (True, 9999.0),  # critical, very stale data
            "ingame_live_loop": (True, 10.0),
            "line_daemon": (True, 12.0),
            "paper_loop": (True, 20.0),
        })
        monkeypatch.setattr(agg._liveness, "liveness_snapshot", lambda **k: snap)
        status = agg.aggregate(now=1000.0)
        # predict_service SLA 120s, age 9999s -> stale -> overall not ok.
        assert status["overall"] != "ok"
        row = next(s for s in status["services"] if s["name"] == "m1_producer")
        assert row["fresh"] == "stale"

    def test_breaker_open_marks_down(self, monkeypatch, all_live):
        from ops.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker("m1_api_boards", fail_threshold=1, cooldown_sec=999)
        cb.record_failure()  # trips OPEN
        status = agg.aggregate(now=1000.0, breakers={"m1_api_boards": cb})
        # m1_api_boards is non-critical -> degraded
        assert status["overall"] == "degraded"
        row = next(s for s in status["services"] if s["name"] == "m1_api_boards")
        assert row["breaker"] == "OPEN"

    def test_last_seen_derived_from_age(self, all_live):
        status = agg.aggregate(now=1000.0)
        row = next(s for s in status["services"] if s["name"] == "m1_producer")
        assert row["last_seen"] is not None
        assert row["age_sec"] == 5.0

    def test_never_raises_on_bad_snapshot(self, monkeypatch):
        def _boom(**k):
            raise RuntimeError("boom")
        monkeypatch.setattr(agg._liveness, "liveness_snapshot", _boom)
        status = agg.aggregate(now=1.0)
        assert "overall" in status  # degraded conservatively, no exception


# --------------------------------------------------------------------------- #
# write_status atomic + shape
# --------------------------------------------------------------------------- #
class TestWriteStatus:
    def test_writes_json(self, tmp_path, all_live):
        out = tmp_path / "ops" / "status.json"
        status = agg.aggregate(now=1000.0)
        agg.write_status(status, out_path=out)
        assert out.exists()
        loaded = json.loads(out.read_text(encoding="ascii"))
        assert loaded["overall"] == "ok"
        assert "services" in loaded

    def test_no_tmp_left(self, tmp_path, all_live):
        out = tmp_path / "status.json"
        agg.write_status(agg.aggregate(now=1000.0), out_path=out)
        assert not list(tmp_path.glob("*.tmp"))


# --------------------------------------------------------------------------- #
# doctor() names the failing service + remedy
# --------------------------------------------------------------------------- #
class TestDoctor:
    def test_all_ok(self, all_live):
        diag = rb.doctor(now=1000.0)
        assert diag["overall"] == "ok"
        assert diag["problems"] == []
        assert "healthy" in diag["summary"].lower()

    def test_names_failing_service(self, monkeypatch):
        snap = _fake_snapshot({
            "predict_service_scheduler": (False, None),
            "ingame_live_loop": (True, 10.0),
            "line_daemon": (True, 12.0),
            "paper_loop": (True, 20.0),
        })
        monkeypatch.setattr(agg._liveness, "liveness_snapshot", lambda **k: snap)
        diag = rb.doctor(now=1000.0)
        assert diag["overall"] == "down"
        names = {p["service"] for p in diag["problems"]}
        assert "m1_producer" in names
        prod = next(p for p in diag["problems"] if p["service"] == "m1_producer")
        assert prod["severity"] == "critical"
        assert prod["remedy"]  # non-empty remedy
        assert "boot.ps1" in prod["remedy"]

    def test_render_is_ascii(self, monkeypatch):
        snap = _fake_snapshot({
            "predict_service_scheduler": (False, None),
            "ingame_live_loop": (True, 10.0),
            "line_daemon": (True, 12.0),
            "paper_loop": (True, 20.0),
        })
        monkeypatch.setattr(agg._liveness, "liveness_snapshot", lambda **k: snap)
        text = rb.render(rb.doctor(now=1000.0))
        text.encode("ascii")  # raises if non-ASCII
        assert "OPS DOCTOR" in text
        assert "m1_producer" in text


# --------------------------------------------------------------------------- #
# metrics_rollup -- CLV pass-through, no $/ROI
# --------------------------------------------------------------------------- #
class TestMetricsRollup:
    def test_missing_scoreboard_zeroes(self, tmp_path, all_live):
        missing = tmp_path / "nope.json"
        m = mr.rollup(scoreboard_path=missing, now=1000.0)
        assert m["clv"]["n_settled"] == 0
        assert m["clv"]["mean_clv_pct"] is None

    def test_reads_clv_block_only(self, tmp_path, all_live):
        sb = tmp_path / "grade_summary.json"
        sb.write_text(json.dumps({
            "n_settled": 42, "mean_clv_pct": 1.5, "pct_beat_close": 56.0,
            "flat_unit_wins": 20, "flat_unit_losses": 22,
            "roi": 999.0, "profit": 12345.0,  # MUST NOT leak
        }), encoding="utf-8")
        m = mr.rollup(scoreboard_path=sb, now=1000.0)
        assert m["clv"]["n_settled"] == 42
        assert m["clv"]["mean_clv_pct"] == 1.5
        # no $ / ROI field leaks through the allowlist
        blob = json.dumps(m)
        assert "roi" not in blob.lower()
        assert "profit" not in blob.lower()

    def test_liveness_counts(self, all_live):
        m = mr.rollup(now=1000.0)
        assert m["liveness"]["live"] >= 1
        assert m["liveness"]["total"] >= m["liveness"]["live"]
