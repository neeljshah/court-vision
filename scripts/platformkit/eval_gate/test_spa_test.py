"""Focused synthetic checks for the game-clustered Hansen SPA cross-check."""
from __future__ import annotations

import numpy as np
import pytest

from scripts.platformkit.eval_gate.retro_correction import catalog_signals
from scripts.platformkit.eval_gate.spa_test import hansen_spa, render_catalog_report


def _fixture(effect: float, seed: int = 9):
    rng = np.random.default_rng(seed)
    values, ids = [], []
    for game in range(48):
        game_effect = effect + float(rng.normal(0.0, 0.025))
        for _ in range(5):
            values.append(game_effect + float(rng.normal(0.0, 0.003)))
            ids.append("game%02d" % game)
    return values, ids


def test_identical_candidates_have_the_single_candidate_family_p():
    values, ids = _fixture(0.012)
    one = hansen_spa([values], [ids], n_bootstrap=499, seed=3)
    copies = hansen_spa([values, values, values], [ids, ids, ids], n_bootstrap=499, seed=3)
    assert copies.family_p == one.family_p
    assert copies.studentized_stats == (one.studentized_stats[0],) * 3


def test_planted_null_is_not_rejected_and_signal_is_rejected():
    null_values, ids = _fixture(0.0)
    null = hansen_spa([null_values], [ids], n_bootstrap=499, seed=4)
    assert null.family_p > 0.05 and not null.rejected
    signal_values, signal_ids = _fixture(0.035)
    signal = hansen_spa([signal_values], [signal_ids], n_bootstrap=499, seed=4)
    assert signal.family_p <= 0.05 and signal.rejected
    assert signal.studentized_stats[0] > 0.0


def test_unaligned_candidate_games_fail_closed():
    values, ids = _fixture(0.0)
    bad_ids = list(ids)
    bad_ids[-1] = "different_game"
    with pytest.raises(ValueError, match="same game_id"):
        hansen_spa([values, values], [ids, bad_ids], n_bootstrap=10)


def test_catalog_report_does_not_invent_missing_statistics():
    text = render_catalog_report(catalog_signals())
    assert "catalog_signals_on_disk=60" in text
    assert "family_spa_p=NA" in text
    assert "retro_verdict_comparison=NOT_EVALUABLE" in text
