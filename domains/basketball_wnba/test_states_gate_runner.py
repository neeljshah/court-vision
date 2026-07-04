"""Per-file tests for states_gate_runner.py (LANE 5: run_gate/write_gate
assembly + I/O). Hermetic: synthetic games/linescores/states DataFrames + a
monkeypatched join map -- no real cdn_backfill/ boxscore reads, no network.

See test_states_gate.py for the core-math unit tests (build_rows, fit_coef,
crossfit, descriptive_stats) this module's run_gate assembles.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_states_gate_runner.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from domains.basketball_wnba.ingame_blend import ANCHORED_K, ANCHORED_W0
from domains.basketball_wnba.ingame_blend_families import build_corpus_with_p0
from domains.basketball_wnba.states_gate import CHECKPOINTS, FEATURES
from domains.basketball_wnba.states_gate_runner import run_gate, write_gate


def _synthetic_games(n: int = 40) -> pd.DataFrame:
    rows = []
    base = pd.Timestamp("2026-05-01")
    for i in range(n):
        home_win = 1.0 if i % 2 == 0 else 0.0
        hs, as_ = (85.0, 78.0) if home_win else (78.0, 85.0)
        rows.append({
            "event_id": str(1000 + i), "date": base + pd.Timedelta(days=i),
            "season": "2026", "home_team": "Aces", "away_team": "Fever",
            "home_score": hs, "away_score": as_, "home_win": home_win,
            "neutral_site": False, "status_name": "STATUS_FINAL",
        })
    return pd.DataFrame(rows)


def _synthetic_linescores(games_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, g in games_df.iterrows():
        lead = 6.0 if g["home_win"] >= 0.5 else -6.0
        rows.append({
            "event_id": str(g["event_id"]),
            "home_end_q1": 20.0 + lead / 4, "away_end_q1": 20.0 - lead / 4,
            "home_half": 40.0 + lead / 2, "away_half": 40.0 - lead / 2,
            "home_end_q3": 60.0 + lead * 0.75, "away_end_q3": 60.0 - lead * 0.75,
        })
    return pd.DataFrame(rows)


def _synthetic_states(games_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, g in games_df.iterrows():
        run_sign = 1.0 if g["home_win"] >= 0.5 else -1.0
        for cp in CHECKPOINTS:
            rows.append({
                "game_id": str(g["event_id"]), "checkpoint": cp,
                "run_last_3min": run_sign * 4.0,
                "in_bonus_home": True, "in_bonus_away": False,
            })
    return pd.DataFrame(rows)


@pytest.fixture()
def synthetic_corpus():
    games = _synthetic_games()
    lines = _synthetic_linescores(games)
    states = _synthetic_states(games)
    join_map = {str(e): str(e) for e in games["event_id"]}
    return games, lines, states, join_map


def _patch_join(monkeypatch, join_map):
    monkeypatch.setattr(
        "domains.basketball_wnba.states_gate_runner.build_join_map",
        lambda game_ids, linescores_df=None: {
            "game_id_to_event_id": join_map, "matched": len(join_map), "unmatched": []
        },
    )


def test_run_gate_end_to_end_shape(synthetic_corpus, monkeypatch):
    games, lines, states, join_map = synthetic_corpus
    _patch_join(monkeypatch, join_map)
    result = run_gate(games_df=games, linescores_df=lines, states_df=states)

    assert result["edge_claimed"] is False
    assert result["provenance"] == "cdn_backfill_validation"
    assert set(result["crossfit_results"].keys()) == set(FEATURES)
    for feature in FEATURES:
        assert len(result["crossfit_results"][feature]) == len(CHECKPOINTS)
    assert result["anchored_blend_frozen_params"] == {"ANCHORED_K": ANCHORED_K, "ANCHORED_W0": ANCHORED_W0}
    assert result["overall_verdict"] in (
        "AT_LEAST_ONE_FEATURE_SUPPORTED_V2",
        "NO_FEATURE_SUPPORTED_V2__HONEST_NULL",
    )
    assert "descriptive_stats" in result
    assert "supported_cells_v2" in result
    for feature_results in result["crossfit_results"].values():
        for cell in feature_results:
            assert "verdict_v2" in cell
            assert "delta_ci95_eval_h1" in cell
            assert "delta_ci95_eval_h0" in cell
    assert result["join"]["n_matched_to_linescores"] == len(join_map)


def test_run_gate_never_mutates_anchored_constants(synthetic_corpus, monkeypatch):
    """The anchored blend's frozen constants must be byte-identical before and
    after run_gate -- this gate is read-only w.r.t. the shipped blend."""
    import domains.basketball_wnba.ingame_blend as ib
    before_k, before_w0 = ib.ANCHORED_K, ib.ANCHORED_W0

    games, lines, states, join_map = synthetic_corpus
    _patch_join(monkeypatch, join_map)
    run_gate(games_df=games, linescores_df=lines, states_df=states)
    assert ib.ANCHORED_K == before_k
    assert ib.ANCHORED_W0 == before_w0


def test_write_gate_round_trips_json(tmp_path, synthetic_corpus, monkeypatch):
    games, lines, states, join_map = synthetic_corpus
    _patch_join(monkeypatch, join_map)
    result = run_gate(games_df=games, linescores_df=lines, states_df=states)

    out_path = tmp_path / "states_gate_validation.json"
    written = write_gate(result, out_path=out_path)
    assert written == out_path
    assert out_path.exists()
    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert loaded["overall_verdict"] == result["overall_verdict"]
    assert loaded["edge_claimed"] is False


def test_run_gate_join_guard_reports_unmatched(synthetic_corpus, monkeypatch):
    """A partial join map is honestly reflected in n_matched/n_unmatched, not
    silently padded to full corpus size."""
    games, lines, states, join_map = synthetic_corpus
    partial_map = {k: v for i, (k, v) in enumerate(join_map.items()) if i < 10}
    monkeypatch.setattr(
        "domains.basketball_wnba.states_gate_runner.build_join_map",
        lambda game_ids, linescores_df=None: {
            "game_id_to_event_id": partial_map,
            "matched": len(partial_map),
            "unmatched": [{"game_id": gid, "reason": "test_gap"}
                          for gid in join_map if gid not in partial_map],
        },
    )
    result = run_gate(games_df=games, linescores_df=lines, states_df=states)
    assert result["join"]["n_matched_to_linescores"] == 10
    assert result["join"]["n_unmatched"] == len(join_map) - 10
    assert result["join"]["unmatched_reasons"] == ["test_gap"]
