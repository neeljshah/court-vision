"""Per-file test for scripts.platformkit.eval_gate.s86_nba_every_tick (S86).

Covers the rails the screen rests on: the state buckets, the informative flag, the
as-of prior (a same-day game may not reach it), the no-future-read guard actually
firing on a planted later-tick read, and a disjoint screen/verdict partition.
python -m pytest tests/platformkit/ingame/test_s86_nba_every_tick.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.eval_gate import s86_nba_every_tick as S


def _ticks(n_games=4, per_game=5):
    rows = []
    for g in range(n_games):
        for i in range(per_game):
            rows.append({"game_id": 100 + g, "game_date": "2025-01-%02d" % (g + 1),
                         "ts": 1000 + i, "period": 1 + i % 4, "game_clock_s": 600.0 - 100.0 * i,
                         "score_home": 10 * i, "score_away": 9 * i, "margin": i,
                         "market_prob": 0.5 + 0.01 * i, "y": float(g % 2),
                         "informative": True, "home": "BOS", "away": "NYK", "unit": "2024-25"})
    df = pd.DataFrame(rows)
    df["elapsed"] = [S._elapsed_minutes(int(p), float(c)) for p, c in zip(df["period"], df["game_clock_s"])]
    df["rem"] = [S.rem_minutes(p, c) for p, c in zip(df["period"], df["game_clock_s"])]
    df["period_bucket"] = df["period"].map(S.period_bucket)
    df["margin_bucket"] = df["margin"].map(S.margin_bucket)
    df["rem_bucket"] = df["rem"].map(S.rem_bucket)
    return df


def _priors(df):
    return {int(g): (0.6, str(d)) for g, d in df.groupby("game_id")["game_date"].first().items()}


def test_state_buckets_are_the_declared_edges():
    assert S.rem_minutes(1, 720.0) == 48.0 and S.rem_minutes(4, 0.0) == 0.0
    assert S.rem_minutes(5, 300.0) == 5.0          # OT: remaining in that period, never negative
    assert [S.margin_bucket(m) for m in (0, 5, 6, 12, 13)] == [
        "close_le5", "close_le5", "mid_06_12", "mid_06_12", "blowout_gt12"]
    assert [S.rem_bucket(r) for r in (13, 12, 6.1, 6, 2.1, 2)] == [
        "rem_gt12", "rem_06_12", "rem_06_12", "rem_02_06", "rem_02_06", "rem_le02"]
    assert S.period_bucket(4) == "P4" and S.period_bucket(6) == "OT"


def test_informative_flag_is_a_change_from_the_previous_tick_of_the_same_game(tmp_path):
    raw = pd.DataFrame({
        "game_id": [1, 1, 1, 2, 2], "game_date": ["2025-01-01"] * 5, "ts": [1, 2, 3, 1, 2],
        "period": [1, 1, 2, 1, 1], "game_clock_s": [700.0, 600.0, 500.0, 700.0, 600.0],
        "score_home": [0, 2, 4, 0, 3], "score_away": [0, 2, 3, 0, 1], "margin": [0, 0, 1, 0, 2],
        "market_prob": [0.5, 0.5, 0.6, 0.4, 0.4], "traded": [True] * 5,
        "market_ticker": ["nba-nyk-bos-2025-01-01"] * 5, "outcome_home_win": [1, 1, 1, 0, 0],
        "venue": ["polymarket"] * 5})
    path = tmp_path / "t.parquet"
    raw.to_parquet(path)
    out = S.load_ticks(path)
    # first tick of each game is informative; a repeated price is not
    assert out["informative"].tolist() == [True, False, True, True, False]
    assert out["home"].tolist()[0] == "BOS" and out["away"].tolist()[0] == "NYK"


def test_asof_prior_never_sees_a_game_on_or_after_its_own_date():
    frame = _ticks(n_games=1, per_game=2)
    frame["game_date"] = "2025-01-10"
    base = pd.DataFrame({"game_id": [1], "date": ["2025-01-05"], "season": ["2024-25"],
                         "home_team": ["BOS"], "away_team": ["NYK"], "home_win": [1.0]})
    same_day = pd.concat([base, base.assign(game_id=2, date="2025-01-10", home_win=0.0)], ignore_index=True)
    later = pd.concat([base, base.assign(game_id=3, date="2025-02-01", home_win=0.0)], ignore_index=True)
    p_base = S.asof_priors(frame, base)[100][0]
    assert S.asof_priors(frame, same_day)[100][0] == p_base, "a same-day game reached the prior"
    assert S.asof_priors(frame, later)[100][0] == p_base, "a later game reached the prior"
    assert S.asof_priors(frame, base)[100][1] == "2025-01-10"


def test_no_future_read_guard_fires_on_a_planted_later_tick_read():
    frame = _ticks()
    priors = _priors(frame)
    scored = S.price(frame, priors)
    assert S.assert_no_future_read(scored, priors)["max_abs_delta"] == 0.0
    leaked = scored.copy()
    # plant the classic leak: each tick priced off its game's LAST tick instead of its own state
    leaked["model"] = leaked.groupby("game_id")["model"].transform("last")
    with pytest.raises(S.AsOfLeak):
        S.assert_no_future_read(leaked, priors)


def test_screen_side_is_disjoint_and_cells_reproduce_their_own_brier():
    frame = _ticks(n_games=6)
    screen, part = S.screen_side(frame)
    assert set(part.screen_ids) & set(part.verdict_ids) == set()
    assert set(screen["game_id"].astype(str)) <= set(part.screen_ids)
    assert len(part.screen_ids) + len(part.verdict_ids) == 6
    scored = S.price(frame, _priors(frame))
    cell = S._cell(scored)
    y = scored["y"].to_numpy()
    assert cell["brier_model"] == pytest.approx(float(np.mean((scored["model"] - y) ** 2)), abs=1e-12)
    assert cell["brier_market"] == pytest.approx(float(np.mean((scored["market"] - y) ** 2)), abs=1e-12)
    assert cell["improvement_vs_market"] == pytest.approx(cell["brier_market"] - cell["brier_model"], abs=1e-12)
    assert 0.0 < cell["n_eff"] <= cell["n"]
