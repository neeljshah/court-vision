"""tests/platform/test_tennis_scouting.py — Tests for atlas_scouting.build_scouting().

Tiny synthetic vault tree: two Playstyles notes + one Style_Matchups note +
a Trends overview.  Exercises build_scouting() end-to-end without real FS reads.

Run: python -m pytest tests/platform/test_tennis_scouting.py -q --timeout=120
"""
from __future__ import annotations

import pathlib
import re
from typing import Optional

import pytest

# ---------------------------------------------------------------------------
# Forbidden content constants
# ---------------------------------------------------------------------------

_REAL_NAMES = ["djokovic", "nadal", "federer", "alcaraz", "sinner"]
_SYNTH_NAMES = ["SynthAlpha", "SynthBeta", "Alice", "Bob"]
_FORBIDDEN_BETTING = ["betting", " edge", "roi", "wager", "gamble", " odds "]

# ---------------------------------------------------------------------------
# Synthetic vault builders
# ---------------------------------------------------------------------------

_PLAYSTYLE_A_SLUG = "Clay_Court_Specialist"
_PLAYSTYLE_B_SLUG = "Fast_Court_Big_Server"
_PAIR_STEM = f"{_PLAYSTYLE_A_SLUG}_vs_{_PLAYSTYLE_B_SLUG}"

def _write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

_PS_A = (
    "---\narchetype: Clay Court Specialist\nplayer_count: 60\ncorpus_share_pct: 14.7\n"
    "tags:\n  - sport/tennis\n  - playstyle\n---\n\n# Clay Court Specialist\n\n"
    "## Description\nExcels on slow clay surfaces where heavy topspin and baseline "
    "consistency are rewarded.\n\n## Surface Tendencies\n- **Pattern:** Clay >> Hard ≈ Grass\n\n"
    "---\n#sport/tennis #playstyle\n"
)
_PS_B = (
    "---\narchetype: Fast Court Big Server\nplayer_count: 63\ncorpus_share_pct: 15.4\n"
    "tags:\n  - sport/tennis\n  - playstyle\n---\n\n# Fast Court Big Server\n\n"
    "## Description\nTall players whose physical frame translates into outsized performance "
    "on faster courts.\n\n## Surface Tendencies\n- **Pattern:** Hard ≈ Grass >> Clay\n\n"
    "---\n#sport/tennis #playstyle\n"
)
_MATCHUP_NOTE = (
    "---\narchetype_a: Clay Court Specialist\narchetype_b: Fast Court Big Server\n"
    "total_meetings: 500\nwin_rate_a: 0.55\nwin_rate_b: 0.45\n"
    "tags:\n  - sport/tennis\n  - style-matchup\n---\n\n"
    "## Outcome Summary\n- **Total meetings (archetype level):** 500\n\n"
    "## Surface Breakdown\n"
    "- **Clay:** win-rate of A = 62.0% (250 meetings)\n"
    "- **Hard:** win-rate of A = 47.0% (200 meetings)\n"
    "- **Grass:** win-rate of A = 41.0% (50 meetings)\n\n"
    "*Surface spread 21.0 pp — surface context is meaningful.*\n\n"
    "---\n#sport/tennis #style-matchup\n"
)
_TRENDS_NOTE = (
    "---\ntype: style-trends\nyear_range: \"2020-2025\"\ntags:\n  - sport/tennis\n---\n\n"
    "# Tennis Style-Era Trends\n\n## Archetype Share by Year (%)\n\n```\n"
    "+---------+---------+---------+---------+---------+---------+---------+---------+---------+\n"
    "|    Year |    Clay |  BigSrv |  AllCrt |   LeftH |   GSlam |    Hard |   Grass |    Jrny |\n"
    "+---------+---------+---------+---------+---------+---------+---------+---------+---------+\n"
    "|    2020 |   12.3% |   16.9% |   14.8% |   11.0% |    5.9% |    0.8% |    3.8% |   34.3% |\n"
    "|    2025 |   13.2% |   13.7% |   13.7% |   12.3% |    7.1% |    2.8% |    2.4% |   34.9% |\n"
    "+---------+---------+---------+---------+---------+---------+---------+---------+---------+\n"
    "```\n\n---\n#sport/tennis #trends\n"
)

def _make_vault(base: pathlib.Path, *, missing_b_playstyle: bool = False) -> pathlib.Path:
    """Create minimal vault/Sports/Tennis tree under *base*; return its path."""
    tennis = base / "vault" / "Sports" / "Tennis"
    _write(tennis / "Playstyles" / f"{_PLAYSTYLE_A_SLUG}.md", _PS_A)
    if not missing_b_playstyle:
        _write(tennis / "Playstyles" / f"{_PLAYSTYLE_B_SLUG}.md", _PS_B)
    _write(tennis / "Style_Matchups" / f"{_PAIR_STEM}.md", _MATCHUP_NOTE)
    _write(tennis / "Trends" / "_Style_Trends_Overview.md", _TRENDS_NOTE)
    return tennis

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def vault_dir(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    base = tmp_path_factory.mktemp("vault_full")
    return _make_vault(base)

@pytest.fixture(scope="module")
def scout_out(
    tmp_path_factory: pytest.TempPathFactory,
    vault_dir: pathlib.Path,
) -> pathlib.Path:
    from domains.tennis.atlas_scouting import build_scouting
    out = tmp_path_factory.mktemp("scout_out")
    build_scouting(out, vault_tennis_dir=vault_dir)
    return out

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _parse_fm(text: str) -> dict:
    fm: dict = {}
    in_fm = False
    for line in text.splitlines():
        if line.strip() == "---":
            if not in_fm:
                in_fm = True
                continue
            break
        if in_fm and ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm

# ---------------------------------------------------------------------------
# Existence
# ---------------------------------------------------------------------------

class TestExistence:
    def test_brief_note_exists(self, scout_out: pathlib.Path) -> None:
        assert (scout_out / f"{_PAIR_STEM}.md").exists()

    def test_index_exists(self, scout_out: pathlib.Path) -> None:
        assert (scout_out / "_Scouting_Index.md").exists()

    def test_returns_list_of_existing_paths(
        self, vault_dir: pathlib.Path, tmp_path: pathlib.Path
    ) -> None:
        from domains.tennis.atlas_scouting import build_scouting
        paths = build_scouting(tmp_path / "out", vault_tennis_dir=vault_dir)
        assert isinstance(paths, list) and len(paths) >= 2
        assert all(isinstance(p, pathlib.Path) and p.exists() for p in paths)

# ---------------------------------------------------------------------------
# Synthesis: both sides present
# ---------------------------------------------------------------------------

class TestSynthesis:
    def test_brief_contains_archetype_a_content(self, scout_out: pathlib.Path) -> None:
        text = (scout_out / f"{_PAIR_STEM}.md").read_text(encoding="utf-8")
        assert "clay surfaces" in text.lower() or "clay court specialist" in text.lower()

    def test_brief_contains_archetype_b_content(self, scout_out: pathlib.Path) -> None:
        text = (scout_out / f"{_PAIR_STEM}.md").read_text(encoding="utf-8")
        assert "faster courts" in text.lower() or "fast court big server" in text.lower()

    def test_brief_contains_win_rate(self, scout_out: pathlib.Path) -> None:
        text = (scout_out / f"{_PAIR_STEM}.md").read_text(encoding="utf-8")
        assert "55.0%" in text

    def test_brief_contains_total_meetings(self, scout_out: pathlib.Path) -> None:
        text = (scout_out / f"{_PAIR_STEM}.md").read_text(encoding="utf-8")
        assert "500" in text

    def test_brief_contains_surface_breakdown(self, scout_out: pathlib.Path) -> None:
        text = (scout_out / f"{_PAIR_STEM}.md").read_text(encoding="utf-8")
        assert "62.0%" in text  # Clay surface win-rate from matchup note

    def test_brief_contains_trend_direction(self, scout_out: pathlib.Path) -> None:
        text = (scout_out / f"{_PAIR_STEM}.md").read_text(encoding="utf-8")
        assert "rising" in text or "falling" in text or "stable" in text

# ---------------------------------------------------------------------------
# Wikilinks
# ---------------------------------------------------------------------------

class TestWikilinks:
    def _brief(self, scout_out: pathlib.Path) -> str:
        return (scout_out / f"{_PAIR_STEM}.md").read_text(encoding="utf-8")

    def test_brief_links_to_both_playstyles(self, scout_out: pathlib.Path) -> None:
        # Bare-stem form: [[Slug|...]] — no leading path, no .md extension
        text = self._brief(scout_out)
        assert f"[[{_PLAYSTYLE_A_SLUG}" in text
        assert f"[[{_PLAYSTYLE_B_SLUG}" in text
        # Must NOT contain old malformed relative-path form
        assert "[[../Playstyles/" not in text

    def test_brief_links_to_style_matchups_and_trends(self, scout_out: pathlib.Path) -> None:
        # Bare-stem form: target before | must be stem only (no path, no .md)
        text = self._brief(scout_out)
        assert f"[[{_PAIR_STEM}|" in text or f"[[{_PAIR_STEM}]]" in text
        assert "[[_Style_Trends_Overview" in text
        # Must NOT contain old malformed forms
        assert "[[../Style_Matchups/" not in text
        assert "[[../Trends/" not in text

    def test_brief_links_back_to_scouting_index(self, scout_out: pathlib.Path) -> None:
        assert "[[_Scouting_Index" in self._brief(scout_out)

    def test_index_cross_links(self, scout_out: pathlib.Path) -> None:
        text = (scout_out / "_Scouting_Index.md").read_text(encoding="utf-8")
        # Bare-stem form — no leading ../Folder/ prefix
        assert "[[_Style_Matchups_Index" in text
        assert "[[_Playstyles_Index" in text
        assert "[[../Style_Matchups/" not in text
        assert "[[../Playstyles/" not in text

# ---------------------------------------------------------------------------
# No player names
# ---------------------------------------------------------------------------

class TestNoNames:
    def test_no_real_names(self, scout_out: pathlib.Path) -> None:
        for md in scout_out.glob("*.md"):
            low = md.read_text(encoding="utf-8").lower()
            for name in _REAL_NAMES:
                assert name not in low, f"Real name '{name}' found in {md.name}"

    def test_no_synth_names(self, scout_out: pathlib.Path) -> None:
        for md in scout_out.glob("*.md"):
            for name in _SYNTH_NAMES:
                assert name not in md.read_text(encoding="utf-8"), \
                    f"Synthetic name '{name}' found in {md.name}"

# ---------------------------------------------------------------------------
# No betting language
# ---------------------------------------------------------------------------

class TestNoBettingLanguage:
    def test_no_betting_terms(self, scout_out: pathlib.Path) -> None:
        for md in scout_out.glob("*.md"):
            low = md.read_text(encoding="utf-8").lower()
            for term in _FORBIDDEN_BETTING:
                assert not re.search(r"\b" + re.escape(term.strip()) + r"\b", low), \
                    f"Forbidden term '{term!r}' in {md.name}"

# ---------------------------------------------------------------------------
# Front-matter
# ---------------------------------------------------------------------------

class TestFrontmatter:
    def test_brief_frontmatter_fields(self, scout_out: pathlib.Path) -> None:
        fm = _parse_fm((scout_out / f"{_PAIR_STEM}.md").read_text(encoding="utf-8"))
        assert "archetype_a" in fm and "archetype_b" in fm
        assert "total_meetings" in fm
        assert "win_rate_a" in fm and "win_rate_b" in fm

    def test_brief_has_sport_tennis_tag(self, scout_out: pathlib.Path) -> None:
        text = (scout_out / f"{_PAIR_STEM}.md").read_text(encoding="utf-8")
        assert "sport/tennis" in text

    def test_index_frontmatter_type(self, scout_out: pathlib.Path) -> None:
        fm = _parse_fm((scout_out / "_Scouting_Index.md").read_text(encoding="utf-8"))
        assert fm.get("type") == "scouting-index"

# ---------------------------------------------------------------------------
# Graceful missing Playstyle note
# ---------------------------------------------------------------------------

class TestGracefulMissing:
    def test_brief_emitted_when_playstyle_b_missing(
        self, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        base = tmp_path_factory.mktemp("vault_missing_b")
        vault = _make_vault(base, missing_b_playstyle=True)
        from domains.tennis.atlas_scouting import build_scouting
        out = tmp_path_factory.mktemp("scout_missing")
        paths = build_scouting(out, vault_tennis_dir=vault)
        brief = out / f"{_PAIR_STEM}.md"
        assert brief.exists(), "Brief not emitted when one playstyle note is missing"
        text = brief.read_text(encoding="utf-8")
        assert "not found" in text.lower()

    def test_no_exception_when_trends_missing(
        self, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        base = tmp_path_factory.mktemp("vault_no_trends")
        vault = _make_vault(base)
        trends_file = vault / "Trends" / "_Style_Trends_Overview.md"
        if trends_file.exists():
            trends_file.unlink()
        from domains.tennis.atlas_scouting import build_scouting
        out = tmp_path_factory.mktemp("scout_no_trends")
        build_scouting(out, vault_tennis_dir=vault)  # must not raise
        assert (out / f"{_PAIR_STEM}.md").exists()

# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_idempotent_same_count(
        self, vault_dir: pathlib.Path, tmp_path: pathlib.Path
    ) -> None:
        from domains.tennis.atlas_scouting import build_scouting
        out = tmp_path / "idem"
        p1 = build_scouting(out, vault_tennis_dir=vault_dir)
        p2 = build_scouting(out, vault_tennis_dir=vault_dir)
        assert len(p1) == len(p2)
