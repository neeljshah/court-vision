"""tests/platform/test_soccer_scouting.py — Tests for atlas_scouting.build_scouting().

Tiny synthetic vault tree: two Playstyles + one Style_Matchups + Trends + Stickiness.
Exercises build_scouting() end-to-end without real FS reads.

Run: python -m pytest tests/platform/test_soccer_scouting.py -q --timeout=120
"""
from __future__ import annotations

import pathlib
import re

import pytest

_REAL_PLAYER_NAMES = ["messi", "ronaldo", "mbappe", "haaland", "salah"]
_FORBIDDEN_BETTING = ["betting", " edge", "roi", "wager", "gamble"]

_SCHEME_A_KEY = "High-Scoring_Attacking"
_SCHEME_B_KEY = "Defensive_Low-Block"
_PAIR_STEM = f"{_SCHEME_A_KEY}_vs_{_SCHEME_B_KEY}"

_PS_A = (
    '---\nscheme: "High-Scoring Attacking"\nteam_count: 15\ngenerated: 2026-06-13\n'
    "tags:\n  - sport/soccer\n  - scheme\n---\n\n# High-Scoring Attacking\n\n"
    "Up: [[_Playstyles_Index|Playstyles Index]]\n\n"
    "*Prolific attacking output driving high match totals; "
    "invests heavily in front-line creation regardless of defensive cost.*\n\n"
    "## Stat Signature\n\n"
    "**Classification rule:** GF/game ≥ 1.60  AND  Over-2.5 rate ≥ 58%\n\n"
    "## Teams (15)\n\n- [[Teams/Barcelona|Barcelona]]\n\n---\n#sport/soccer #scheme\n"
)
_PS_B = (
    '---\nscheme: "Defensive Low-Block"\nteam_count: 7\ngenerated: 2026-06-13\n'
    "tags:\n  - sport/soccer\n  - scheme\n---\n\n# Defensive Low-Block\n\n"
    "Up: [[_Playstyles_Index|Playstyles Index]]\n\n"
    "*Compact defensive structure limiting opposition chances; "
    "high clean-sheet frequency and low match totals are the signature.*\n\n"
    "## Stat Signature\n\n"
    "**Classification rule:** GA/game ≤ 1.15  AND  Clean-sheet% ≥ 31%  AND  Over-2.5 rate ≤ 49%\n\n"
    "## Teams (7)\n\n- [[Teams/Juventus|Juventus]]\n\n---\n#sport/soccer #scheme\n"
)
_MATCHUP_NOTE = (
    '---\nhome_scheme: "High-Scoring Attacking"\naway_scheme: "Defensive Low-Block"\n'
    "total_meetings: 400\nhome_win_rate: 0.380\ndraw_rate: 0.245\n"
    "away_win_rate: 0.375\nover25_rate: 0.530\ngenerated: 2026-06-13\n"
    "tags:\n  - sport/soccer\n  - scheme-matchup\n---\n\n"
    "# High-Scoring Attacking (home) vs Defensive Low-Block (away)\n\n"
    "## Outcome Rates\n\n| Result | Count | Rate |\n|--------|-------|------|\n"
    "| Home Win | 152 | 38.0% |\n| Draw | 98 | 24.5% |\n"
    "| Away Win | 150 | 37.5% |\n| Over 2.5 Goals | 212 | 53.0% |\n"
    "| Total Meetings | 400 | — |\n\n---\n#sport/soccer #scheme-matchup\n"
)
_TRENDS_NOTE = (
    "---\ntype: style-trends-overview\nsport: soccer\n---\n\n"
    "# Soccer Scheme-Season Trends\n\n"
    "| Season  | Matches  | Goals/G | O2.5%  | HWin%  | HighScr | HiVar  | DefBlk  | DrawPr  | Leaky  | StHome  | Bal   |\n"
    "|---------|----------|---------|--------|--------|---------|--------|---------|---------|--------|---------|-------|\n"
    "| 2015    | 2378     | 2.61    | 49.2%  | 43.6%  | 9.0%    | 6.6%   | 13.9%   | 26.2%   | 3.3%   | 13.9%   | 27.0% |\n"
    "| 2024    | 2304     | 2.74    | 51.3%  | 42.9%  | 19.2%   | 5.0%   | 10.8%   | 20.0%   | 7.5%   | 5.8%    | 31.7% |\n\n"
    "---\n#sport/soccer #atlas/style-trends\n"
)
_STICKINESS_NOTE = (
    "---\ntype: scheme-stickiness\nsport: soccer\n---\n\n# Scheme Stickiness\n\n"
    "| Scheme | Stickiness | Stayed | Total |\n|--------|-----------|--------|-------|\n"
    "| [[Playstyles/High-Scoring_Attacking|High-Scoring Attacking]] | 49.2% | 89 | 181 |\n"
    "| [[Playstyles/Defensive_Low-Block|Defensive Low-Block]] | 25.2% | 37 | 147 |\n\n"
    "---\n#sport/soccer #atlas/scheme-transitions\n"
)


def _write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_vault(
    base: pathlib.Path,
    *,
    missing_b_playstyle: bool = False,
    missing_trends: bool = False,
    missing_stickiness: bool = False,
) -> pathlib.Path:
    soccer = base / "vault" / "Sports" / "Soccer"
    _write(soccer / "Playstyles" / f"{_SCHEME_A_KEY}.md", _PS_A)
    if not missing_b_playstyle:
        _write(soccer / "Playstyles" / f"{_SCHEME_B_KEY}.md", _PS_B)
    _write(soccer / "Style_Matchups" / f"{_PAIR_STEM}.md", _MATCHUP_NOTE)
    if not missing_trends:
        _write(soccer / "Trends" / "_Style_Trends_Overview.md", _TRENDS_NOTE)
    if not missing_stickiness:
        _write(soccer / "Scheme_Transitions" / "Stickiness.md", _STICKINESS_NOTE)
    return soccer


@pytest.fixture(scope="module")
def vault_dir(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    return _make_vault(tmp_path_factory.mktemp("vault_full"))


@pytest.fixture(scope="module")
def scout_out(tmp_path_factory: pytest.TempPathFactory, vault_dir: pathlib.Path) -> pathlib.Path:
    from domains.soccer.atlas_scouting import build_scouting
    out = tmp_path_factory.mktemp("scout_out")
    build_scouting(out, vault_soccer_dir=vault_dir)
    return out


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


def _brief(scout_out: pathlib.Path) -> str:
    return (scout_out / f"{_PAIR_STEM}.md").read_text(encoding="utf-8")


class TestExistence:
    def test_brief_note_exists(self, scout_out: pathlib.Path) -> None:
        assert (scout_out / f"{_PAIR_STEM}.md").exists()

    def test_index_exists(self, scout_out: pathlib.Path) -> None:
        assert (scout_out / "_Scouting_Index.md").exists()

    def test_returns_list_of_existing_paths(
        self, vault_dir: pathlib.Path, tmp_path: pathlib.Path
    ) -> None:
        from domains.soccer.atlas_scouting import build_scouting
        paths = build_scouting(tmp_path / "out", vault_soccer_dir=vault_dir)
        assert isinstance(paths, list) and len(paths) >= 2
        assert all(isinstance(p, pathlib.Path) and p.exists() for p in paths)


class TestSynthesis:
    def test_scheme_a_content(self, scout_out: pathlib.Path) -> None:
        text = _brief(scout_out)
        assert "high-scoring attacking" in text.lower() or "prolific attacking" in text.lower()

    def test_scheme_b_content(self, scout_out: pathlib.Path) -> None:
        text = _brief(scout_out)
        assert "defensive low-block" in text.lower() or "compact defensive" in text.lower()

    def test_home_win_rate(self, scout_out: pathlib.Path) -> None:
        assert "38.0%" in _brief(scout_out)

    def test_draw_rate(self, scout_out: pathlib.Path) -> None:
        assert "24.5%" in _brief(scout_out)

    def test_over25_rate(self, scout_out: pathlib.Path) -> None:
        assert "53.0%" in _brief(scout_out)

    def test_total_meetings(self, scout_out: pathlib.Path) -> None:
        assert "400" in _brief(scout_out)

    def test_trend_direction(self, scout_out: pathlib.Path) -> None:
        text = _brief(scout_out)
        assert "rising" in text or "falling" in text or "stable" in text

    def test_stickiness_present(self, scout_out: pathlib.Path) -> None:
        text = _brief(scout_out)
        assert "49.2%" in text or "25.2%" in text


class TestWikilinks:
    def test_links_to_both_schemes(self, scout_out: pathlib.Path) -> None:
        text = _brief(scout_out)
        assert f"[[{_SCHEME_A_KEY}" in text
        assert f"[[{_SCHEME_B_KEY}" in text

    def test_no_relative_path_links(self, scout_out: pathlib.Path) -> None:
        text = _brief(scout_out)
        assert "[[../" not in text
        assert "[[Playstyles/" not in text

    def test_no_md_extension_in_targets(self, scout_out: pathlib.Path) -> None:
        targets = re.findall(r"\[\[([^\]|]+)", _brief(scout_out))
        for t in targets:
            assert not t.endswith(".md"), f"Wikilink has .md extension: [[{t}]]"

    def test_links_to_pair_note_and_trends(self, scout_out: pathlib.Path) -> None:
        text = _brief(scout_out)
        assert f"[[{_PAIR_STEM}" in text
        assert "[[_Style_Trends_Overview" in text

    def test_links_to_scouting_index(self, scout_out: pathlib.Path) -> None:
        assert "[[_Scouting_Index" in _brief(scout_out)

    def test_links_to_stickiness(self, scout_out: pathlib.Path) -> None:
        assert "[[Stickiness" in _brief(scout_out)

    def test_index_cross_links(self, scout_out: pathlib.Path) -> None:
        text = (scout_out / "_Scouting_Index.md").read_text(encoding="utf-8")
        assert "[[_Style_Matchups_Index" in text and "[[_Playstyles_Index" in text
        assert "[[../" not in text


class TestNoNamesNoBetting:
    def test_no_real_player_names(self, scout_out: pathlib.Path) -> None:
        for md in scout_out.glob("*.md"):
            low = md.read_text(encoding="utf-8").lower()
            for name in _REAL_PLAYER_NAMES:
                assert name not in low, f"Player name '{name}' in {md.name}"

    def test_no_betting_terms(self, scout_out: pathlib.Path) -> None:
        for md in scout_out.glob("*.md"):
            low = md.read_text(encoding="utf-8").lower()
            for term in _FORBIDDEN_BETTING:
                assert term not in low, f"Forbidden term {term!r} in {md.name}"


class TestFrontmatter:
    def test_brief_fields(self, scout_out: pathlib.Path) -> None:
        fm = _parse_fm(_brief(scout_out))
        assert all(k in fm for k in ("home_scheme", "away_scheme", "total_meetings",
                                     "home_win_rate", "over25_rate"))

    def test_sport_soccer_tag(self, scout_out: pathlib.Path) -> None:
        assert "sport/soccer" in _brief(scout_out)

    def test_index_type(self, scout_out: pathlib.Path) -> None:
        fm = _parse_fm((scout_out / "_Scouting_Index.md").read_text(encoding="utf-8"))
        assert fm.get("type") == "scouting-index"


class TestGracefulMissing:
    def test_brief_emitted_when_playstyle_b_missing(
        self, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        vault = _make_vault(tmp_path_factory.mktemp("v_miss_b"), missing_b_playstyle=True)
        from domains.soccer.atlas_scouting import build_scouting
        out = tmp_path_factory.mktemp("out_miss_b")
        build_scouting(out, vault_soccer_dir=vault)
        text = (out / f"{_PAIR_STEM}.md").read_text(encoding="utf-8")
        assert "not found" in text.lower()

    def test_no_exception_when_trends_missing(
        self, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        vault = _make_vault(tmp_path_factory.mktemp("v_no_trends"), missing_trends=True)
        from domains.soccer.atlas_scouting import build_scouting
        out = tmp_path_factory.mktemp("out_no_trends")
        build_scouting(out, vault_soccer_dir=vault)  # must not raise
        assert (out / f"{_PAIR_STEM}.md").exists()

    def test_no_exception_when_stickiness_missing(
        self, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        vault = _make_vault(tmp_path_factory.mktemp("v_no_stick"), missing_stickiness=True)
        from domains.soccer.atlas_scouting import build_scouting
        out = tmp_path_factory.mktemp("out_no_stick")
        build_scouting(out, vault_soccer_dir=vault)  # must not raise
        assert (out / f"{_PAIR_STEM}.md").exists()


class TestIdempotency:
    def test_same_count_on_rerun(self, vault_dir: pathlib.Path, tmp_path: pathlib.Path) -> None:
        from domains.soccer.atlas_scouting import build_scouting
        out = tmp_path / "idem"
        assert len(build_scouting(out, vault_soccer_dir=vault_dir)) == \
               len(build_scouting(out, vault_soccer_dir=vault_dir))
