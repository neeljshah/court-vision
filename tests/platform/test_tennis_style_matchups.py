"""tests/platform/test_tennis_style_matchups.py — Tests for atlas_style_matchups.py.

Tiny synthetic fixture; no real filesystem reads.
Checks: index + pair notes exist, [[Playstyles/...]] wikilinks present,
no player names in output, win-rate arithmetic correct in a hand case,
no betting language, frontmatter fields, idempotency.

Run: python -m pytest tests/platform/test_tennis_style_matchups.py -q --timeout=120
"""
from __future__ import annotations

import pathlib
import re

import numpy as np
import pandas as pd
import pytest

_SYNTH_NAMES = [f"SynthPlayer {i:02d}" for i in range(1, 26)]
_REAL_NAMES = ["djokovic", "nadal", "federer", "alcaraz", "sinner"]
_FORBIDDEN_BETTING = ["betting", "edge", "roi", "wager", "gamble", " odds"]


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _row(mid: int, p1: int, p2: int, surf: str, winner: int, best_of: int = 3) -> dict:
    return {
        "event_id": f"ev_{mid:05d}", "date": f"2020-01-{(mid % 28) + 1:02d}",
        "tour": "atp", "tourney_id": f"T{mid % 20:03d}", "tourney_name": "Synth Open",
        "tourney_level": "G" if best_of == 5 else "A", "surface": surf,
        "best_of": best_of, "round": "R32", "match_num": mid,
        "p1_id": p1, "p2_id": p2,
        "p1_name": f"SynthPlayer {p1:02d}", "p2_name": f"SynthPlayer {p2:02d}",
        "p1_rank": 10.0, "p2_rank": 20.0, "winner": winner,
        "score": "6-4 6-3", "retirement": False, "minutes": 90.0,
    }


def _make_large_matches(n: int = 2000) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    surfs = ["Hard", "Clay", "Grass"]
    rows = []
    for i in range(n):
        p1 = int(rng.integers(1, 26))
        p2 = int(rng.integers(1, 26))
        while p2 == p1:
            p2 = int(rng.integers(1, 26))
        rows.append(_row(i, p1, p2, surfs[i % 3], int(rng.integers(1, 3)),
                         5 if i % 10 == 0 else 3))
    return pd.DataFrame(rows)


def _make_large_players() -> pd.DataFrame:
    return pd.DataFrame([{
        "player_id": i, "full_name": _SYNTH_NAMES[i - 1],
        "hand": "L" if i % 5 == 0 else "R",
        "height": float(191 + i % 5) if i >= 20 else float(175 + i % 10),
    } for i in range(1, 26)])


def _make_hand_case() -> tuple[pd.DataFrame, pd.DataFrame]:
    """p1→Clay_Court_Specialist, p2→Fast_Court_Big_Server (height 195).
    40 cross-archetype bouts: p1 wins first 30 → wr_a > 0.5.
    p3/p4 are foils to give p1/p2 qualifying match counts.
    """
    rows = []; mid = 0

    def _m(p1: int, p2: int, surf: str, w: int) -> None:
        nonlocal mid; rows.append(_row(mid, p1, p2, surf, w)); mid += 1

    for _ in range(60): _m(1, 3, "Clay", 1)   # p1 clay wins
    for _ in range(10): _m(1, 3, "Hard", 2)   # p1 hard losses
    for _ in range(10): _m(1, 3, "Grass", 2)  # p1 grass losses
    for _ in range(60): _m(2, 4, "Hard", 1)   # p2 hard wins
    for _ in range(10): _m(2, 4, "Clay", 2)   # p2 clay losses
    for _ in range(10): _m(2, 4, "Grass", 2)  # p2 grass losses
    for i in range(15): _m(3, 4, ["Hard", "Clay", "Grass"][i % 3], 1 if i % 2 else 2)
    for i in range(15): _m(4, 3, ["Hard", "Clay", "Grass"][i % 3], 1 if i % 2 else 2)
    for i in range(40): _m(1, 2, ["Hard", "Clay", "Grass"][i % 3], 1 if i < 30 else 2)

    players = pd.DataFrame([
        {"player_id": 1, "full_name": "SynthPlayer 01", "hand": "R", "height": 180.0},
        {"player_id": 2, "full_name": "SynthPlayer 02", "hand": "R", "height": 195.0},
        {"player_id": 3, "full_name": "SynthPlayer 03", "hand": "R", "height": 180.0},
        {"player_id": 4, "full_name": "SynthPlayer 04", "hand": "R", "height": 180.0},
    ])
    return pd.DataFrame(rows), players


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def large_matches() -> pd.DataFrame:
    return _make_large_matches()


@pytest.fixture(scope="module")
def large_players() -> pd.DataFrame:
    return _make_large_players()


@pytest.fixture(scope="module")
def style_out(
    tmp_path_factory: pytest.TempPathFactory,
    large_matches: pd.DataFrame,
    large_players: pd.DataFrame,
) -> pathlib.Path:
    from domains.tennis.atlas_style_matchups import build_style_matchups
    out = tmp_path_factory.mktemp("style_matchups")
    build_style_matchups(out, _matches_df=large_matches, _players_df=large_players)
    return out


@pytest.fixture(scope="module")
def hand_case_out(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    from domains.tennis.atlas_style_matchups import build_style_matchups
    matches, players = _make_hand_case()
    out = tmp_path_factory.mktemp("hand_case")
    build_style_matchups(out, _matches_df=matches, _players_df=players)
    return out


# ---------------------------------------------------------------------------
# Existence & structure
# ---------------------------------------------------------------------------

class TestIndexAndPairNotes:
    def test_index_exists(self, style_out: pathlib.Path) -> None:
        assert (style_out / "_Style_Matchups_Index.md").exists()

    def test_at_least_one_pair_note(self, style_out: pathlib.Path) -> None:
        pairs = [p for p in style_out.glob("*.md") if p.name != "_Style_Matchups_Index.md"]
        assert len(pairs) >= 1

    def test_returns_list_of_existing_paths(
        self, large_matches: pd.DataFrame, large_players: pd.DataFrame, tmp_path: pathlib.Path
    ) -> None:
        from domains.tennis.atlas_style_matchups import build_style_matchups
        paths = build_style_matchups(tmp_path / "sm2", _matches_df=large_matches,
                                     _players_df=large_players)
        assert isinstance(paths, list) and len(paths) >= 1
        assert all(isinstance(p, pathlib.Path) and p.exists() for p in paths)


# ---------------------------------------------------------------------------
# Wikilinks
# ---------------------------------------------------------------------------

class TestWikilinks:
    def test_pair_notes_have_playstyles_wikilink(self, style_out: pathlib.Path) -> None:
        pairs = [p for p in style_out.glob("*.md") if p.name != "_Style_Matchups_Index.md"]
        for note in pairs:
            assert "[[Playstyles/" in note.read_text(encoding="utf-8"), \
                f"{note.name} missing [[Playstyles/...]]"

    def test_pair_notes_link_back_to_index(self, style_out: pathlib.Path) -> None:
        pairs = [p for p in style_out.glob("*.md") if p.name != "_Style_Matchups_Index.md"]
        for note in pairs:
            assert "[[_Style_Matchups_Index" in note.read_text(encoding="utf-8"), \
                f"{note.name} missing [[_Style_Matchups_Index]]"

    def test_index_links_to_playstyle_index(self, style_out: pathlib.Path) -> None:
        text = (style_out / "_Style_Matchups_Index.md").read_text(encoding="utf-8")
        assert "[[Playstyles/_Playstyles_Index" in text

    def test_index_has_tennis_index_link(self, style_out: pathlib.Path) -> None:
        text = (style_out / "_Style_Matchups_Index.md").read_text(encoding="utf-8")
        assert "[[_Index" in text


# ---------------------------------------------------------------------------
# No player names
# ---------------------------------------------------------------------------

class TestNoPlayerNames:
    def test_no_synth_names(self, style_out: pathlib.Path) -> None:
        for md in style_out.glob("*.md"):
            text = md.read_text(encoding="utf-8")
            for name in _SYNTH_NAMES:
                assert name not in text, f"Name '{name}' leaked into {md.name}"

    def test_no_real_names(self, style_out: pathlib.Path) -> None:
        for md in style_out.glob("*.md"):
            text = md.read_text(encoding="utf-8").lower()
            for name in _REAL_NAMES:
                assert name not in text, f"Real name '{name}' found in {md.name}"


# ---------------------------------------------------------------------------
# Hand-case win-rate correctness
# ---------------------------------------------------------------------------

def _parse_fm(text: str) -> dict:
    fm: dict = {}
    in_fm = False
    for line in text.splitlines():
        if line == "---":
            if not in_fm: in_fm = True; continue
            else: break
        if in_fm and ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


class TestHandCaseWinRate:
    def test_clay_vs_fast_note_exists(self, hand_case_out: pathlib.Path) -> None:
        note = hand_case_out / "Clay_Court_Specialist_vs_Fast_Court_Big_Server.md"
        assert note.exists(), \
            f"Missing Clay_vs_Fast note; found: {[p.name for p in hand_case_out.glob('*.md')]}"

    def test_win_rate_a_plus_b_equals_one(self, hand_case_out: pathlib.Path) -> None:
        note = hand_case_out / "Clay_Court_Specialist_vs_Fast_Court_Big_Server.md"
        if not note.exists():
            pytest.skip("pair note missing")
        fm = _parse_fm(note.read_text(encoding="utf-8"))
        wr_a = float(fm["win_rate_a"]); wr_b = float(fm["win_rate_b"])
        assert abs(wr_a + wr_b - 1.0) < 0.001

    def test_win_rate_a_greater_than_half(self, hand_case_out: pathlib.Path) -> None:
        """Clay specialist wins 30/40 cross-archetype bouts so A-side wr > 0.5."""
        note = hand_case_out / "Clay_Court_Specialist_vs_Fast_Court_Big_Server.md"
        if not note.exists():
            pytest.skip("pair note missing")
        fm = _parse_fm(note.read_text(encoding="utf-8"))
        assert float(fm["win_rate_a"]) > 0.5

    def test_total_meets_min_threshold(self, hand_case_out: pathlib.Path) -> None:
        note = hand_case_out / "Clay_Court_Specialist_vs_Fast_Court_Big_Server.md"
        if not note.exists():
            pytest.skip("pair note missing")
        from domains.tennis.atlas_style_matchups import MIN_PAIR_MEETINGS
        fm = _parse_fm(note.read_text(encoding="utf-8"))
        assert int(fm["total_meetings"]) >= MIN_PAIR_MEETINGS


# ---------------------------------------------------------------------------
# Frontmatter & tags
# ---------------------------------------------------------------------------

class TestFrontmatterAndTags:
    def test_all_notes_have_frontmatter(self, style_out: pathlib.Path) -> None:
        for md in style_out.glob("*.md"):
            text = md.read_text(encoding="utf-8")
            assert text.startswith("---") and text.count("---") >= 2

    def test_index_frontmatter_fields(self, style_out: pathlib.Path) -> None:
        fm = _parse_fm((style_out / "_Style_Matchups_Index.md").read_text(encoding="utf-8"))
        assert "total_corpus_matches" in fm
        assert "qualified_pairs" in fm
        assert "min_pair_meetings" in fm

    def test_pair_frontmatter_fields(self, style_out: pathlib.Path) -> None:
        pairs = [p for p in style_out.glob("*.md") if p.name != "_Style_Matchups_Index.md"]
        if not pairs:
            pytest.skip("no pair notes")
        fm = _parse_fm(pairs[0].read_text(encoding="utf-8"))
        assert "archetype_a" in fm and "archetype_b" in fm
        assert "total_meetings" in fm and "win_rate_a" in fm

    def test_all_notes_have_sport_tennis_tag(self, style_out: pathlib.Path) -> None:
        for md in style_out.glob("*.md"):
            assert "sport/tennis" in md.read_text(encoding="utf-8")

    def test_pair_notes_have_style_matchup_tag(self, style_out: pathlib.Path) -> None:
        pairs = [p for p in style_out.glob("*.md") if p.name != "_Style_Matchups_Index.md"]
        for note in pairs:
            assert "style-matchup" in note.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# No betting language
# ---------------------------------------------------------------------------

class TestNoBettingLanguage:
    def test_no_betting_terms(self, style_out: pathlib.Path) -> None:
        for md in style_out.glob("*.md"):
            text = md.read_text(encoding="utf-8").lower()
            for term in _FORBIDDEN_BETTING:
                assert not re.search(r"\b" + re.escape(term.strip()) + r"\b", text), \
                    f"Forbidden term '{term}' in {md.name}"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_idempotent(
        self, large_matches: pd.DataFrame, large_players: pd.DataFrame, tmp_path: pathlib.Path
    ) -> None:
        from domains.tennis.atlas_style_matchups import build_style_matchups
        out = tmp_path / "idem"
        p1 = build_style_matchups(out, _matches_df=large_matches, _players_df=large_players)
        p2 = build_style_matchups(out, _matches_df=large_matches, _players_df=large_players)
        assert len(p1) == len(p2)
