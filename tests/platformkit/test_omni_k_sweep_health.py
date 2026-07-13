"""Tests for scripts.platformkit.omni.k_sweep_health (K health dimension sweep v1).

Per-file run only:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_k_sweep_health.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_coverage as kc
from scripts.platformkit.omni import k_sweep_health as ksh


def _injury_rows(pid, name, dates, statuses):
    return [
        {"player_id": pid, "player_name": name, "report_date": d, "status": s}
        for d, s in zip(dates, statuses)
    ]


def _synthetic_injury_frame() -> pd.DataFrame:
    """15 report_dates. Player 1: one 3-day QUESTIONABLE episode then cleared (n=1 episode,
    below MIN_EPISODES_N). Player 2: 3 separate short QUESTIONABLE->cleared episodes (meets
    the n>=3 floor). Player 3: one QUESTIONABLE->OUT episode (to_out outcome)."""
    dates = pd.date_range("2026-06-01", periods=15, freq="D")
    rows = []
    rows += _injury_rows(1, "Alpha", dates[0:3], ["QUESTIONABLE"] * 3)
    for start in (0, 5, 10):
        rows += _injury_rows(2, "Bravo", dates[start:start + 2], ["QUESTIONABLE"] * 2)
    rows += _injury_rows(3, "Charlie", dates[2:4], ["QUESTIONABLE", "OUT"])
    rows += _injury_rows(3, "Charlie", dates[14:15], ["OUT"])  # pushes global_max past player 2's episodes
    return pd.DataFrame(rows)


@pytest.fixture(autouse=True)
def _stub_deps(monkeypatch, tmp_path):
    monkeypatch.setattr(ksh, "_archetype_map", lambda: {1: "Scoring Guard", 2: "Scoring Guard", 3: "Stretch Big"})
    players = pd.DataFrame({"player_id": [1, 2, 3], "player_name": ["Alpha", "Bravo", "Charlie"]})
    kc.init_matrix(base_dir=tmp_path, players=players)
    return tmp_path


def test_wilson_ci_bounds():
    assert ksh._wilson_ci(0, 0) == (0.0, 0.0, 0.0)
    phat, lo, hi = ksh._wilson_ci(5, 10)
    assert phat == pytest.approx(0.5)
    assert 0.0 <= lo <= phat <= hi <= 1.0


def test_episode_derivation_transition_days_and_outcome():
    """Core math check: a synthetic 3-day QUESTIONABLE run followed by a gap must derive
    transition_days = 2 (last - first), outcome='cleared', and NOT be censored."""
    inj = _synthetic_injury_frame()
    episodes = ksh._build_episodes(inj)
    p1_eps = episodes[1]
    assert len(p1_eps) == 1
    ep = p1_eps[0]
    assert ep["transition_days"] == 2
    assert ep["outcome"] == "cleared"
    assert ep["censored"] is False

    # Player 3: QUESTIONABLE -> OUT in a 2-day run -> to_out, transition_days = 1.
    p3_ep = episodes[3][0]
    assert p3_ep["transition_days"] == 1
    assert p3_ep["outcome"] == "to_out"

    # Player 2 has 3 distinct episodes (gaps > EPISODE_GAP_DAYS between them).
    assert len(episodes[2]) == 3


def test_status_transition_uses_min_episodes_floor(tmp_path):
    inj = _synthetic_injury_frame()
    episodes = ksh._build_episodes(inj)
    arche_map = {1: "Scoring Guard", 2: "Scoring Guard", 3: "Stretch Big"}
    records = ksh._mine_status_transition(episodes, arche_map, tmp_path)
    player_cells = {r["key"]: r for r in records if r["level"] == "player"}
    # Player 1: only 1 resolved episode -> below MIN_EPISODES_N(3) -> INSUFFICIENT_DATA.
    assert player_cells[1].get("insufficient") is True
    # Player 2: 3 resolved episodes -> meets the floor, real median computed.
    assert player_cells[2].get("insufficient") is not True
    assert player_cells[2]["n"] == 3
    league_cells = [r for r in records if r["level"] == "league"]
    assert len(league_cells) == 1
    assert (tmp_path / "k_sweep_health_v1" / "status_transition.parquet").is_file()


def test_minutes_response_join_rate_computed_on_full_overlap(tmp_path):
    """Synthetic slice with a box game right after the clear date: join rate must hit 1.0
    (proves the join logic itself works before real-data honesty kicks in)."""
    episodes = {1: [{"first_date": pd.Timestamp("2026-06-01"), "first_status": "QUESTIONABLE",
                     "last_date": pd.Timestamp("2026-06-02"), "last_status": "QUESTIONABLE",
                     "transition_days": 1, "outcome": "cleared", "censored": False}]}
    box_df = pd.DataFrame({
        "player_id": [1, 1, 1], "date": pd.to_datetime(["2026-05-20", "2026-05-25", "2026-06-05"]),
        "is_home": [1.0, 0.0, 1.0], "pf": [1.0, 1.0, 1.0], "pts": [10.0, 12.0, 30.0], "min": [30.0, 32.0, 20.0],
    })
    # MIN_SIDE_N floor requires >=10 attempts; lower it for this focused unit test.
    orig_floor = ksh.MIN_SIDE_N
    ksh.MIN_SIDE_N = 1
    try:
        records = ksh._mine_minutes_response(episodes, box_df, tmp_path)
    finally:
        ksh.MIN_SIDE_N = orig_floor
    assert len(records) == 1
    assert records[0].get("insufficient") is not True
    assert records[0]["join_rate"] == 1.0


def test_minutes_response_insufficient_honest_shortfall(tmp_path):
    """Mirrors the real premise-checked gap: box data ends before the injury clear dates ->
    zero matches, honestly INSUFFICIENT_DATA with the date-range evidence documented."""
    episodes = {1: [{"first_date": pd.Timestamp("2026-06-01"), "first_status": "QUESTIONABLE",
                     "last_date": pd.Timestamp("2026-06-02"), "last_status": "QUESTIONABLE",
                     "transition_days": 1, "outcome": "cleared", "censored": False}]}
    box_df = pd.DataFrame({
        "player_id": [1], "date": pd.to_datetime(["2026-04-12"]),
        "is_home": [1.0], "pf": [1.0], "pts": [10.0], "min": [30.0],
    })
    records = ksh._mine_minutes_response(episodes, box_df, tmp_path)
    assert records[0]["insufficient"] is True
    assert records[0]["join_rate"] == 0.0
    assert records[0]["box_max_date"] == "2026-04-12 00:00:00"


def test_load_management_insufficient_below_b2b_floor(tmp_path):
    dates = pd.date_range("2026-01-01", periods=3, freq="D")
    box_df = pd.DataFrame({
        "player_id": [9, 9, 9], "date": dates, "is_home": [1.0, 0.0, 1.0],
        "pf": [1.0, 1.0, 1.0], "pts": [20.0, 18.0, 22.0], "min": [32.0, 31.0, 33.0],
    })
    records = ksh._mine_load_management(box_df, {9: "Stretch Big"}, tmp_path)
    player_cells = [r for r in records if r["level"] == "player" and r["key"] == 9]
    assert len(player_cells) == 1
    assert player_cells[0]["insufficient"] is True


def test_run_sweep_insufficient_data_path_ledgered(_stub_deps):
    tmp_path = _stub_deps
    inj = _synthetic_injury_frame()
    box_df = pd.DataFrame({
        "player_id": [1, 1], "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
        "is_home": [1.0, 0.0], "pf": [1.0, 1.0], "pts": [10.0, 12.0], "min": [30.0, 31.0],
    })
    result = ksh.run_sweep(base_dir=tmp_path, injury_source=inj, box_source=box_df)
    assert result["cells_mined"] > 0
    claims = cl.query(sport="nba", base_dir=tmp_path)
    insufficient = claims[claims["effect_json"].str.contains("INSUFFICIENT_DATA")]
    assert len(insufficient) > 0
    assert result["insufficient_data_share"] > 0


def test_idempotent_rerun_adds_zero_claims(_stub_deps):
    tmp_path = _stub_deps
    inj = _synthetic_injury_frame()
    box_df = pd.DataFrame({
        "player_id": [1, 1], "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
        "is_home": [1.0, 0.0], "pf": [1.0, 1.0], "pts": [10.0, 12.0], "min": [30.0, 31.0],
    })
    first = ksh.run_sweep(base_dir=tmp_path, injury_source=inj, box_source=box_df)
    assert first["claims_added"] > 0
    journal_path = tmp_path / "journal.jsonl"
    lines_after_first = journal_path.read_text(encoding="ascii").count("\n")

    second = ksh.run_sweep(base_dir=tmp_path, injury_source=inj, box_source=box_df)
    assert second["claims_added"] == 0
    assert journal_path.read_text(encoding="ascii").count("\n") == lines_after_first


def test_coverage_matrix_updated_for_health_dimension(_stub_deps):
    tmp_path = _stub_deps
    inj = _synthetic_injury_frame()
    box_df = pd.DataFrame({
        "player_id": [1, 1], "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
        "is_home": [1.0, 0.0], "pf": [1.0, 1.0], "pts": [10.0, 12.0], "min": [30.0, 31.0],
    })
    ksh.run_sweep(base_dir=tmp_path, injury_source=inj, box_source=box_df)
    matrix = kc.load_matrix(base_dir=tmp_path)
    health = matrix[matrix["dimension"] == "health"]
    assert (health["status"] != "UNMINED").any()
