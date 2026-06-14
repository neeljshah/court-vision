"""tests.platform.test_brain_archetypes — PERSON-FREE as-of archetype clustering.

Drives ``scripts.platformkit.brain_archetypes.build_archetypes`` with SYNTHETIC
as-of entity frames (the entity-source functions are monkeypatched; no real
parquet is read), then asserts:
  * the ``_Computed_<kind>.md`` notes + ``_Computed_Index.md`` are written,
  * each rendered file passes the REAL no-edge audit (``scan_text(...) == []``),
  * no rendered file contains a named entity (only numeric/categorical centroids),
  * clustering is deterministic across two runs,
  * a missing source skips that kind honestly (no crash, no file).

Run:
    python -m pytest tests/platform/test_brain_archetypes.py -q --timeout=120
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

import pytest

import scripts.platformkit.brain_archetypes as ba
from scripts.platformkit.brain_audit import scan_text

# ---------------------------------------------------------------------------
# Synthetic as-of entity frames (NO real parquet). Spread across the tertiles so
# every clustering cell is exercised and the centroid math is non-degenerate.
# ---------------------------------------------------------------------------

# Named entities that MUST NOT leak into any rendered note.
_FORBIDDEN_NAMES = ["Verlander", "Kershaw", "Ohtani", "Arsenal", "Chelsea",
                    "Liverpool", "Scherzer", "Cole"]


def _synthetic_sp_rows() -> List[Dict[str, float]]:
    rows: List[Dict[str, float]] = []
    # form_ra low/mid/high x starts low/mid/high x both hands -> all 9 cells.
    for ra in (1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5):
        for starts in (2.0, 10.0, 30.0):
            for hand in ("L", "R"):
                rows.append({"form_ra": ra, "starts": starts, "hand": hand})
    return rows


def _synthetic_team_rows() -> List[Dict[str, float]]:
    rows: List[Dict[str, float]] = []
    for att in (3.0, 4.0, 5.0, 6.0, 7.0, 8.0):
        for conc in (3.0, 5.0, 7.0):
            rows.append({"attack": att, "concede": conc})
    return rows


@pytest.fixture()
def patched(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch both entity sources to return synthetic rows (no I/O)."""
    monkeypatch.setattr(ba, "_mlb_sp_entities", _synthetic_sp_rows)
    monkeypatch.setattr(ba, "_soccer_team_entities", _synthetic_team_rows)


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    for sport in ("MLB", "Soccer"):
        (tmp_path / sport / "Archetypes").mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_writes_computed_notes_and_index(patched: None, vault: Path) -> None:
    paths = ba.build_archetypes(vault)
    names = {p.name for p in paths}
    assert "_Computed_starting_pitchers.md" in names
    assert "_Computed_team_styles.md" in names
    assert "_Computed_Index.md" in names
    assert (vault / "MLB" / "Archetypes" / "_Computed_starting_pitchers.md").exists()
    assert (vault / "Soccer" / "Archetypes" / "_Computed_team_styles.md").exists()


def test_distinct_prefix_avoids_legacy_collision(patched: None, vault: Path) -> None:
    # Legacy hand-curated note in the same dir must be untouched.
    legacy = vault / "MLB" / "Archetypes" / "pitching_run_prevention.md"
    legacy.write_text("# Playstyle: legacy\n", encoding="utf-8")
    ba.build_archetypes(vault)
    assert legacy.read_text(encoding="utf-8") == "# Playstyle: legacy\n"


def test_audit_clean_scan_text_empty(patched: None, vault: Path) -> None:
    for p in ba.build_archetypes(vault):
        rendered = p.read_text(encoding="utf-8")
        assert scan_text(rendered) == [], f"edge-claim flagged in {p.name}: {scan_text(rendered)}"


def test_person_free_no_named_entities(patched: None, vault: Path) -> None:
    for p in ba.build_archetypes(vault):
        rendered = p.read_text(encoding="utf-8")
        for name in _FORBIDDEN_NAMES:
            assert name not in rendered, f"named entity {name!r} leaked into {p.name}"
        # No "First Last" Title-Case pair and no "X vs Y" matchup tokens.
        assert not re.search(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b\s+(?:vs|@)\b", rendered)


def test_honest_banner_present(patched: None, vault: Path) -> None:
    for p in ba.build_archetypes(vault):
        rendered = p.read_text(encoding="utf-8").lower()
        assert "no edge claimed" in rendered
        assert "person-free" in rendered


def test_signature_has_numeric_centroids(patched: None, vault: Path) -> None:
    sp = (vault / "MLB" / "Archetypes" / "_Computed_starting_pitchers.md")
    ba.build_archetypes(vault)
    text = sp.read_text(encoding="utf-8")
    assert "EW first-6 RA" in text and "prior starts" in text
    # At least one share percentage and one numeric centroid cell.
    assert re.search(r"\d+\.\d%", text)
    assert re.search(r"\|\s*\d+\.\d{3}\s*\|", text)


def test_archetype_labels_appear(patched: None, vault: Path) -> None:
    text = (vault / "MLB" / "Archetypes" / "_Computed_starting_pitchers.md")
    ba.build_archetypes(vault)
    body = text.read_text(encoding="utf-8")
    # synthetic rows span all tertile cells -> the ace + raw_volatile poles exist.
    assert "ace_workhorse" in body
    assert "raw_volatile" in body


def test_deterministic_across_runs(patched: None, vault: Path) -> None:
    strip = lambda t: [l for l in t.splitlines() if not l.startswith(("*Generated", "generated:"))]
    p = vault / "MLB" / "Archetypes" / "_Computed_starting_pitchers.md"
    ba.build_archetypes(vault)
    first = p.read_text(encoding="utf-8")
    ba.build_archetypes(vault)
    second = p.read_text(encoding="utf-8")
    assert strip(first) == strip(second)


def test_missing_source_skips_honestly(monkeypatch: pytest.MonkeyPatch, vault: Path) -> None:
    monkeypatch.setattr(ba, "_mlb_sp_entities", lambda: None)
    monkeypatch.setattr(ba, "_soccer_team_entities", _synthetic_team_rows)
    paths = ba.build_archetypes(vault)
    names = {p.name for p in paths}
    assert "_Computed_starting_pitchers.md" not in names
    assert "_Computed_team_styles.md" in names
    assert not (vault / "MLB" / "Archetypes" / "_Computed_starting_pitchers.md").exists()


def test_all_sources_absent_writes_nothing(monkeypatch: pytest.MonkeyPatch, vault: Path) -> None:
    monkeypatch.setattr(ba, "_mlb_sp_entities", lambda: None)
    monkeypatch.setattr(ba, "_soccer_team_entities", lambda: None)
    assert ba.build_archetypes(vault) == []


def test_shares_sum_to_one(patched: None, vault: Path) -> None:
    ba.build_archetypes(vault)
    text = (vault / "Soccer" / "Archetypes" / "_Computed_team_styles.md").read_text(encoding="utf-8")
    shares = [float(m) for m in re.findall(r"\|\s*(\d+\.\d)%\s*\|", text)]
    assert shares, "no share cells found"
    assert abs(sum(shares) - 100.0) < 1.5  # rounding tolerance


# ---------------------------------------------------------------------------
# Pure-helper unit tests (no I/O, no monkeypatch)
# ---------------------------------------------------------------------------

def test_tertiles_and_bucket() -> None:
    lo, hi = ba._tertiles([1, 2, 3, 4, 5, 6, 7, 8, 9])
    assert lo < hi
    assert ba._bucket(1.0, lo, hi) == 0
    assert ba._bucket(9.0, lo, hi) == 2
    assert ba._bucket(float("nan"), lo, hi) == 1  # NaN -> mid


def test_tertiles_all_nan_returns_nan() -> None:
    lo, hi = ba._tertiles([float("nan"), float("nan")])
    assert lo != lo and hi != hi  # both NaN
    assert ba._bucket(5.0, lo, hi) == 1  # degenerate cut -> mid
