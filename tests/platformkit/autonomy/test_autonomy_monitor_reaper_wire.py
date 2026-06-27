"""Per-file tests: autonomy_monitor_runner IOP-08 reaper wire.

Acceptance criteria (all must pass):
  * STALE_HUNG reaper row degrades the matching service to degraded/down (never ok).
  * NO_HEARTBEAT reaper row also degrades the matching service.
  * HEALTHY reaper rows do NOT change a service's severity (never upgrade to ok).
  * Missing reaper file leaves services unchanged (unknown, not green).
  * Degrade-only: a service already "down" is NOT softened to "degraded".
  * Overall severity re-derives from the degraded services (DEGRADED never green).
  * No $ field anywhere in the output document.
  * The doc written to disk matches what tick() returns.

All offline: stub compose, injected clock, isolated paths. No sleep, no network.
Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/autonomy/test_autonomy_monitor_reaper_wire.py -q
"""
from __future__ import annotations

import json
import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import pytest

from scripts.platformkit.autonomy import autonomy_monitor_runner as amr
from scripts.platformkit.autonomy.reaper_status_bridge import write_reaper_status
from scripts.platformkit.autonomy.heartbeat_reaper import STALE_HUNG, NO_HEARTBEAT, HEALTHY

NOW = 1_000_000.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compose_with_services(services):
    """Return a stub compose fn that emits the supplied services list."""
    def _compose(**kw):
        return {
            "generated_at": kw.get("now"),
            "overall": "ok",
            "services": list(services),
            "loop": {},
            "ratchet": {},
            "high_water": {},
            "idle_reason": None,
            "notes": [],
            "honest_note": "stub",
        }
    return _compose


def _svc(name: str, severity: str = "ok") -> dict:
    return {"name": name, "severity": severity, "live": True}


def _reaper_path(tmp: pathlib.Path) -> pathlib.Path:
    return tmp / "reaper_status.json"


def _write_reaper(path, rows, now=NOW):
    write_reaper_status(rows, out_path=path, now=now)


def _run_tick(compose, tmp, reaper_path=None):
    """Run one tick with isolated paths; return the published doc."""
    from ops import liveness as lv
    status_path = tmp / "autonomy_status.json"
    monkeypatch_hb = tmp / "hb"
    # Patch liveness heartbeat dir so no real file is touched.
    old = lv._DAEMON_HB_DIR
    lv._DAEMON_HB_DIR = monkeypatch_hb
    try:
        doc = amr.tick(
            now=NOW,
            compose=compose,
            status_path=status_path,
            reaper_path=reaper_path,
        )
    finally:
        lv._DAEMON_HB_DIR = old
    return doc, status_path


# ---------------------------------------------------------------------------
# Test: STALE_HUNG degrades service
# ---------------------------------------------------------------------------

class TestStaleHungDegrades:
    def test_stale_hung_degrades_ok_service_to_degraded(self, tmp_path, monkeypatch):
        """A STALE_HUNG reaper row must degrade an 'ok' service to 'degraded'."""
        from ops import liveness as lv
        monkeypatch.setattr(lv, "_DAEMON_HB_DIR", tmp_path / "hb")

        rp = _reaper_path(tmp_path)
        _write_reaper(rp, [{"name": "m3_ingame", "status": STALE_HUNG, "breaker": {}}])
        compose = _compose_with_services([_svc("m3_ingame", "ok")])
        status_path = tmp_path / "out.json"

        doc = amr.tick(now=NOW, compose=compose, status_path=status_path, reaper_path=rp)
        svcs = {s["name"]: s for s in doc["services"]}
        assert svcs["m3_ingame"]["severity"] == "degraded"
        assert svcs["m3_ingame"]["reaper_status"] == STALE_HUNG

    def test_stale_hung_overall_not_ok(self, tmp_path, monkeypatch):
        """Overall must not remain 'ok' when a STALE_HUNG service exists."""
        from ops import liveness as lv
        monkeypatch.setattr(lv, "_DAEMON_HB_DIR", tmp_path / "hb")

        rp = _reaper_path(tmp_path)
        _write_reaper(rp, [{"name": "svc_a", "status": STALE_HUNG, "breaker": {}}])
        compose = _compose_with_services([_svc("svc_a", "ok")])
        status_path = tmp_path / "out.json"

        doc = amr.tick(now=NOW, compose=compose, status_path=status_path, reaper_path=rp)
        assert doc["overall"] != "ok", "overall must be degraded/down, never ok when a service is STALE_HUNG"

    def test_stale_hung_already_down_stays_down(self, tmp_path, monkeypatch):
        """A service already 'down' must remain 'down'; never softened to 'degraded'."""
        from ops import liveness as lv
        monkeypatch.setattr(lv, "_DAEMON_HB_DIR", tmp_path / "hb")

        rp = _reaper_path(tmp_path)
        _write_reaper(rp, [{"name": "m1_prod", "status": STALE_HUNG, "breaker": {}}])
        compose = _compose_with_services([_svc("m1_prod", "down")])
        status_path = tmp_path / "out.json"

        doc = amr.tick(now=NOW, compose=compose, status_path=status_path, reaper_path=rp)
        svcs = {s["name"]: s for s in doc["services"]}
        assert svcs["m1_prod"]["severity"] == "down", "down must not be upgraded to degraded"

    def test_multiple_stale_hung_all_degraded(self, tmp_path, monkeypatch):
        """Every STALE_HUNG row must degrade its matching service."""
        from ops import liveness as lv
        monkeypatch.setattr(lv, "_DAEMON_HB_DIR", tmp_path / "hb")

        rp = _reaper_path(tmp_path)
        names = ["svc_0", "svc_1", "svc_2"]
        _write_reaper(rp, [{"name": n, "status": STALE_HUNG, "breaker": {}} for n in names])
        compose = _compose_with_services([_svc(n, "ok") for n in names])
        status_path = tmp_path / "out.json"

        doc = amr.tick(now=NOW, compose=compose, status_path=status_path, reaper_path=rp)
        for svc in doc["services"]:
            assert svc["severity"] == "degraded"
            assert svc["reaper_status"] == STALE_HUNG


# ---------------------------------------------------------------------------
# Test: NO_HEARTBEAT degrades service
# ---------------------------------------------------------------------------

class TestNoHeartbeatDegrades:
    def test_no_heartbeat_degrades_ok_service(self, tmp_path, monkeypatch):
        """NO_HEARTBEAT must also degrade a service that reads 'ok'."""
        from ops import liveness as lv
        monkeypatch.setattr(lv, "_DAEMON_HB_DIR", tmp_path / "hb")

        rp = _reaper_path(tmp_path)
        _write_reaper(rp, [{"name": "m6_predict", "status": NO_HEARTBEAT, "breaker": {}}])
        compose = _compose_with_services([_svc("m6_predict", "ok")])
        status_path = tmp_path / "out.json"

        doc = amr.tick(now=NOW, compose=compose, status_path=status_path, reaper_path=rp)
        svcs = {s["name"]: s for s in doc["services"]}
        assert svcs["m6_predict"]["severity"] == "degraded"
        assert svcs["m6_predict"]["reaper_status"] == NO_HEARTBEAT
        assert doc["overall"] != "ok"


# ---------------------------------------------------------------------------
# Test: HEALTHY rows leave severity unchanged
# ---------------------------------------------------------------------------

class TestHealthyNeverUpgrades:
    def test_healthy_row_does_not_change_degraded_service(self, tmp_path, monkeypatch):
        """A HEALTHY reaper row must NOT upgrade a 'degraded' service to 'ok'."""
        from ops import liveness as lv
        monkeypatch.setattr(lv, "_DAEMON_HB_DIR", tmp_path / "hb")

        rp = _reaper_path(tmp_path)
        _write_reaper(rp, [{"name": "m1_producer", "status": HEALTHY, "breaker": {}}])
        compose = _compose_with_services([_svc("m1_producer", "degraded")])
        status_path = tmp_path / "out.json"

        doc = amr.tick(now=NOW, compose=compose, status_path=status_path, reaper_path=rp)
        svcs = {s["name"]: s for s in doc["services"]}
        assert svcs["m1_producer"]["severity"] == "degraded"
        assert "reaper_status" not in svcs["m1_producer"]

    def test_healthy_row_ok_service_stays_ok(self, tmp_path, monkeypatch):
        """A HEALTHY reaper row for an 'ok' service must leave it 'ok'."""
        from ops import liveness as lv
        monkeypatch.setattr(lv, "_DAEMON_HB_DIR", tmp_path / "hb")

        rp = _reaper_path(tmp_path)
        _write_reaper(rp, [{"name": "m1_producer", "status": HEALTHY, "breaker": {}}])
        compose = _compose_with_services([_svc("m1_producer", "ok")])
        status_path = tmp_path / "out.json"

        doc = amr.tick(now=NOW, compose=compose, status_path=status_path, reaper_path=rp)
        svcs = {s["name"]: s for s in doc["services"]}
        assert svcs["m1_producer"]["severity"] == "ok"


# ---------------------------------------------------------------------------
# Test: missing reaper file leaves services unchanged
# ---------------------------------------------------------------------------

class TestMissingReaperFile:
    def test_missing_reaper_file_leaves_services_unchanged(self, tmp_path, monkeypatch):
        """Missing reaper file -> services unchanged (unknown, NOT green-forced)."""
        from ops import liveness as lv
        monkeypatch.setattr(lv, "_DAEMON_HB_DIR", tmp_path / "hb")

        no_file = tmp_path / "nonexistent_reaper.json"
        compose = _compose_with_services([_svc("some_svc", "degraded")])
        status_path = tmp_path / "out.json"

        doc = amr.tick(now=NOW, compose=compose, status_path=status_path, reaper_path=no_file)
        svcs = {s["name"]: s for s in doc["services"]}
        # Must not upgrade degraded to ok; must not change severity at all.
        assert svcs["some_svc"]["severity"] == "degraded"
        assert "reaper_status" not in svcs["some_svc"]

    def test_no_reaper_path_arg_does_not_crash(self, tmp_path, monkeypatch):
        """tick() with no reaper_path must not crash (defaults to bridge default)."""
        from ops import liveness as lv
        monkeypatch.setattr(lv, "_DAEMON_HB_DIR", tmp_path / "hb")

        compose = _compose_with_services([_svc("svc_x", "ok")])
        status_path = tmp_path / "out.json"
        # reaper_path not supplied -> defaults to real path which may not exist; must not crash.
        doc = amr.tick(now=NOW, compose=compose, status_path=status_path)
        assert doc["overall"] in ("ok", "degraded", "down")


# ---------------------------------------------------------------------------
# Test: published file on disk matches returned doc
# ---------------------------------------------------------------------------

class TestDiskMatchesReturnedDoc:
    def test_disk_file_matches_returned_doc(self, tmp_path, monkeypatch):
        """The JSON file written to disk must parse to the same doc tick() returns."""
        from ops import liveness as lv
        monkeypatch.setattr(lv, "_DAEMON_HB_DIR", tmp_path / "hb")

        rp = _reaper_path(tmp_path)
        _write_reaper(rp, [{"name": "m3", "status": STALE_HUNG, "breaker": {}}])
        compose = _compose_with_services([_svc("m3", "ok")])
        status_path = tmp_path / "out.json"

        doc = amr.tick(now=NOW, compose=compose, status_path=status_path, reaper_path=rp)
        assert status_path.exists()
        on_disk = json.loads(status_path.read_text(encoding="ascii"))
        # Both must agree on overall and service severity.
        assert on_disk["overall"] == doc["overall"]
        disk_svcs = {s["name"]: s for s in on_disk["services"]}
        assert disk_svcs["m3"]["severity"] == "degraded"


# ---------------------------------------------------------------------------
# Test: no $ field anywhere
# ---------------------------------------------------------------------------

class TestNoDollarField:
    def test_no_dollar_key_in_published_doc(self, tmp_path, monkeypatch):
        """Merged output must never contain a $ key."""
        from ops import liveness as lv
        monkeypatch.setattr(lv, "_DAEMON_HB_DIR", tmp_path / "hb")

        rp = _reaper_path(tmp_path)
        _write_reaper(rp, [{"name": "m3", "status": STALE_HUNG, "breaker": {}}])
        compose = _compose_with_services([_svc("m3", "ok")])
        status_path = tmp_path / "out.json"

        doc = amr.tick(now=NOW, compose=compose, status_path=status_path, reaper_path=rp)
        # Walk all keys in doc and nested services dicts.
        for key in doc:
            assert "$" not in str(key), f"$ in top-level key: {key}"
        for svc in doc.get("services", []):
            if isinstance(svc, dict):
                for key in svc:
                    assert "$" not in str(key), f"$ in service key: {key}"
        # Also check no pnl/roi/edge claim keys.
        all_keys = set(doc.keys())
        for svc in doc.get("services", []):
            if isinstance(svc, dict):
                all_keys.update(svc.keys())
        assert not any(k.lower() in ("pnl", "roi", "edge") for k in all_keys)


# ---------------------------------------------------------------------------
# Test: mixed STALE_HUNG + HEALTHY in same batch
# ---------------------------------------------------------------------------

class TestMixedReaperBatch:
    def test_mixed_batch_stale_hung_degrades_healthy_leaves_ok(self, tmp_path, monkeypatch):
        """Batch with STALE_HUNG and HEALTHY: only STALE_HUNG service is degraded."""
        from ops import liveness as lv
        monkeypatch.setattr(lv, "_DAEMON_HB_DIR", tmp_path / "hb")

        rp = _reaper_path(tmp_path)
        _write_reaper(rp, [
            {"name": "m3_ingame", "status": STALE_HUNG, "breaker": {"state": "OPEN"}},
            {"name": "m1_producer", "status": HEALTHY, "breaker": {"state": "CLOSED"}},
        ])
        compose = _compose_with_services([
            _svc("m3_ingame", "ok"),
            _svc("m1_producer", "ok"),
        ])
        status_path = tmp_path / "out.json"

        doc = amr.tick(now=NOW, compose=compose, status_path=status_path, reaper_path=rp)
        svcs = {s["name"]: s for s in doc["services"]}
        assert svcs["m3_ingame"]["severity"] == "degraded"
        assert svcs["m3_ingame"]["reaper_status"] == STALE_HUNG
        assert svcs["m1_producer"]["severity"] == "ok"
        assert "reaper_status" not in svcs["m1_producer"]
        assert doc["overall"] != "ok"
