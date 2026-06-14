"""tests/platform/test_brain_digest.py — unit tests for brain_digest.

Builds a tmp fixture _Organized with 2 sports (NBA, Tennis), calls
build_digests(organized_root=fixture, write=True) and asserts:
  1. Each sport's _Digest.md is written and contains archetype titles + counts line.
  2. _Index/_Cross_Sport_Digest.md is written and names both sports + has an
     analogue column.
  3. No digest contains a probability/odds/'edge'/ROI token.
  4. The report dict counts match the fixture.

Pure stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.brain_digest import build_digests  # noqa: E402

# ---------------------------------------------------------------------------
# forbidden tokens — must NOT appear in any generated digest
# ---------------------------------------------------------------------------
_FORBIDDEN = re.compile(
    r"\b(probability|odds|\bedge\b|ROI|roi|kelly|kelly_fraction|vig)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# fixture builder
# ---------------------------------------------------------------------------

def _mkfile(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_fixture(root: Path) -> None:
    """Create a minimal 2-sport _Organized fixture."""

    # ---- NBA ----
    nba = root / "NBA"

    # Archetypes: 2 notes with **Key:** value stat lines
    _mkfile(
        nba / "Archetypes" / "High_Usage_Creator.md",
        "---\ntags: [sport/nba, archetype]\n---\n\n"
        "# High-Usage Creator\n\n"
        "## Signature\n\n"
        "- **usage%**: >= 0.22\n"
        "- **ast%**: >= 0.20\n"
        "- **position**: Guard\n\n"
        "## Population\n\n"
        "- **Players fitting this archetype:** 59\n",
    )
    _mkfile(
        nba / "Archetypes" / "Defensive_Anchor.md",
        "---\ntags: [sport/nba, archetype]\n---\n\n"
        "# Defensive Anchor\n\n"
        "## Signature\n\n"
        "- **position**: Center\n"
        "- **def_rtg**: <= 110\n"
        "- **reb%**: >= 0.10\n\n"
        "## Population\n\n"
        "- **Players fitting this archetype:** 30\n",
    )

    # Schemes: 1 note
    _mkfile(
        nba / "Schemes" / "switch_heavy.md",
        "---\ntags: [sport/nba, scheme]\n---\n\n# Switch-Heavy Defense\n\n"
        "Defensive scheme using universal switching.\n",
    )

    # Teams: 1 subdir (counts as 1 team)
    (nba / "Teams" / "GSW").mkdir(parents=True, exist_ok=True)

    # Trends: 1 note
    _mkfile(
        nba / "Trends" / "pace_trend.md",
        "# Pace Trend\n\nLeague pace increased season-over-season.\n",
    )

    # ---- Tennis ----
    tennis = root / "Tennis"

    _mkfile(
        tennis / "Archetypes" / "Fast_Court_Big_Server.md",
        "---\ntags: [sport/tennis, playstyle]\n---\n\n"
        "# Fast Court Big Server\n\n"
        "## Stat Signature\n\n"
        "- **Players in archetype:** 63\n"
        "- **corpus_share_pct:** 15.4\n"
        "- **height**: >= 190 cm\n\n",
    )
    _mkfile(
        tennis / "Archetypes" / "Clay_Court_Specialist.md",
        "---\ntags: [sport/tennis, playstyle]\n---\n\n"
        "# Clay Court Specialist\n\n"
        "## Stat Signature\n\n"
        "- **clay_win_rate**: > overall\n"
        "- **Players in archetype:** 45\n\n",
    )

    # Tennis has no Schemes subdir (like real Tennis in the vault)
    # Trends: 1 note
    _mkfile(
        tennis / "Trends" / "surface_shift.md",
        "# Surface Shift Trend\n\nHard-court dominance growing.\n",
    )

    # _Index dir must exist (the organizer normally creates it)
    (root / "_Index").mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def fixture_root(tmp_path: Path) -> Path:
    _build_fixture(tmp_path)
    return tmp_path


def test_sport_digests_written(fixture_root: Path) -> None:
    """Assert each sport's _Digest.md is written."""
    report = build_digests(organized_root=fixture_root, write=True)

    for sport in ("NBA", "Tennis"):
        digest_path = fixture_root / sport / "_Digest.md"
        assert digest_path.exists(), f"_Digest.md missing for {sport}"

        text = digest_path.read_text(encoding="utf-8")

        # must contain archetype titles
        if sport == "NBA":
            assert "High-Usage Creator" in text, "NBA archetype title missing"
            assert "Defensive Anchor" in text, "NBA archetype title missing"
        else:
            assert "Fast Court Big Server" in text or "Fast_Court_Big_Server" in text
            assert "Clay Court Specialist" in text or "Clay_Court_Specialist" in text

        # must contain a counts line
        assert "Teams" in text or "teams" in text, "counts section missing"
        assert "Archetypes" in text or "archetypes" in text, "archetype count missing"


def test_cross_sport_digest_written(fixture_root: Path) -> None:
    """Assert _Cross_Sport_Digest.md is written and names both sports."""
    build_digests(organized_root=fixture_root, write=True)

    cross_path = fixture_root / "_Index" / "_Cross_Sport_Digest.md"
    assert cross_path.exists(), "_Cross_Sport_Digest.md not found"

    text = cross_path.read_text(encoding="utf-8")
    assert "NBA" in text, "NBA missing from cross-sport digest"
    assert "Tennis" in text, "Tennis missing from cross-sport digest"

    # analogue column / shape table must be present
    assert "primary" in text.lower() or "grinder" in text.lower(), \
        "no analogue shape column found"
    assert "Shape" in text or "shape" in text.lower(), \
        "no analogue header found"


def test_no_forbidden_tokens(fixture_root: Path) -> None:
    """Assert no probability/odds/edge/ROI tokens appear in any digest."""
    build_digests(organized_root=fixture_root, write=True)

    # gather all generated digest files
    digest_files = list(fixture_root.rglob("_Digest.md"))
    cross_path = fixture_root / "_Index" / "_Cross_Sport_Digest.md"
    if cross_path.exists():
        digest_files.append(cross_path)

    assert digest_files, "no digest files found"

    for path in digest_files:
        text = path.read_text(encoding="utf-8")
        m = _FORBIDDEN.search(text)
        assert m is None, (
            f"Forbidden token '{m.group()}' found in {path.name}; "
            "digests must not contain probability/odds/edge/ROI numbers."
        )


def test_report_counts_match_fixture(fixture_root: Path) -> None:
    """Assert the returned report dict counts match what we built."""
    report = build_digests(organized_root=fixture_root, write=True)

    ps = report["per_sport"]
    assert "NBA" in ps, "NBA missing from report"
    assert "Tennis" in ps, "Tennis missing from report"

    nba_info = ps["NBA"]
    assert nba_info["archetypes"] == 2, f"expected 2 NBA archetypes, got {nba_info['archetypes']}"
    assert nba_info["schemes"] == 1, f"expected 1 NBA scheme, got {nba_info['schemes']}"
    assert nba_info["trends"] == 1, f"expected 1 NBA trend, got {nba_info['trends']}"
    assert nba_info["teams"] == 1, f"expected 1 NBA team, got {nba_info['teams']}"

    tennis_info = ps["Tennis"]
    assert tennis_info["archetypes"] == 2, \
        f"expected 2 Tennis archetypes, got {tennis_info['archetypes']}"
    assert tennis_info["schemes"] == 0, \
        f"expected 0 Tennis schemes, got {tennis_info['schemes']}"
    assert tennis_info["trends"] == 1, \
        f"expected 1 Tennis trend, got {tennis_info['trends']}"

    # n_written: 2 sport digests + 1 cross-sport = 3
    assert report["n_written"] == 3, f"expected 3 files written, got {report['n_written']}"

    # cross_sport_path must be set
    assert report["cross_sport_path"] is not None


def test_digest_paths_in_report(fixture_root: Path) -> None:
    """Assert report digest_path values point to existing files."""
    report = build_digests(organized_root=fixture_root, write=True)
    for sport, info in report["per_sport"].items():
        dp = info.get("digest_path")
        assert dp is not None, f"digest_path None for {sport}"
        assert Path(dp).exists(), f"digest_path does not exist: {dp}"
