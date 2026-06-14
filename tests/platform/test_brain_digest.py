"""tests/platform/test_brain_digest.py — unit tests for brain_digest MOC digests.

Builds a tmp _Organized fixture with 2 sports (NBA, Tennis), calls
build_digests(organized_root=fixture, write=True) and asserts:
  1. Per-sport _Digest.md exists, contains archetype titles as wikilinks,
     hub links to _WhatWins/_Mechanisms/_Archetypes_Index/_Index/_Brain.
  2. _Cross_Sport_Digest.md names both sports, has analogue shape table,
     links each sport's _WhatWins + each archetype wikilinked.
  3. No digest contains probability/odds/edge/ROI/player-name tokens.
  4. Report dict counts match the fixture. >= N resolving wikilinks.
  5. moc tag present in frontmatter. Drivers/Mechanisms counts present.

Hermetic — no live vault access. Pure stdlib + pytest.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.brain_digest import build_digests  # noqa: E402

_FORBIDDEN = re.compile(
    r"\b(probability|odds|\bedge\b|ROI|roi|kelly|kelly_fraction|vig)\b",
    re.IGNORECASE,
)
# Detect "Firstname Lastname" on plain content lines (not headings/#/|/wikilinks/frontmatter)
_PERSON_LINE = re.compile(r"\b([A-Z][a-z]{2,}\s+[A-Z][a-z]{2,})\b")
# Known-safe structural Title-Case compound phrases from the digest template
_PERSON_SAFE = re.compile(
    r"\b(High.Usage|Fast.Court|Clay.Court|What.Wins|Cross.Sport|Transfer.Note|"
    r"Stat.Signature|Honest.Verdict|Trend.Notes|Intelligence.MOC|Dense.Intelligence|"
    r"Analogue.Map|Per.Sport|Archetype.Taxonomy|Hub.Links|Sport.Hubs|Sport.Brain|"
    r"Schemes?.Tactics|Switch.Heavy|Pace.Trend|Surface.Shift|Defensive.Anchor|"
    r"Digest.Note|Archetype.Transfer|Mechanisms.Hub|Archetypes?.Index|Sport.Index|"
    r"What.Works|Poisson.NegBinom|Analogue.Shapes|Base.Rates|"
    r"Run.Prevention|Big.Server|Usage.Creator|Run.Scoring|"
    r"Archetype.Inventory|Transfer.Scope|Honest.Verdict|"
    r"Market.Lines|Market.Prices|Market.Advantage|Market.Efficiency|"
    r"Model.Family|Calibration.Approach|Statistical.Reasoning)\b",
    re.IGNORECASE,
)
_WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")


# ---------------------------------------------------------------------------
# fixture helpers
# ---------------------------------------------------------------------------

def _mkfile(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_fixture(root: Path) -> None:
    nba = root / "NBA"
    # hub notes
    _mkfile(nba / "_WhatWins.md", "# NBA — What Wins\n\nCalibration choices.\n")
    _mkfile(nba / "_Index.md", "# NBA — Index\n\nSport index.\n")
    _mkfile(nba / "Mechanisms" / "_Mechanisms.md", "# NBA Mechanisms\n\nHub.\n")
    _mkfile(nba / "Archetypes" / "_Archetypes_Index.md", "# NBA Archetypes Index\n\n")
    # archetypes
    _mkfile(nba / "Archetypes" / "High_Usage_Creator.md",
            "# High-Usage Creator\n\n**usage%**: >= 0.22\n**ast%**: >= 0.20\n"
            "**position**: Guard\n**Count**: 59\n")
    _mkfile(nba / "Archetypes" / "Defensive_Anchor.md",
            "# Defensive Anchor\n\n**position**: Center\n**def_rtg**: <= 110\n"
            "**reb%**: >= 0.10\n**Count**: 30\n")
    # drivers, mechanisms, schemes, trends, teams
    _mkfile(nba / "Drivers" / "shooting.md", "# Shooting Driver\n\nShooting margin drives outcomes.\n")
    _mkfile(nba / "Mechanisms" / "pace_x_shooting.md", "# Pace × Shooting\n\nInteraction.\n")
    _mkfile(nba / "Schemes" / "switch_heavy.md", "# Switch-Heavy Defense\n\nUniversal switching.\n")
    _mkfile(nba / "Trends" / "pace_trend.md", "# Pace Trend\n\nPace increased.\n")
    (nba / "Teams" / "GSW").mkdir(parents=True, exist_ok=True)

    tennis = root / "Tennis"
    _mkfile(tennis / "_WhatWins.md", "# Tennis — What Wins\n\nCalibration choices.\n")
    _mkfile(tennis / "_Index.md", "# Tennis — Index\n\nSport index.\n")
    _mkfile(tennis / "Archetypes" / "_Archetypes_Index.md", "# Tennis Archetypes Index\n\n")
    _mkfile(tennis / "Archetypes" / "Fast_Court_Big_Server.md",
            "# Fast Court Big Server\n\n**Count**: 63\n**corpus_share_pct**: 15.4\n**height**: >= 190\n")
    _mkfile(tennis / "Archetypes" / "Clay_Court_Specialist.md",
            "# Clay Court Specialist\n\n**clay_win_rate**: > overall\n**Count**: 45\n")
    _mkfile(tennis / "Trends" / "surface_shift.md", "# Surface Shift Trend\n\nHard-court dominance.\n")
    (root / "_Index").mkdir(parents=True, exist_ok=True)


def _wikilinks(text: str) -> List[str]:
    return _WIKILINK.findall(text)


def _resolved(text: str, root: Path) -> List[str]:
    """Wikilink targets whose stem file exists anywhere under root."""
    found = []
    for target in _wikilinks(text):
        stem = target.split("|")[0].split("/")[-1]
        if list(root.rglob(f"{stem}.md")):
            found.append(target)
    return found


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def fixture_root(tmp_path: Path) -> Path:
    _build_fixture(tmp_path)
    return tmp_path


@pytest.fixture()
def digests(fixture_root: Path):
    report = build_digests(organized_root=fixture_root, write=True)
    nba = (fixture_root / "NBA" / "_Digest.md").read_text(encoding="utf-8")
    ten = (fixture_root / "Tennis" / "_Digest.md").read_text(encoding="utf-8")
    cross = (fixture_root / "_Index" / "_Cross_Sport_Digest.md").read_text(encoding="utf-8")
    return report, nba, ten, cross


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

def test_sport_digests_written(digests, fixture_root: Path) -> None:
    _, nba, ten, _ = digests
    assert (fixture_root / "NBA" / "_Digest.md").exists()
    assert (fixture_root / "Tennis" / "_Digest.md").exists()
    assert "High-Usage Creator" in nba and "Defensive Anchor" in nba
    assert "Fast Court Big Server" in ten or "Fast_Court_Big_Server" in ten
    assert "Clay Court Specialist" in ten or "Clay_Court_Specialist" in ten
    assert "Teams" in nba and "Archetypes" in nba


def test_hub_wikilinks_present(digests) -> None:
    _, nba, ten, _ = digests
    for text, sport in [(nba, "NBA"), (ten, "Tennis")]:
        flat = " ".join(_wikilinks(text))
        assert "_WhatWins" in flat, f"{sport}: missing _WhatWins link"
        assert "_Index" in flat, f"{sport}: missing _Index link"
        assert "_Brain" in flat, f"{sport}: missing _Brain link"
        assert "_Archetypes_Index" in flat, f"{sport}: missing _Archetypes_Index link"
    assert "_Mechanisms" in " ".join(_wikilinks(nba)), "NBA: missing _Mechanisms link"


def test_archetype_names_are_wikilinked(digests) -> None:
    _, nba, ten, _ = digests
    assert "[[High_Usage_Creator|High-Usage Creator]]" in nba
    assert "[[Defensive_Anchor|Defensive Anchor]]" in nba
    assert "[[Fast_Court_Big_Server|" in ten
    assert "[[Clay_Court_Specialist|" in ten


def test_resolving_wikilinks_count(digests, fixture_root: Path) -> None:
    _, nba, ten, _ = digests
    nba_res = _resolved(nba, fixture_root)
    ten_res = _resolved(ten, fixture_root)
    assert len(nba_res) >= 4, f"NBA: only {len(nba_res)} resolving wikilinks: {nba_res}"
    assert len(ten_res) >= 4, f"Tennis: only {len(ten_res)} resolving wikilinks: {ten_res}"


def test_cross_sport_digest_written(digests, fixture_root: Path) -> None:
    _, _, _, cross = digests
    assert (fixture_root / "_Index" / "_Cross_Sport_Digest.md").exists()
    assert "NBA" in cross and "Tennis" in cross
    assert "primary" in cross.lower() or "grinder" in cross.lower()
    assert "Shape" in cross


def test_cross_sport_whatwins_links(digests) -> None:
    _, _, _, cross = digests
    links = _wikilinks(cross)
    flat = " ".join(links)
    assert "_WhatWins" in flat, "cross digest missing _WhatWins links"
    assert sum(1 for lnk in links if "_WhatWins" in lnk) >= 2


def test_cross_sport_archetype_links(digests) -> None:
    _, _, _, cross = digests
    assert "[[High_Usage_Creator|" in cross or "[[Defensive_Anchor|" in cross
    assert "[[Fast_Court_Big_Server|" in cross or "[[Clay_Court_Specialist|" in cross


def test_no_forbidden_tokens(digests, fixture_root: Path) -> None:
    build_digests(organized_root=fixture_root, write=True)
    digest_files = list(fixture_root.rglob("_Digest.md"))
    cross_path = fixture_root / "_Index" / "_Cross_Sport_Digest.md"
    if cross_path.exists():
        digest_files.append(cross_path)
    for path in digest_files:
        text = path.read_text(encoding="utf-8")
        m = _FORBIDDEN.search(text)
        assert m is None, f"Forbidden token '{m.group()}' in {path.name}"


def test_no_player_team_proper_names(digests) -> None:
    """Digest must be PERSON-FREE: no player/team proper names on content lines."""
    _, nba, ten, cross = digests
    # Only inspect plain content lines — skip headings, table rows, wikilinks, frontmatter
    def _plain_lines(text: str) -> List[str]:
        return [ln for ln in text.splitlines()
                if ln.strip() and not ln.strip().startswith(("#", "|", "-", ">", "!", "[", "---"))]
    for text, label in [(nba, "NBA"), (ten, "Tennis"), (cross, "Cross")]:
        for line in _plain_lines(text):
            for m in _PERSON_LINE.finditer(line):
                phrase = m.group(1)
                if not _PERSON_SAFE.search(phrase):
                    pytest.fail(f"{label} digest: possible proper name '{phrase}' in: {line!r}")


def test_report_counts_match_fixture(digests) -> None:
    report, _, _, _ = digests
    ps = report["per_sport"]
    assert "NBA" in ps and "Tennis" in ps
    nba = ps["NBA"]
    assert nba["archetypes"] == 2 and nba["schemes"] == 1
    assert nba["trends"] == 1 and nba["teams"] == 1
    assert nba["drivers"] == 1 and nba["mechanisms"] == 1
    tennis = ps["Tennis"]
    assert tennis["archetypes"] == 2 and tennis["schemes"] == 0 and tennis["trends"] == 1
    assert report["n_written"] == 3
    assert report["cross_sport_path"] is not None


def test_digest_paths_in_report(digests) -> None:
    report, _, _, _ = digests
    for sport, info in report["per_sport"].items():
        dp = info.get("digest_path")
        assert dp is not None and Path(dp).exists(), f"digest_path invalid for {sport}"


def test_counts_section_present(digests) -> None:
    _, nba, _, _ = digests
    assert "Drivers" in nba and "Mechanisms" in nba


def test_moc_tag_present(digests) -> None:
    _, nba, ten, cross = digests
    for text, label in [(nba, "NBA"), (ten, "Tennis"), (cross, "Cross")]:
        assert "moc" in text, f"{label} digest missing 'moc' tag"
