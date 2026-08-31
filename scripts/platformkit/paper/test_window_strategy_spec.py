"""Exact synthetic checks for the offline absorption-window benchmark."""
import pytest

from scripts.platformkit.paper.window_strategy_spec import WindowStrategySpec, simulate


def _tick(game, index, model, market, outcome, score=0):
    return {"game": game, "timestamp": "2026-01-10T00:%02d:00Z" % index,
            "model_prob": model, "market_prob": market, "outcome": outcome,
            "state_summary": {"home_score": score if index >= 2 else 0, "away_score": 0},
            "raw": {"sport": "nba"}}


def test_engineered_divergence_creates_exact_entry_and_stats():
    rows = []
    for day, outcome in ((1, 1.0), (2, 0.0), (3, 1.0), (4, 0.0)):
        game = "KXNBAGAME-prior-%d" % day
        rows.append({"game": game, "timestamp": "2026-01-%02dT00:00:00Z" % day,
                     "model_prob": 0.9 if outcome else 0.1, "market_prob": 0.5,
                     "outcome": outcome, "raw": {"sport": "nba"}})
    game = "KXNBAGAME-entry"
    rows.extend(_tick(game, index, 0.9, 0.5, 1.0, score=1) for index in range(2))
    rows.extend(_tick(game, index, 0.9 if index > 2 else 0.5, market, 1.0, score=1)
                for index, market in enumerate((0.5, 0.5, 0.55, 0.60, 0.65, 0.70,
                                                0.75, 0.80, 0.80, 0.80, 0.80, 0.80), 2))
    result = simulate(rows, WindowStrategySpec(threshold=0.05, window_s=159.0))
    summary = result["by_sport"]["nba"]
    assert summary["n_entries"] == 1
    assert summary["entry_brier"] == 0.0
    assert summary["market_brier"] == 0.25
    assert summary["mean_clv_proxy_prob_units"] == pytest.approx(0.30)
    assert summary["win_rate"] == 1.0
    assert result["entries"][0]["entry_tick"] == 3
    assert result["honest_verdict"]["edge_claim"] is False
