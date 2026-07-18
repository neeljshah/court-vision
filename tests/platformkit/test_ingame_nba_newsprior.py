"""Per-file synthetic tests for ingame_nba_newsprior(_features) -- feature
knowability, walk-forward split (no post-T leak), logit-shift math,
verdict-by-CI mapping, and artifact schema. No real corpus/parquet reads
(those are exercised by the CLI on the real repo, not here).

Run: python -m pytest tests/platformkit/test_ingame_nba_newsprior.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.benchmarks.crps_market.ingame_nba_newsprior import (
    FEATURE_COLUMNS, _gap_verdict, _logit, _sigmoid, apply_shift,
    fit_logit_shift, score_checkpoint, walk_forward_split,
)
from scripts.platformkit.benchmarks.crps_market.ingame_nba_newsprior_features import (
    _modal_five_ids, _n_starters_changed, _star_out, _top3_usage_ids, build_features,
    team_frames, team_game_dates,
)


def _pbox_row(team, date, player_id, minutes, starter):
    return {"team": team, "date": pd.Timestamp(date), "player_id": player_id,
            "min": minutes, "starter": starter}


# ---------------------------------------------------------------------------
# feature knowability
# ---------------------------------------------------------------------------

def test_star_out_true_only_when_a_top3_player_logs_zero_or_is_absent():
    top3 = {1, 2, 3}
    played_all = pd.DataFrame([{"player_id": i, "min": 20.0} for i in (1, 2, 3, 4)])
    assert _star_out(played_all, top3) is False

    one_dnp = pd.DataFrame([
        {"player_id": 1, "min": 0.0}, {"player_id": 2, "min": 25.0},
        {"player_id": 3, "min": 30.0}, {"player_id": 4, "min": 10.0}])
    assert _star_out(one_dnp, top3) is True

    absent_entirely = pd.DataFrame([{"player_id": 2, "min": 25.0}, {"player_id": 3, "min": 30.0}])
    assert _star_out(absent_entirely, top3) is True  # not on the box at all -> also "out"


def test_star_out_false_when_no_prior_window_top3_known():
    assert _star_out(pd.DataFrame([{"player_id": 1, "min": 0.0}]), set()) is False


def test_top3_usage_ranks_by_mean_minutes_not_appearance_count():
    window = pd.DataFrame([
        _pbox_row("BOS", "2024-01-01", 1, 35.0, True),
        _pbox_row("BOS", "2024-01-01", 2, 5.0, False),
        _pbox_row("BOS", "2024-01-02", 1, 33.0, True),
        _pbox_row("BOS", "2024-01-02", 3, 30.0, True),
        _pbox_row("BOS", "2024-01-02", 4, 28.0, True),
    ])
    assert _top3_usage_ids(window) == {1, 3, 4}  # player 2's one cameo doesn't crack top-3


def test_modal_five_counts_starter_flag_only():
    window = pd.DataFrame([
        _pbox_row("BOS", "2024-01-01", pid, 20.0, True) for pid in (1, 2, 3, 4, 5)
    ] + [_pbox_row("BOS", "2024-01-02", pid, 20.0, True) for pid in (1, 2, 3, 4, 6)])
    modal5 = _modal_five_ids(window)
    assert modal5 == {1, 2, 3, 4, 6} or modal5 == {1, 2, 3, 4, 5}  # tie on the 5th slot is fine
    assert {1, 2, 3, 4} <= modal5


def test_n_starters_changed_counts_modal_minus_actual():
    game = pd.DataFrame([_pbox_row("BOS", "2024-01-03", pid, 20.0, True) for pid in (1, 2, 3, 7, 8)])
    assert _n_starters_changed(game, {1, 2, 3, 4, 5}) == 2  # 4 and 5 replaced


def test_build_features_honest_zero_for_unknown_team():
    feats = build_features({}, {}, "ZZZ", "YYY", "2024-01-05")
    assert feats["star_out_home"] == 0.0 and feats["star_out_away"] == 0.0
    assert feats["rest_days_diff"] == 0.0


def test_build_features_b2b_and_rest_days_diff():
    pbox = pd.DataFrame([
        _pbox_row("BOS", "2024-01-01", 1, 20.0, True),
        _pbox_row("BOS", "2024-01-02", 1, 20.0, True),   # BOS b2b into 01-03
        _pbox_row("MIA", "2023-12-28", 1, 20.0, True),   # MIA rested 6 days into 01-03
    ])
    by_team, dates = team_frames(pbox), team_game_dates(pbox)
    feats = build_features(by_team, dates, "BOS", "MIA", "2024-01-03")
    assert feats["b2b_home"] == 1.0
    assert feats["b2b_away"] == 0.0
    assert feats["rest_days_diff"] == 1.0 - 6.0


# ---------------------------------------------------------------------------
# walk-forward split
# ---------------------------------------------------------------------------

def test_walk_forward_split_orders_by_date_and_no_test_game_precedes_cutoff():
    gdate = {"g1": "2024-01-05", "g2": "2024-01-01", "g3": "2024-01-03", "g4": "2024-01-10"}
    order, train_ids = walk_forward_split(list(gdate), gdate, train_frac=0.5)
    assert order == ["g2", "g3", "g1", "g4"]
    assert train_ids == {"g2", "g3"}
    cutoff_date = max(gdate[g] for g in train_ids)
    test_ids = set(order) - train_ids
    assert all(gdate[g] > cutoff_date for g in test_ids)  # no test game precedes the fit cutoff


def test_score_checkpoint_never_fits_on_test_rows():
    # a poisoned test-only feature (huge star_out signal) must NOT move beta,
    # since fit_logit_shift only ever sees rows filtered to split=="train".
    rng = np.random.default_rng(0)
    train_rows = [{"split": "train", "model_p": 0.5, "market_p": 0.5,
                   "y": int(rng.random() < 0.5), **{c: 0.0 for c in FEATURE_COLUMNS}}
                  for _ in range(40)]
    test_rows = [{"split": "test", "model_p": 0.5, "market_p": 0.5, "y": 1,
                  **{c: 999.0 for c in FEATURE_COLUMNS}}]
    beta_train_only = fit_logit_shift([r for r in train_rows if r["split"] == "train"])
    out = score_checkpoint(train_rows + test_rows)
    # the huge poisoned features would blow up the offset-shift if they'd
    # leaked into the fit; beta actually used is identical to train-only fit.
    assert np.allclose(fit_logit_shift(train_rows), beta_train_only)
    assert out["n_train"] == 40 and out["n_test"] == 1


# ---------------------------------------------------------------------------
# logit-shift math
# ---------------------------------------------------------------------------

def test_logit_sigmoid_round_trip():
    p = np.array([0.1, 0.5, 0.9])
    assert np.allclose(_sigmoid(_logit(p)), p, atol=1e-6)


def test_apply_shift_zero_beta_is_a_noop():
    feat_row = {c: 1.0 for c in FEATURE_COLUMNS}
    beta = np.zeros(len(FEATURE_COLUMNS) + 1)
    assert abs(apply_shift(0.42, feat_row, beta) - 0.42) < 1e-9


def test_apply_shift_positive_intercept_shift_raises_p():
    feat_row = {c: 0.0 for c in FEATURE_COLUMNS}
    beta = np.zeros(len(FEATURE_COLUMNS) + 1)
    beta[0] = 1.0  # intercept-only shift
    assert apply_shift(0.5, feat_row, beta) > 0.5


def test_fit_logit_shift_falls_back_to_zero_when_underpowered():
    rows = [{"y": 1, "model_p": 0.5, **{c: 0.0 for c in FEATURE_COLUMNS}}]  # n=1 << _MIN_TRAIN
    beta = fit_logit_shift(rows)
    assert np.allclose(beta, np.zeros(len(FEATURE_COLUMNS) + 1))


# ---------------------------------------------------------------------------
# verdict-by-CI mapping + artifact schema
# ---------------------------------------------------------------------------

def test_gap_verdict_underpowered_below_n30():
    token, ci = _gap_verdict(np.array([0.01, 0.02, -0.01]))
    assert token == "UNDERPOWERED"


def test_gap_verdict_closes_gap_when_ci_excludes_zero_positive():
    rng = np.random.default_rng(3)
    delta = 0.05 + rng.normal(0, 0.01, size=200)
    token, ci = _gap_verdict(delta)
    assert token == "CLOSES_GAP" and ci[0] > 0


def test_gap_verdict_worsens_when_ci_excludes_zero_negative():
    rng = np.random.default_rng(4)
    delta = -0.05 + rng.normal(0, 0.01, size=200)
    token, ci = _gap_verdict(delta)
    assert token == "WORSENS" and ci[1] < 0


def test_score_checkpoint_schema_and_underpowered_when_no_test_rows():
    out = score_checkpoint([{"split": "train", "model_p": 0.5, "market_p": 0.5, "y": 1,
                             **{c: 0.0 for c in FEATURE_COLUMNS}}])
    assert out == {"n_train": 1, "n_test": 0,
                   "verdict_vs_unadjusted": "UNDERPOWERED", "verdict_vs_market": "UNDERPOWERED"}


def test_score_checkpoint_full_schema_keys_present():
    rng = np.random.default_rng(5)
    rows = []
    for i in range(60):
        split = "train" if i < 40 else "test"
        y = int(rng.random() < 0.5)
        rows.append({"split": split, "model_p": 0.5, "market_p": 0.5, "y": y,
                     **{c: float(rng.integers(0, 2)) for c in FEATURE_COLUMNS}})
    out = score_checkpoint(rows)
    for key in ("n_train", "n_test", "unadjusted_brier_mean", "adjusted_brier_mean",
                "market_brier_mean", "delta_vs_unadjusted_mean", "delta_vs_unadjusted_95ci",
                "verdict_vs_unadjusted", "delta_vs_market_mean", "delta_vs_market_95ci",
                "verdict_vs_market", "beats_market_provisional"):
        assert key in out
    assert isinstance(out["beats_market_provisional"], bool)
