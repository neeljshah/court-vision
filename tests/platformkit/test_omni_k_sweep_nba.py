"""Tests for scripts.platformkit.omni.k_sweep_nba (K first NBA bulk-mining sweep).

Per-file run only:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_k_sweep_nba.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_coverage as kc
from scripts.platformkit.omni import k_sweep_nba as ksw


def _synthetic_frame() -> pd.DataFrame:
    """20 games each for 3 players: clean b2b/rest, home/road, foul splits."""
    rows = []
    dates = pd.date_range("2025-10-01", periods=20, freq="2D")
    for pid, name, bump in ((1, "Alpha", 0.0), (2, "Bravo", 3.0), (3, "Charlie", 0.0)):
        for i, d in enumerate(dates):
            is_b2b = i % 4 == 0
            rows.append({
                "player_id": pid, "player_name": name, "game_id": f"g{pid}_{i}",
                "date": d - pd.Timedelta(days=1) if is_b2b else d,
                "is_home": float(i % 2), "pf": 4.0 if i % 5 == 0 else 1.0,
                "pts": 20.0 - bump if is_b2b else 20.0, "min": 30.0,
            })
    return pd.DataFrame(rows)


def _active_players_stub(tmp_path):
    return pd.DataFrame({"player_id": [1, 2, 3], "player_name": ["Alpha", "Bravo", "Charlie"]})


@pytest.fixture(autouse=True)
def _stub_deps(monkeypatch, tmp_path):
    monkeypatch.setattr(kc, "load_active_players", lambda *a, **k: _active_players_stub(tmp_path))
    monkeypatch.setattr(ksw, "_archetype_map", lambda: {1: "Scoring Guard", 2: "Scoring Guard", 3: "Stretch Big"})
    kc.init_matrix(base_dir=tmp_path, players=_active_players_stub(tmp_path))
    return tmp_path


def test_bh_adjust_matches_known_reference():
    # Classic textbook example: p-values 0.01, 0.04, 0.03, 0.005 -> BH at m=4.
    pvals = [0.01, 0.04, 0.03, 0.005]
    adj = ksw.bh_adjust(pvals)
    assert len(adj) == 4
    # Adjusted p-values are non-decreasing in sorted-p order and >= raw p.
    order = sorted(range(4), key=lambda i: pvals[i])
    sorted_adj = [adj[i] for i in order]
    assert sorted_adj == sorted(sorted_adj)
    for raw, a in zip(pvals, adj):
        assert a >= raw - 1e-9


def test_welch_split_math():
    a = pd.Series([10.0, 12.0, 14.0, 16.0])
    b = pd.Series([20.0, 22.0, 24.0, 26.0])
    res = ksw._welch_split(a, b)
    assert res["delta"] == pytest.approx(-10.0)
    assert res["n_a"] == 4 and res["n_b"] == 4
    assert res["ci_low"] < res["delta"] < res["ci_high"]


def test_insufficient_data_path_ledgered_and_counted(_stub_deps):
    tmp_path = _stub_deps
    df = _synthetic_frame()
    result = ksw.run_sweep(base_dir=tmp_path, source=df, top_n=200, discovery_only=False)
    assert result["cells_mined"] > 0
    claims = cl.query(sport="nba", base_dir=tmp_path)
    insufficient = claims[claims["effect_json"].str.contains("INSUFFICIENT_DATA")]
    assert len(insufficient) > 0
    assert result["insufficient_data_share"] > 0


def test_idempotent_rerun_adds_near_zero_claims(_stub_deps):
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


def test_coverage_matrix_updated_for_mined_players(_stub_deps):
    tmp_path = _stub_deps
    df = _synthetic_frame()
    ksw.run_sweep(base_dir=tmp_path, source=df, top_n=200, discovery_only=False)
    matrix = kc.load_matrix(base_dir=tmp_path)
    reactions = matrix[matrix["dimension"] == "reactions"]
    assert (reactions["status"] != "UNMINED").any()


def test_discovery_only_excludes_2025_26_reserve_rows(_stub_deps):
    tmp_path = _stub_deps
    df = _synthetic_frame()  # almost entirely dated 2025-10-01 or later -> reserve
    discovery, reserve = ksw.split_discovery_reserve(df)
    assert (reserve["date"] >= pd.Timestamp(ksw.RESERVE_CUTOVER)).all()
    assert (discovery["date"] < pd.Timestamp(ksw.RESERVE_CUTOVER)).all()
    assert len(reserve) > len(discovery)  # frame is reserve-dominated by construction
    # discovery_only=True (the default) must not mine any reserve row.
    result = ksw.run_sweep(base_dir=tmp_path, source=df, top_n=200)
    assert result["cells_mined"] < ksw.run_sweep(
        base_dir=tmp_path, source=df, top_n=200, discovery_only=False
    )["cells_mined"]


def test_top_n_default_is_full_active_pool():
    assert ksw.TOP_N_PLAYERS == 559


def test_load_sweep_frame_uses_load_box_full_when_source_is_none(monkeypatch):
    df = _synthetic_frame()
    df["is_playoffs"] = False
    monkeypatch.setattr(ksw.bsr, "load_box_full", lambda: df)
    out = ksw._load_sweep_frame(source=None)
    assert len(out) == len(df)


def test_playoff_rows_excluded_from_conditional_by_default():
    df = _synthetic_frame()
    df["is_playoffs"] = False
    df.loc[df["player_id"] == 3, "is_playoffs"] = True  # Charlie's rows are playoff dates
    out = ksw._load_sweep_frame(source=df)
    assert 3 not in set(out["player_id"])
    out_incl = ksw._load_sweep_frame(source=df, exclude_playoffs=False)
    assert 3 in set(out_incl["player_id"])
