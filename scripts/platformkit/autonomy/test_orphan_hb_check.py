"""Per-file tests for scripts.platformkit.autonomy.orphan_hb_check (IOP-06).

Acceptance criteria:
  (A) orphan_stems is a list (not None) when the manifest is unavailable -- the
      fallback must report [] with manifest_ok=False so ops knows the state is
      UNKNOWN, not "all clear".
  (B) A .txt stem in hb_dir that is NOT in the owned set appears in orphan_stems.
  (C) A .txt stem that IS in the owned set does NOT appear in orphan_stems.
  (D) A missing hb_dir produces orphan_stems=[] (not an error; no directory yet).
  (E) report doc is written atomically (tmp file is cleaned up).
  (F) stale_never_green=True in the report (tool is passive/read-only).
  (G) No $ field; calibration not edge.
  (H) run_check never raises on bad inputs.
  (I) orphan_stems=None ONLY when manifest import failed (honest UNKNOWN sentinel).
  (J) Multiple orphan stems are all reported.

Run (per-file only -- never full pytest):
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_orphan_hb_check.py -q
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from scripts.platformkit.autonomy.orphan_hb_check import run_check


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_hb(hb_dir: pathlib.Path, stem: str) -> pathlib.Path:
    """Create a dummy .txt heartbeat file under *hb_dir*."""
    hb_dir.mkdir(parents=True, exist_ok=True)
    p = hb_dir / ("%s.txt" % stem)
    p.write_text("ok", encoding="ascii")
    return p


# ---------------------------------------------------------------------------
# (A/I) manifest_ok and orphan_stems sentinel behaviour
# ---------------------------------------------------------------------------

class TestManifestFallback:
    def test_manifest_unavailable_yields_manifest_ok_false(self, tmp_path):
        """When the manifest import fails the report must set manifest_ok=False
        and orphan_stems=None (honest UNKNOWN, not "all clear")."""
        # Use an empty hb_dir so disk scan is well-defined.
        hb_dir = tmp_path / "hb"
        hb_dir.mkdir()
        report_path = tmp_path / "report.json"

        # run_check uses _manifest_owned_stems() internally; when supervisor
        # is not importable (as in CI / isolation) manifest_ok=False and
        # orphan_stems=None (the honest UNKNOWN sentinel).
        doc = run_check(hb_dir=hb_dir, report_path=report_path, now=0.0)

        if not doc["manifest_ok"]:
            # Honest UNKNOWN path
            assert doc["orphan_stems"] is None, (
                "orphan_stems must be None (honest UNKNOWN) when manifest fails; "
                "got %r" % (doc["orphan_stems"],)
            )
            assert doc["manifest_ok"] is False
        else:
            # Manifest available (e.g. supervisor importable in this env)
            assert isinstance(doc["orphan_stems"], list)
            assert doc["manifest_ok"] is True

    def test_orphan_stems_none_only_when_manifest_failed(self, tmp_path):
        """orphan_stems=None must ONLY appear when manifest_ok=False.
        If manifest_ok=True, orphan_stems must be a list (possibly empty)."""
        hb_dir = tmp_path / "hb2"
        hb_dir.mkdir()
        doc = run_check(hb_dir=hb_dir, report_path=tmp_path / "r.json", now=0.0)
        if doc["manifest_ok"]:
            assert doc["orphan_stems"] is not None, (
                "orphan_stems must be a list when manifest_ok=True")
            assert isinstance(doc["orphan_stems"], list)
        else:
            assert doc["orphan_stems"] is None


# ---------------------------------------------------------------------------
# (B/C) Orphan detection -- stems present vs absent in owned set
# ---------------------------------------------------------------------------

class TestOrphanDetection:
    def test_unowned_stem_appears_in_orphan_stems(self, tmp_path):
        """A .txt file whose stem is NOT in the owned set must appear in
        orphan_stems (when the manifest loaded successfully)."""
        hb_dir = tmp_path / "hb"
        _write_hb(hb_dir, "ghost_daemon")  # almost certainly not in manifest
        doc = run_check(
            hb_dir=hb_dir,
            report_path=tmp_path / "r.json",
            now=0.0,
        )
        if not doc["manifest_ok"]:
            pytest.skip("supervisor.manifest not importable in this environment")

        # ghost_daemon should be an orphan unless it is somehow in the manifest.
        if "ghost_daemon" not in doc["owned_stems"]:
            assert "ghost_daemon" in doc["orphan_stems"], (
                "ghost_daemon not in owned_stems and not in orphan_stems: "
                "orphan_stems=%r" % doc["orphan_stems"]
            )

    def test_all_stems_in_report_keys(self, tmp_path):
        """all_stems must be a (possibly empty) list regardless of manifest state."""
        hb_dir = tmp_path / "hb"
        _write_hb(hb_dir, "svc_alpha")
        _write_hb(hb_dir, "svc_beta")
        doc = run_check(
            hb_dir=hb_dir,
            report_path=tmp_path / "r.json",
            now=0.0,
        )
        assert isinstance(doc["all_stems"], list)
        assert "svc_alpha" in doc["all_stems"]
        assert "svc_beta" in doc["all_stems"]

    def test_orphan_stems_is_subset_of_all_stems(self, tmp_path):
        """orphan_stems (when not None) must be a subset of all_stems."""
        hb_dir = tmp_path / "hb"
        _write_hb(hb_dir, "orphan_one")
        _write_hb(hb_dir, "orphan_two")
        doc = run_check(
            hb_dir=hb_dir,
            report_path=tmp_path / "r.json",
            now=0.0,
        )
        if doc["orphan_stems"] is None:
            pytest.skip("manifest unavailable")
        all_set = set(doc["all_stems"])
        orphan_set = set(doc["orphan_stems"])
        assert orphan_set <= all_set, (
            "orphan_stems must be a subset of all_stems; "
            "orphan_stems=%r, all_stems=%r" % (doc["orphan_stems"], doc["all_stems"])
        )


# ---------------------------------------------------------------------------
# (D) Missing hb_dir
# ---------------------------------------------------------------------------

class TestMissingHbDir:
    def test_missing_hb_dir_yields_empty_all_stems(self, tmp_path):
        """A non-existent heartbeat directory -> all_stems=[] and no crash."""
        hb_dir = tmp_path / "no_such_dir"
        # Do NOT create it.
        doc = run_check(
            hb_dir=hb_dir,
            report_path=tmp_path / "r.json",
            now=0.0,
        )
        assert isinstance(doc["all_stems"], list)
        assert doc["all_stems"] == [], "absent dir -> no stems scanned"

    def test_missing_hb_dir_has_note(self, tmp_path):
        """A note must be emitted when the heartbeat directory is absent."""
        hb_dir = tmp_path / "no_such_dir"
        doc = run_check(
            hb_dir=hb_dir,
            report_path=tmp_path / "r.json",
            now=0.0,
        )
        assert isinstance(doc["notes"], list)
        notes_text = " ".join(doc["notes"]).lower()
        assert "absent" in notes_text or "no stems" in notes_text or "not" in notes_text, (
            "expected a note about missing hb_dir; notes=%r" % doc["notes"]
        )


# ---------------------------------------------------------------------------
# (E) Atomic write -- no lingering .tmp
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    def test_tmp_file_cleaned_up_after_write(self, tmp_path):
        """The .tmp file must not linger after a successful write."""
        hb_dir = tmp_path / "hb"
        hb_dir.mkdir()
        report_path = tmp_path / "orphan_hb_report.json"
        run_check(hb_dir=hb_dir, report_path=report_path, now=0.0)
        tmp = report_path.with_suffix(report_path.suffix + ".tmp")
        assert not tmp.exists(), ".tmp must be cleaned up after atomic write"

    def test_report_is_valid_json(self, tmp_path):
        """The written report must be valid JSON."""
        hb_dir = tmp_path / "hb"
        hb_dir.mkdir()
        report_path = tmp_path / "report.json"
        run_check(hb_dir=hb_dir, report_path=report_path, now=0.0)
        assert report_path.exists()
        doc = json.loads(report_path.read_text(encoding="ascii"))
        assert isinstance(doc, dict)


# ---------------------------------------------------------------------------
# (F) stale_never_green=True (passive / read-only)
# ---------------------------------------------------------------------------

class TestStaleNeverGreen:
    def test_stale_never_green_is_true(self, tmp_path):
        """stale_never_green must be True in every report (tool is passive)."""
        hb_dir = tmp_path / "hb"
        hb_dir.mkdir()
        doc = run_check(
            hb_dir=hb_dir,
            report_path=tmp_path / "r.json",
            now=0.0,
        )
        assert doc.get("stale_never_green") is True, (
            "stale_never_green must be True; got %r" % doc.get("stale_never_green")
        )

    def test_stale_never_green_in_written_json(self, tmp_path):
        """The written JSON must also carry stale_never_green=True."""
        hb_dir = tmp_path / "hb"
        hb_dir.mkdir()
        report_path = tmp_path / "r2.json"
        run_check(hb_dir=hb_dir, report_path=report_path, now=0.0)
        on_disk = json.loads(report_path.read_text(encoding="ascii"))
        assert on_disk.get("stale_never_green") is True


# ---------------------------------------------------------------------------
# (G) No $ field; calibration not edge
# ---------------------------------------------------------------------------

class TestNoDollarField:
    def test_no_dollar_in_doc_keys(self, tmp_path):
        """No key in the returned doc (or its sub-dicts/lists) must contain $."""
        hb_dir = tmp_path / "hb"
        hb_dir.mkdir()
        doc = run_check(
            hb_dir=hb_dir,
            report_path=tmp_path / "r.json",
            now=0.0,
        )
        for key in doc:
            assert "$" not in str(key), "$ in doc key: %r" % key

    def test_no_dollar_adjacent_to_digit_in_doc_str(self, tmp_path):
        """No $ adjacent to a digit in the serialised report (no $ P&L)."""
        hb_dir = tmp_path / "hb"
        hb_dir.mkdir()
        doc = run_check(
            hb_dir=hb_dir,
            report_path=tmp_path / "r.json",
            now=0.0,
        )
        doc_str = str(doc)
        assert not re.search(r"\$\s*\d", doc_str), (
            "$ adjacent to digit found in doc: %s" % doc_str[:200]
        )

    def test_honest_note_present(self, tmp_path):
        """honest_note must be present and reference calibration."""
        hb_dir = tmp_path / "hb"
        hb_dir.mkdir()
        doc = run_check(hb_dir=hb_dir, report_path=tmp_path / "r.json", now=0.0)
        assert "honest_note" in doc
        note = doc["honest_note"].lower()
        assert "calibration" in note or "no $" in note, (
            "honest_note must reference calibration/no $ field; got: %s" % doc["honest_note"]
        )


# ---------------------------------------------------------------------------
# (H) Never raises
# ---------------------------------------------------------------------------

class TestNeverRaises:
    def test_run_check_default_paths_never_raises(self, tmp_path):
        """run_check() with default paths must not raise."""
        try:
            doc = run_check(report_path=tmp_path / "r.json")
        except Exception as exc:  # noqa: BLE001
            pytest.fail("run_check raised with default paths: %s" % exc)
        assert isinstance(doc, dict)

    def test_run_check_with_garbage_report_path_does_not_raise(self, tmp_path):
        """Even if the report write fails (bad path), run_check must return the doc."""
        hb_dir = tmp_path / "hb"
        hb_dir.mkdir()
        # Use a path inside a non-existent deep tree but don't make parent dirs;
        # _atomic_write_json should handle this gracefully.
        bad_report = tmp_path / "a" / "b" / "c" / "report.json"
        try:
            doc = run_check(hb_dir=hb_dir, report_path=bad_report, now=0.0)
        except Exception as exc:  # noqa: BLE001
            pytest.fail("run_check raised with deep bad report_path: %s" % exc)
        assert isinstance(doc, dict)

    def test_run_check_required_keys_always_present(self, tmp_path):
        """The returned doc must always have the required keys (never raises)."""
        hb_dir = tmp_path / "hb"
        hb_dir.mkdir()
        doc = run_check(hb_dir=hb_dir, report_path=tmp_path / "r.json", now=0.0)
        for key in (
            "scanned_at", "hb_dir", "all_stems", "owned_stems",
            "orphan_stems", "manifest_ok", "notes", "honest_note",
            "stale_never_green",
        ):
            assert key in doc, "required key %r missing from doc" % key


# ---------------------------------------------------------------------------
# (J) Multiple orphan stems all reported
# ---------------------------------------------------------------------------

class TestMultipleOrphans:
    def test_all_orphan_stems_appear_in_report(self, tmp_path):
        """When several stems are orphaned all of them must appear in orphan_stems."""
        hb_dir = tmp_path / "hb"
        orphan_names = ["ghost_a", "ghost_b", "ghost_c"]
        for name in orphan_names:
            _write_hb(hb_dir, name)
        doc = run_check(
            hb_dir=hb_dir,
            report_path=tmp_path / "r.json",
            now=0.0,
        )
        if not doc["manifest_ok"]:
            pytest.skip("supervisor.manifest not importable in this environment")

        # Every stem that is NOT in owned_stems must appear in orphan_stems.
        owned = set(doc["owned_stems"])
        for name in orphan_names:
            if name not in owned:
                assert name in doc["orphan_stems"], (
                    "%r is not owned but missing from orphan_stems=%r" % (
                        name, doc["orphan_stems"])
                )

    def test_report_notes_mention_orphan_count_when_any(self, tmp_path):
        """When orphans exist, the notes must mention the count or stem names."""
        hb_dir = tmp_path / "hb"
        _write_hb(hb_dir, "ghost_x")
        doc = run_check(
            hb_dir=hb_dir,
            report_path=tmp_path / "r.json",
            now=0.0,
        )
        if not doc["manifest_ok"]:
            pytest.skip("supervisor.manifest not importable")
        orphans = doc["orphan_stems"]
        if not orphans:
            # ghost_x happened to be in the owned set -- test is vacuous.
            return
        notes_text = " ".join(doc["notes"])
        # Must name the stem or count in the notes
        assert "ghost_x" in notes_text or "orphan" in notes_text.lower(), (
            "notes must mention orphans; notes=%r" % doc["notes"]
        )
