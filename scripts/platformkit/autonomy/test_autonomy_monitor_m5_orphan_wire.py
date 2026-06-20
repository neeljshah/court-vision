"""Per-file tests: BE7-3-m5-orphan-status-wire (IOP-06/IOP-07).

Covers _apply_m5fix (stale/null hb -> degraded, monotone-down), _apply_orphan_surface
(orphan stems -> notes, unconditional -- manifest IS importable here), tick() integration
(both wires fire, compose-error degrades), and the full monotone-down invariant.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_autonomy_monitor_m5_orphan_wire.py -q
"""
from __future__ import annotations

import json
import pathlib
import re
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

from scripts.platformkit.autonomy.autonomy_monitor_runner import (
    _apply_m5fix,
    _apply_orphan_surface,
    tick,
)

_NOW = 1_750_000_000.0


def _ok_doc(overall: str = "ok",
            services: Optional[List[Dict[str, Any]]] = None,
            notes: Optional[List[str]] = None) -> Dict[str, Any]:
    return {"overall": overall, "services": list(services or []),
            "notes": list(notes or []), "loop": {},
            "honest_note": "calibration not edge; no $ field"}


def _write_hb(path: pathlib.Path, age_sec: float, now: float) -> None:
    ts = now - age_sec
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dt.strftime("%Y-%m-%dT%H:%M:%SZ"), encoding="ascii")


def _write_orphan_hb(hb_dir: pathlib.Path, stem: str) -> pathlib.Path:
    hb_dir.mkdir(parents=True, exist_ok=True)
    p = hb_dir / ("%s.txt" % stem)
    p.write_text("ok", encoding="ascii")
    return p


def _stub_compose(doc: Dict[str, Any]):
    def _compose(**_kwargs):
        return dict(doc)
    return _compose


def _minimal_tick(tmp_path: pathlib.Path, *,
                  m5_hb_path: Optional[pathlib.Path] = None,
                  orphan_hb_dir: Optional[pathlib.Path] = None,
                  compose_doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return tick(
        now=_NOW,
        compose=_stub_compose(compose_doc or _ok_doc()),
        status_path=tmp_path / "autonomy_status.json",
        reaper_path=tmp_path / "reaper_status.json",
        m5_hb_path=m5_hb_path,
        orphan_hb_dir=orphan_hb_dir,
        orphan_report_path=tmp_path / "orphan_report.json",
    )


# ---------------------------------------------------------------------------
# 1. _apply_m5fix: stale/null m5 hb -> severity=degraded, never ok
# ---------------------------------------------------------------------------

class TestM5FixWire:

    @pytest.mark.parametrize("age_sec,exists", [(400.0, True), (0.0, False)])
    def test_hb_absent_or_stale_forces_degraded(self, age_sec, exists):
        """Stale (age>300s) or absent m5 hb -> severity=degraded in services[]."""
        with tempfile.TemporaryDirectory() as td:
            hb = pathlib.Path(td) / "m5_autonomy_monitor.txt"
            if exists:
                _write_hb(hb, age_sec=age_sec, now=_NOW)
            doc = _apply_m5fix(_ok_doc(), now=_NOW, m5_hb_path=hb)
        m5 = [r for r in doc["services"] if r.get("name") == "m5_autonomy_monitor"]
        assert m5, "m5 row must be present"
        assert m5[0]["severity"] == "degraded", "got %r" % m5[0]["severity"]

    def test_stale_m5_degrades_overall(self):
        """Stale m5 must push an ok overall to degraded."""
        with tempfile.TemporaryDirectory() as td:
            hb = pathlib.Path(td) / "m5_autonomy_monitor.txt"
            _write_hb(hb, age_sec=500.0, now=_NOW)
            doc = _apply_m5fix(_ok_doc("ok"), now=_NOW, m5_hb_path=hb)
        assert doc["overall"] == "degraded", "got %r" % doc["overall"]

    def test_fresh_hb_does_not_upgrade_degraded_overall(self):
        """Fresh m5 beat must NOT upgrade an already-degraded overall."""
        pre = _ok_doc("degraded")
        with tempfile.TemporaryDirectory() as td:
            hb = pathlib.Path(td) / "m5_autonomy_monitor.txt"
            _write_hb(hb, age_sec=10.0, now=_NOW)
            doc = _apply_m5fix(pre, now=_NOW, m5_hb_path=hb)
        assert doc["overall"] == "degraded", "monotone-down violated; got %r" % doc["overall"]

    def test_never_upgrades_down_row(self):
        """Fresh m5 hb must not upgrade a pre-existing DOWN row."""
        pre_m5 = {"name": "m5_autonomy_monitor", "severity": "down", "reason": "pre"}
        doc = _ok_doc("down", services=[pre_m5])
        with tempfile.TemporaryDirectory() as td:
            hb = pathlib.Path(td) / "m5_autonomy_monitor.txt"
            _write_hb(hb, age_sec=5.0, now=_NOW)
            result = _apply_m5fix(doc, now=_NOW, m5_hb_path=hb)
        m5 = [r for r in result["services"] if r.get("name") == "m5_autonomy_monitor"]
        assert m5[0]["severity"] == "down", "got %r" % m5[0]["severity"]
        assert result["overall"] == "down"

    def test_m5fix_never_raises_on_bad_doc(self):
        """_apply_m5fix must not raise on garbage doc inputs."""
        with tempfile.TemporaryDirectory() as td:
            hb = pathlib.Path(td) / "m5_autonomy_monitor.txt"
            _write_hb(hb, age_sec=10.0, now=_NOW)
            for bad in (None, 42, [], "string"):
                try:
                    _apply_m5fix(bad, now=_NOW, m5_hb_path=hb)  # type: ignore[arg-type]
                except Exception as exc:
                    pytest.fail("_apply_m5fix raised on %r: %s" % (bad, exc))


# ---------------------------------------------------------------------------
# 2. _apply_orphan_surface: orphan stems -> surfaced in doc["notes"]
# ---------------------------------------------------------------------------

class TestOrphanSurfaceWire:

    def test_orphan_stems_appear_in_notes(self):
        """Orphan stems must appear in notes unconditionally (manifest is importable)."""
        with tempfile.TemporaryDirectory() as td:
            hb_dir = pathlib.Path(td) / "hb"
            _write_orphan_hb(hb_dir, "ghost_svc_a")
            _write_orphan_hb(hb_dir, "ghost_svc_b")
            report = pathlib.Path(td) / "orphan_report.json"
            result = _apply_orphan_surface(
                _ok_doc(), hb_dir=hb_dir, orphan_report_path=report, now=_NOW
            )
        notes_text = " ".join(result.get("notes") or [])
        assert "ghost_svc_a" in notes_text, "ghost_svc_a missing; notes=%r" % result["notes"]
        assert "ghost_svc_b" in notes_text, "ghost_svc_b missing; notes=%r" % result["notes"]
        assert "orphan" in notes_text.lower(), "orphan header missing; notes=%r" % result["notes"]

    def test_orphan_surface_does_not_degrade_severity(self):
        """_apply_orphan_surface must never change overall or services[] severity."""
        with tempfile.TemporaryDirectory() as td:
            hb_dir = pathlib.Path(td) / "hb"
            _write_orphan_hb(hb_dir, "ghost_x")
            result = _apply_orphan_surface(
                _ok_doc("ok", services=[{"name": "svc_a", "severity": "ok"}]),
                hb_dir=hb_dir, orphan_report_path=pathlib.Path(td) / "r.json", now=_NOW
            )
        assert result["overall"] == "ok", "orphan surface must not degrade overall"
        for row in result.get("services") or []:
            if isinstance(row, dict) and row.get("name") == "svc_a":
                assert row.get("severity") == "ok"

    def test_no_orphans_no_notes_added(self):
        """Empty hb_dir (no stems) -> no orphan notes appended."""
        with tempfile.TemporaryDirectory() as td:
            hb_dir = pathlib.Path(td) / "hb"
            hb_dir.mkdir()
            result = _apply_orphan_surface(
                _ok_doc(notes=["existing note"]),
                hb_dir=hb_dir, orphan_report_path=pathlib.Path(td) / "r.json", now=_NOW
            )
        orphan_notes = [n for n in (result.get("notes") or []) if "orphan" in str(n).lower()]
        assert not orphan_notes, "unexpected orphan notes with empty hb_dir: %r" % orphan_notes


# ---------------------------------------------------------------------------
# 3. tick() integration: both wires fire; compose-error path degrades
# ---------------------------------------------------------------------------

class TestTickIntegration:

    def test_stale_m5_hb_degrades_overall(self, tmp_path):
        """tick() with stale m5 hb -> published doc overall=degraded."""
        hb = tmp_path / "m5_autonomy_monitor.txt"
        _write_hb(hb, age_sec=600.0, now=_NOW)
        doc = _minimal_tick(tmp_path, m5_hb_path=hb)
        assert doc["overall"] == "degraded", "got %r" % doc["overall"]

    def test_absent_m5_hb_degrades_overall(self, tmp_path):
        """tick() with absent m5 hb -> overall=degraded (absent != ok)."""
        doc = _minimal_tick(tmp_path, m5_hb_path=tmp_path / "nonexistent_m5.txt")
        assert doc["overall"] == "degraded", "got %r" % doc["overall"]

    def test_m5_row_present_in_services(self, tmp_path):
        """tick() must include the m5_autonomy_monitor row in services[]."""
        hb = tmp_path / "m5_autonomy_monitor.txt"
        _write_hb(hb, age_sec=500.0, now=_NOW)
        doc = _minimal_tick(tmp_path, m5_hb_path=hb)
        m5 = [r for r in doc.get("services") or [] if r.get("name") == "m5_autonomy_monitor"]
        assert m5, "m5_autonomy_monitor row must be present in services[]"

    def test_orphan_stems_surface_in_tick(self, tmp_path):
        """tick() with orphan stems in hb_dir must surface them into notes unconditionally."""
        hb_dir = tmp_path / "hb"
        _write_orphan_hb(hb_dir, "ghost_daemon_z")
        doc = _minimal_tick(tmp_path, m5_hb_path=tmp_path / "absent.txt",
                            orphan_hb_dir=hb_dir)
        notes_text = " ".join(str(n) for n in (doc.get("notes") or []))
        assert "ghost_daemon_z" in notes_text, (
            "ghost_daemon_z must be in notes; notes=%r" % doc.get("notes"))
        assert "orphan" in notes_text.lower(), (
            "orphan header must be in notes; notes=%r" % doc.get("notes"))

    def test_bad_compose_yields_degraded_never_raises(self, tmp_path):
        """tick() must not raise on compose failure and must yield overall=degraded."""
        def _bad_compose(**_kw):
            raise RuntimeError("compose exploded")
        try:
            doc = tick(
                now=_NOW, compose=_bad_compose, status_path=tmp_path / "s.json",
                m5_hb_path=tmp_path / "absent.txt",
                orphan_hb_dir=tmp_path / "hb",
                orphan_report_path=tmp_path / "r.json",
            )
            assert doc["overall"] == "degraded", "got %r" % doc["overall"]
        except Exception as exc:
            pytest.fail("tick raised on bad compose: %s" % exc)

    def test_no_severity_ever_upgraded(self, tmp_path):
        """Merge chain must never upgrade an existing severity."""
        base = _ok_doc("degraded", services=[{"name": "some_svc", "severity": "degraded"}])
        hb = tmp_path / "m5_autonomy_monitor.txt"
        _write_hb(hb, age_sec=5.0, now=_NOW)  # fresh m5 beat
        doc = _minimal_tick(tmp_path, m5_hb_path=hb, compose_doc=base)
        rank = {"ok": 0, "degraded": 1, "down": 2}
        assert rank.get(doc["overall"], 1) >= rank["degraded"], (
            "overall must not be upgraded; got %r" % doc["overall"])
        for row in doc.get("services") or []:
            if isinstance(row, dict) and row.get("name") == "some_svc":
                assert rank.get(str(row.get("severity", "ok")), 0) >= rank["degraded"], (
                    "some_svc severity must not be upgraded; got %r" % row.get("severity"))

    def test_published_doc_invariants(self, tmp_path):
        """Published doc: valid JSON on disk, monitor block present, no $ P&L."""
        hb = tmp_path / "m5.txt"
        _write_hb(hb, age_sec=10.0, now=_NOW)
        status_path = tmp_path / "autonomy_status.json"
        doc = tick(
            now=_NOW, compose=_stub_compose(_ok_doc()), status_path=status_path,
            m5_hb_path=hb, orphan_hb_dir=tmp_path / "hb",
            orphan_report_path=tmp_path / "r.json",
        )
        assert status_path.exists()
        assert isinstance(json.loads(status_path.read_text(encoding="ascii")), dict)
        monitor = doc.get("monitor") or {}
        assert monitor.get("component") == "m5_autonomy_monitor"
        assert "wrote_at" in monitor
        assert not re.search(r"\$\s*\d", str(doc)), "$ adjacent to digit in doc"


# ---------------------------------------------------------------------------
# 4. Monotone-down invariant
# ---------------------------------------------------------------------------

class TestMonotoneDown:

    def test_age_progression_never_back_to_ok(self):
        """fresh -> ok; stale -> degraded; very stale -> still degraded (never improves)."""
        from scripts.platformkit.autonomy.status_composer_m5fix import _RANK
        with tempfile.TemporaryDirectory() as td:
            hb = pathlib.Path(td) / "m5_autonomy_monitor.txt"
            _write_hb(hb, age_sec=10.0, now=_NOW)
            sev0 = [r["severity"] for r in _apply_m5fix(_ok_doc(), now=_NOW, m5_hb_path=hb)
                    ["services"] if r.get("name") == "m5_autonomy_monitor"]
            assert sev0 and sev0[0] == "ok"
            _write_hb(hb, age_sec=350.0, now=_NOW)
            sev1 = [r["severity"] for r in _apply_m5fix(_ok_doc(), now=_NOW, m5_hb_path=hb)
                    ["services"] if r.get("name") == "m5_autonomy_monitor"]
            assert sev1 and sev1[0] == "degraded"
            _write_hb(hb, age_sec=700.0, now=_NOW)
            sev2 = [r["severity"] for r in _apply_m5fix(_ok_doc(), now=_NOW, m5_hb_path=hb)
                    ["services"] if r.get("name") == "m5_autonomy_monitor"]
            assert sev2
            assert _RANK.get(sev2[0], 1) >= _RANK.get(sev1[0], 1), (
                "must not improve: %r -> %r" % (sev1[0], sev2[0]))

    def test_double_m5fix_does_not_upgrade(self):
        """Applying m5fix twice with a stale hb must not change severity."""
        with tempfile.TemporaryDirectory() as td:
            hb = pathlib.Path(td) / "m5_autonomy_monitor.txt"
            _write_hb(hb, age_sec=400.0, now=_NOW)
            d1 = _apply_m5fix(_ok_doc(), now=_NOW, m5_hb_path=hb)
            d2 = _apply_m5fix(d1, now=_NOW, m5_hb_path=hb)
        for d in (d1, d2):
            m5 = [r for r in d["services"] if r.get("name") == "m5_autonomy_monitor"]
            assert m5 and m5[0]["severity"] == "degraded"
        assert d2["overall"] == "degraded"
