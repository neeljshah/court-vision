"""S309 attempt-2 design arms: variable cluster sizes and future-label propagation."""
from __future__ import annotations

import numpy as np
import pandas as pd

import pytest

from scripts.platformkit.s309_design_evaluators import evaluate_designs, fit_calibrator

PATHS_PER_GAME = 7          # C(8-1, 2-1) with the frozen 8 groups / 2 test groups
TEAMS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III", "JJJ"]


def _corpus(n_games: int = 40) -> pd.DataFrame:
    """Unequal tick clusters (3..11 ticks) and unequal games per calendar day."""
    rng = np.random.default_rng(7)
    rows, day = [], 0
    for game in range(n_games):
        if game % 4 != 3:                      # every fourth day carries two games
            day += 1
        start = pd.Timestamp("2025-01-01 18:00:00+00:00") + pd.Timedelta(days=day, hours=game % 3)
        prob = np.clip(rng.beta(2.0, 2.0, 3 + game % 9), 0.02, 0.98)
        outcome = int(rng.random() < float(prob.mean()))
        for step, value in enumerate(prob):
            stamp = start + pd.Timedelta(minutes=5 * step)
            rows.append({"game_id": "G%02d" % game, "game_date": str(start.date()),
                         "state_ts": str(stamp), "state_key": "G%02d|%s" % (game, stamp),
                         "home": TEAMS[game % 10], "away": TEAMS[(game + 3) % 10],
                         "market_prob": float(value), "outcome_home_win": outcome})
    return pd.DataFrame(rows)


def test_variable_cluster_sizes_keep_one_oof_record_per_tick_per_design() -> None:
    ticks = _corpus()
    scored, folds, provenance = evaluate_designs(ticks)

    cluster_sizes = scored.groupby("game_id").size()
    assert cluster_sizes.nunique() > 1, "the fixture must carry unequal clusters"
    assert scored.state_key.is_unique and len(scored) == len(ticks)
    assert set(scored.evaluator_records) == {1}

    # one walk_forward record per game cluster; PATHS_PER_GAME cpcv records per cluster
    assert provenance["forward"]["records"] == len(cluster_sizes)
    assert provenance["cpcv"]["records"] == PATHS_PER_GAME * len(cluster_sizes)
    assert provenance["cpcv"]["paths_per_game"] == PATHS_PER_GAME
    assert provenance["record_agreement_max_abs_error"] <= 1e-9
    assert provenance["n_ticks"] == len(ticks) and provenance["forward"]["fits"] > 1

    columns = ["loss_forward_baseline", "loss_forward_candidate",
               "loss_cpcv_baseline", "loss_cpcv_candidate"]
    assert scored[columns].notna().all().all()
    # B9: the two designs must be genuinely different series, never one aliased onto the other
    assert not np.allclose(scored.loss_forward_candidate, scored.loss_cpcv_candidate)

    cpcv_folds = [fold for fold in folds if fold["arm"] == "cpcv"]
    assert cpcv_folds and all(fold["symmetric_embargo"] and fold["embargo_days"] == 1
                              for fold in cpcv_folds)
    assert all(not fold["symmetric_embargo"] for fold in folds if fold["arm"] == "forward")


def test_a_planted_future_label_moves_no_prior_forward_loss() -> None:
    ticks = _corpus()
    # the hour offset reorders games inside a day, so take the chronologically last one
    last = ticks.loc[ticks.state_ts.idxmax(), "game_id"]
    before, _, _ = evaluate_designs(ticks)

    planted = ticks.copy()
    tail = planted.game_id.eq(last)
    planted.loc[tail, "outcome_home_win"] = 1 - planted.loc[tail, "outcome_home_win"]
    after, _, _ = evaluate_designs(planted)

    prior = before.game_id.ne(last).to_numpy()
    assert prior.sum() > 0 and before.game_id.eq(last).sum() > 0
    # forward-only: the last game is settled after every prior test state, so no prior
    # out-of-fold loss may move by a single bit.
    assert np.array_equal(before.loc[prior, "loss_forward_candidate"].to_numpy(),
                          after.loc[prior, "loss_forward_candidate"].to_numpy())
    assert np.array_equal(before.loc[prior, "loss_forward_baseline"].to_numpy(),
                          after.loc[prior, "loss_forward_baseline"].to_numpy())
    # power check: the symmetric design DOES straddle, so the same plant must move it.
    # A test that cannot see the plant anywhere would pass on an aliased route too.
    assert not np.array_equal(before.loc[prior, "loss_cpcv_candidate"].to_numpy(),
                              after.loc[prior, "loss_cpcv_candidate"].to_numpy())


def test_every_fold_archives_membership_tails_and_the_attempt1_aliases() -> None:
    """Each fold carries exact train/test ids and the fitted tails, so its candidate refits."""
    ticks = _corpus()
    _, folds, _ = evaluate_designs(ticks)
    legacy = {"fold_date", "min_test_date", "max_train_date", "train_games", "test_games",
              "test_ticks", "forward_only", "cpcv_group", "purge", "embargo_days",
              "fallback_market", "coef", "intercept", "low_points", "high_points"}
    # the archive schema is the fold FRAME: pandas fills a fallback fit's coef/intercept as null,
    # exactly as the attempt-1 folds JSON did.
    assert folds and legacy <= set(pd.DataFrame(folds).columns)

    per_game = ticks.groupby("game_id").size().to_dict()
    for fold in folds:
        train, test = fold["train_game_ids"], fold["test_game_ids"]
        assert fold["train_games"] == fold["n_train_games"] == len(train) == len(set(train))
        assert fold["test_games"] == len(test) == len(set(test)) > 0
        assert fold["test_ticks"] == sum(per_game[game] for game in test)
        assert not set(train) & set(test), "a fold trained on one of its own test games"

    fitted = [fold for fold in folds if not fold["fallback_market"]]
    assert fitted, "the fixture must produce at least one real fit"
    fold = fitted[-1]
    rows = ticks[ticks.game_id.isin(fold["train_game_ids"])]
    models, params = fit_calibrator(rows.market_prob.to_numpy(float),
                                    rows.outcome_home_win.to_numpy(float))
    assert params["coef"] == pytest.approx(fold["coef"])
    assert params["intercept"] == pytest.approx(fold["intercept"])
    for name, model in (("low", models[1]), ("high", models[2])):
        if model is None:
            assert fold["isotonic_%s_x" % name] == []
            continue
        assert list(model.X_thresholds_) == pytest.approx(fold["isotonic_%s_x" % name])
        assert list(model.y_thresholds_) == pytest.approx(fold["isotonic_%s_y" % name])
