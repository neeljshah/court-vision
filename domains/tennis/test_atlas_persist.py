"""Tests for domains.tennis.atlas_persist -- row-count + schema parity vs the
in-memory atlas builders (extraction-lane pattern: no gate, no tuning).
"""
from __future__ import annotations

import pathlib
import tempfile

import pandas as pd
import pytest

from domains.tennis.atlas_persist import persist_playstyles, persist_h2h
from domains.tennis.atlas_playstyles import _compute_stats
from domains.tennis.atlas_h2h import _compute_pair_stats


def _fixture_matches(n_per_player: int = 16) -> pd.DataFrame:
    """20 matches: player 1 vs player 2 repeated (2 players, enough matches
    each to clear MIN_MATCHES=15 in atlas_playstyle_specs)."""
    rows = []
    surfaces = ["Hard", "Clay", "Grass"]
    for i in range(n_per_player):
        winner = 1 if i % 2 == 0 else 2
        rows.append({
            "event_id": f"e{i}",
            "date": f"2024-{(i % 12) + 1:02d}-01",
            "tour": "atp",
            "tourney_id": "T1",
            "tourney_name": "Test Open",
            "tourney_level": "A",
            "surface": surfaces[i % 3],
            "best_of": 3,
            "round": "R32",
            "match_num": i,
            "p1_id": 1001,
            "p2_id": 1002,
            "p1_name": "Player One",
            "p2_name": "Player Two",
            "p1_rank": 10.0,
            "p2_rank": 20.0,
            "winner": winner,
            "score": "6-4 6-4",
            "retirement": False,
            "minutes": 90.0,
        })
    return pd.DataFrame(rows)


def _fixture_players() -> pd.DataFrame:
    return pd.DataFrame([
        {"player_id": 1001, "full_name": "Player One", "hand": "R", "height": 188.0},
        {"player_id": 1002, "full_name": "Player Two", "hand": "L", "height": 180.0},
    ])


def test_persist_playstyles_row_count_and_schema(tmp_path, monkeypatch):
    matches = _fixture_matches()
    players = _fixture_players()

    fixture_dir = tmp_path / "corpus"
    fixture_dir.mkdir()
    matches.to_parquet(fixture_dir / "matches.parquet", index=False)
    players.to_parquet(fixture_dir / "players.parquet", index=False)

    out_path = tmp_path / "atlas_playstyles.parquet"
    result = persist_playstyles(out_path, corpus_dir=fixture_dir, as_of="2026-07-04")

    # Ground truth: call the SAME in-memory compute helper directly.
    expected_stats = _compute_stats(matches, players)

    assert result.row_count == len(expected_stats)
    assert out_path.exists()

    persisted = pd.read_parquet(out_path)
    assert len(persisted) == len(expected_stats)
    # Provenance columns present.
    for col in ("as_of", "corpus_id", "corpus_season_min", "corpus_season_max"):
        assert col in persisted.columns
    assert (persisted["as_of"] == "2026-07-04").all()
    assert (persisted["corpus_id"] == "sackmann_atp_matches_parquet").all()
    # Underlying stat columns preserved (not dropped by persistence).
    for col in expected_stats.columns:
        assert col in persisted.columns
    # player_id set matches exactly.
    assert set(persisted["player_id"]) == set(expected_stats["player_id"])


def test_persist_h2h_row_count_and_pair_keys(tmp_path):
    matches = _fixture_matches()

    fixture_dir = tmp_path / "corpus"
    fixture_dir.mkdir()
    matches.to_parquet(fixture_dir / "matches.parquet", index=False)

    out_path = tmp_path / "atlas_h2h.parquet"
    result = persist_h2h(out_path, corpus_dir=fixture_dir, as_of="2026-07-04")

    df = matches.copy()
    df["date"] = df["date"].astype(str)
    expected_pair_df = _compute_pair_stats(df)

    assert result.row_count == len(expected_pair_df) == len(matches)
    persisted = pd.read_parquet(out_path)
    assert len(persisted) == len(matches)

    # Pair-keyed id columns explicitly preserved.
    assert "p1_id" in persisted.columns
    assert "p2_id" in persisted.columns
    assert set(persisted["p1_id"].unique()) == {1001}
    assert set(persisted["p2_id"].unique()) == {1002}

    # Provenance columns present.
    for col in ("as_of", "corpus_id", "season"):
        assert col in persisted.columns
    assert (persisted["as_of"] == "2026-07-04").all()
    assert (persisted["corpus_id"] == "sackmann_atp_matches_parquet").all()
    assert persisted["season"].notna().all()


def test_persist_h2h_row_mismatch_raises(tmp_path, monkeypatch):
    """If the compute helper's row count ever diverges from the input matches
    (e.g. a future filtering change), the positional id-join guard must raise
    rather than silently mis-key p1_id/p2_id."""
    import domains.tennis.atlas_persist as ap
    from domains.tennis.atlas_h2h import _compute_pair_stats as _real_compute_pair_stats

    matches = _fixture_matches()
    fixture_dir = tmp_path / "corpus"
    fixture_dir.mkdir()
    matches.to_parquet(fixture_dir / "matches.parquet", index=False)

    def _bad_compute_pair_stats(df):
        return _real_compute_pair_stats(df).iloc[:-1]  # drop one row to simulate a mismatch

    monkeypatch.setattr(ap, "_compute_pair_stats", _bad_compute_pair_stats)

    with pytest.raises(ValueError, match="row count"):
        ap.persist_h2h(tmp_path / "atlas_h2h_bad.parquet", corpus_dir=fixture_dir)
