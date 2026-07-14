"""Tests for scripts.platformkit.omni.k_sweep_synergy (K synergy sweep).

Per-file run only:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_k_sweep_synergy.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_coverage as kc
from scripts.platformkit.omni import k_sweep_synergy as ksw


def _game_row(team, game_id, date, player_id, name, pts, minutes=30.0, season="2023-24"):
    return {"team": team, "game_id": game_id, "date": date, "season": season,
            "player_id": player_id, "player_name": name, "min": minutes, "pts": pts}


def _synthetic_frame() -> pd.DataFrame:
    """Team ATL, 40 games. Players 1 (star) & 2 (regular pair partner of 1) &
    3 (a low-minutes teammate never above the pair floor). Player 2 scores
    higher when player 1 (the star) sits, and player 3's pair count with 1
    stays below MIN_PAIR_GAMES on purpose."""
    rows = []
    dates = pd.date_range("2023-11-01", periods=40, freq="2D")
    for i, d in enumerate(dates):
        star_sits = i % 8 == 0  # star absent 5 times (>= MIN_ABSENCE_N)
        rows.append(_game_row("ATL", f"g{i}", d, 1, "Star", 25.0, 30.0 if not star_sits else 0.0))
        rows.append(_game_row("ATL", f"g{i}", d, 2, "Reg", 14.0 if star_sits else 10.0))
        if i < 10:  # player 3 only shares 10 games -> below MIN_PAIR_GAMES(30) with player 1
            rows.append(_game_row("ATL", f"g{i}", d, 3, "Rare", 8.0))
    return pd.DataFrame(rows)


def _active_players_stub():
    return pd.DataFrame({"player_id": [1, 2, 3], "player_name": ["Star", "Reg", "Rare"]})


@pytest.fixture(autouse=True)
def _stub_deps(monkeypatch, tmp_path):
    monkeypatch.setattr(kc, "load_active_players", lambda *a, **k: _active_players_stub())
    monkeypatch.setattr(ksw, "_archetype_map", lambda: {1: "Scoring Guard", 2: "Scoring Guard", 3: "Stretch Big"})
    kc.init_matrix(base_dir=tmp_path, players=_active_players_stub())
    return tmp_path


def test_with_without_split_math():
    played = _synthetic_frame()
    played = played[played["min"] > 0]
    res, with_b, a_games = ksw._with_without_split(played, 2, 1)
    # player 2 scores MORE when 1 (star) is absent -> delta positive (with - without)
    assert res is not None
    assert res["delta"] < 0  # "with" star present side should be lower-scoring than "without"


def test_pair_floor_enforcement_marks_insufficient(_stub_deps):
    tmp_path = _stub_deps
    df = _synthetic_frame()
    result = ksw.run_sweep(base_dir=tmp_path, source=df, top_n=200, discovery_only=False)
    claims = cl.query(sport="nba", base_dir=tmp_path)
    insufficient = claims[claims["effect_json"].str.contains("INSUFFICIENT_DATA")]
    assert len(insufficient) > 0
    assert result["insufficient_data_share"] > 0


def test_no_raw_all_pairs_explosion():
    """Candidate pairs come from ACTUAL roster co-occurrence, bounded by real
    roster size per game -- not the full N(N-1)/2 cross product over all
    players ever seen."""
    played = _synthetic_frame()
    played = played[played["min"] > 0]
    n_players = played["player_id"].nunique()
    full_cross_product = n_players * (n_players - 1) // 2
    counts = ksw._pair_counts(played)
    assert len(counts) <= full_cross_product
    # with only 3 players sharing a roster at all, real bound is tiny
    assert len(counts) <= 3


def test_idempotent_rerun_adds_zero_claims(_stub_deps):
    tmp_path = _stub_deps
    df = _synthetic_frame()
    first = ksw.run_sweep(base_dir=tmp_path, source=df, top_n=200, discovery_only=False)
    assert first["claims_added"] > 0
    journal_path = tmp_path / "journal.jsonl"
    lines_after_first = journal_path.read_text(encoding="ascii").count("\n")

    second = ksw.run_sweep(base_dir=tmp_path, source=df, top_n=200, discovery_only=False)
    assert second["claims_added"] == 0
    lines_after_second = journal_path.read_text(encoding="ascii").count("\n")
    assert lines_after_second == lines_after_first


def test_coverage_matrix_updated_for_synergy_dimension(_stub_deps):
    tmp_path = _stub_deps
    df = _synthetic_frame()
    ksw.run_sweep(base_dir=tmp_path, source=df, top_n=200, discovery_only=False)
    matrix = kc.load_matrix(base_dir=tmp_path)
    synergy = matrix[matrix["dimension"] == "synergy"]
    assert (synergy["status"] != "UNMINED").any()


def test_star_sits_row_retention_written(_stub_deps):
    tmp_path = _stub_deps
    df = _synthetic_frame()
    ksw.run_sweep(base_dir=tmp_path, source=df, top_n=200, discovery_only=False)
    preds_dir = tmp_path / "k_sweep_synergy_v1"
    assert (preds_dir / "star_sits.parquet").is_file()
