"""Per-file tests for ops.metrics_rollup._liveness_counts liveness fix.

Acceptance criteria:
  1. Port-bound service with no heartbeat file is NOT in liveness.down.
  2. Heartbeat daemon with stale/absent beat IS in liveness.down.
  3. No $/ROI key leaks through rollup output.

Per-file run only:
    python -m pytest ops/tests/test_metrics_rollup.py -q
"""
from __future__ import annotations

import json
from typing import Any, Dict

import pytest

from ops import metrics_rollup as mr
from ops import service_registry as sr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _snap(live_map: Dict[str, bool]) -> Dict[str, Any]:
    return {
        name: {"live": live, "age_sec": 5.0 if live else None, "path": "/fake/%s" % name}
        for name, live in live_map.items()
    }


def _port_desc(name: str, port: int):
    return sr.ServiceDescriptor(name=name, liveness_component=None, port=port)


def _hb_desc(name: str, comp: str):
    return sr.ServiceDescriptor(name=name, liveness_component=comp, port=None)


# ---------------------------------------------------------------------------
# 1. Port-bound service NOT in down
# ---------------------------------------------------------------------------

class TestPortBoundNotInDown:
    def test_manifest_port_server_excluded(self, monkeypatch):
        """Port-probed server (liveness_component=None, port set) must not appear
        in liveness.down even when the snapshot has it with live=False."""
        monkeypatch.setattr(mr._liveness, "liveness_snapshot",
                            lambda **k: _snap({"m1_api_paper": False, "line_daemon": True}))
        monkeypatch.setattr(mr._registry, "service_descriptors", lambda *a, **k: [
            _port_desc("m1_api_paper", port=8099),
            _hb_desc("m1_line_daemon", comp="line_daemon"),
        ])
        down = mr.rollup(now=9999.0)["liveness"]["down"]
        assert "m1_api_paper" not in down

    def test_legacy_alias_excluded(self, monkeypatch):
        """predict_service_api is a daemon_registry legacy alias for the
        port-bound Auto-API.  Its component key is not in hb_components, so
        it must be excluded from liveness.down (false-positive fix)."""
        monkeypatch.setattr(mr._liveness, "liveness_snapshot",
                            lambda **k: _snap({"predict_service_api": False,
                                               "paper_loop": True}))
        # Only paper_loop is a recognised heartbeat component.
        monkeypatch.setattr(mr._registry, "service_descriptors", lambda *a, **k: [
            _hb_desc("m1_paper", comp="paper_loop"),
        ])
        down = mr.rollup(now=9999.0)["liveness"]["down"]
        assert "predict_service_api" not in down

    def test_all_known_port_servers_excluded(self, monkeypatch):
        """m1_api_paper, m1_api_boards, m1_ui, and a non-manifest alias are all
        excluded; only a genuine heartbeat daemon with live=False stays in down."""
        monkeypatch.setattr(mr._liveness, "liveness_snapshot", lambda **k: _snap({
            "m1_api_paper": False, "m1_api_boards": False,
            "m1_ui": False, "paper_loop": False,
        }))
        monkeypatch.setattr(mr._registry, "service_descriptors", lambda *a, **k: [
            _port_desc("m1_api_paper", port=8099),
            _port_desc("m1_api_boards", port=8098),
            _port_desc("m1_ui", port=3000),
            _hb_desc("m1_paper", comp="paper_loop"),
        ])
        down = mr.rollup(now=9999.0)["liveness"]["down"]
        assert "m1_api_paper" not in down
        assert "m1_api_boards" not in down
        assert "m1_ui" not in down
        assert "paper_loop" in down  # genuine daemon still in down

    def test_total_excludes_port_bound(self, monkeypatch):
        """Port-probed entries do not inflate total or live counts."""
        monkeypatch.setattr(mr._liveness, "liveness_snapshot", lambda **k: _snap({
            "m1_api_paper": False, "paper_loop": True, "line_daemon": False,
        }))
        monkeypatch.setattr(mr._registry, "service_descriptors", lambda *a, **k: [
            _port_desc("m1_api_paper", port=8099),
            _hb_desc("m1_paper", comp="paper_loop"),
            _hb_desc("m1_line_daemon", comp="line_daemon"),
        ])
        lv = mr.rollup(now=9999.0)["liveness"]
        assert lv["total"] == 2       # only the 2 heartbeat daemons
        assert lv["live"] == 1
        assert lv["down"] == ["line_daemon"]


# ---------------------------------------------------------------------------
# 2. Heartbeat daemon with stale/absent beat IS in down
# ---------------------------------------------------------------------------

class TestHeartbeatDaemonInDown:
    def test_stale_daemon_in_down(self, monkeypatch):
        monkeypatch.setattr(mr._liveness, "liveness_snapshot",
                            lambda **k: _snap({"auto_settle_daemon": False}))
        monkeypatch.setattr(mr._registry, "service_descriptors", lambda *a, **k: [
            _hb_desc("auto_settle_daemon", comp="auto_settle_daemon"),
        ])
        assert "auto_settle_daemon" in mr.rollup(now=9999.0)["liveness"]["down"]

    def test_absent_beat_daemon_in_down(self, monkeypatch):
        monkeypatch.setattr(mr._liveness, "liveness_snapshot",
                            lambda **k: _snap({"missing_daemon": False}))
        monkeypatch.setattr(mr._registry, "service_descriptors", lambda *a, **k: [
            _hb_desc("missing_daemon", comp="missing_daemon"),
        ])
        assert "missing_daemon" in mr.rollup(now=9999.0)["liveness"]["down"]

    def test_live_daemon_not_in_down(self, monkeypatch):
        monkeypatch.setattr(mr._liveness, "liveness_snapshot",
                            lambda **k: _snap({"paper_loop": True}))
        monkeypatch.setattr(mr._registry, "service_descriptors", lambda *a, **k: [
            _hb_desc("paper_loop", comp="paper_loop"),
        ])
        assert "paper_loop" not in mr.rollup(now=9999.0)["liveness"]["down"]


# ---------------------------------------------------------------------------
# 3. No $/ROI leak
# ---------------------------------------------------------------------------

class TestNoROILeak:
    def test_roi_and_profit_blocked(self, tmp_path, monkeypatch):
        sb = tmp_path / "grade_summary.json"
        sb.write_text(json.dumps({
            "n_settled": 10, "mean_clv_pct": 1.2,
            "pct_beat_close": 55.0, "flat_unit_wins": 6, "flat_unit_losses": 4,
            "roi": 999.0, "profit": 500.0,   # must NOT leak
        }), encoding="utf-8")
        monkeypatch.setattr(mr._liveness, "liveness_snapshot", lambda **k: {})
        monkeypatch.setattr(mr._registry, "service_descriptors", lambda *a, **k: [])
        result = mr.rollup(scoreboard_path=sb, now=9999.0)
        blob = json.dumps(result).lower()
        assert "roi" not in blob
        assert "profit" not in blob
        assert result["clv"]["n_settled"] == 10
        assert result["clv"]["mean_clv_pct"] == 1.2


# ---------------------------------------------------------------------------
# _port_probed_names unit tests
# ---------------------------------------------------------------------------

class TestPortProbedNamesHelper:
    def test_returns_port_bound_names_only(self, monkeypatch):
        monkeypatch.setattr(mr._registry, "service_descriptors", lambda *a, **k: [
            _port_desc("api_server", port=8080),
            _hb_desc("my_daemon", comp="my_daemon"),
        ])
        names = mr._port_probed_names()
        assert "api_server" in names
        assert "my_daemon" not in names

    def test_empty_registry_returns_empty(self, monkeypatch):
        monkeypatch.setattr(mr._registry, "service_descriptors", lambda *a, **k: [])
        assert mr._port_probed_names() == frozenset()

    def test_never_raises_on_failure(self, monkeypatch):
        monkeypatch.setattr(mr._registry, "service_descriptors",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
        assert mr._port_probed_names() == frozenset()


# ---------------------------------------------------------------------------
# Integration (real service_registry)
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_rollup_shape(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mr._liveness, "liveness_snapshot", lambda **k: {})
        result = mr.rollup(scoreboard_path=tmp_path / "nope.json", now=1000.0)
        for key in ("generated_at", "clv", "liveness", "honest_note"):
            assert key in result

    def test_real_registry_port_servers_not_in_down(self, monkeypatch):
        """Using the real service_registry: the three manifest port-servers must
        not appear in liveness.down when their snapshot entry is live=False."""
        port_names = {"m1_api_paper", "m1_api_boards", "m1_ui"}
        monkeypatch.setattr(mr._liveness, "liveness_snapshot", lambda **k: {
            n: {"live": False, "age_sec": None, "path": "/fake"} for n in port_names
        })
        down = mr.rollup(now=9999.0)["liveness"]["down"]
        for n in port_names:
            assert n not in down

    def test_predict_service_api_not_in_down_real_registry(self, monkeypatch):
        """predict_service_api (legacy daemon_registry alias, not in manifest)
        must not appear in liveness.down with the real service_registry."""
        monkeypatch.setattr(mr._liveness, "liveness_snapshot", lambda **k: {
            "predict_service_api": {"live": False, "age_sec": None, "path": "/fake"},
        })
        assert "predict_service_api" not in mr.rollup(now=9999.0)["liveness"]["down"]
