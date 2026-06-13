"""tests.platform.test_generators_person_free_part2 — Extended generator coverage.

Covers generators skipped in part1 (mlb.atlas, soccer.atlas) plus sub-generators
that accept corpus_dir or vault_dir: soccer h2h/seasons/playstyles/style_trends/
scheme_transitions/style_matchups, mlb h2h/seasons/playstyles/style_trends/
home_environment, and vault-reading scouting generators (tennis/mlb/soccer).

Synthetic corpora written into tmp_path only — no real parquet reads.
Invariants: (a) PERSON-FREE  (b) BARE-STEM WIKILINKS  (c) YAML FRONTMATTER.
"""
from __future__ import annotations

import pathlib
import re
from typing import List

import numpy as np
import pandas as pd

from scripts.platformkit.atlas.graph_health import _is_person_bearing

_WIKILINK_RE = re.compile(r"\[\[([^\]|#\n]+)")


def _run_all(out_dir: pathlib.Path) -> None:
    """Assert all 3 invariants on every .md note under out_dir."""
    notes = list(out_dir.rglob("*.md"))
    assert notes, f"No .md notes emitted under {out_dir}"
    bad_pf = [str(p) for p in notes
              if _is_person_bearing(p.read_text(encoding="utf-8", errors="replace"))]
    assert not bad_pf, "Person-bearing:\n" + "\n".join(bad_pf)
    bad_wl = [
        f"{p}: [[{m.group(1).strip()}]]"
        for p in notes
        for m in _WIKILINK_RE.finditer(p.read_text(encoding="utf-8", errors="replace"))
        if "../" in m.group(1) or m.group(1).strip().endswith(".md")
    ]
    assert not bad_wl, "Malformed wikilinks:\n" + "\n".join(bad_wl)
    bad_fm = [str(p) for p in notes
              if not p.read_text(encoding="utf-8", errors="replace").lstrip("﻿").startswith("---")]
    assert not bad_fm, "Missing frontmatter:\n" + "\n".join(bad_fm)


def _write_soccer_parquet(corpus_dir: pathlib.Path, n: int = 42) -> None:
    """Write corpus_dir/matches.parquet: 2 teams × n games across 2 seasons."""
    rng = np.random.default_rng(42)
    rows = []
    for i in range(n):
        season = 2022 if i < n // 2 else 2023
        home, away = ("TeamA", "TeamB") if i % 2 == 0 else ("TeamB", "TeamA")
        fthg, ftag = int(rng.integers(0, 4)), int(rng.integers(0, 4))
        ftr = "H" if fthg > ftag else ("A" if ftag > fthg else "D")
        rows.append({
            "date": f"{season}-04-{(i % 28) + 1:02d}", "season": season,
            "div": "E0", "home_team": home, "away_team": away,
            "fthg": fthg, "ftag": ftag, "total_goals": fthg + ftag,
            "target_over25": int((fthg + ftag) > 2), "ftr": ftr,
        })
    corpus_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(corpus_dir / "matches.parquet", index=False)


def _write_mlb_parquet(corpus_dir: pathlib.Path, n: int = 115) -> None:
    """Write corpus_dir/games.parquet: NYY vs BOS × n games across 2 seasons.
    n>=210 gives both teams >=100 home games (required by home_environment).
    """
    rng = np.random.default_rng(7)
    rows = []
    for i in range(n):
        season = 2019 if i < n // 2 else 2020
        home, away = ("NYY", "BOS") if i % 2 == 0 else ("BOS", "NYY")
        hr, ar = int(rng.integers(0, 10)), int(rng.integers(0, 10))
        rows.append({
            "date": f"{season}-05-{(i % 28) + 1:02d}", "season": season,
            "home_team": home, "away_team": away,
            "home_runs": hr, "away_runs": ar,
            "target_home_win": int(hr > ar), "home_league": "AL",
        })
    corpus_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(corpus_dir / "games.parquet", index=False)


# ---------------------------------------------------------------------------
# Soccer generators
# ---------------------------------------------------------------------------

class TestSoccerAtlas:
    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from domains.soccer.atlas import build_atlas
        corpus = tmp_path / "c"
        _write_soccer_parquet(corpus)
        assert build_atlas(tmp_path / "o", corpus_dir=corpus, min_matches=1)
        _run_all(tmp_path / "o")


class TestSoccerH2H:
    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from domains.soccer.atlas_h2h import build_h2h
        corpus = tmp_path / "c"
        _write_soccer_parquet(corpus)
        assert build_h2h(tmp_path / "o", corpus_dir=corpus)
        _run_all(tmp_path / "o")


class TestSoccerSeasons:
    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from domains.soccer.atlas_seasons import build_seasons
        corpus = tmp_path / "c"
        _write_soccer_parquet(corpus)
        assert build_seasons(tmp_path / "o", corpus_dir=corpus)
        _run_all(tmp_path / "o")


class TestSoccerPlaystyles:
    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from domains.soccer.atlas_playstyles import build_playstyles
        corpus = tmp_path / "c"
        _write_soccer_parquet(corpus)
        assert build_playstyles(tmp_path / "o", corpus_dir=corpus, min_matches=1)
        _run_all(tmp_path / "o")


class TestSoccerStyleTrends:
    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from domains.soccer.atlas_style_trends import build_style_trends
        corpus = tmp_path / "c"
        _write_soccer_parquet(corpus)
        assert build_style_trends(tmp_path / "o", corpus_dir=corpus, min_matches=1)
        _run_all(tmp_path / "o")


class TestSoccerStyleMatchups:
    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from domains.soccer.atlas_style_matchups import build_style_matchups
        corpus = tmp_path / "c"
        _write_soccer_parquet(corpus)
        assert build_style_matchups(
            tmp_path / "o", corpus_dir=corpus, min_pair_meetings=1)
        _run_all(tmp_path / "o")


class TestSoccerSchemeTransitions:
    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from domains.soccer.atlas_scheme_transitions import build_scheme_transitions
        corpus = tmp_path / "c"
        _write_soccer_parquet(corpus)
        assert build_scheme_transitions(
            tmp_path / "o", corpus_dir=corpus, min_matches=1)
        _run_all(tmp_path / "o")


# ---------------------------------------------------------------------------
# MLB generators
# ---------------------------------------------------------------------------

class TestMLBAtlas:
    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from domains.mlb.atlas import build_atlas
        corpus = tmp_path / "c"
        _write_mlb_parquet(corpus)
        assert build_atlas(tmp_path / "o", corpus_dir=corpus)
        _run_all(tmp_path / "o")


class TestMLBH2H:
    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from domains.mlb.atlas_h2h import build_h2h
        corpus = tmp_path / "c"
        _write_mlb_parquet(corpus)
        assert build_h2h(tmp_path / "o", corpus_dir=corpus)
        _run_all(tmp_path / "o")


class TestMLBSeasons:
    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from domains.mlb.atlas_seasons import build_seasons
        corpus = tmp_path / "c"
        _write_mlb_parquet(corpus)
        assert build_seasons(tmp_path / "o", corpus_dir=corpus)
        _run_all(tmp_path / "o")


class TestMLBPlaystyles:
    """Needs >=100 games/franchise; _MIN_GAMES=100 in atlas_playstyles."""
    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from domains.mlb.atlas_playstyles import build_playstyles
        corpus = tmp_path / "c"
        _write_mlb_parquet(corpus, n=210)
        assert build_playstyles(tmp_path / "o", corpus_dir=corpus)
        _run_all(tmp_path / "o")


class TestMLBStyleTrends:
    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from domains.mlb.atlas_style_trends import build_style_trends
        corpus = tmp_path / "c"
        _write_mlb_parquet(corpus, n=115)
        assert build_style_trends(tmp_path / "o", corpus_dir=corpus)
        _run_all(tmp_path / "o")


class TestMLBHomeEnvironment:
    """Needs >=100 home games/team; _MIN_HOME_GAMES=100 in atlas_home_environment."""
    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from domains.mlb.atlas_home_environment import build_home_environment
        corpus = tmp_path / "c"
        _write_mlb_parquet(corpus, n=210)
        assert build_home_environment(tmp_path / "o", corpus_dir=corpus)
        _run_all(tmp_path / "o")


# ---------------------------------------------------------------------------
# Scouting generators — vault-reading, graceful when source notes absent
# ---------------------------------------------------------------------------

class TestTennisScouting:
    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from domains.tennis.atlas_scouting import build_scouting
        vault = tmp_path / "vault" / "Sports" / "Tennis"
        vault.mkdir(parents=True)
        assert build_scouting(tmp_path / "o", vault_tennis_dir=vault)
        _run_all(tmp_path / "o")


class TestMLBScouting:
    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from domains.mlb.atlas_scouting import build_scouting
        vault = tmp_path / "vault" / "Sports" / "MLB"
        vault.mkdir(parents=True)
        assert build_scouting(tmp_path / "o", vault_mlb_dir=vault)
        _run_all(tmp_path / "o")


class TestSoccerScouting:
    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from domains.soccer.atlas_scouting import build_scouting
        vault = tmp_path / "vault" / "Sports" / "Soccer"
        vault.mkdir(parents=True)
        assert build_scouting(tmp_path / "o", vault_soccer_dir=vault)
        _run_all(tmp_path / "o")
