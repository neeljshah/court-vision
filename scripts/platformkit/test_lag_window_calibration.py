from scripts.platformkit.lag_window_calibration import analyze


def _records(model_window, market_window):
    rows = []
    for game_number in range(4):
        game = "KXNBAGAME%d" % game_number
        for tick in range(14):
            score = {"home_score": 1 if tick >= 1 else 0, "away_score": 0}
            in_window = tick <= 4
            rows.append({"game": game, "timestamp": str(tick * 60), "model_prob": model_window if in_window else .4,
                         "market_prob": market_window if in_window else .4, "outcome": 1.0,
                         "state_summary": score, "raw": {"sport": "nba"}})
    return rows


def test_engineered_window_advantage_has_positive_excluding_zero_ci():
    summary = analyze(_records(.9, .5))["summaries"][0]
    assert summary["delta"] > 0
    assert summary["window_delta_ci_90"][0] > 0


def test_identical_series_has_zero_delta():
    summary = analyze(_records(.7, .7))["summaries"][0]
    assert abs(summary["delta"]) < 1e-12
    assert summary["window_delta_ci_90"] == [0.0, 0.0]
