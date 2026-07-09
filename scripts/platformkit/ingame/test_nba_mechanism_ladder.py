"""Per-file tests for nba_mechanism_ladder -- synthetic, no real corpus.
Covers: pure helpers, game-clustered DM sign, walk-forward train/inference
parity (no leak), and rung isolation (base vs candidate differ ONLY by the
rung feature and score the SAME eligible ticks).

  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_nba_mechanism_ladder.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.ingame import nba_mechanism_ladder as M


def test_season_label_and_team_pair():
    assert M._season_label("2024-10-22") == "2024-25"
    assert M._season_label("2025-03-01") == "2024-25"
    assert M._season_label("2025-11-01") == "2025-26"
    assert M._team_pair("nba-nyk-bos-2024-10-22") == frozenset(["NYK", "BOS"])
    assert M._team_pair("garbage") is None


def test_logit_monotone_and_clamped():
    assert M._logit(0.5) == 0.0
    assert M._logit(0.9) > M._logit(0.1)
    assert np.isfinite(M._logit(0.0)) and np.isfinite(M._logit(1.0))


def test_dm_gameclustered_sign():
    # candidate loss strictly below base in every game -> positive mean, tiny p
    test = pd.DataFrame({"game_id": np.repeat(np.arange(30), 5)})
    lb = np.full(150, 0.30)
    lc = np.full(150, 0.20)
    md, p, g = M._dm_gameclustered(test, lb, lc)
    assert g == 30 and md > 0 and p < 0.05


def _synth(feat_signal: bool, seed: int = 0):
    """Two seasons of synthetic ticks. When feat_signal, the per-game feature
    drives the outcome and base cols are noise; else the feature is pure noise."""
    rng = np.random.default_rng(seed)
    rows, feat = [], {}
    gid = 0
    for season in (M.TRAIN_SEASON, M.TEST_SEASON):
        for _ in range(80):
            f = float(rng.normal())
            feat[gid] = f
            latent = (f if feat_signal else rng.normal())
            y = int((latent + 0.25 * rng.normal()) > 0)
            for _t in range(8):
                rows.append({
                    "game_id": gid, "season": season, "period": 3,
                    "phase": "P3", "outcome_home_win": y,
                    "market_prob": 0.5,
                    "logit_p0": rng.normal(), "margin_s": rng.normal(),
                    "z": rng.normal(),
                })
            gid += 1
    return pd.DataFrame(rows), feat


def test_rung_isolation_same_ticks():
    df, feat = _synth(feat_signal=True, seed=1)
    r = M.eval_rung(df, feat, "elo_diff", post_endq1=False)
    # base and candidate scored on the SAME test ticks (isolation)
    assert r["n_test_ticks"] == int((df["season"] == M.TEST_SEASON).sum())
    assert r["n_test_games"] == 80


def test_signal_feature_matters():
    df, feat = _synth(feat_signal=True, seed=2)
    r = M.eval_rung(df, feat, "elo_diff", post_endq1=False)
    assert r["delta_base_minus_cand"] > 0  # candidate improves on base
    assert r["verdict"] == "MATTERS" and r["dm_p_gameclustered"] < M.ALPHA_FWER


def test_noise_feature_null():
    df, feat = _synth(feat_signal=False, seed=3)
    r = M.eval_rung(df, feat, "elo_diff", post_endq1=False)
    assert r["verdict"] == "NULL"


def test_no_leak_train_only_standardization():
    # A feature constant across TRAIN but varying in TEST cannot help: the model
    # never saw its variation -> delta ~ 0 (no train/test leakage of test stats).
    df, feat = _synth(feat_signal=True, seed=4)
    for g in feat:
        if df[df["game_id"] == g]["season"].iloc[0] == M.TRAIN_SEASON:
            feat[g] = 0.0  # constant in train
    r = M.eval_rung(df, feat, "elo_diff", post_endq1=False)
    assert abs(r["delta_base_minus_cand"]) < 0.02


def test_post_endq1_restriction():
    df, feat = _synth(feat_signal=True, seed=5)
    df.loc[df.index[:400], "period"] = 1  # some pre-endQ1 ticks
    r = M.eval_rung(df, feat, "star_load", post_endq1=True)
    assert r["n_test_ticks"] == int(((df["season"] == M.TEST_SEASON) & (df["period"] >= 2)).sum())
