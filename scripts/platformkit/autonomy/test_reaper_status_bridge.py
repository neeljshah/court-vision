"""Per-file tests for scripts.platformkit.autonomy.reaper_status_bridge.

IOP-08 acceptance tests:
  - reaper STALE_HUNG rows surface in reaper_status.json (write + load round-trip)
  - merge only degrades severity, never upgrades to "ok"
  - missing reaper file -> empty list (unknown, not green)
  - no $ field in any output
  - services[] gets reaper_status annotation when STALE_HUNG

Run (per-file only -- never full pytest):
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_reaper_status_bridge.py -q
"""
from __future__ import annotations

import json
import pathlib
import tempfile

import pytest

from scripts.platformkit.autonomy.reaper_status_bridge import (
    DEFAULT_REAPER_STATUS_PATH,
    load_reaper_status,
    merge_reaper_into_services,
    write_reaper_status,
)
from scripts.platformkit.autonomy.heartbeat_reaper import (
    STALE_HUNG,
    NO_HEARTBEAT,
    HEALTHY,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_path_custom(tmp_path: pathlib.Path) -> pathlib.Path:
    """A fresh temp directory for each test."""
    return tmp_path


def _reaper_path(tmp: pathlib.Path) -> pathlib.Path:
    return tmp / "reaper_status.json"


# ---------------------------------------------------------------------------
# Test: write_reaper_status -- basic round-trip
# ---------------------------------------------------------------------------

class TestWriteReaperStatus:
    def test_stale_hung_row_persisted(self, tmp_path_custom):
        """STALE_HUNG rows must appear in the written JSON under 'rows'."""
        rows = [
            {"name": "m3_ingame_loop", "status": STALE_HUNG, "breaker": {"state": "OPEN"}},
        ]
        path = _reaper_path(tmp_path_custom)
        ok = write_reaper_status(rows, out_path=path, now=1_000_000.0)
        assert ok, "write must succeed"
        assert path.exists(), "reaper_status.json must be written"
        doc = json.loads(path.read_text(encoding="ascii"))
        assert doc["rows"][0]["status"] == STALE_HUNG
        assert doc["rows"][0]["name"] == "m3_ingame_loop"

    def test_no_dollar_field_in_output(self, tmp_path_custom):
        """No $ key in any dict in the document (honest_note text is exempt)."""
        rows = [{"name": "svc", "status": STALE_HUNG, "breaker": {}}]
        path = _reaper_path(tmp_path_custom)
        write_reaper_status(rows, out_path=path, now=0.0)
        doc = json.loads(path.read_text(encoding="ascii"))
        # Walk every dict key at top level and in rows -- no $ key allowed
        top_keys = set(doc.keys())
        assert not any("$" in k for k in top_keys), "no $ key in top-level doc"
        for row in doc.get("rows", []):
            if isinstance(row, dict):
                assert not any("$" in k for k in row), "no $ key in row dict"
        # No PnL / ROI / edge-claim KEYS (values like honest_note text are exempt)
        all_keys = top_keys.union(*(set(r.keys()) for r in doc.get("rows", [])
                                    if isinstance(r, dict)))
        assert not any(k.lower() in ("pnl", "roi", "edge") for k in all_keys)

    def test_generated_at_present(self, tmp_path_custom):
        path = _reaper_path(tmp_path_custom)
        write_reaper_status([], out_path=path, now=12345.0)
        doc = json.loads(path.read_text(encoding="ascii"))
        assert doc["generated_at"] == pytest.approx(12345.0)

    def test_atomic_tmp_cleaned_up(self, tmp_path_custom):
        """The .tmp file must not remain after a successful write."""
        path = _reaper_path(tmp_path_custom)
        write_reaper_status([], out_path=path)
        tmp = path.with_suffix(path.suffix + ".tmp")
        assert not tmp.exists(), ".tmp file must be removed after atomic write"

    def test_honest_note_present(self, tmp_path_custom):
        path = _reaper_path(tmp_path_custom)
        write_reaper_status([], out_path=path)
        doc = json.loads(path.read_text(encoding="ascii"))
        assert "honest_note" in doc
        assert "no $" in doc["honest_note"]

    def test_multiple_rows(self, tmp_path_custom):
        rows = [
            {"name": "m1_producer", "status": HEALTHY, "breaker": {}},
            {"name": "m3_ingame", "status": STALE_HUNG, "breaker": {"state": "OPEN"}},
            {"name": "m6_predict", "status": NO_HEARTBEAT, "breaker": {}},
        ]
        path = _reaper_path(tmp_path_custom)
        write_reaper_status(rows, out_path=path)
        doc = json.loads(path.read_text(encoding="ascii"))
        assert len(doc["rows"]) == 3
        statuses = {r["name"]: r["status"] for r in doc["rows"]}
        assert statuses["m3_ingame"] == STALE_HUNG
        assert statuses["m6_predict"] == NO_HEARTBEAT

    def test_non_dict_rows_dropped(self, tmp_path_custom):
        """Non-dict items in the rows list are silently dropped."""
        rows = [{"name": "good", "status": STALE_HUNG}, "bad", None, 42]
        path = _reaper_path(tmp_path_custom)
        write_reaper_status(rows, out_path=path)  # type: ignore[arg-type]
        doc = json.loads(path.read_text(encoding="ascii"))
        assert all(isinstance(r, dict) for r in doc["rows"])
        assert len(doc["rows"]) == 1


# ---------------------------------------------------------------------------
# Test: load_reaper_status -- missing/absent cases
# ---------------------------------------------------------------------------

class TestLoadReaperStatus:
    def test_missing_file_returns_empty_list(self, tmp_path_custom):
        """Missing file -> [] (unknown, NOT green)."""
        path = tmp_path_custom / "nonexistent.json"
        rows = load_reaper_status(path=path)
        assert rows == [], "missing file must yield empty list, not fabricated data"

    def test_round_trip_stale_hung(self, tmp_path_custom):
        """Write then load must recover the STALE_HUNG row."""
        path = _reaper_path(tmp_path_custom)
        write_reaper_status(
            [{"name": "svc_a", "status": STALE_HUNG, "breaker": {"state": "OPEN"}}],
            out_path=path,
        )
        rows = load_reaper_status(path=path)
        assert len(rows) == 1
        assert rows[0]["status"] == STALE_HUNG
        assert rows[0]["name"] == "svc_a"

    def test_empty_file_returns_empty_list(self, tmp_path_custom):
        path = _reaper_path(tmp_path_custom)
        path.write_text("", encoding="ascii")
        assert load_reaper_status(path=path) == []

    def test_garbage_json_returns_empty_list(self, tmp_path_custom):
        path = _reaper_path(tmp_path_custom)
        path.write_text("not json at all {{{{", encoding="ascii")
        assert load_reaper_status(path=path) == []

    def test_rows_key_missing_returns_empty(self, tmp_path_custom):
        path = _reaper_path(tmp_path_custom)
        path.write_text(json.dumps({"other": 1}), encoding="ascii")
        assert load_reaper_status(path=path) == []


# ---------------------------------------------------------------------------
# Test: merge_reaper_into_services -- degrade-only invariant
# ---------------------------------------------------------------------------

class TestMergeReaperIntoServices:
    def _svc(self, name: str, severity: str = "ok") -> dict:
        return {"name": name, "severity": severity, "live": True}

    def test_stale_hung_degrades_ok_to_degraded(self):
        """A STALE_HUNG reaper row must degrade an 'ok' service to 'degraded'."""
        services = [self._svc("m3_ingame", "ok")]
        reaper_rows = [{"name": "m3_ingame", "status": STALE_HUNG, "breaker": {}}]
        result = merge_reaper_into_services(services, reaper_rows)
        assert result[0]["severity"] == "degraded"
        assert result[0]["reaper_status"] == STALE_HUNG

    def test_healthy_reaper_row_never_upgrades_severity(self):
        """A HEALTHY reaper row must NOT upgrade a degraded service to 'ok'."""
        services = [self._svc("m1_producer", "degraded")]
        reaper_rows = [{"name": "m1_producer", "status": HEALTHY, "breaker": {}}]
        result = merge_reaper_into_services(services, reaper_rows)
        # severity must stay at least 'degraded'; never upgraded to 'ok'
        assert result[0]["severity"] == "degraded"
        assert "reaper_status" not in result[0], "HEALTHY must not annotate reaper_status"

    def test_no_heartbeat_degrades_service(self):
        """NO_HEARTBEAT must also degrade the matching service."""
        services = [self._svc("m6_predict", "ok")]
        reaper_rows = [{"name": "m6_predict", "status": NO_HEARTBEAT, "breaker": {}}]
        result = merge_reaper_into_services(services, reaper_rows)
        assert result[0]["severity"] == "degraded"
        assert result[0]["reaper_status"] == NO_HEARTBEAT

    def test_down_is_not_upgraded_to_degraded(self):
        """A service already 'down' must stay 'down' after merge; never softened."""
        services = [self._svc("m1_producer", "down")]
        reaper_rows = [{"name": "m1_producer", "status": STALE_HUNG, "breaker": {}}]
        result = merge_reaper_into_services(services, reaper_rows)
        # degrade(down, degraded) == down; must never upgrade to degraded
        assert result[0]["severity"] == "down"

    def test_service_not_in_reaper_unchanged(self):
        """A service missing from reaper_rows must be returned unchanged."""
        services = [self._svc("untracked_svc", "ok")]
        reaper_rows = [{"name": "other_svc", "status": STALE_HUNG, "breaker": {}}]
        result = merge_reaper_into_services(services, reaper_rows)
        assert result[0]["severity"] == "ok"
        assert "reaper_status" not in result[0]

    def test_empty_reaper_rows_returns_services_unchanged(self):
        """Empty reaper_rows list -> services unchanged."""
        services = [self._svc("m1_producer", "ok"), self._svc("m3", "degraded")]
        result = merge_reaper_into_services(services, [])
        assert result[0]["severity"] == "ok"
        assert result[1]["severity"] == "degraded"

    def test_result_is_new_list_not_mutated_in_place(self):
        """merge must not mutate the input services list."""
        svc = self._svc("m3_ingame", "ok")
        services = [svc]
        reaper_rows = [{"name": "m3_ingame", "status": STALE_HUNG, "breaker": {}}]
        result = merge_reaper_into_services(services, reaper_rows)
        # Original dict must be untouched
        assert svc.get("reaper_status") is None, "original svc dict must not be mutated"
        assert svc["severity"] == "ok"
        # Result is a NEW list
        assert result is not services

    def test_multiple_stale_hung_all_degraded(self):
        """All STALE_HUNG services in a batch must each be degraded."""
        services = [self._svc(f"svc_{i}") for i in range(4)]
        reaper_rows = [
            {"name": f"svc_{i}", "status": STALE_HUNG, "breaker": {}}
            for i in range(4)
        ]
        result = merge_reaper_into_services(services, reaper_rows)
        for r in result:
            assert r["severity"] == "degraded"
            assert r["reaper_status"] == STALE_HUNG

    def test_no_dollar_key_in_merged_output(self):
        """Merged services must not introduce any $ key."""
        services = [self._svc("m3", "ok")]
        reaper_rows = [{"name": "m3", "status": STALE_HUNG, "breaker": {}}]
        result = merge_reaper_into_services(services, reaper_rows)
        for item in result:
            for key in item:
                assert "$" not in str(key), f"no $ in key: {key}"


# ---------------------------------------------------------------------------
# Test: full flow -- write -> load -> merge
# ---------------------------------------------------------------------------

class TestFullFlow:
    def test_stale_hung_appears_in_services_after_full_flow(self, tmp_path_custom):
        """End-to-end: reaper writes STALE_HUNG, bridge loads it, merge surfaces it."""
        path = _reaper_path(tmp_path_custom)

        # Simulate supervisor writing the reaper snapshot
        reaper_snapshot = [
            {"name": "m3_ingame_loop", "status": STALE_HUNG,
             "breaker": {"state": "OPEN", "fail_count": 3}},
            {"name": "m1_producer", "status": HEALTHY,
             "breaker": {"state": "CLOSED", "fail_count": 0}},
        ]
        write_reaper_status(reaper_snapshot, out_path=path, now=9999.0)

        # Load reaper rows (as the compose-time consumer would)
        loaded = load_reaper_status(path=path)
        assert len(loaded) == 2

        # Merge into a services[] list (simulating status_composer extension)
        services = [
            {"name": "m3_ingame_loop", "severity": "ok", "live": True},
            {"name": "m1_producer", "severity": "ok", "live": True},
        ]
        merged = merge_reaper_into_services(services, loaded)

        # m3_ingame_loop was STALE_HUNG -> must read degraded
        m3 = next(s for s in merged if s["name"] == "m3_ingame_loop")
        assert m3["severity"] == "degraded"
        assert m3["reaper_status"] == STALE_HUNG

        # m1_producer was HEALTHY -> must remain ok
        m1 = next(s for s in merged if s["name"] == "m1_producer")
        assert m1["severity"] == "ok"
        assert "reaper_status" not in m1

    def test_missing_reaper_file_does_not_green_services(self, tmp_path_custom):
        """Missing reaper file -> no rows -> services unchanged (not green-forced)."""
        path = tmp_path_custom / "no_such_file.json"
        loaded = load_reaper_status(path=path)
        assert loaded == []

        services = [{"name": "m3", "severity": "degraded", "live": False}]
        merged = merge_reaper_into_services(services, loaded)
        # Must not upgrade degraded to ok
        assert merged[0]["severity"] == "degraded"
