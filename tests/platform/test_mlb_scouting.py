"""tests/platform/test_mlb_scouting.py — Tests for domains.mlb.atlas_scouting.build_scouting().

Tiny synthetic vault/Sports/MLB tree: two Playstyles notes + one Style_Matchups note +
a Trends overview.  Exercises build_scouting() end-to-end without real FS reads.

Run: python -m pytest tests/platform/test_mlb_scouting.py -q --timeout=120
"""
from __future__ import annotations

import pathlib
import re

import pytest

_REAL_PLAYER_NAMES = ["trout", "judge", "betts", "ohtani", "verlander"]
_FORBIDDEN_BETTING = ["betting", " edge", "roi", "wager", "gamble", " odds "]

_HOME_SLUG = "power_run_scoring"
_AWAY_SLUG = "pitching_run_prevention"
_PAIR_FILE = f"{_HOME_SLUG}__vs__{_AWAY_SLUG}.md"
_PAIR_STEM = f"{_HOME_SLUG}__vs__{_AWAY_SLUG}"


def _write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


_PS_HOME = (
    "---\narchetype: power_run_scoring\nsport: mlb\ncorpus_span: 2010-2021\nteam_count: 4\n"
    "tags:\n  - sport/mlb\n  - playstyle\n---\n\n"
    "# Playstyle: Power / Run-Scoring\n\n## Style Description\n\n"
    "Offense-first franchises that consistently produce high run totals and positive "
    "run differentials. High-scoring games are a recurring identity signature.\n\n"
    "## Signature Thresholds\n*(measured over the 2010-2021 corpus)*\n\n"
    "| Metric | Threshold |\n|--------|-----------|\n"
    "| Runs Scored / G | >= 4.65 |\n| Run Differential / G | > 0 |\n\n"
    "#sport/mlb #playstyle\n"
)
_PS_AWAY = (
    "---\narchetype: pitching_run_prevention\nsport: mlb\ncorpus_span: 2010-2021\nteam_count: 5\n"
    "tags:\n  - sport/mlb\n  - playstyle\n---\n\n"
    "# Playstyle: Pitching-Led / Run-Prevention\n\n## Style Description\n\n"
    "Franchises that limit opponent run production as their primary identity. "
    "Positive run differentials are driven by pitching and defense.\n\n"
    "## Signature Thresholds\n*(measured over the 2010-2021 corpus)*\n\n"
    "| Metric | Threshold |\n|--------|-----------|\n"
    "| Runs Allowed / G | <= 4.10 |\n| Run Differential / G | > 0 |\n\n"
    "#sport/mlb #playstyle\n"
)
_MATCHUP_NOTE = (
    "---\nsport: mlb\nmatchup_type: style_vs_style\nhome_style: power_run_scoring\n"
    "away_style: pitching_run_prevention\ncorpus_span: 2010-2021\ngame_count: 312\n"
    "tags:\n  - sport/mlb\n  - style-matchup\n---\n\n"
    "## Outcome Summary\n\n| Metric | Value |\n|--------|-------|\n"
    "| Games in corpus | 312 |\n| Home-win rate | 57.7% |\n"
    "| Avg total runs / game | 9.42 |\n| High-scoring rate (>=10 total runs) | 43.3% |\n\n"
    "#sport/mlb #style-matchup\n"
)
_TRENDS_NOTE = (
    "---\nsport: mlb\ncorpus_span: 2010-2021\nnote_type: style_trends_overview\ntags:\n"
    "  - sport/mlb\n  - trends\n---\n\n"
    "# MLB Style and Run-Scoring Trends\n\n## League Run-Scoring Environment by Season\n\n"
    "| Season | RPG |\n|--------|-----|\n| 2010 | 8.76 |\n| 2021 | 9.05 |\n\n"
    "## Team Style Distribution by Season\n*(% of qualifying franchises per archetype)*\n\n"
    "| Season | Power | Pitching | Balanced | Hi-Var | Grinder | Deficit |\n"
    "|--------|--------|--------|--------|--------|--------|--------|\n"
    "| 2010 | 30.0% | 26.7% | 30.0% | 10.0% | 6.7% | 30.0% |\n"
    "| 2021 | 30.0% | 26.7% | 33.3% | 33.3% | 6.7% | 40.0% |\n\n"
    "#sport/mlb #trends\n"
)


def _make_vault(base: pathlib.Path, *, missing_away: bool = False) -> pathlib.Path:
    mlb = base / "vault" / "Sports" / "MLB"
    _write(mlb / "Playstyles" / f"{_HOME_SLUG}.md", _PS_HOME)
    if not missing_away:
        _write(mlb / "Playstyles" / f"{_AWAY_SLUG}.md", _PS_AWAY)
    _write(mlb / "Style_Matchups" / _PAIR_FILE, _MATCHUP_NOTE)
    _write(mlb / "Trends" / "_Style_Trends_Overview.md", _TRENDS_NOTE)
    return mlb


@pytest.fixture(scope="module")
def vault_dir(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    return _make_vault(tmp_path_factory.mktemp("vault_full"))


@pytest.fixture(scope="module")
def scout_out(tmp_path_factory: pytest.TempPathFactory, vault_dir: pathlib.Path) -> pathlib.Path:
    from domains.mlb.atlas_scouting import build_scouting
    out = tmp_path_factory.mktemp("scout_out")
    build_scouting(out, vault_mlb_dir=vault_dir)
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


class TestExistence:
    def test_brief_exists(self, scout_out: pathlib.Path) -> None:
        assert (scout_out / _PAIR_FILE).exists()

    def test_index_exists(self, scout_out: pathlib.Path) -> None:
        assert (scout_out / "_Scouting_Index.md").exists()

    def test_returns_list_of_paths(self, vault_dir: pathlib.Path, tmp_path: pathlib.Path) -> None:
        from domains.mlb.atlas_scouting import build_scouting
        paths = build_scouting(tmp_path / "out2", vault_mlb_dir=vault_dir)
        assert isinstance(paths, list) and len(paths) >= 2
        assert all(isinstance(p, pathlib.Path) and p.exists() for p in paths)


class TestSynthesis:
    def _text(self, scout_out: pathlib.Path) -> str:
        return (scout_out / _PAIR_FILE).read_text(encoding="utf-8")

    def test_synthesizes_home_style(self, scout_out: pathlib.Path) -> None:
        assert "power" in self._text(scout_out).lower()

    def test_synthesizes_away_style(self, scout_out: pathlib.Path) -> None:
        assert "pitching" in self._text(scout_out).lower()

    def test_contains_home_win_rate(self, scout_out: pathlib.Path) -> None:
        assert "57.7%" in self._text(scout_out)

    def test_contains_game_count(self, scout_out: pathlib.Path) -> None:
        assert "312" in self._text(scout_out)

    def test_contains_avg_total_runs(self, scout_out: pathlib.Path) -> None:
        assert "9.42" in self._text(scout_out)

    def test_contains_trend_direction(self, scout_out: pathlib.Path) -> None:
        t = self._text(scout_out)
        assert "rising" in t or "falling" in t or "stable" in t

    def test_contains_style_description(self, scout_out: pathlib.Path) -> None:
        t = self._text(scout_out).lower()
        assert "offense-first" in t or "run total" in t


class TestWikilinks:
    def _text(self, scout_out: pathlib.Path) -> str:
        return (scout_out / _PAIR_FILE).read_text(encoding="utf-8")

    def test_links_to_home_playstyle(self, scout_out: pathlib.Path) -> None:
        assert f"[[{_HOME_SLUG}" in self._text(scout_out)

    def test_links_to_away_playstyle(self, scout_out: pathlib.Path) -> None:
        assert f"[[{_AWAY_SLUG}" in self._text(scout_out)

    def test_links_to_pair_stem(self, scout_out: pathlib.Path) -> None:
        t = self._text(scout_out)
        assert f"[[{_PAIR_STEM}|" in t or f"[[{_PAIR_STEM}]]" in t

    def test_links_to_trends(self, scout_out: pathlib.Path) -> None:
        assert "[[_Style_Trends_Overview" in self._text(scout_out)

    def test_links_to_scouting_index(self, scout_out: pathlib.Path) -> None:
        assert "[[_Scouting_Index" in self._text(scout_out)

    def test_no_path_prefixed_links(self, scout_out: pathlib.Path) -> None:
        for md in scout_out.glob("*.md"):
            t = md.read_text(encoding="utf-8")
            assert "[[../Playstyles/" not in t and "[[../Trends/" not in t

    def test_index_cross_links(self, scout_out: pathlib.Path) -> None:
        t = (scout_out / "_Scouting_Index.md").read_text(encoding="utf-8")
        assert "[[_Style_Matchups_Index" in t and "[[_Playstyles_Index" in t


class TestNoForbiddenContent:
    def test_no_real_player_names(self, scout_out: pathlib.Path) -> None:
        for md in scout_out.glob("*.md"):
            low = md.read_text(encoding="utf-8").lower()
            for name in _REAL_PLAYER_NAMES:
                assert name not in low, f"Player name '{name}' in {md.name}"

    def test_no_betting_terms(self, scout_out: pathlib.Path) -> None:
        for md in scout_out.glob("*.md"):
            low = md.read_text(encoding="utf-8").lower()
            for term in _FORBIDDEN_BETTING:
                assert not re.search(r"\b" + re.escape(term.strip()) + r"\b", low), \
                    f"Forbidden term '{term!r}' in {md.name}"


class TestFrontmatter:
    def test_brief_frontmatter_fields(self, scout_out: pathlib.Path) -> None:
        fm = _parse_fm((scout_out / _PAIR_FILE).read_text(encoding="utf-8"))
        assert "home_slug" in fm and "away_slug" in fm and "home_win_rate" in fm

    def test_brief_has_sport_mlb_tag(self, scout_out: pathlib.Path) -> None:
        assert "sport/mlb" in (scout_out / _PAIR_FILE).read_text(encoding="utf-8")

    def test_index_type_field(self, scout_out: pathlib.Path) -> None:
        fm = _parse_fm((scout_out / "_Scouting_Index.md").read_text(encoding="utf-8"))
        assert fm.get("type") == "scouting-index"


class TestGracefulMissing:
    def test_brief_emitted_when_away_playstyle_missing(
        self, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        vault = _make_vault(tmp_path_factory.mktemp("vm"), missing_away=True)
        from domains.mlb.atlas_scouting import build_scouting
        out = tmp_path_factory.mktemp("sm")
        build_scouting(out, vault_mlb_dir=vault)
        text = (out / _PAIR_FILE).read_text(encoding="utf-8")
        assert "not found" in text.lower()

    def test_no_exception_trends_missing(self, tmp_path_factory: pytest.TempPathFactory) -> None:
        vault = _make_vault(tmp_path_factory.mktemp("vt"))
        (vault / "Trends" / "_Style_Trends_Overview.md").unlink()
        from domains.mlb.atlas_scouting import build_scouting
        build_scouting(tmp_path_factory.mktemp("st"), vault_mlb_dir=vault)

    def test_no_exception_empty_matchups(self, tmp_path_factory: pytest.TempPathFactory) -> None:
        mlb = tmp_path_factory.mktemp("ve") / "vault" / "Sports" / "MLB"
        (mlb / "Style_Matchups").mkdir(parents=True)
        from domains.mlb.atlas_scouting import build_scouting
        paths = build_scouting(tmp_path_factory.mktemp("se"), vault_mlb_dir=mlb)
        assert any(p.name == "_Scouting_Index.md" for p in paths)


class TestIdempotency:
    def test_same_count_on_rerun(self, vault_dir: pathlib.Path, tmp_path: pathlib.Path) -> None:
        from domains.mlb.atlas_scouting import build_scouting
        out = tmp_path / "idem"
        assert len(build_scouting(out, vault_mlb_dir=vault_dir)) == \
               len(build_scouting(out, vault_mlb_dir=vault_dir))
