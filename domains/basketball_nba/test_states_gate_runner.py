"""Per-file tests for states_gate_runner.py (LANE 2: run_gate/write_gate
assembly + I/O + the NO_CORPUS honest path). PORTED from
domains/basketball_wnba/test_states_gate_runner.py.

Hermetic: synthetic games/linescores/states DataFrames + a monkeypatched
join map -- no real box-cache reads, no network.

See test_states_gate.py for the core-math unit tests (build_rows, fit_coef,
crossfit, descriptive_stats) this module's run_gate assembles.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_states_gate_runner.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from domains.basketball_nba.states_gate import CHECKPOINTS, FEATURES, REG_SEC
from domains.basketball_nba.states_gate_runner import run_gate, write_gate


def _synthetic_games(n: int = 40) -> pd.DataFrame:
    rows = []
    base = pd.Timestamp("2026-01-01")
    for i in range(n):
        home_win = 1.0 if i % 2 == 0 else 0.0
        rows.append({
            "game_id": f"00225{i:05d}", "date": base + pd.Timedelta(days=i),
            "season": 2025, "home_team": "Knicks", "away_team": "Celtics",
            "home_win": home_win,
        })
    return pd.DataFrame(rows)


def _synthetic_linescores(event_ids) -> pd.DataFrame:
    rows = []
    for i, eid in enumerate(event_ids):
        lead = 6.0 if i % 2 == 0 else -6.0
        rows.append({
            "event_id": str(eid),
            "home_q1": 20.0 + lead / 8, "away_q1": 20.0 - lead / 8,
            "home_q2": 20.0 + lead / 8, "away_q2": 20.0 - lead / 8,
            "home_q3": 20.0 + lead / 8, "away_q3": 20.0 - lead / 8,
            "home_q4": 20.0 + lead / 8, "away_q4": 20.0 - lead / 8,
        })
    return pd.DataFrame(rows)


def _synthetic_states(games_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, g in games_df.iterrows():
        run_sign = 1.0 if g["home_win"] >= 0.5 else -1.0
        for cp in CHECKPOINTS:
            rows.append({
                "game_id": str(g["game_id"]), "checkpoint": cp,
                "run_last_3min": run_sign * 4.0,
                "in_bonus_home": True, "in_bonus_away": False,
            })
    return pd.DataFrame(rows)


@pytest.fixture()
def synthetic_corpus():
    games = _synthetic_games()
    event_ids = [f"40180{i:05d}" for i in range(len(games))]
    lines = _synthetic_linescores(event_ids)
    states = _synthetic_states(games)
    join_map = {str(gid): str(eid) for gid, eid in zip(games["game_id"], event_ids)}
    return games, lines, states, join_map


def _patch_join(monkeypatch, join_map):
    monkeypatch.setattr(
        "domains.basketball_nba.states_gate_runner.build_join_map",
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
    assert result["reg_sec"] == REG_SEC
    assert set(result["crossfit_results"].keys()) == set(FEATURES)
    for feature in FEATURES:
        assert len(result["crossfit_results"][feature]) == len(CHECKPOINTS)
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
        "domains.basketball_nba.states_gate_runner.build_join_map",
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


# ---------------------------------------------------------------------------
# NO_CORPUS honest path (LANE 2 step 2): corpus absent -> honest report, not
# a raise, not a fabricated verdict.
# ---------------------------------------------------------------------------


def test_run_gate_no_corpus_when_states_parquet_absent(tmp_path):
    missing_path = tmp_path / "does_not_exist.parquet"
    result = run_gate(states_parquet_path=missing_path)
    assert result["overall_verdict"] == "NO_CORPUS"
    assert result["edge_claimed"] is False
    assert result["n_rows_total"] == 0
    assert set(result["crossfit_results"].keys()) == set(FEATURES)
    for feature in FEATURES:
        cells = result["crossfit_results"][feature]
        assert len(cells) == len(CHECKPOINTS)
        for cell in cells:
            assert cell["verdict"] == "NO_CORPUS"
            assert cell["verdict_v2"] == "NO_CORPUS"
    assert result["join"]["n_cdn_games"] == 0


def test_run_gate_no_corpus_is_writable_json(tmp_path):
    missing_path = tmp_path / "does_not_exist.parquet"
    result = run_gate(states_parquet_path=missing_path)
    out_path = tmp_path / "out.json"
    write_gate(result, out_path=out_path)
    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert loaded["overall_verdict"] == "NO_CORPUS"


def test_run_gate_uses_real_corpus_when_states_df_given_even_if_path_absent(tmp_path, synthetic_corpus, monkeypatch):
    """Passing states_df directly (as tests / a future lane-4 caller would)
    bypasses the on-disk existence check entirely -- the NO_CORPUS path only
    triggers when NEITHER states_df NOR the on-disk parquet is available."""
    games, lines, states, join_map = synthetic_corpus
    _patch_join(monkeypatch, join_map)
    missing_path = tmp_path / "does_not_exist.parquet"
    result = run_gate(games_df=games, linescores_df=lines, states_df=states,
                       states_parquet_path=missing_path)
    assert result["overall_verdict"] != "NO_CORPUS"
    assert result["n_rows_total"] > 0
