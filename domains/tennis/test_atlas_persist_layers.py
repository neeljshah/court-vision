"""Tests for domains.tennis.atlas_persist_layers + atlas_persist_manifest
(lane tennis-persist, program v3): scouting/surface_splits persistence +
the four-layer manifest builder.
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.tennis.atlas_persist_layers import (
    MIN_SURFACE_SPLIT_MATCHES,
    persist_scouting,
    persist_surface_splits,
)
from domains.tennis.atlas_persist_manifest import build_and_persist, write_manifest


def _fixture_matches(n_per_surface: int = 12) -> pd.DataFrame:
    """3 surfaces x n_per_surface matches each, same 2-player pair, so both
    players clear MIN_SURFACE_SPLIT_MATCHES=10 on every surface."""
    rows = []
    surfaces = ["Hard", "Clay", "Grass"]
    i = 0
    for surf in surfaces:
        for _ in range(n_per_surface):
            winner = 1 if i % 2 == 0 else 2
            rows.append({
                "event_id": f"e{i}", "date": f"2024-{(i % 12) + 1:02d}-01",
                "surface": surf, "best_of": 3, "p1_id": 1001, "p2_id": 1002,
                "p1_name": "Player One", "p2_name": "Player Two", "winner": winner,
            })
            i += 1
    return pd.DataFrame(rows)


def _fixture_match_stats(matches: pd.DataFrame) -> pd.DataFrame:
    n = len(matches)
    return pd.DataFrame({
        "event_id": matches["event_id"].values,
        "p1_ace_rate": [0.10] * n,
        "p1_1st_in_pct": [0.60] * n,
        "p1_df_rate": [0.05] * n,
        "p2_ace_rate": [0.08] * n,
        "p2_1st_in_pct": [0.65] * n,
        "p2_df_rate": [0.04] * n,
    })


def test_persist_surface_splits_schema_and_floor(tmp_path):
    matches = _fixture_matches()
    match_stats = _fixture_match_stats(matches)

    fixture_dir = tmp_path / "corpus"
    fixture_dir.mkdir()
    matches.to_parquet(fixture_dir / "matches.parquet", index=False)
    match_stats.to_parquet(fixture_dir / "match_stats.parquet", index=False)

    out_path = tmp_path / "surface_splits.parquet"
    result = persist_surface_splits(out_path, corpus_dir=fixture_dir, as_of="2026-07-05")

    assert out_path.exists()
    df = pd.read_parquet(out_path)
    # 2 players x 3 surfaces = 6 rows (each cell clears the floor: 12 >= 10).
    assert len(df) == 6
    assert result.row_count == 6
    for col in ("player_id", "surface", "n_matches", "ace_rate",
                "first_serve_in_pct", "double_fault_rate", "as_of", "corpus_id"):
        assert col in df.columns
    assert (df["n_matches"] >= MIN_SURFACE_SPLIT_MATCHES).all()
    assert (df["as_of"] == "2026-07-05").all()
    # Player 1001's ace_rate on every surface is the fixture constant 0.10.
    p1001 = df[df["player_id"] == 1001]
    assert (p1001["ace_rate"] == 0.10).all()


def test_persist_surface_splits_below_floor_dropped(tmp_path):
    """A surface cell with fewer than MIN_SURFACE_SPLIT_MATCHES matches must
    NOT appear as a row (dropped, not fabricated with a tiny n)."""
    matches = _fixture_matches(n_per_surface=3)  # below floor=10 on every surface
    match_stats = _fixture_match_stats(matches)

    fixture_dir = tmp_path / "corpus"
    fixture_dir.mkdir()
    matches.to_parquet(fixture_dir / "matches.parquet", index=False)
    match_stats.to_parquet(fixture_dir / "match_stats.parquet", index=False)

    out_path = tmp_path / "surface_splits.parquet"
    persist_surface_splits(out_path, corpus_dir=fixture_dir)
    df = pd.read_parquet(out_path)
    assert len(df) == 0


def test_persist_surface_splits_built_at_is_corpus_max_date_not_wall_clock(tmp_path):
    """as_of=None must fall back to the CORPUS's own max match date, never
    today's wall-clock date."""
    matches = _fixture_matches()
    match_stats = _fixture_match_stats(matches)

    fixture_dir = tmp_path / "corpus"
    fixture_dir.mkdir()
    matches.to_parquet(fixture_dir / "matches.parquet", index=False)
    match_stats.to_parquet(fixture_dir / "match_stats.parquet", index=False)

    out_path = tmp_path / "surface_splits.parquet"
    persist_surface_splits(out_path, corpus_dir=fixture_dir)  # as_of omitted
    df = pd.read_parquet(out_path)
    assert (df["as_of"] == matches["date"].max()).all()


def test_persist_scouting_empty_when_vault_dir_missing(tmp_path):
    """No Style_Matchups dir on disk -> a graceful zero-row layer, never a
    crash (matches the honest-empty-layer contract in the module docstring)."""
    empty_vault = tmp_path / "no_such_vault"
    out_path = tmp_path / "scouting.parquet"
    result = persist_scouting(out_path, vault_tennis_dir=empty_vault, as_of="2026-07-05")
    assert result.row_count == 0
    assert out_path.exists()
    df = pd.read_parquet(out_path)
    assert (df["as_of"] == "2026-07-05").all() if len(df) else True


def test_persist_scouting_parses_real_matchup_note_shape(tmp_path):
    """A Style_Matchups note in the SAME shape atlas_scouting._parse_matchup_note
    expects must produce exactly one row with the parsed fields preserved."""
    vault_dir = tmp_path / "vault"
    matchups_dir = vault_dir / "Style_Matchups"
    matchups_dir.mkdir(parents=True)
    note_text = (
        "---\n"
        "archetype_a: Clay_Court_Specialist\n"
        "archetype_b: Fast_Court_Big_Server\n"
        "total_meetings: 42\n"
        "win_rate_a: 0.55\n"
        "win_rate_b: 0.45\n"
        "---\n"
        "**Clay:** win-rate of A = 60.0%\n"
    )
    (matchups_dir / "Clay_vs_BigServer.md").write_text(note_text, encoding="utf-8")

    out_path = tmp_path / "scouting.parquet"
    result = persist_scouting(out_path, vault_tennis_dir=vault_dir, as_of="2026-07-05")
    assert result.row_count == 1
    df = pd.read_parquet(out_path)
    assert df.iloc[0]["archetype_a"] == "Clay_Court_Specialist"
    assert df.iloc[0]["archetype_b"] == "Fast_Court_Big_Server"
    assert df.iloc[0]["pair_file"] == "Clay_vs_BigServer.md"


def test_build_and_persist_reports_all_four_layers_with_no_crash(tmp_path):
    """The manifest composer must enumerate all four layers even when the
    scouting source (vault/) is absent -- honest rows=0/error=None, not a
    crash and not a silently dropped layer."""
    matches = _fixture_matches()
    match_stats = _fixture_match_stats(matches)

    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    matches.to_parquet(corpus_dir / "matches.parquet", index=False)
    match_stats.to_parquet(corpus_dir / "match_stats.parquet", index=False)
    # players.parquet required by persist_playstyles' _load_corpus fallback path.
    pd.DataFrame(columns=["player_id", "full_name", "hand", "height"]).to_parquet(
        corpus_dir / "players.parquet", index=False
    )

    cache_dir = tmp_path / "cache"
    empty_vault = tmp_path / "no_such_vault"
    manifest = build_and_persist(cache_dir=cache_dir, corpus_dir=corpus_dir, vault_tennis_dir=empty_vault)

    layer_names = {layer["layer"] for layer in manifest["layers"]}
    assert layer_names == {"playstyles", "h2h", "scouting", "surface_splits"}
    for layer in manifest["layers"]:
        assert layer["error"] is None, layer
    assert manifest["built_at"] == matches["date"].max()


def test_write_manifest_writes_json_with_built_at_from_corpus(tmp_path):
    matches = _fixture_matches()
    match_stats = _fixture_match_stats(matches)

    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    matches.to_parquet(corpus_dir / "matches.parquet", index=False)
    match_stats.to_parquet(corpus_dir / "match_stats.parquet", index=False)
    pd.DataFrame(columns=["player_id", "full_name", "hand", "height"]).to_parquet(
        corpus_dir / "players.parquet", index=False
    )

    cache_dir = tmp_path / "cache"
    empty_vault = tmp_path / "no_such_vault"
    manifest = write_manifest(cache_dir=cache_dir, corpus_dir=corpus_dir, vault_tennis_dir=empty_vault)

    manifest_path = cache_dir / "manifest.json"
    assert manifest_path.exists()
    import json
    on_disk = json.loads(manifest_path.read_text(encoding="ascii"))
    assert on_disk["built_at"] == matches["date"].max()
    assert len(on_disk["layers"]) == 4
    # tmp_path lives outside the real repo tree, so source falls back to an
    # absolute path (relative_to raises ValueError) -- every layer still gets
    # a non-null source string, never a missing/omitted field.
    for layer in on_disk["layers"]:
        assert layer["source"] is not None
