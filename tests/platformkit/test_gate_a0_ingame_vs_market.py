"""Tests for scripts/platformkit/ingame/gate_a0_ingame_vs_market.py (Q01)."""
import pandas as pd

from scripts.platformkit.ingame.gate_a0_ingame_vs_market import (
    brier, cluster_bootstrap, verdict, phase_mlb, phase_soccer,
)


def test_paired_brier_delta_hand_computed():
    # game A: model closer to outcome; game B: model further from outcome.
    df = pd.DataFrame({
        'game_id': ['A', 'A', 'B', 'B'],
        'model_prob': [0.6, 0.7, 0.3, 0.2],
        'market_prob': [0.5, 0.5, 0.4, 0.4],
        'outcome': [1.0, 1.0, 0.0, 0.0],
    })
    df['se_model'] = brier(df['model_prob'], df['outcome'])
    df['se_market'] = brier(df['market_prob'], df['outcome'])
    # hand-computed: se_model = [0.16, 0.09, 0.09, 0.04] mean=0.095
    #                se_market = [0.25, 0.25, 0.16, 0.16] mean=0.205
    #                delta = 0.095 - 0.205 = -0.11
    point, _, _ = cluster_bootstrap(df, 'se_model', 'se_market', n_boot=10, seed=1)
    assert abs(point - (-0.11)) < 1e-9


def test_bootstrap_resamples_games_not_rows():
    # 30 games, 10 ticks each. Games 2..30 have model == market (zero signal).
    # Game 1 alone carries a large model-vs-market gap on every one of its ticks.
    rows = []
    for g in range(1, 31):
        for _ in range(10):
            if g == 1:
                rows.append({'game_id': 'g1', 'model_prob': 0.9, 'market_prob': 0.5, 'outcome': 0.0})
            else:
                rows.append({'game_id': f'g{g}', 'model_prob': 0.5, 'market_prob': 0.5, 'outcome': 0.0})
    df = pd.DataFrame(rows)
    df['se_model'] = brier(df['model_prob'], df['outcome'])
    df['se_market'] = brier(df['market_prob'], df['outcome'])
    point, lo, hi = cluster_bootstrap(df, 'se_model', 'se_market', n_boot=2000, seed=13)
    # game-level resampling: P(game1 excluded from a resample) = (29/30)**30 ~= 0.36,
    # so a large share of resamples score exactly 0 -> the CI touches/contains 0
    # even though the point estimate is nonzero (proves clustering is by game,
    # not by row -- a row-level bootstrap of 300 ticks would almost never drop
    # all 10 of game1's rows at once and would yield a tight, non-zero-touching CI).
    assert point > 0
    assert lo <= 1e-9 <= hi


def test_verdict_three_ci_cases():
    assert verdict(lo=0.01, hi=0.05, n_games=50) == 'BEHIND'   # CI > 0: market better
    assert verdict(lo=-0.05, hi=-0.01, n_games=50) == 'AHEAD'  # CI < 0: model better
    assert verdict(lo=-0.01, hi=0.01, n_games=50) == 'UNDERPOWERED'  # CI contains 0


def test_phase_parser():
    mlb_early = 'home_score=0.0 away_score=0.0 inning=2 half=top outs=0 base=0 bos=0 re=0.481 count=0-1 pitch_count=2 tto=1'
    mlb_late = 'home_score=3.0 away_score=2.0 inning=8 half=bot outs=1 base=1 bos=1 re=0.254 count=1-2 pitch_count=44 tto=3'
    soccer_mid = 'home_score=0.0 away_score=0.0 minute=45'
    assert phase_mlb(mlb_early) == '1-3'
    assert phase_mlb(mlb_late) == '7-9+'
    assert phase_soccer(soccer_mid) == '31-60'
