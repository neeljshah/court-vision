"""Tests for scripts.platformkit.brain_validated — provenance-tagged improvements.

Hermetic: uses only the STATIC provenance data embedded in the module (no real
parquet or vault needed).  Asserts:
  (a) per-sport + index artifacts are rendered with correct counts
  (b) every entry's provenance (wave + commit + module) is present in the text
  (c) honest-banner / calibration framing is present in every rendered file
  (d) absorbed-nulls section is present and honest
  (e) every rendered artifact passes the REAL no-edge audit: scan_text(text) == []
      (W96 lesson: assert against the real audit, not a token list)
  (f) files are written to the correct paths in tmp_path
  (g) person-free (no player/team name nodes)
"""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit.brain_validated import (
    build_validated,
    _ENTRIES,
    _ABSORBED,
    _SPORTS_ORDER,
    _render_sport,
    _render_index,
)
from scripts.platformkit.brain_audit import scan_text


# ---------------------------------------------------------------------------
# provenance completeness
# ---------------------------------------------------------------------------

def test_all_entries_have_required_provenance_fields():
    required = ("sport", "name", "metric_delta", "module", "wave", "commit")
    for e in _ENTRIES:
        for field in required:
            assert field in e and e[field], f"Entry missing '{field}': {e}"


def test_all_sports_order_covered():
    assert set(_SPORTS_ORDER) == {"NBA", "MLB", "Soccer", "Tennis"}


# ---------------------------------------------------------------------------
# per-sport rendering
# ---------------------------------------------------------------------------

def test_render_sport_contains_provenance_for_all_entries():
    for sport in _SPORTS_ORDER:
        md = _render_sport(sport)
        entries = [e for e in _ENTRIES if e["sport"] == sport]
        for e in entries:
            assert e["wave"] in md, f"{sport}: wave {e['wave']} missing"
            assert e["commit"] in md, f"{sport}: commit {e['commit']} missing"
            assert e["module"] in md, f"{sport}: module {e['module']} missing"


def test_render_sport_has_honest_banner():
    for sport in _SPORTS_ORDER:
        md = _render_sport(sport)
        assert "no edge claimed" in md.lower(), f"{sport}: missing 'no edge claimed'"
        assert "calibration" in md.lower(), f"{sport}: missing 'calibration'"
        assert "not a market edge" in md.lower(), f"{sport}: missing 'not a market edge'"


def test_render_sport_has_key_framing_line():
    for sport in _SPORTS_ORDER:
        md = _render_sport(sport)
        assert "distribution-shape" in md.lower() or "shape" in md.lower(), (
            f"{sport}: missing distribution-shape framing"
        )
        assert "mean-shift" in md.lower() or "absorbed" in md.lower(), (
            f"{sport}: missing absorbed framing"
        )


def test_render_sport_has_absorbed_section():
    for sport in _SPORTS_ORDER:
        md = _render_sport(sport)
        assert "absorbed" in md.lower(), f"{sport}: missing absorbed section"
        assert "not shipped" in md.lower(), f"{sport}: missing 'not shipped'"


def test_render_sport_passes_real_no_edge_audit():
    for sport in _SPORTS_ORDER:
        md = _render_sport(sport)
        hits = scan_text(md)
        assert hits == [], f"{sport}: audit flagged {hits}"


def test_render_sport_person_free():
    for sport in _SPORTS_ORDER:
        md = _render_sport(sport)
        assert "Players/" not in md
        assert "Teams/" not in md


# ---------------------------------------------------------------------------
# index rendering
# ---------------------------------------------------------------------------

def test_render_index_contains_all_entries_provenance():
    idx = _render_index()
    for e in _ENTRIES:
        assert e["wave"] in idx, f"index missing wave {e['wave']}"
        assert e["commit"] in idx, f"index missing commit {e['commit']}"
        assert e["module"] in idx, f"index missing module {e['module']}"


def test_render_index_has_honest_banner():
    idx = _render_index()
    assert "no edge claimed" in idx.lower()
    assert "calibration is not edge" in idx.lower()
    assert "distribution-shape" in idx.lower() or "shape" in idx.lower()
    assert "absorbed" in idx.lower()


def test_render_index_passes_real_no_edge_audit():
    idx = _render_index()
    hits = scan_text(idx)
    assert hits == [], f"index: audit flagged {hits}"


def test_render_index_total_count():
    idx = _render_index()
    assert str(len(_ENTRIES)) in idx


# ---------------------------------------------------------------------------
# build_validated (write=False, in-memory)
# ---------------------------------------------------------------------------

def test_build_validated_returns_all_sports(tmp_path):
    rep = build_validated(organized_root=tmp_path, write=False)
    for sport in _SPORTS_ORDER:
        assert sport in rep, f"sport {sport} missing from report"
    assert "_index" in rep
    assert "_note" in rep


def test_build_validated_counts_match_entries():
    rep = build_validated(write=False)
    for sport in _SPORTS_ORDER:
        expected = sum(1 for e in _ENTRIES if e["sport"] == sport)
        assert rep[sport]["n_entries"] == expected, (
            f"{sport}: expected {expected}, got {rep[sport]['n_entries']}"
        )
    assert rep["_index"]["n_total"] == len(_ENTRIES)


def test_build_validated_md_in_report():
    rep = build_validated(write=False)
    for sport in _SPORTS_ORDER:
        assert "md" in rep[sport]
        assert len(rep[sport]["md"]) > 50
    assert "md" in rep["_index"]


def test_build_validated_all_rendered_pass_audit():
    rep = build_validated(write=False)
    for sport in _SPORTS_ORDER:
        hits = scan_text(rep[sport]["md"])
        assert hits == [], f"{sport}: audit flagged {hits}"
    idx_hits = scan_text(rep["_index"]["md"])
    assert idx_hits == [], f"index: audit flagged {idx_hits}"


# ---------------------------------------------------------------------------
# file writing
# ---------------------------------------------------------------------------

def test_build_validated_writes_files(tmp_path):
    build_validated(organized_root=tmp_path, write=True)
    for sport in _SPORTS_ORDER:
        p = tmp_path / sport / "_Validated_Improvements.md"
        assert p.is_file(), f"expected {p}"
        assert p.stat().st_size > 50
    idx_p = tmp_path / "_Index" / "_Validated_Improvements.md"
    assert idx_p.is_file(), f"expected {idx_p}"


def test_written_files_pass_audit(tmp_path):
    build_validated(organized_root=tmp_path, write=True)
    for sport in _SPORTS_ORDER:
        p = tmp_path / sport / "_Validated_Improvements.md"
        text = p.read_text(encoding="utf-8")
        hits = scan_text(text)
        assert hits == [], f"{sport} file: audit flagged {hits}"
    idx_text = (tmp_path / "_Index" / "_Validated_Improvements.md").read_text(encoding="utf-8")
    hits = scan_text(idx_text)
    assert hits == [], f"index file: audit flagged {hits}"


def test_written_files_contain_provenance(tmp_path):
    build_validated(organized_root=tmp_path, write=True)
    for e in _ENTRIES:
        p = tmp_path / e["sport"] / "_Validated_Improvements.md"
        text = p.read_text(encoding="utf-8")
        assert e["wave"] in text, f"{e['sport']}: wave {e['wave']} not in file"
        assert e["commit"] in text, f"{e['sport']}: commit {e['commit']} not in file"
        assert e["module"] in text, f"{e['sport']}: module {e['module']} not in file"
