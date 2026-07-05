"""Tests for domains.basketball_nba.moves_corpus.

Two layers:
  1. Synthetic-fixture unit tests for the strict-move rule itself (no disk
     dependency, fast, exercises the 2TM/3TM exclusion + single-appearance
     rule directly).
  2. A REPRODUCTION test against the real on-disk bbref_advanced_extended
     .parquet that must match the pre-registration's own verified counts
     (488 / 510 / 350 / 96) EXACTLY -- this is the load-bearing check that
     the strict rule was not altered when porting it into this module. This
     test is skipped honestly if the source parquet is not present (e.g. a
     fresh clone without data/cache/ populated).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from domains.basketball_nba import moves_corpus


def _mini_frame() -> pd.DataFrame:
    """Two synthetic seasons: 5 players.
    - Alice: clean BOS->LAL (a strict move)
    - Bob: clean MIA->MIA (no move, stays)
    - Carol: 2TM in season 1 (mid-season trade stint) -- must be excluded
      from season-1 clean count even though she also appears once
    - Dave: clean in season 1 only, absent season 2 (no pair to evaluate)
    - Eve: clean season 2 only, absent season 1
    """
    rows = [
        {"player_name": "Alice", "team": "BOS", "season": "2020-21", "bpm": 1.0, "vorp": 0.5, "ts_pct": 0.55, "usg_pct": 20.0},
        {"player_name": "Alice", "team": "LAL", "season": "2021-22", "bpm": 3.0, "vorp": 1.5, "ts_pct": 0.60, "usg_pct": 22.0},
        {"player_name": "Bob", "team": "MIA", "season": "2020-21", "bpm": 0.0, "vorp": 0.2, "ts_pct": 0.50, "usg_pct": 18.0},
        {"player_name": "Bob", "team": "MIA", "season": "2021-22", "bpm": 0.5, "vorp": 0.3, "ts_pct": 0.51, "usg_pct": 18.5},
        {"player_name": "Carol", "team": "2TM", "season": "2020-21", "bpm": -1.0, "vorp": -0.1, "ts_pct": 0.48, "usg_pct": 15.0},
        {"player_name": "Carol", "team": "GSW", "season": "2020-21", "bpm": -0.9, "vorp": -0.05, "ts_pct": 0.49, "usg_pct": 15.2},
        {"player_name": "Carol", "team": "DEN", "season": "2021-22", "bpm": 0.2, "vorp": 0.1, "ts_pct": 0.52, "usg_pct": 16.0},
        {"player_name": "Dave", "team": "CHI", "season": "2020-21", "bpm": 2.0, "vorp": 1.0, "ts_pct": 0.58, "usg_pct": 21.0},
        {"player_name": "Eve", "team": "DAL", "season": "2021-22", "bpm": 1.5, "vorp": 0.7, "ts_pct": 0.56, "usg_pct": 19.0},
    ]
    return pd.DataFrame(rows)


def test_clean_single_team_season_excludes_multiteam_marker():
    df = _mini_frame()
    season1 = df[df["season"] == "2020-21"]
    clean = moves_corpus._clean_single_team_season(season1)
    names = set(clean["player_name"])
    # Carol has a 2TM row AND a real-code (GSW) row in season 1 -- two
    # appearances total, so she fails the single-appearance test even
    # restricted to real-code rows... but GSW alone would pass "real code"
    # if she appeared only once under GSW. She appears twice total in the
    # season (2TM + GSW), so counts()==2 excludes her correctly.
    assert "Carol" not in names
    assert names == {"Alice", "Bob", "Dave"}


def test_build_moves_corpus_finds_the_one_strict_move(tmp_path: Path, monkeypatch):
    df = _mini_frame()
    src_path = tmp_path / "bbref_advanced_extended.parquet"
    df.to_parquet(src_path, index=False)
    empty_backfill_dir = tmp_path / "no_backfill"

    monkeypatch.setattr(moves_corpus, "_EXISTING_SRC", src_path)
    monkeypatch.setattr(moves_corpus, "_BACKFILL_DIR", empty_backfill_dir)

    result = moves_corpus.build_moves_corpus()

    assert result.seasons_used == ["2020-21", "2021-22"]
    # season 1 clean: Alice/Bob/Dave (Carol excluded: 2TM marker that season)
    # season 2 clean: Alice/Bob/Eve/Carol (Carol is clean in season 2 -- her
    # single DEN row that season has no multi-team marker; Dave is absent)
    assert result.clean_counts_per_season == {"2020-21": 3, "2021-22": 4}
    # Carol has no clean season-1 row, so she can't form a pair despite being
    # clean in season 2 -- only Alice (BOS->LAL) is a strict move; Bob stays.
    assert result.moves_per_season_pair == {"2020-21_to_2021-22": 1}
    assert result.n_moves_total == 1

    move_row = result.moves_df.iloc[0]
    assert move_row["player_name"] == "Alice"
    assert move_row["team_pre"] == "BOS"
    assert move_row["team_post"] == "LAL"
    assert move_row["bpm_delta"] == pytest.approx(2.0)


def test_write_moves_corpus_lands_a_parquet(tmp_path: Path, monkeypatch):
    df = _mini_frame()
    src_path = tmp_path / "src.parquet"
    df.to_parquet(src_path, index=False)
    monkeypatch.setattr(moves_corpus, "_EXISTING_SRC", src_path)
    monkeypatch.setattr(moves_corpus, "_BACKFILL_DIR", tmp_path / "empty")

    result = moves_corpus.build_moves_corpus()
    out_path = moves_corpus.write_moves_corpus(result, tmp_path / "moves_corpus.parquet")

    assert out_path.exists()
    written = pd.read_parquet(out_path)
    assert len(written) == 1
    assert written.iloc[0]["player_name"] == "Alice"


def test_backfilled_season_widens_the_corpus_without_touching_existing(tmp_path: Path, monkeypatch):
    """A third season landing in the backfill dir should produce a SECOND
    season-pair and grow n_moves_total, while the original 2020-21_to_2021-22
    pair count is UNCHANGED -- proving new seasons only ADD coverage."""
    df = _mini_frame()
    src_path = tmp_path / "src.parquet"
    df.to_parquet(src_path, index=False)
    backfill_dir = tmp_path / "backfill"
    backfill_dir.mkdir()

    # season 3: Bob moves MIA->POR; Alice stays LAL->LAL
    season3 = pd.DataFrame([
        {"player_name": "Alice", "team": "LAL", "season": "2022-23", "bpm": 3.2, "vorp": 1.6, "ts_pct": 0.61, "usg_pct": 22.5},
        {"player_name": "Bob", "team": "POR", "season": "2022-23", "bpm": 0.8, "vorp": 0.4, "ts_pct": 0.52, "usg_pct": 19.0},
    ])
    season3.to_parquet(backfill_dir / "advanced_2022-23.parquet", index=False)

    monkeypatch.setattr(moves_corpus, "_EXISTING_SRC", src_path)
    monkeypatch.setattr(moves_corpus, "_BACKFILL_DIR", backfill_dir)

    result = moves_corpus.build_moves_corpus()

    assert result.seasons_used == ["2020-21", "2021-22", "2022-23"]
    # original pair's move count is unchanged by adding a third season
    assert result.moves_per_season_pair["2020-21_to_2021-22"] == 1
    assert result.moves_per_season_pair["2021-22_to_2022-23"] == 1  # Bob: MIA->POR
    assert result.n_moves_total == 2


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[2] / "data" / "cache" / "bbref_advanced_extended.parquet").exists(),
    reason="real on-disk bbref_advanced_extended.parquet not present (fresh clone / no data cache)",
)
def test_reproduces_prereg_verified_counts_on_real_2season_corpus():
    """Load-bearing: the strict rule ported into this module must reproduce
    the pre-registration's own verified_counts EXACTLY on the real 2-season
    on-disk corpus (fit_validity_gate_prereg.json's corpus.verified_counts:
    488 / 510 / 350 / 96), with no additional backfilled seasons present."""
    repo_root = Path(__file__).resolve().parents[2]
    df = pd.read_parquet(repo_root / "data" / "cache" / "bbref_advanced_extended.parquet")
    seasons = sorted(df["season"].unique())
    assert seasons == ["2024-25", "2025-26"]

    clean_2425 = moves_corpus._clean_single_team_season(df[df["season"] == "2024-25"])
    clean_2526 = moves_corpus._clean_single_team_season(df[df["season"] == "2025-26"])
    assert clean_2425["player_name"].nunique() == 488
    assert clean_2526["player_name"].nunique() == 510

    both = set(clean_2425["player_name"]) & set(clean_2526["player_name"])
    assert len(both) == 350

    pre = clean_2425.set_index("player_name")["team"]
    post = clean_2526.set_index("player_name")["team"]
    moves = [p for p in both if pre[p] != post[p]]
    assert len(moves) == 96


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
