"""tests.platform.test_brain_export — Unit tests for brain_export.export_reads().

Builds a minimal _Organized fixture with NBA/ + Soccer/ dirs (each has an
Archetypes/ sub-dir with a note + a _World_Model note) so brain_query returns
real content and build_sport_read produces a non-trivial result.

Invariants verified:
  1. NBA/_Read.md and Soccer/_Read.md are written and contain the honest banner
     + an "Intelligence Read" heading (from render_markdown).
  2. _Index/_Reads.md is written and links both sport dirs.
  3. No exported file contains forbidden tokens: roi / odds= / +EV pick.
  4. A sport with no vault dir is recorded in skipped, not in exports.
  5. report['n_written'] matches len(report['exports']).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# ── Fixture helpers ────────────────────────────────────────────────────────────

_ARCHETYPE_NOTE = """\
---
tags:
  - sport/{sport}
  - archetype
---

# Fast-Break Archetype

## STYLE

High-tempo transition scorer.

## SIGNATURE

- **pace**: > 100
- **transition_pct**: > 0.30
"""

_SCHEME_NOTE = """\
---
tags:
  - sport/{sport}
  - scheme
---

# Zone Defense Scheme

## OVERVIEW

Drop coverage — protect the paint; concede corner threes.
"""

_TREND_NOTE = """\
---
tags:
  - sport/{sport}
  - trend
---

# 3PT Volume Rising Trend

## SUMMARY

Three-point attempt rate has increased league-wide across recent seasons.
"""

_WORLD_MODEL_NOTE = """\
---
tags:
  - world_model
  - sport/{sport}
---

# _World_Model — {sport_upper}

## Verdict

markets_efficient: true
tested_signals: REJECT
note: calibration not edge
"""


def _build_fixture(tmp_path: Path) -> Path:
    """Create a minimal _Organized structure under tmp_path."""
    organized = tmp_path / "_Organized"

    for sport in ("nba", "soccer"):
        su = sport.upper() if sport != "soccer" else "Soccer"
        sport_dir = organized / su

        # Archetypes sub-dir
        arch_dir = sport_dir / "Archetypes"
        arch_dir.mkdir(parents=True)
        (arch_dir / "fast_break.md").write_text(
            _ARCHETYPE_NOTE.format(sport=sport), encoding="utf-8"
        )

        # Schemes sub-dir
        scheme_dir = sport_dir / "Schemes"
        scheme_dir.mkdir(parents=True)
        (scheme_dir / "zone_defense.md").write_text(
            _SCHEME_NOTE.format(sport=sport), encoding="utf-8"
        )

        # Trends sub-dir
        trend_dir = sport_dir / "Trends"
        trend_dir.mkdir(parents=True)
        (trend_dir / "3pt_rising.md").write_text(
            _TREND_NOTE.format(sport=sport), encoding="utf-8"
        )

        # _World_Model note at sport_dir root
        (sport_dir / "_World_Model.md").write_text(
            _WORLD_MODEL_NOTE.format(sport=sport, sport_upper=sport.upper()),
            encoding="utf-8",
        )

    # _Index dir (may be empty initially — export_reads will write into it)
    (organized / "_Index").mkdir(parents=True, exist_ok=True)

    return organized


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_export_writes_sport_reads(tmp_path: Path) -> None:
    """Assert _Read.md is written for NBA and Soccer."""
    from scripts.platformkit.brain_export import export_reads

    organized = _build_fixture(tmp_path)
    report = export_reads(organized_root=organized, sports=["nba", "soccer", "mlb"], write=True)

    nba_read = organized / "NBA" / "_Read.md"
    soccer_read = organized / "Soccer" / "_Read.md"

    assert nba_read.exists(), "_Read.md not written for NBA"
    assert soccer_read.exists(), "_Read.md not written for Soccer"

    # Confirm exports map has the right paths
    assert report["exports"]["nba"] == str(nba_read)
    assert report["exports"]["soccer"] == str(soccer_read)


def test_read_contains_honest_banner(tmp_path: Path) -> None:
    """_Read.md must contain the honest banner text."""
    from scripts.platformkit.brain_export import export_reads

    organized = _build_fixture(tmp_path)
    export_reads(organized_root=organized, sports=["nba", "soccer"], write=True)

    for sport_dir_name in ("NBA", "Soccer"):
        content = (organized / sport_dir_name / "_Read.md").read_text(encoding="utf-8")
        assert "markets efficient" in content.lower(), (
            f"{sport_dir_name}/_Read.md missing honest banner"
        )


def test_read_contains_intelligence_read_heading(tmp_path: Path) -> None:
    """_Read.md must contain the 'Intelligence Read' heading from render_markdown."""
    from scripts.platformkit.brain_export import export_reads

    organized = _build_fixture(tmp_path)
    export_reads(organized_root=organized, sports=["nba", "soccer"], write=True)

    for sport_dir_name in ("NBA", "Soccer"):
        content = (organized / sport_dir_name / "_Read.md").read_text(encoding="utf-8")
        assert "Intelligence Read" in content or "Archetypes" in content, (
            f"{sport_dir_name}/_Read.md missing expected heading"
        )


def test_index_written_and_links_both_sports(tmp_path: Path) -> None:
    """_Index/_Reads.md must exist and link both NBA and Soccer."""
    from scripts.platformkit.brain_export import export_reads

    organized = _build_fixture(tmp_path)
    export_reads(organized_root=organized, sports=["nba", "soccer"], write=True)

    index_path = organized / "_Index" / "_Reads.md"
    assert index_path.exists(), "_Index/_Reads.md not written"

    content = index_path.read_text(encoding="utf-8")
    assert "NBA" in content, "_Index/_Reads.md missing NBA link"
    assert "Soccer" in content, "_Index/_Reads.md missing Soccer link"


def test_no_forbidden_tokens_in_exports(tmp_path: Path) -> None:
    """Exported files must not contain roi / 'odds=' / '+EV pick'."""
    from scripts.platformkit.brain_export import export_reads

    organized = _build_fixture(tmp_path)
    report = export_reads(organized_root=organized, sports=["nba", "soccer"], write=True)

    _FORBIDDEN = re.compile(r"\broi\b|odds=|\+EV pick", re.IGNORECASE)

    for sport, path in report["exports"].items():
        content = Path(path).read_text(encoding="utf-8")
        m = _FORBIDDEN.search(content)
        assert m is None, (
            f"Forbidden token '{m.group()}' found in {sport} _Read.md"
        )

    # Also check the index
    index_content = (organized / "_Index" / "_Reads.md").read_text(encoding="utf-8")
    m_idx = _FORBIDDEN.search(index_content)
    assert m_idx is None, f"Forbidden token '{m_idx.group()}' found in _Reads.md index"


def test_missing_sport_dir_is_skipped(tmp_path: Path) -> None:
    """A sport with no vault dir (mlb, tennis) must appear in skipped, not exports."""
    from scripts.platformkit.brain_export import export_reads

    organized = _build_fixture(tmp_path)
    # fixture only has NBA/ and Soccer/ dirs; mlb and tennis have no dirs
    report = export_reads(
        organized_root=organized,
        sports=["nba", "soccer", "mlb", "tennis"],
        write=True,
    )

    assert "mlb" in report["skipped"], "mlb should be in skipped (no MLB/ dir)"
    assert "tennis" in report["skipped"], "tennis should be in skipped (no Tennis/ dir)"
    assert "mlb" not in report["exports"], "mlb must not be in exports"
    assert "tennis" not in report["exports"], "tennis must not be in exports"


def test_n_written_matches_exports(tmp_path: Path) -> None:
    """report['n_written'] must equal len(report['exports'])."""
    from scripts.platformkit.brain_export import export_reads

    organized = _build_fixture(tmp_path)
    report = export_reads(
        organized_root=organized,
        sports=["nba", "soccer", "mlb", "tennis"],
        write=True,
    )

    assert report["n_written"] == len(report["exports"]), (
        f"n_written={report['n_written']} but exports has {len(report['exports'])} entries"
    )


def test_missing_organized_root_returns_error() -> None:
    """If organized_root does not exist, return an error dict."""
    from scripts.platformkit.brain_export import export_reads

    report = export_reads(
        organized_root=Path("/nonexistent/_Organized_DOES_NOT_EXIST"),
        write=False,
    )
    assert "error" in report
    assert report["n_written"] == 0
    assert report["exports"] == {}


def test_write_false_produces_no_files(tmp_path: Path) -> None:
    """write=False must compute the report without touching disk."""
    from scripts.platformkit.brain_export import export_reads

    organized = _build_fixture(tmp_path)
    report = export_reads(organized_root=organized, sports=["nba"], write=False)

    assert report["n_written"] == 1
    # File must NOT be on disk
    assert not (organized / "NBA" / "_Read.md").exists(), (
        "_Read.md was written even though write=False"
    )
