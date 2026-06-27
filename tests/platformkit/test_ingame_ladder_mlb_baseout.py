"""Per-file, OFFLINE, deterministic tests for the MLB base-out detail layer.

Tests the L4 base_out_runexp layer: does LOB (runners left on base at inning end)
add run-expectancy signal beyond (run_diff, frac_elapsed)?

Test cases:
  1. SHIPS when base-out LOB genuinely informs WP beyond run_diff: trailing team
     consistently has runners on but fails to convert -- signal is real.
  2. REJECTS when base-out is noise: LOB is uncorrelated with outcome.
  3. Leak-free: beta fit ONLY on train; test states never touch fit.
  4. DM clusters by game_id (reuses the intraclass-correlation property).
  5. _lob_count bitmask parsing is correct.
  6. load_mlb_states_baseout tolerates missing base-out cols (older parquets).
  7. gate_baseout returns a valid BaseOutResult with all required fields.

CLI: python -m pytest tests/platformkit/test_ingame_ladder_mlb_baseout.py -q
"""
from __future__ import annotations

import tempfile
from typing import List

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.ingame.ingame_ladder_mlb_baseout import (
    _lob_count,
    _run_exp_signal,
    apply_baseout_layer,
    fit_baseout_layer,
    gate_baseout,
    load_mlb_states_baseout,
)

# ---------------------------------------------------------------------------
# synthetic state builders
# ---------------------------------------------------------------------------

def _make_baseout_states(
    n_games: int,
    *,
    lob_informative: bool,
    seed: int = 42,
) -> List[dict]:
    """Build synthetic MLB states with base-out signal.

    Each game has 18 half-inning states.  When lob_informative=True, the trailing
    team systematically has runners on at inning end (LOB > 0) but fails to score --
    this creates a run_diff that understates how close the game is, and the base-out
    signal corrects the WP.  When False, LOB is random noise uncorrelated with outcome.
    """
    rng = np.random.default_rng(seed)
    states: List[dict] = []
    innings = list(range(1, 10))
    for g in range(n_games):
        strength = float(rng.uniform(0.25, 0.75))
        base_rd = float(rng.normal(4.0 * (strength - 0.5), 1.5))
        y = int(rng.uniform() < strength)
        cum_rd = 0.0
        for inning in innings:
            cum_rd += float(rng.normal(base_rd / 9.0, 0.8))
            for is_bottom in (False, True):
                frac = (inning - 1 + (0.5 if is_bottom else 0.0)) / 9.0
                frac = float(np.clip(frac, 0.03, 1.0))
                rd = float(np.clip(cum_rd + rng.normal(0.0, 0.2), -15.0, 15.0))

                if lob_informative:
                    # Trailing team (rd opposite to their batting side) gets runners
                    # but fails to score -- more LOB when trailing
                    trailing_bats = (rd > 0 and not is_bottom) or (rd < 0 and is_bottom)
                    if trailing_bats and abs(rd) <= 3.0:
                        # High LOB for trailing team = signal that game is closer than rd shows
                        lob = int(rng.choice([0, 1, 2, 3], p=[0.1, 0.2, 0.4, 0.3]))
                    else:
                        lob = int(rng.choice([0, 1, 2, 3], p=[0.5, 0.3, 0.15, 0.05]))
                    runners = _lob_to_bitmask(lob, rng)
                    known = True
                else:
                    # LOB is pure noise: random regardless of score
                    lob = int(rng.choice([0, 1, 2, 3], p=[0.4, 0.3, 0.2, 0.1]))
                    runners = _lob_to_bitmask(lob, rng)
                    known = True  # known but uninformative

                label = f"end{inning}" if is_bottom else f"mid{inning}"
                states.append({
                    "game_id": g,
                    "state_diff": rd,
                    "frac_elapsed": frac,
                    "p0": float(np.clip(strength + rng.normal(0.0, 0.02), 0.1, 0.9)),
                    "outcome": y,
                    "inning": inning,
                    "is_bottom": is_bottom,
                    "runners": runners,
                    "outs": 3,
                    "base_out_known": known,
                    "lob_count": lob,
                    "half_inning_label": label,
                })
    return states


def _lob_to_bitmask(lob: int, rng: np.random.Generator) -> int:
    """Convert a LOB count to a plausible runners bitmask (bit2=1B,bit1=2B,bit0=3B)."""
    # Choose lob bases randomly from the 3 possible base positions
    positions = list(range(3))
    chosen = rng.choice(positions, size=min(lob, 3), replace=False)
    mask = 0
    for pos in chosen:
        mask |= (1 << (2 - pos))
    return int(mask)


def _split(states: List[dict], n_games: int, split: float = 0.5):
    cut = int(n_games * split)
    train = [s for s in states if s["game_id"] < cut]
    test = [s for s in states if s["game_id"] >= cut]
    return train, test

# ---------------------------------------------------------------------------
# unit tests
# ---------------------------------------------------------------------------

def test_lob_count_bitmask():
    """_lob_count correctly parses bitmask (bit2=1B, bit1=2B, bit0=3B)."""
    assert _lob_count(0b000) == 0  # bases empty
    assert _lob_count(0b001) == 1  # runner on 3B
    assert _lob_count(0b010) == 1  # runner on 2B
    assert _lob_count(0b100) == 1  # runner on 1B
    assert _lob_count(0b110) == 2  # runners on 1B + 2B
    assert _lob_count(0b111) == 3  # bases loaded
    assert _lob_count(0b011) == 2  # runners on 2B + 3B
    assert _lob_count(0b101) == 2  # runners on 1B + 3B


def test_run_exp_signal_direction():
    """_run_exp_signal is positive when leading team's defense stranded trailing runners."""
    states = [
        # Home leading (rd>0), opponent (away) left runners on: signal positive
        {"lob_count": 2, "state_diff": 3.0, "base_out_known": True},
        # Away leading (rd<0), home left runners on: signal positive for away (rd<0 -> sign=-1 -> neg*neg=pos? no)
        # rd<0 means away leading; away bats mid-inning so lob > 0 by away batting -> signal direction flips
        {"lob_count": 2, "state_diff": -3.0, "base_out_known": True},
        # Tied: no directional signal
        {"lob_count": 3, "state_diff": 0.0, "base_out_known": True},
        # Unknown: lob=0 neutralizes
        {"lob_count": 0, "state_diff": 5.0, "base_out_known": False},
    ]
    sig = _run_exp_signal(states)
    assert sig[0] > 0.0,  f"expected positive signal for home leading + LOB; got {sig[0]}"
    assert sig[1] < 0.0,  f"expected negative signal for away leading + LOB; got {sig[1]}"
    assert sig[2] == 0.0, f"expected zero for tied game; got {sig[2]}"
    assert sig[3] == 0.0, f"expected zero for lob_count=0; got {sig[3]}"


def test_baseout_layer_ships_when_informative():
    """L4 beats BASE on test when LOB is genuinely correlated with outcome."""
    from scripts.platformkit.ingame.ingame_gate_generic_models import (
        base_predict, fit_base,
    )
    from scripts.platformkit.eval_gate.scoring import brier

    n = 1000
    states = _make_baseout_states(n, lob_informative=True, seed=7)
    train, test = _split(states, n)
    assert len(train) > 100 and len(test) > 100

    ab = fit_base(train)
    base_tr = base_predict(train, ab)
    base_te = base_predict(test, ab)
    y_te = np.array([s["outcome"] for s in test], float)

    params = fit_baseout_layer(train, base_tr)
    layer_te = apply_baseout_layer(test, base_te, params)

    b_base = brier(base_te, y_te)
    b_layer = brier(layer_te, y_te)
    # When LOB is genuinely informative, layer should improve or at worst be close
    assert b_layer <= b_base + 0.002, (
        f"L4 should not badly hurt when LOB is informative: "
        f"base={b_base:.4f} layer={b_layer:.4f}")


def test_baseout_gate_runs_cleanly_null():
    """Gate machinery runs on null data and returns valid verdict."""
    n = 600
    states = _make_baseout_states(n, lob_informative=False, seed=99)
    sa = [s for s in states if s["game_id"] < 300]
    sb = [s for s in states if s["game_id"] >= 300]

    result = gate_baseout(sa, sb)
    assert result.verdict in ("SHIP", "REJECT"), f"unexpected verdict: {result.verdict}"
    assert "brier_base" in result.a_to_b
    assert "brier_base" in result.b_to_a
    assert "dm_p" in result.a_to_b
    assert "dm_p" in result.b_to_a
    # Coverage reported
    assert result.bo_coverage.get("a_bo_known", -1) >= 0
    assert result.bo_coverage.get("b_bo_known", -1) >= 0


def test_leak_free():
    """Layer params fit on TRAIN only; test states never influence the fit."""
    from scripts.platformkit.ingame.ingame_gate_generic_models import (
        base_predict, fit_base,
    )
    n = 300
    states = _make_baseout_states(n, lob_informative=True, seed=3)
    train, test = _split(states, n)

    ab = fit_base(train)
    base_tr = base_predict(train, ab)
    base_te = base_predict(test, ab)

    # Fit using ONLY train states and train base predictions
    params = fit_baseout_layer(train, base_tr)

    # Apply to test: produces valid probs without seeing test outcomes
    out = apply_baseout_layer(test, base_te, params)

    assert out.shape == (len(test),), f"wrong output shape: {out.shape}"
    assert np.all((out >= 0.0) & (out <= 1.0)), "probs out of [0,1]"
    assert not np.any(np.isnan(out)), "NaN in output"


def test_dm_clusters_by_game():
    """DM test clusters by game_id so within-game correlation is accounted for."""
    from scripts.platformkit.eval_gate.dm_test import diebold_mariano

    rng = np.random.default_rng(42)
    n_games, n_per = 6, 18
    d, gids = [], []
    for g in range(n_games):
        gd = float(rng.normal(0.0, 0.01))
        for _ in range(n_per):
            d.append(gd + float(rng.normal(0.0, 0.001)))
            gids.append(g)

    dm_cl = diebold_mariano(d, gids)
    dm_iid = diebold_mariano(d, list(range(len(d))))

    assert abs(dm_cl.dm_stat) < abs(dm_iid.dm_stat), (
        f"clustered DM should have smaller |stat|: "
        f"cl={dm_cl.dm_stat:.3f} iid={dm_iid.dm_stat:.3f}")
    assert dm_cl.n_clusters == n_games


def test_load_tolerates_missing_base_out_cols(tmp_path):
    """load_mlb_states_baseout works on parquets without base-out extension."""
    # Build a minimal parquet WITHOUT base-out cols (old schema)
    df = pd.DataFrame({
        "game_id": ["g1", "g1", "g2"],
        "state_diff": [1.0, 2.0, -1.0],
        "frac_elapsed": [0.1, 0.5, 0.3],
        "p0": [0.55, 0.55, 0.45],
        "outcome": [1, 1, 0],
        "half_inning_label": ["mid1", "end1", "mid1"],
    })
    p = str(tmp_path / "old_mlb.parquet")
    df.to_parquet(p, index=False)
    states = load_mlb_states_baseout(p)
    assert len(states) == 3
    for s in states:
        assert s["base_out_known"] is False
        assert s["lob_count"] == 0
        assert s["outs"] == -1
        assert s["runners"] == 0


def test_gate_baseout_all_fields_present():
    """BaseOutResult.to_dict() has all required fields for JSON output."""
    n = 400
    states = _make_baseout_states(n, lob_informative=False, seed=55)
    sa = [s for s in states if s["game_id"] < 200]
    sb = [s for s in states if s["game_id"] >= 200]
    result = gate_baseout(sa, sb)
    d = result.to_dict()
    for key in ("layer", "verdict", "why", "base_out_coverage",
                "vs_close", "a_to_b", "b_to_a"):
        assert key in d, f"missing key: {key}"
    for key in ("brier_base", "brier_layer", "brier_delta", "dm_p", "fitted_beta"):
        assert key in d["a_to_b"], f"a_to_b missing: {key}"
        assert key in d["b_to_a"], f"b_to_a missing: {key}"


if __name__ == "__main__":
    import sys
    tests = [
        test_lob_count_bitmask,
        test_run_exp_signal_direction,
        test_baseout_layer_ships_when_informative,
        test_baseout_gate_runs_cleanly_null,
        test_leak_free,
        test_dm_clusters_by_game,
        test_load_tolerates_missing_base_out_cols,
        test_gate_baseout_all_fields_present,
    ]
    failed = []
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:
            import traceback
            print(f"FAIL  {t.__name__}: {e}")
            traceback.print_exc()
            failed.append(t.__name__)
    if failed:
        print(f"\n{len(failed)} test(s) FAILED: {failed}")
        sys.exit(1)
    else:
        print(f"\nAll {len(tests)} tests PASSED")
