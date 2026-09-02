"""Per-file test for the S99 cross-market screen.

python -m pytest tests/platformkit/ingame/test_s99_cross_market.py -q
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.eval_gate import s99_corpus as corpus
from scripts.platformkit.eval_gate import s99_cross_market as s99

REPO = Path(__file__).resolve().parents[3]
ARTIFACT = REPO / "data" / "cache" / "eval_gate" / (s99.STEM + ".json")


def _mlb_games():
    rows = [{"d": dt.date(2026, 6, 1), "season": 2026, "home_team": "AAA", "away_team": "BBB",
             "home_runs": 10, "away_runs": 0},
            {"d": dt.date(2026, 6, 2), "season": 2026, "home_team": "AAA", "away_team": "BBB",
             "home_runs": 10, "away_runs": 0},
            {"d": dt.date(2026, 6, 3), "season": 2026, "home_team": "AAA", "away_team": "BBB",
             "home_runs": 10, "away_runs": 0},
            {"d": dt.date(2026, 6, 4), "season": 2026, "home_team": "AAA", "away_team": "BBB",
             "home_runs": 10, "away_runs": 0},
            {"d": dt.date(2026, 6, 5), "season": 2026, "home_team": "AAA", "away_team": "BBB",
             "home_runs": 10, "away_runs": 0},
            # The poison pill: a 900-run game ON the as-of date. A rate that moves when this row
            # is added is reading its own game (or the future) -- the S99 leak contract.
            {"d": dt.date(2026, 6, 6), "season": 2026, "home_team": "AAA", "away_team": "BBB",
             "home_runs": 900, "away_runs": 900}]
    return pd.DataFrame(rows)


def test_asof_rates_are_strictly_before_the_game_date():
    games = _mlb_games()
    rates, league = corpus.mlb_asof_rates(games, dt.date(2026, 6, 6))
    assert rates["AAA"] == pytest.approx(10.0 / 9.0)
    assert rates["BBB"] == pytest.approx(0.0)
    assert league == pytest.approx(5.0 / 9.0)
    # Same call one day later must SEE the poison row -- proving the guard is a date filter and
    # not an accident of the fixture.
    later, _ = corpus.mlb_asof_rates(games, dt.date(2026, 6, 7))
    assert later["AAA"] > rates["AAA"]


def test_soccer_asof_rates_are_strictly_before_the_match_date():
    frame = pd.DataFrame([{"d": dt.date(2026, 6, i), "home_team": "X", "away_team": "Y",
                           "home_score": 2, "away_score": 0} for i in range(1, 6)] +
                         [{"d": dt.date(2026, 6, 6), "home_team": "X", "away_team": "Y",
                           "home_score": 99, "away_score": 99}])
    rates, _ = corpus.soccer_asof_rates(frame, dt.date(2026, 6, 6))
    assert rates["X"] == pytest.approx(2.0 / 90.0)
    assert rates["Y"] == pytest.approx(0.0)


def test_game_key_strips_only_the_series_prefix():
    frame = pd.DataFrame({"event_key": ["KXMLBGAME-26JUL011235CWSBAL",
                                        "KXMLBTOTAL-26JUL011235CWSBAL",
                                        "KXWCTEAMTOTAL-26JUL01BELSEN"]})
    keys = frame["event_key"].str.split("-", n=1).str[1]
    assert keys.iloc[0] == keys.iloc[1] == "26JUL011235CWSBAL"
    assert keys.iloc[2] == "26JUL01BELSEN"


def test_total_probability_uses_the_at_least_settlement_rule():
    # Kalshi settles a total-runs contract YES iff the final total is >= its strike (verified
    # 1.000 on 917 settled (game, strike) pairs). A strike already reached is certain.
    cur = np.array([4.0, 4.0, 4.0])
    lam = np.array([2.0, 2.0, 2.0])
    p = s99.p_total_at_least(cur, lam, np.array([4.0, 5.0, 9.0]))
    assert p[0] == 1.0
    assert p[1] > p[2] > 0.0
    assert np.all((p >= 0.0) & (p <= 1.0))


def test_home_win_is_symmetric_and_collapses_when_no_time_is_left():
    tied = s99.p_home_win([3.0], [3.0], [1.5], [1.5], 0.5)
    assert tied[0] == pytest.approx(0.5, abs=1e-9)
    done = s99.p_home_win([5.0, 2.0], [2.0, 5.0], [1e-12, 1e-12], [1e-12, 1e-12], 0.5)
    assert done[0] == pytest.approx(1.0, abs=1e-6)
    assert done[1] == pytest.approx(0.0, abs=1e-6)
    # A draw is a LOSS for a soccer home-moneyline contract: tie weight 0, not 0.5.
    assert s99.p_home_win([1.0], [1.0], [1e-12], [1e-12], 0.0)[0] == pytest.approx(0.0, abs=1e-6)


def test_crps_is_zero_for_a_point_mass_on_the_truth():
    zero = s99.crps_total(np.array([7.0]), np.array([1e-12]), np.array([7.0]), 20)
    assert zero[0] == pytest.approx(0.0, abs=1e-6)
    worse = s99.crps_total(np.array([0.0]), np.array([1e-12]), np.array([7.0]), 20)
    assert worse[0] > zero[0]


def test_mlb_remaining_half_innings():
    away, home = corpus.mlb_remaining(np.array([1.0, 9.0]), np.array(["top", "bottom"]),
                                      np.array([0.0, 2.0]))
    assert list(away) == [9.0, 0.0]
    assert list(home) == [9.0, pytest.approx(1.0 / 3.0)]


def test_paired_delta_is_zero_when_model_equals_market():
    rows = pd.DataFrame({"game": ["a", "a", "b", "b"], "loss_model": [0.1, 0.2, 0.3, 0.4],
                         "loss_market": [0.1, 0.2, 0.3, 0.4]})
    out = s99.paired(rows)
    assert out["delta_market_minus_model"] == pytest.approx(0.0)
    assert out["n_games"] == 2


@pytest.mark.skipif(not ARTIFACT.exists(), reason="run the module first")
def test_artifact_headline_reproduces_from_the_archived_differential():
    """A2/Q9: every headline must be recomputable from the archived per-tick series alone."""
    report = json.loads(ARTIFACT.read_text(encoding="ascii"))
    for sport, block in report["sports"].items():
        series = pd.read_csv(ARTIFACT.parent / ("%s_%s_series.csv" % (s99.STEM, sport)))
        screen = series[series["partition_side"] == "screen"]
        for leg, mask in (("moneyline", screen["market"] == "moneyline"),
                          ("total", screen["market"] != "moneyline")):
            sub = screen[mask]
            assert len(sub) == block[leg]["n_ticks"]
            assert s99.paired(sub)["delta_market_minus_model"] == pytest.approx(
                block[leg]["delta_market_minus_model"], abs=1e-9)
        assert block["prereg_draft_warranted"] is (
            block["total"]["delta_market_minus_model"] >= s99.BAR
            and block["total"]["ci95"][0] > 0.0)
