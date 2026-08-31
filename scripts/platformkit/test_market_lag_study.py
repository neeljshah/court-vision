import pytest

from scripts.platformkit.market_lag_study import analyze


def _tick(index, score, market, model):
    return {"game": "KXMLBGAME-demo", "timestamp": "2026-01-01T00:%02d:00Z" % index,
            "market_prob": market, "model_prob": model,
            "state_summary": "home_score=%s away_score=0 inning=1 outs=0" % score,
            "raw": {}}


def test_engineered_lag_is_recovered_exactly():
    ticks = [_tick(0, 0, .50, .50), _tick(1, 1, .50, .50)]
    ticks += [_tick(i, 1, value, model) for i, (value, model) in enumerate(
        [( .55, .70), (.60, .70), (.70, .70), (.80, .70), (.80, .70), (.80, .70), (.80, .70), (.80, .70), (.80, .70), (.80, .70)], 2)]
    event = analyze(ticks)["events"][0]
    assert event["market_prob"]["lag_ticks"] == 4
    assert event["market_prob"]["lag_seconds"] == 240.0
    assert event["model_prob"]["lag_ticks"] == 1
    assert event["market_prob"]["moves"] == pytest.approx({"1": .05, "2": .10, "5": .30, "10": .30})


def test_no_event_game_is_empty_and_safe():
    report = analyze([_tick(index, 0, .5, .5) for index in range(12)])
    assert report["events"] == []
    assert report["summaries"] == []
