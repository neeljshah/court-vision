"""Tests for scripts.platformkit.ingame.mlb_blend_fit -- the MLB margin-aware blend fit+gate.

Per-file run:
  C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
    tests/platformkit/ingame/test_mlb_blend_fit.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame.mlb_blend_fit import (
    _MIN_EVAL_GAMES,
    _attach_derived,
    _split_by_date,
    fit_and_gate,
    gate,
)
from scripts.platformkit.ingame.mlb_live_model import _W_BY_TIME

N_DATES = 30
N_GAMES_PER_DATE = 10


def _write_corpus(tmp_path) -> None:
    """Synthetic corpus: cell (t=2,m=4) and (t=2,m=0) are margin-responsive (outcome tracks
    run_diff perfectly); every other cell is UNTOUCHED (sparse -> must fall back to flat)."""
    gidx = 0
    for d in range(N_DATES):
        date = "2026-06-%02d" % (d + 1)
        for g in range(N_GAMES_PER_DATE):
            gidx += 1
            game_id = "SYN-%04d" % gidx
            home_leads = (g % 2 == 0)  # alternate so both m=4 and m=0 get populated
            y = 1.0 if home_leads else 0.0
            diff = 6.0 if home_leads else -6.0
            rows = [
                {"sport": "mlb", "game_id": game_id, "ts": date + "T00:00:00Z",
                 "model_prob": 0.5, "market_prob": 0.5, "side": "home",
                 "state_summary": "home_score=0.0 away_score=0.0 inning=1 half=top",
                 "outcome": y, "edge_claimed": False},
                {"sport": "mlb", "game_id": game_id, "ts": date + "T01:00:00Z",
                 "model_prob": 0.5, "market_prob": 0.5, "side": "home",
                 "state_summary": "home_score=%.1f away_score=0.0 inning=5 half=bottom"
                 % max(diff, 0.0) if diff >= 0 else
                 "home_score=0.0 away_score=%.1f inning=5 half=bottom" % abs(diff),
                 "outcome": y, "edge_claimed": False},
            ]
            with open(tmp_path / ("%s.jsonl" % game_id), "w") as fh:
                for r in rows:
                    fh.write(json.dumps(r) + "\n")


def test_margin_responsive_cells_fit_higher_than_flat(tmp_path):
    _write_corpus(tmp_path)
    result = fit_and_gate(tmp_path)
    grid = result["grid"]
    flat_t2 = _W_BY_TIME[2]
    assert grid["2,4"]["source"] == "fitted"
    assert grid["2,4"]["w"] > flat_t2
    assert grid["2,0"]["source"] == "fitted"
    assert grid["2,0"]["w"] > flat_t2


def test_sparse_cell_falls_back_to_flat(tmp_path):
    _write_corpus(tmp_path)
    result = fit_and_gate(tmp_path)
    grid = result["grid"]
    # (t=1,m=0) is never populated by the synthetic corpus (first ticks land at (0,2),
    # margin ticks land at (2,4)/(2,0)) -> must be the untouched flat fallback.
    cell = grid["1,0"]
    assert cell["source"] == "flat_fallback"
    assert cell["n"] == 0
    assert cell["w"] == _W_BY_TIME[1]


def test_gate_insufficient_on_tiny_eval_split():
    tiny_rows = [{"game_id": "g1", "t": 0, "m": 2, "p0": 0.5, "p_live": 0.5,
                  "outcome": 1.0, "run_diff": 0.0, "inning": 1}]
    fitted_grid = {"0,2": {"w": 0.5, "n": 1, "source": "flat_fallback"}}
    out = gate(tiny_rows, fitted_grid)
    assert out["verdict"] == "INSUFFICIENT"


def test_artifact_schema_and_edge_claimed_false(tmp_path):
    _write_corpus(tmp_path)
    result = fit_and_gate(tmp_path)
    for key in ("as_of", "p0_source", "fit_dates", "eval_dates", "n_time", "n_margin",
                "grid", "flat_baseline", "gate", "honest_note", "edge_claimed"):
        assert key in result
    assert result["edge_claimed"] is False
    assert result["p0_source"] == "first_tick_model_prob_proxy"
    assert result["gate"]["verdict"] in ("PASS", "FAIL", "INSUFFICIENT")


def test_walk_forward_split_is_leak_free_by_date(tmp_path):
    _write_corpus(tmp_path)
    from scripts.platformkit.ingame.mlb_blend_fit import _load_rows
    rows = _attach_derived(_load_rows(tmp_path))
    fit_rows, eval_rows = _split_by_date(rows)
    fit_dates = {r["date"] for r in fit_rows}
    eval_dates = {r["date"] for r in eval_rows}
    assert fit_dates.isdisjoint(eval_dates)
    assert max(fit_dates) < min(eval_dates)
    assert len({r["game_id"] for r in eval_rows}) >= _MIN_EVAL_GAMES


def test_strong_margin_signal_passes_the_gate(tmp_path):
    _write_corpus(tmp_path)
    result = fit_and_gate(tmp_path)
    assert result["gate"]["verdict"] == "PASS"
