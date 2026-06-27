"""Per-file tests for domains.mlb.pregame_gate_eval -- honesty / anti-artifact checks.

Verifies:
  1. _A1_MOV_SCALE is a pre-registered constant (not selected by test-set Brier).
  2. The run() function no longer sweeps a grid and cherry-picks; it uses a fixed scale.
  3. mov_scale=0 (baseline sanity) produces identical output to the standard Elo baseline
     (bit-exact zero-delta guard).
  4. The return dict key is 'A1_mov_scale', NOT 'A1_best_scale' (old cherry-pick key removed).
  5. _build_a1 with mov_scale == _A1_MOV_SCALE runs without error on synthetic data and
     produces a calibration frame with the expected columns.

These tests do NOT require the real parquet corpora -- they use synthetic DataFrames so the
test always passes without disk access.

Run:
    /c/Users/neelj/anaconda3/envs/basketball_ai/python.exe \
        -m pytest tests/platformkit/test_mlb_pregame_gate_eval_honesty.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domains.mlb.pregame_gate_eval import _A1_MOV_SCALE, _build_a1


# ---------------------------------------------------------------------------
# Synthetic data builder
# ---------------------------------------------------------------------------

def _synthetic_games(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """Minimal MLB games DataFrame sufficient for _build_a1 and walk_forward_elo_mov.

    walk_forward_elo_mov requires: event_id, date, home_team, away_team, season,
    home_runs, away_runs, target_home_win, run_diff.
    """
    rng = np.random.default_rng(seed)
    teams = [f"T{i:02d}" for i in range(10)]
    dates = pd.date_range("2015-04-01", periods=n, freq="D")
    home = rng.choice(teams, size=n)
    away = np.array([rng.choice([t for t in teams if t != h]) for h in home])
    home_runs = rng.integers(0, 10, size=n).astype(float)
    away_runs = rng.integers(0, 10, size=n).astype(float)
    # Avoid ties: add 1 to home_runs whenever they're equal
    ties = home_runs == away_runs
    home_runs[ties] += 1
    run_diff = home_runs - away_runs
    target = (run_diff > 0).astype(int)
    return pd.DataFrame({
        "event_id": [f"evt_{i}" for i in range(n)],
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "home_team": home,
        "away_team": away,
        "home_runs": home_runs,
        "away_runs": away_runs,
        "run_diff": run_diff,
        "target_home_win": target,
        "season": [2015] * n,
    })


# ---------------------------------------------------------------------------
# 1. Pre-registered scale is a scalar in (0, 5]
# ---------------------------------------------------------------------------

def test_a1_mov_scale_is_preregistered_scalar():
    """_A1_MOV_SCALE must be a plain numeric constant, not computed at import time."""
    assert isinstance(_A1_MOV_SCALE, float), \
        f"_A1_MOV_SCALE must be float, got {type(_A1_MOV_SCALE)}"
    assert 0 < _A1_MOV_SCALE <= 5.0, \
        f"_A1_MOV_SCALE={_A1_MOV_SCALE} outside sane range (0, 5]"


def test_a1_mov_scale_is_not_2():
    """scale=2.0 was the cherry-picked test-set winner; the pre-registered value
    must be different to avoid re-encoding the artifact as a constant."""
    assert _A1_MOV_SCALE != 2.0, (
        "mov_scale must NOT be 2.0 -- that was the cherry-picked test-set winner. "
        "Use a principled value (e.g. 1.0) with documented justification."
    )


# ---------------------------------------------------------------------------
# 2. Return dict uses 'A1_mov_scale', not 'A1_best_scale'
# ---------------------------------------------------------------------------

def test_run_return_key_is_mov_scale_not_best_scale(monkeypatch):
    """run() must return 'A1_mov_scale' (pre-registered) not 'A1_best_scale' (cherry-pick)."""
    import domains.mlb.pregame_gate_eval as mod

    df = _synthetic_games()

    # Monkeypatch _load to avoid real parquet files
    monkeypatch.setattr(mod, "_load", lambda path: df)

    result = mod.run()
    assert "A1_mov_scale" in result, \
        "run() must return key 'A1_mov_scale' (pre-registered, not cherry-picked)"
    assert "A1_best_scale" not in result, \
        "run() must NOT return 'A1_best_scale' -- that key encodes the cherry-pick artifact"


# ---------------------------------------------------------------------------
# 3. _build_a1 produces expected columns (calibration frame structure)
# ---------------------------------------------------------------------------

def test_build_a1_output_columns():
    """_build_a1 must return a DataFrame with event_id, target_home_win, p_base, p_cand."""
    df = _synthetic_games(100)
    out = _build_a1(df, _A1_MOV_SCALE)
    required = {"event_id", "target_home_win", "p_base", "p_cand"}
    assert required.issubset(set(out.columns)), \
        f"Missing columns: {required - set(out.columns)}"
    assert len(out) == len(df)


def test_build_a1_probs_in_unit_interval():
    """Both p_base and p_cand must be strictly in (0, 1)."""
    df = _synthetic_games(100)
    out = _build_a1(df, _A1_MOV_SCALE)
    assert (out["p_base"] > 0).all() and (out["p_base"] < 1).all(), \
        "p_base must be in (0, 1)"
    assert (out["p_cand"] > 0).all() and (out["p_cand"] < 1).all(), \
        "p_cand must be in (0, 1)"


# ---------------------------------------------------------------------------
# 4. Baseline sanity: mov_scale=0 -> p_base == p_cand (zero delta, bit-exact)
# ---------------------------------------------------------------------------

def test_build_a1_mov_scale_zero_is_bit_exact_baseline():
    """_build_a1(df, 0.0) must produce p_base == p_cand exactly.

    mov_scale=0 means the candidate update is identical to the baseline update,
    so every row should be bit-exact.  This guards the sanity that the two
    walk-forward runs with the same scale produce the same sequence.
    """
    df = _synthetic_games(150)
    out = _build_a1(df, mov_scale=0.0)
    diff = (out["p_base"] - out["p_cand"]).abs().max()
    assert diff == pytest.approx(0.0, abs=1e-12), \
        f"mov_scale=0 baseline: p_base and p_cand must be bit-exact, max_diff={diff}"


# ---------------------------------------------------------------------------
# 5. run() does NOT iterate over a grid of scales
# ---------------------------------------------------------------------------

def test_run_calls_build_a1_exactly_once(monkeypatch):
    """run() must call _build_a1 exactly once per corpus (2 total), not 4x2=8 times
    (old grid sweep was 4 scales x 2 corpora = 8 calls)."""
    import domains.mlb.pregame_gate_eval as mod

    df = _synthetic_games()
    monkeypatch.setattr(mod, "_load", lambda path: df)

    call_count = []
    original_build_a1 = mod._build_a1

    def counting_build_a1(df_, ms):
        call_count.append(ms)
        return original_build_a1(df_, ms)

    monkeypatch.setattr(mod, "_build_a1", counting_build_a1)
    mod.run()

    assert len(call_count) == 2, (
        f"run() must call _build_a1 exactly 2 times (once per corpus), "
        f"got {len(call_count)} calls with scales {call_count}"
    )
    # All calls must use the pre-registered scale
    for s in call_count:
        assert s == _A1_MOV_SCALE, (
            f"_build_a1 called with scale={s}, expected pre-registered _A1_MOV_SCALE={_A1_MOV_SCALE}"
        )
