"""Per-file tests for ingame_smooth_tune_nba.

Acceptance criteria (from BACKLOG ig-exp-smooth-tune):
  1. Fit alpha lowers tick jitter while EVAL-season Brier is non-worse vs unsmoothed.
  2. alpha=1.0 identity passthrough preserved (smoothed == unsmoothed).
  3. Thin data (<MIN_GAMES) -> default alpha=1.0 + INSUFFICIENT_DATA.
  4. No $ field in result dict.
  5. Per-file test GREEN.

Synthetic corpus design mirrors test_ingame_blend.py: game outcomes follow a latent
true-probability; p0 is a noisy pregame estimate; p_blend is noisy with short-range
autocorrelation (simulated possession noise). We construct a corpus where alpha<1 should
provably reduce tick-to-tick jitter without meaningfully worsening Brier.
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.eval_gate.ingame_blend import fit_weight_surface
from scripts.platformkit.ingame.ingame_smooth_tune_nba import (
    DEFAULT_ALPHA,
    MIN_GAMES,
    SmoothTuneResult,
    apply_smooth_to_states,
    enrich_with_blend,
    mean_jitter_across_games,
    smooth_series,
    tick_jitter,
    tune_alpha,
)


# ---------------------------------------------------------------------------
# synthetic corpus builder
# ---------------------------------------------------------------------------

def _make_blend_states(seed: int, n_games: int = 80,
                       ticks_per_game: int = 4,
                       noise_scale: float = 0.18) -> list:
    """Synthetic states with p_blend drawn from a noisy AR(1) process per game.

    Tick-to-tick noise is intentionally large (noise_scale=0.18) so alpha<1 visibly
    reduces jitter. The true-p is consistent within each game so smoothed values track
    it well; unsmoothed values ping-pong +-noise.
    """
    rng = np.random.default_rng(seed)
    states = []
    for g in range(n_games):
        true_p = float(np.clip(0.5 + 0.35 * rng.standard_normal(), 0.05, 0.95))
        outcome = int(rng.random() < true_p)
        prev = true_p
        for t in range(ticks_per_game):
            # AR(1): each tick is 0.7*prev + 0.3*true + big noise
            raw = 0.7 * prev + 0.3 * true_p + noise_scale * rng.standard_normal()
            p_b = float(np.clip(raw, 0.01, 0.99))
            prev = p_b
            states.append({
                "game_id": g,
                "period": t + 1,
                "outcome": outcome,
                "p_blend": p_b,
                # extra keys needed by apply_smooth_to_states (orders by game)
            })
    return states


# ---------------------------------------------------------------------------
# unit tests
# ---------------------------------------------------------------------------

def test_smooth_series_identity():
    """alpha=1.0 is an identity passthrough."""
    vals = [0.3, 0.7, 0.5, 0.6]
    result = smooth_series(vals, alpha=1.0)
    for a, b in zip(vals, result):
        assert abs(a - b) < 1e-12, f"identity failed: {a} != {b}"


def test_smooth_series_full_dampen():
    """alpha=0.0 -> all ticks equal the first value (no new info)."""
    vals = [0.3, 0.7, 0.5, 0.6]
    result = smooth_series(vals, alpha=0.0)
    assert abs(result[0] - 0.3) < 1e-12
    for v in result[1:]:
        assert abs(v - 0.3) < 1e-12, f"full dampen failed: {v}"


def test_tick_jitter_empty_and_single():
    assert tick_jitter([]) == 0.0
    assert tick_jitter([0.5]) == 0.0


def test_tick_jitter_constant():
    assert tick_jitter([0.4, 0.4, 0.4]) == 0.0


def test_tick_jitter_decreases_with_lower_alpha():
    """Smoothing (lower alpha) should reduce jitter on a noisy series."""
    rng = np.random.default_rng(77)
    noisy = list(np.clip(0.5 + 0.2 * rng.standard_normal(20), 0.01, 0.99))
    j_raw = tick_jitter(noisy)
    j_smooth = tick_jitter(smooth_series(noisy, alpha=0.3))
    assert j_smooth < j_raw, f"expected smoothed jitter {j_smooth:.4f} < raw {j_raw:.4f}"


def test_apply_smooth_identity():
    """apply_smooth_to_states with alpha=1.0 returns the original p_blend values."""
    states = _make_blend_states(seed=42, n_games=10, ticks_per_game=3)
    orig = np.array([s["p_blend"] for s in states])
    sm = apply_smooth_to_states(states, alpha=1.0)
    assert np.allclose(orig, sm, atol=1e-12), "identity broken for alpha=1.0"


def test_mean_jitter_identity():
    """mean_jitter with alpha=1.0 gives baseline; alpha=0.5 must be lower for noisy data."""
    states = _make_blend_states(seed=55, n_games=50, ticks_per_game=5, noise_scale=0.25)
    j1 = mean_jitter_across_games(states, alpha=1.0)
    j05 = mean_jitter_across_games(states, alpha=0.5)
    assert j05 < j1, f"alpha=0.5 jitter {j05:.5f} should be < alpha=1.0 jitter {j1:.5f}"


def test_insufficient_data_returns_default():
    """Fewer than MIN_GAMES -> INSUFFICIENT_DATA + alpha=1.0."""
    tiny_states = _make_blend_states(seed=1, n_games=MIN_GAMES - 1)
    result = tune_alpha(tiny_states, tiny_states)
    assert result.status == "INSUFFICIENT_DATA"
    assert result.alpha == DEFAULT_ALPHA
    assert result.train_n_games < MIN_GAMES


def test_no_dollar_field_in_result_dict():
    """Result dict must not contain any $ or dollar-edge field."""
    tiny = _make_blend_states(seed=2, n_games=5)
    result = tune_alpha(tiny, tiny)
    d = result.to_dict()
    forbidden = {"dollar", "pnl", "roi", "profit", "edge_claimed"}
    for k in d:
        assert k.lower() not in forbidden, f"forbidden $ field '{k}' in result"


def test_tune_alpha_on_synthetic_corpus():
    """Main acceptance: tuned alpha lowers jitter; EVAL Brier is not worse.

    Uses two independent synthetic corpora (different seeds) to mirror the
    real cross-corpus design.
    """
    train_states = _make_blend_states(seed=10, n_games=100, ticks_per_game=5,
                                      noise_scale=0.20)
    eval_states = _make_blend_states(seed=20, n_games=80, ticks_per_game=5,
                                     noise_scale=0.20)

    result: SmoothTuneResult = tune_alpha(train_states, eval_states)

    # status must be TUNED or IDENTITY_SAFE_DEFAULT (never INSUFFICIENT_DATA here)
    assert result.status in ("TUNED", "IDENTITY_SAFE_DEFAULT"), result.status
    assert 0.0 <= result.alpha <= 1.0

    # EVAL Brier must not worsen vs unsmoothed (the non-degradation constraint)
    assert result.eval_brier_smoothed <= result.eval_brier_unsmoothed + 1e-5, (
        f"smoothed Brier {result.eval_brier_smoothed:.6f} > "
        f"unsmoothed {result.eval_brier_unsmoothed:.6f}"
    )

    # alpha=1.0 must be identity-safe (smoothed Brier == unsmoothed at alpha=1.0)
    y_eval = np.array([s["outcome"] for s in eval_states], dtype=float)
    sm1 = apply_smooth_to_states(eval_states, 1.0)
    p_raw = np.array([s["p_blend"] for s in eval_states], dtype=float)
    from scripts.platformkit.eval_gate.scoring import brier
    b_id = brier(sm1, y_eval)
    b_raw = brier(p_raw, y_eval)
    assert abs(b_id - b_raw) < 1e-12, "identity alpha=1.0 should not alter Brier"

    # if TUNED, smoothed jitter must be strictly lower
    if result.status == "TUNED":
        assert result.train_jitter_smoothed < result.train_jitter_unsmoothed, (
            f"TUNED but smoothed jitter {result.train_jitter_smoothed:.5f} "
            f">= unsmoothed {result.train_jitter_unsmoothed:.5f}"
        )


def test_enrich_with_blend_uses_real_surface():
    """enrich_with_blend adds p_blend using the blend surface, stays in [0,1]."""
    from scripts.platformkit.ingame.ingame_layer_gate_nba_io import p_live_from_margin
    rng = np.random.default_rng(99)
    raw_states = []
    for g in range(40):
        q_true = float(np.clip(0.5 + 0.3 * rng.standard_normal(), 0.05, 0.95))
        y = int(rng.random() < q_true)
        p0 = float(np.clip(q_true + 0.1 * rng.standard_normal(), 0.01, 0.99))
        for period in (1, 2, 3):
            secs_map = {1: 2160.0, 2: 1440.0, 3: 720.0}
            secs = secs_map[period]
            diff = (2 * y - 1) * period * 4.0 + 2.0 * rng.standard_normal()
            frac = 1.0 - secs / 2880.0
            raw_states.append({
                "game_id": g, "period": period,
                "seconds_remaining": secs, "score_diff": diff,
                "p0": p0, "p_live": p_live_from_margin(diff, frac),
                "outcome": y,
            })
    surf = fit_weight_surface(raw_states, min_cell=5)
    enriched = enrich_with_blend(raw_states, surf)
    assert len(enriched) == len(raw_states)
    for s in enriched:
        assert "p_blend" in s, "p_blend field missing"
        assert 0.0 <= s["p_blend"] <= 1.0, f"p_blend out of range: {s['p_blend']}"


# ---------------------------------------------------------------------------
# standalone runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} tests passed.")
