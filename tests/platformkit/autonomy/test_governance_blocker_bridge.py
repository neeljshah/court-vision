"""Per-file tests for scripts.platformkit.autonomy.governance_blocker_bridge.

IOPiii-02 acceptance tests:
  - snapshot() reads clv_dup_report.json -> writes governance_blockers.json with
    {blockers:[{name:'clv_ledger_dups', status, n_dups, blocking}], generated_at}
  - DUPS_FOUND -> blocking=True; CLEAN -> blockers=[] (blocking absent)
  - Absent dup report -> UNAVAILABLE, blocking=True (never green on missing file)
  - merge_into(compose_doc) degrades overall to >=DEGRADED when any blocking
  - merge_into is degrade-only (never upgrades overall from 'down' to 'degraded')
  - Never mutates the CLV ledger (read-only check)
  - No $ key in any output
  - Never raises even on garbage input

Run (per-file only -- never full pytest):
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/autonomy/test_governance_blocker_bridge.py -q
"""
from __future__ import annotations

import json
import pathlib

import pytest

from scripts.platformkit.autonomy.governance_blocker_bridge import (
    DEFAULT_BLOCKERS_PATH,
    DEFAULT_DUP_REPORT_PATH,
    merge_into,
    snapshot,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_DUPS_FOUND_DOC = {
    "status": "DUPS_FOUND",
    "n_dups": 9,
    "dup_keys": ["nba|NYK@SAS|moneyline|away|espn:DraftKings|2026-06-20"],
    "component": "m18_dupaudit",
    "generated_at": "2026-06-20T05:28:22Z",
}

_CLEAN_DOC = {
    "status": "CLEAN",
    "n_dups": 0,
    "dup_keys": [],
    "component": "m18_dupaudit",
    "generated_at": "2026-06-20T06:00:00Z",
}


def _write_dup_report(path: pathlib.Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=True), encoding="ascii")


# ---------------------------------------------------------------------------
# Tests: snapshot() -- basic cases
# ---------------------------------------------------------------------------

class TestSnapshotDupsFound:
    """DUPS_FOUND in clv_dup_report.json -> blocking=True in governance_blockers."""

    def test_dups_found_produces_blocking_true(self, tmp_path):
        dup_path = tmp_path / "clv_dup_report.json"
        out_path = tmp_path / "governance_blockers.json"
        _write_dup_report(dup_path, _DUPS_FOUND_DOC)

        doc = snapshot(dup_report_path=dup_path, out_path=out_path, now=1_000_000.0)

        assert doc["blockers"], "blockers must be non-empty for DUPS_FOUND"
        b = doc["blockers"][0]
        assert b["name"] == "clv_ledger_dups"
        assert b["status"] == "DUPS_FOUND"
        assert b["n_dups"] == 9
        assert b["blocking"] is True

    def test_dups_found_writes_file_to_disk(self, tmp_path):
        dup_path = tmp_path / "clv_dup_report.json"
        out_path = tmp_path / "governance_blockers.json"
        _write_dup_report(dup_path, _DUPS_FOUND_DOC)

        snapshot(dup_report_path=dup_path, out_path=out_path, now=0.0)

        assert out_path.exists(), "governance_blockers.json must be written to disk"
        on_disk = json.loads(out_path.read_text(encoding="ascii"))
        assert on_disk["blockers"][0]["blocking"] is True

    def test_dups_found_generated_at_present(self, tmp_path):
        dup_path = tmp_path / "clv_dup_report.json"
        out_path = tmp_path / "governance_blockers.json"
        _write_dup_report(dup_path, _DUPS_FOUND_DOC)

        doc = snapshot(dup_report_path=dup_path, out_path=out_path, now=12345.0)
        assert doc["generated_at"] == pytest.approx(12345.0)

    def test_dups_found_atomic_write_no_tmp_leftover(self, tmp_path):
        dup_path = tmp_path / "clv_dup_report.json"
        out_path = tmp_path / "governance_blockers.json"
        _write_dup_report(dup_path, _DUPS_FOUND_DOC)

        snapshot(dup_report_path=dup_path, out_path=out_path)

        tmp = out_path.with_suffix(out_path.suffix + ".tmp")
        assert not tmp.exists(), ".tmp must be cleaned up after atomic write"


class TestSnapshotClean:
    """CLEAN in clv_dup_report.json -> blockers=[] (no blocking entry)."""

    def test_clean_status_produces_empty_blockers(self, tmp_path):
        dup_path = tmp_path / "clv_dup_report.json"
        out_path = tmp_path / "governance_blockers.json"
        _write_dup_report(dup_path, _CLEAN_DOC)

        doc = snapshot(dup_report_path=dup_path, out_path=out_path, now=0.0)

        assert doc["blockers"] == [], "CLEAN must yield blockers=[]"

    def test_clean_writes_file(self, tmp_path):
        dup_path = tmp_path / "clv_dup_report.json"
        out_path = tmp_path / "governance_blockers.json"
        _write_dup_report(dup_path, _CLEAN_DOC)

        snapshot(dup_report_path=dup_path, out_path=out_path)

        on_disk = json.loads(out_path.read_text(encoding="ascii"))
        assert on_disk["blockers"] == []


class TestSnapshotAbsent:
    """Absent clv_dup_report.json -> UNAVAILABLE, blocking=True (never green)."""

    def test_absent_file_produces_unavailable_and_blocking(self, tmp_path):
        dup_path = tmp_path / "no_such_file.json"
        out_path = tmp_path / "governance_blockers.json"

        doc = snapshot(dup_report_path=dup_path, out_path=out_path, now=0.0)

        assert doc["blockers"], "absent file must produce a blocking entry"
        b = doc["blockers"][0]
        assert b["status"] == "UNAVAILABLE"
        assert b["blocking"] is True

    def test_absent_file_never_green(self, tmp_path):
        """An absent dup report MUST NOT produce blockers=[] (that would be green)."""
        dup_path = tmp_path / "no_such_file.json"
        out_path = tmp_path / "governance_blockers.json"

        doc = snapshot(dup_report_path=dup_path, out_path=out_path)

        assert doc["blockers"] != [], "absent file must NOT yield empty blockers (green)"

    def test_garbage_json_produces_unavailable(self, tmp_path):
        dup_path = tmp_path / "clv_dup_report.json"
        out_path = tmp_path / "governance_blockers.json"
        dup_path.write_text("not json {{{", encoding="ascii")

        doc = snapshot(dup_report_path=dup_path, out_path=out_path)

        b = doc["blockers"][0]
        assert b["status"] == "UNAVAILABLE"
        assert b["blocking"] is True

    def test_empty_file_produces_unavailable(self, tmp_path):
        dup_path = tmp_path / "clv_dup_report.json"
        out_path = tmp_path / "governance_blockers.json"
        dup_path.write_text("", encoding="ascii")

        doc = snapshot(dup_report_path=dup_path, out_path=out_path)

        assert doc["blockers"][0]["status"] == "UNAVAILABLE"


class TestSnapshotNoDollarKey:
    """No $ key and no forbidden ROI/PnL keys in any snapshot output."""

    def _all_keys(self, doc: dict) -> list:
        keys = list(doc.keys())
        for b in doc.get("blockers", []):
            if isinstance(b, dict):
                keys.extend(b.keys())
        return keys

    def test_no_dollar_key_dups_found(self, tmp_path):
        dup_path = tmp_path / "clv_dup_report.json"
        out_path = tmp_path / "governance_blockers.json"
        _write_dup_report(dup_path, _DUPS_FOUND_DOC)
        doc = snapshot(dup_report_path=dup_path, out_path=out_path)

        for k in self._all_keys(doc):
            assert "$" not in str(k), f"no $ key allowed; found: {k}"
        forbidden = {"pnl", "roi", "edge", "profit"}
        for k in self._all_keys(doc):
            assert k.lower() not in forbidden, f"forbidden key: {k}"

    def test_no_dollar_key_clean(self, tmp_path):
        dup_path = tmp_path / "clv_dup_report.json"
        out_path = tmp_path / "governance_blockers.json"
        _write_dup_report(dup_path, _CLEAN_DOC)
        doc = snapshot(dup_report_path=dup_path, out_path=out_path)

        for k in self._all_keys(doc):
            assert "$" not in str(k)

    def test_honest_note_present(self, tmp_path):
        dup_path = tmp_path / "clv_dup_report.json"
        out_path = tmp_path / "governance_blockers.json"
        _write_dup_report(dup_path, _CLEAN_DOC)
        doc = snapshot(dup_report_path=dup_path, out_path=out_path)
        assert "honest_note" in doc
        assert "no $" in doc["honest_note"]


# ---------------------------------------------------------------------------
# Tests: merge_into() -- degrade-only semantics
# ---------------------------------------------------------------------------

class TestMergeIntoDupsFound:
    """DUPS_FOUND must degrade overall to >=DEGRADED and add a note."""

    def _compose(self, overall: str = "ok") -> dict:
        return {"overall": overall, "notes": [], "services": []}

    def test_dups_found_degrades_ok_to_degraded(self, tmp_path):
        dup_path = tmp_path / "clv_dup_report.json"
        _write_dup_report(dup_path, _DUPS_FOUND_DOC)

        doc = self._compose("ok")
        merge_into(doc, dup_report_path=dup_path)

        assert doc["overall"] == "degraded", "DUPS_FOUND must degrade 'ok' to 'degraded'"

    def test_dups_found_note_appended(self, tmp_path):
        dup_path = tmp_path / "clv_dup_report.json"
        _write_dup_report(dup_path, _DUPS_FOUND_DOC)

        doc = self._compose("ok")
        merge_into(doc, dup_report_path=dup_path)

        assert any("BLOCKED" in n or "DUPS_FOUND" in n for n in doc["notes"]), (
            "A blocking note must be appended"
        )

    def test_dups_found_does_not_upgrade_down_to_degraded(self, tmp_path):
        """Degrade-only: 'down' must stay 'down', never softened to 'degraded'."""
        dup_path = tmp_path / "clv_dup_report.json"
        _write_dup_report(dup_path, _DUPS_FOUND_DOC)

        doc = self._compose("down")
        merge_into(doc, dup_report_path=dup_path)

        assert doc["overall"] == "down", "'down' must never be upgraded to 'degraded'"

    def test_dups_found_degraded_stays_degraded(self, tmp_path):
        dup_path = tmp_path / "clv_dup_report.json"
        _write_dup_report(dup_path, _DUPS_FOUND_DOC)

        doc = self._compose("degraded")
        merge_into(doc, dup_report_path=dup_path)

        assert doc["overall"] == "degraded"


class TestMergeIntoClean:
    """CLEAN must leave overall unchanged (no degradation from a clean ledger)."""

    def _compose(self, overall: str = "ok") -> dict:
        return {"overall": overall, "notes": [], "services": []}

    def test_clean_does_not_degrade_ok(self, tmp_path):
        dup_path = tmp_path / "clv_dup_report.json"
        _write_dup_report(dup_path, _CLEAN_DOC)

        doc = self._compose("ok")
        merge_into(doc, dup_report_path=dup_path)

        assert doc["overall"] == "ok", "CLEAN must not degrade an 'ok' status"

    def test_clean_appends_no_note(self, tmp_path):
        dup_path = tmp_path / "clv_dup_report.json"
        _write_dup_report(dup_path, _CLEAN_DOC)

        doc = self._compose("ok")
        merge_into(doc, dup_report_path=dup_path)

        assert doc["notes"] == [], "CLEAN must not append any note"


class TestMergeIntoAbsent:
    """Absent dup report -> UNAVAILABLE -> blocking=True -> overall degraded."""

    def _compose(self, overall: str = "ok") -> dict:
        return {"overall": overall, "notes": [], "services": []}

    def test_absent_file_degrades_ok(self, tmp_path):
        dup_path = tmp_path / "no_such_file.json"

        doc = self._compose("ok")
        merge_into(doc, dup_report_path=dup_path)

        assert doc["overall"] in ("degraded", "down"), (
            "Absent dup report must degrade overall (never green)"
        )

    def test_absent_file_appends_unavailable_note(self, tmp_path):
        dup_path = tmp_path / "no_such_file.json"

        doc = self._compose("ok")
        merge_into(doc, dup_report_path=dup_path)

        assert any("UNAVAILABLE" in n or "BLOCKED" in n for n in doc["notes"]), (
            "An UNAVAILABLE/BLOCKED note must be appended for absent file"
        )


class TestMergeIntoNeverRaises:
    """merge_into must never raise even on pathological input."""

    def test_garbage_compose_doc_does_not_raise(self, tmp_path):
        dup_path = tmp_path / "no_file.json"
        # Pass a totally wrong type -- must survive
        result = merge_into({"overall": None, "notes": None}, dup_report_path=dup_path)
        assert result is not None

    def test_none_notes_handled(self, tmp_path):
        dup_path = tmp_path / "clv_dup_report.json"
        _write_dup_report(dup_path, _DUPS_FOUND_DOC)

        # notes is None -- should not raise
        doc = {"overall": "ok", "notes": None}
        merge_into(doc, dup_report_path=dup_path)
        # Should have degraded
        assert doc["overall"] in ("degraded", "down")


# ---------------------------------------------------------------------------
# Tests: ledger is never mutated
# ---------------------------------------------------------------------------

class TestLedgerNotMutated:
    """snapshot() and merge_into() must never touch the CLV ledger."""

    def test_snapshot_does_not_write_ledger(self, tmp_path):
        dup_path = tmp_path / "clv_dup_report.json"
        out_path = tmp_path / "governance_blockers.json"
        ledger_path = tmp_path / "clv_ledger.jsonl"
        ledger_content = '{"key": "nba|NYK@SAS|moneyline|away|espn|2026-06-20", "prob": 0.52}\n'
        ledger_path.write_text(ledger_content, encoding="ascii")
        _write_dup_report(dup_path, _DUPS_FOUND_DOC)

        snapshot(dup_report_path=dup_path, out_path=out_path)

        # Ledger content must be unchanged
        assert ledger_path.read_text(encoding="ascii") == ledger_content, (
            "snapshot() must NOT mutate the CLV ledger"
        )

    def test_merge_into_does_not_write_ledger(self, tmp_path):
        dup_path = tmp_path / "clv_dup_report.json"
        ledger_path = tmp_path / "clv_ledger.jsonl"
        ledger_content = '{"key": "mlb|CHW@DET|moneyline|away|espn|2026-06-20"}\n'
        ledger_path.write_text(ledger_content, encoding="ascii")
        _write_dup_report(dup_path, _DUPS_FOUND_DOC)

        doc = {"overall": "ok", "notes": []}
        merge_into(doc, dup_report_path=dup_path)

        assert ledger_path.read_text(encoding="ascii") == ledger_content, (
            "merge_into() must NOT mutate the CLV ledger"
        )


# ---------------------------------------------------------------------------
# Tests: snapshot round-trip schema validation
# ---------------------------------------------------------------------------

class TestSnapshotSchema:
    """The governance_blockers.json on disk must conform to the expected schema."""

    def test_dups_found_on_disk_schema(self, tmp_path):
        dup_path = tmp_path / "clv_dup_report.json"
        out_path = tmp_path / "governance_blockers.json"
        _write_dup_report(dup_path, _DUPS_FOUND_DOC)

        snapshot(dup_report_path=dup_path, out_path=out_path)

        on_disk = json.loads(out_path.read_text(encoding="ascii"))
        assert "blockers" in on_disk
        assert "generated_at" in on_disk
        assert "honest_note" in on_disk
        assert isinstance(on_disk["blockers"], list)
        b = on_disk["blockers"][0]
        assert "name" in b
        assert "status" in b
        assert "n_dups" in b
        assert "blocking" in b
        assert b["name"] == "clv_ledger_dups"

    def test_clean_on_disk_schema(self, tmp_path):
        dup_path = tmp_path / "clv_dup_report.json"
        out_path = tmp_path / "governance_blockers.json"
        _write_dup_report(dup_path, _CLEAN_DOC)

        snapshot(dup_report_path=dup_path, out_path=out_path)

        on_disk = json.loads(out_path.read_text(encoding="ascii"))
        assert on_disk["blockers"] == []
        assert "generated_at" in on_disk
        assert "honest_note" in on_disk
