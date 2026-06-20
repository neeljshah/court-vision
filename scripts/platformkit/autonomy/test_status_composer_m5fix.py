"""Per-file test for scripts.platformkit.autonomy.status_composer_m5fix (IOP-07).

Acceptance criteria (monotone-down, stale-never-green):
  * stale m5 heartbeat  -> services[] row severity DEGRADED (never ok).
  * absent m5 heartbeat -> severity DEGRADED (absent != ok).
  * fresh m5 heartbeat  -> severity ok; overall ok when no other degradation.
  * monotone-down: age progression ok -> degraded -> never back to ok.
  * no $ or edge field in the returned document.
  * patch is idempotent: applying twice does not upgrade a DEGRADED row back to ok.
  * bad doc input (non-dict) -> degraded envelope, never raises.
  * injected hb_path: file does not exist -> DEGRADED.
  * overall inherits worst row: a degraded m5 row raises overall to DEGRADED.
"""
from __future__ import annotations

import pathlib
import re
import tempfile
import time

import pytest

from scripts.platformkit.autonomy.status_composer_m5fix import (
    DEGRADED,
    DOWN,
    M5_COMPONENT,
    M5_FRESH_SEC,
    OK,
    patch_m5_row,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _ok_doc(overall: str = OK, extra_services=None) -> dict:
    """A minimal ok-looking autonomy doc."""
    return {
        "overall": overall,
        "services": list(extra_services or []),
        "notes": [],
        "honest_note": "calibration not edge; no $ field",
    }


def _write_hb(path: pathlib.Path, age_sec: float, now: float) -> None:
    """Write a heartbeat file with a timestamp that is ``age_sec`` seconds old."""
    from datetime import datetime, timezone
    ts = now - age_sec
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    path.write_text(dt.strftime("%Y-%m-%dT%H:%M:%SZ"), encoding="ascii")


# --------------------------------------------------------------------------- #
# Tests: fresh heartbeat
# --------------------------------------------------------------------------- #

def test_fresh_m5_heartbeat_is_ok():
    """A heartbeat well within fresh_sec must resolve to OK for the m5 row."""
    now = time.time()
    with tempfile.TemporaryDirectory() as td:
        hb = pathlib.Path(td) / "m5_autonomy_monitor.txt"
        _write_hb(hb, age_sec=30.0, now=now)
        doc = patch_m5_row(_ok_doc(), now=now, hb_path=hb, fresh_sec=300.0)
    m5_rows = [r for r in doc["services"] if r.get("name") == M5_COMPONENT]
    assert m5_rows, "m5 row must be present after patch"
    assert m5_rows[0]["severity"] == OK, "fresh heartbeat must be ok"


def test_fresh_m5_does_not_degrade_overall():
    """A fresh m5 must not push a previously-ok overall to degraded."""
    now = time.time()
    with tempfile.TemporaryDirectory() as td:
        hb = pathlib.Path(td) / "m5_autonomy_monitor.txt"
        _write_hb(hb, age_sec=10.0, now=now)
        doc = patch_m5_row(_ok_doc(OK), now=now, hb_path=hb, fresh_sec=300.0)
    assert doc["overall"] == OK, "fresh m5 must not degrade an already-ok overall"


# --------------------------------------------------------------------------- #
# Tests: stale heartbeat (core IOP-07 fix)
# --------------------------------------------------------------------------- #

def test_stale_m5_heartbeat_is_degraded_never_ok():
    """A heartbeat older than fresh_sec must yield DEGRADED, never OK. (IOP-07 core)"""
    now = time.time()
    with tempfile.TemporaryDirectory() as td:
        hb = pathlib.Path(td) / "m5_autonomy_monitor.txt"
        _write_hb(hb, age_sec=M5_FRESH_SEC + 1.0, now=now)
        doc = patch_m5_row(_ok_doc(), now=now, hb_path=hb, fresh_sec=M5_FRESH_SEC)
    m5_rows = [r for r in doc["services"] if r.get("name") == M5_COMPONENT]
    assert m5_rows, "m5 row must be present after patch"
    assert m5_rows[0]["severity"] == DEGRADED, (
        "stale m5 heartbeat must be DEGRADED, got %r" % m5_rows[0]["severity"])


def test_stale_m5_degrades_overall():
    """A stale m5 row must push an ok-looking overall to DEGRADED."""
    now = time.time()
    with tempfile.TemporaryDirectory() as td:
        hb = pathlib.Path(td) / "m5_autonomy_monitor.txt"
        _write_hb(hb, age_sec=M5_FRESH_SEC + 60.0, now=now)
        doc = patch_m5_row(_ok_doc(OK), now=now, hb_path=hb, fresh_sec=M5_FRESH_SEC)
    assert doc["overall"] == DEGRADED, (
        "stale m5 must degrade an ok overall, got %r" % doc["overall"])


def test_stale_m5_adds_note():
    """A stale m5 heartbeat must surface a note in the doc."""
    now = time.time()
    with tempfile.TemporaryDirectory() as td:
        hb = pathlib.Path(td) / "m5_autonomy_monitor.txt"
        _write_hb(hb, age_sec=M5_FRESH_SEC + 300.0, now=now)
        doc = patch_m5_row(_ok_doc(), now=now, hb_path=hb, fresh_sec=M5_FRESH_SEC)
    notes_str = str(doc.get("notes", []))
    assert "m5fix" in notes_str.lower() or "stale" in notes_str.lower(), (
        "stale m5 must add a note; got: %s" % notes_str)


# --------------------------------------------------------------------------- #
# Tests: absent heartbeat
# --------------------------------------------------------------------------- #

def test_absent_m5_heartbeat_is_degraded():
    """A missing heartbeat file must yield DEGRADED (absent != ok)."""
    with tempfile.TemporaryDirectory() as td:
        hb = pathlib.Path(td) / "m5_autonomy_monitor.txt"
        # File does NOT exist.
        doc = patch_m5_row(_ok_doc(), now=time.time(), hb_path=hb, fresh_sec=300.0)
    m5_rows = [r for r in doc["services"] if r.get("name") == M5_COMPONENT]
    assert m5_rows, "m5 row must be appended even when heartbeat is absent"
    assert m5_rows[0]["severity"] == DEGRADED, (
        "absent m5 heartbeat must be DEGRADED, got %r" % m5_rows[0]["severity"])


def test_absent_m5_degrades_overall():
    """A missing m5 heartbeat must push the overall to DEGRADED."""
    with tempfile.TemporaryDirectory() as td:
        hb = pathlib.Path(td) / "m5_autonomy_monitor.txt"
        doc = patch_m5_row(_ok_doc(OK), now=time.time(), hb_path=hb, fresh_sec=300.0)
    assert doc["overall"] == DEGRADED, (
        "absent m5 must degrade ok overall, got %r" % doc["overall"])


# --------------------------------------------------------------------------- #
# Tests: monotone-down (the severity invariant)
# --------------------------------------------------------------------------- #

def test_monotone_down_age_progression():
    """Severity must be: age=10s -> ok; age=fresh+1 -> degraded; never green again."""
    now = time.time()
    with tempfile.TemporaryDirectory() as td:
        hb = pathlib.Path(td) / "m5_autonomy_monitor.txt"

        # Fresh (age 10s) -> ok
        _write_hb(hb, age_sec=10.0, now=now)
        d0 = patch_m5_row(_ok_doc(), now=now, hb_path=hb, fresh_sec=300.0)
        sev0 = [r["severity"] for r in d0["services"] if r.get("name") == M5_COMPONENT][0]
        assert sev0 == OK, "age=10s should be ok, got %r" % sev0

        # Just-stale (age fresh+1) -> degraded
        _write_hb(hb, age_sec=301.0, now=now)
        d1 = patch_m5_row(_ok_doc(), now=now, hb_path=hb, fresh_sec=300.0)
        sev1 = [r["severity"] for r in d1["services"] if r.get("name") == M5_COMPONENT][0]
        assert sev1 == DEGRADED, "age=301s should be degraded, got %r" % sev1

        # Very stale (age 2x) -> still degraded (not worse than degraded for a hb alone)
        _write_hb(hb, age_sec=600.0, now=now)
        d2 = patch_m5_row(_ok_doc(), now=now, hb_path=hb, fresh_sec=300.0)
        sev2 = [r["severity"] for r in d2["services"] if r.get("name") == M5_COMPONENT][0]
        # Must be >= DEGRADED (monotone-down: can only stay same or get worse).
        from scripts.platformkit.autonomy.status_composer_m5fix import _RANK
        assert _RANK[sev2] >= _RANK[sev1], (
            "severity must not improve as age grows: %r -> %r" % (sev1, sev2))


def test_monotone_down_does_not_upgrade_worse_row():
    """patch_m5_row must NOT upgrade an already-DOWN row back to DEGRADED/OK."""
    now = time.time()
    pre_existing = {
        "name": M5_COMPONENT,
        "severity": DOWN,
        "reason": "pre-existing down state",
    }
    doc_with_down = _ok_doc(DOWN, extra_services=[pre_existing])
    with tempfile.TemporaryDirectory() as td:
        hb = pathlib.Path(td) / "m5_autonomy_monitor.txt"
        # Fresh heartbeat -- but row was already DOWN.
        _write_hb(hb, age_sec=10.0, now=now)
        patched = patch_m5_row(doc_with_down, now=now, hb_path=hb, fresh_sec=300.0)
    m5_rows = [r for r in patched["services"] if r.get("name") == M5_COMPONENT]
    assert m5_rows[0]["severity"] == DOWN, (
        "monotone-down: a DOWN row must not be upgraded to OK/DEGRADED by a fresh hb")
    assert patched["overall"] == DOWN, "overall must not be upgraded either"


# --------------------------------------------------------------------------- #
# Tests: idempotency
# --------------------------------------------------------------------------- #

def test_patch_is_idempotent_stale():
    """Applying patch_m5_row twice to a stale doc must not upgrade the row."""
    now = time.time()
    with tempfile.TemporaryDirectory() as td:
        hb = pathlib.Path(td) / "m5_autonomy_monitor.txt"
        _write_hb(hb, age_sec=M5_FRESH_SEC + 60.0, now=now)
        doc1 = patch_m5_row(_ok_doc(), now=now, hb_path=hb, fresh_sec=M5_FRESH_SEC)
        doc2 = patch_m5_row(doc1, now=now, hb_path=hb, fresh_sec=M5_FRESH_SEC)
    for d in (doc1, doc2):
        m5 = [r for r in d["services"] if r.get("name") == M5_COMPONENT][0]
        assert m5["severity"] == DEGRADED, "double-apply must not change stale severity"
    assert doc2["overall"] == DEGRADED


# --------------------------------------------------------------------------- #
# Tests: bad / edge-case inputs
# --------------------------------------------------------------------------- #

def test_non_dict_doc_returns_degraded():
    """A non-dict input doc must return a DEGRADED envelope, never raises."""
    result = patch_m5_row(None)  # type: ignore[arg-type]
    assert isinstance(result, dict)
    assert result["overall"] == DEGRADED


def test_patch_never_raises_on_garbage_input():
    """patch_m5_row must never raise even on malformed inputs."""
    for bad in (None, 42, "string", [], object()):
        try:
            r = patch_m5_row(bad)  # type: ignore[arg-type]
            assert isinstance(r, dict)
        except Exception as exc:  # noqa: BLE001
            pytest.fail("patch_m5_row raised on %r: %s" % (bad, exc))


def test_m5_row_appended_when_services_absent():
    """When services[] is missing or empty, the m5 row is appended (never invisible)."""
    with tempfile.TemporaryDirectory() as td:
        hb = pathlib.Path(td) / "m5_autonomy_monitor.txt"
        # No heartbeat file.
        doc = patch_m5_row({"overall": OK, "services": [], "notes": []},
                           now=time.time(), hb_path=hb)
    m5_rows = [r for r in doc["services"] if r.get("name") == M5_COMPONENT]
    assert len(m5_rows) == 1, "m5 row must be present even from empty services list"


def test_m5_row_not_duplicated():
    """Patching a doc that already has a m5 row must not duplicate it."""
    now = time.time()
    pre_existing = {"name": M5_COMPONENT, "severity": OK, "live": True}
    doc = _ok_doc(extra_services=[pre_existing])
    with tempfile.TemporaryDirectory() as td:
        hb = pathlib.Path(td) / "m5_autonomy_monitor.txt"
        _write_hb(hb, age_sec=30.0, now=now)
        patched = patch_m5_row(doc, now=now, hb_path=hb, fresh_sec=300.0)
    m5_rows = [r for r in patched["services"] if r.get("name") == M5_COMPONENT]
    assert len(m5_rows) == 1, "m5 row must not be duplicated"


# --------------------------------------------------------------------------- #
# Tests: no dollar / edge fields
# --------------------------------------------------------------------------- #

def test_no_dollar_edge_field_in_output():
    """Returned doc must not contain any $ adjacent to a digit (fabricated P&L)."""
    now = time.time()
    with tempfile.TemporaryDirectory() as td:
        hb = pathlib.Path(td) / "m5_autonomy_monitor.txt"
        _write_hb(hb, age_sec=30.0, now=now)
        doc = patch_m5_row(_ok_doc(), now=now, hb_path=hb)
    doc_str = str(doc)
    assert not re.search(r"\$\s*\d", doc_str), (
        "doc must not contain $ adjacent to a digit: %s" % doc_str)


def test_honest_note_present():
    """The returned doc must carry an honest_note field (calibration not edge)."""
    with tempfile.TemporaryDirectory() as td:
        hb = pathlib.Path(td) / "m5_autonomy_monitor.txt"
        doc = patch_m5_row(_ok_doc(), now=time.time(), hb_path=hb)
    assert "honest_note" in doc, "honest_note field must be present"
    assert "calibration" in doc["honest_note"].lower() or "no $" in doc["honest_note"], (
        "honest_note must reference calibration or no $ field")
