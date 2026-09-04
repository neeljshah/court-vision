"""Focused checks for S211's archive arithmetic."""
from scripts.platformkit.s211_headline_rederive import _briers, _cluster_interval, _shares


def _row(static: float, score: float, conditional: float) -> dict:
    return {
        "game_id": "g", "timestamp": "2026-01-01", "n_checkpoints": 1,
        "static_loss_sum": static, "score_loss_sum": score,
        "conditional_loss_sum": conditional,
    }


def test_s211_weighted_brier_shares_and_cluster_interval_are_reproducible():
    rows = [_row(0.25, 0.16, 0.09) for _ in range(30)]
    briers = _briers(rows)
    assert abs(briers["static"] - 0.25) < 1e-12
    assert abs(briers["score"] - 0.16) < 1e-12
    assert abs(briers["conditional"] - 0.09) < 1e-12
    shares = _shares(briers)
    assert abs(shares["score_only_share"] - 0.5625) < 1e-12
    assert abs(shares["model_prior_share"] - 0.4375) < 1e-12
    ci = _cluster_interval(rows)
    assert ci["reported"] is True
    assert ci["n_eff"] == 30
    assert abs(ci["lower"] - 0.4375) < 1e-12
    assert abs(ci["upper"] - 0.4375) < 1e-12
