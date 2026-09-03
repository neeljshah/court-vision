"""Per-file test for S114 -- the nested-selection in-game ensemble.

The one thing this row can get wrong is leaking the selection into the scored rows, so the
first test asserts the nesting itself: every fold's ranking rows are disjoint from that
fold's scored rows AND strictly earlier. The rest pin the S79 pick rule, the FIXED market
offset, the missing != bad fallback, and the uncharged/no-bar-moved rails.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.eval_gate import s114_ingame_ensemble as s114
from scripts.platformkit.foundry import ingame_grammar_nba as grammar
from scripts.platformkit.foundry.ingame_screen import BAR

GAMES_PER_BLOCK, TICKS, BLOCKS = 15, 120, 4


def _corpus() -> pd.DataFrame:
    """A synthetic tick corpus with load_screen's schema: 60 games, 120 ticks each."""
    rng = np.random.default_rng(11)
    records = []
    for index in range(GAMES_PER_BLOCK * BLOCKS):
        day = pd.Timestamp("2025-01-01") + pd.Timedelta(days=index)
        drift = rng.normal(0.0, 4.0)
        for tick in range(TICKS):
            stamp = day + pd.Timedelta(hours=12, seconds=30 * tick)
            margin = float(np.round(drift * tick / TICKS + rng.normal(0.0, 1.0)))
            elapsed = 0.5 + 48.0 * tick / TICKS
            records.append({"game": "g%03d" % index, "ts": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "ts_unix": float(stamp.value // 10 ** 9), "date": str(day.date()),
                            "period": 1 + min(3, int(4 * tick / TICKS)), "margin": margin,
                            "score_home": 50.0 + margin, "score_away": 50.0,
                            "elapsed": elapsed, "rem": 48.0 - elapsed,
                            "game_date": "F%d" % (index // GAMES_PER_BLOCK)})
    frame = pd.DataFrame(records)
    price = 1.0 / (1.0 + np.exp(-0.5 * frame["margin"] / 6.0))
    frame["market"] = frame["p_e4"] = frame["model"] = price
    frame["informative"] = True
    outcome = frame.groupby("game")["margin"].transform("last") > 0
    frame["y"] = outcome.astype(float)
    return frame


@pytest.fixture(scope="module")
def scored():
    rows = _corpus()
    grid = grammar.build_grid(rows[list(grammar.REQUIRED)].assign(ts=rows["ts_unix"]))
    hypotheses = {grammar.hypothesis_label(h): h for h in grammar.enumerate_hypotheses()
                  if not grammar.hypothesis_phase(h)}
    hypotheses = dict(list(hypotheses.items())[:8])
    return rows, s114.run(rows, grid, hypotheses, verbose=False)


def test_selection_rows_are_disjoint_from_and_earlier_than_the_scored_rows(scored):
    """THE nesting assertion: nothing the ranking saw is ever scored (Q4)."""
    rows, result = scored
    folds = [f for f in result["folds"] if f["status"] == "OK"]
    assert len(folds) >= 2, "the walk-forward produced too few scored folds to test"
    for fold in folds:
        test = rows[rows["game_date"] == fold["fold"]]
        train, _cut = s114.purge(rows, test)
        inner_train, inner_test = s114.inner_split(train)
        assert fold["n_inner_train"] == len(inner_train) > 0
        for side in (inner_train, inner_test):
            assert not set(side["game"]) & set(test["game"])
            assert side["ts"].max() < test["ts"].min()
        assert not set(inner_train["game"]) & set(inner_test["game"])
        assert inner_train["ts"].max() < inner_test["ts"].min()


def test_every_scored_tick_gets_a_probability_for_every_k(scored):
    _rows, result = scored
    series = result["series"]
    assert len(series) > 0 and series["p_null"].between(0.0, 1.0).all()
    for k in s114.K_VALUES:
        column = "p_k%d" % k
        assert series[column].notna().all() and series[column].between(0.0, 1.0).all()
    assert len(series) == len(series.drop_duplicates(["game", "ts"]))


def test_select_topk_takes_one_hypothesis_per_source_column():
    screens = [{"label": "a|raw", "source": "a", "improvement": 0.1, "p_raw": 0.01},
               {"label": "a|ew5", "source": "a", "improvement": 0.09, "p_raw": 0.02},
               {"label": "b|raw", "source": "b", "improvement": 0.05, "p_raw": 0.03},
               {"label": "c|raw", "source": "c", "improvement": -0.5, "p_raw": 0.001}]
    picked = s114.select_topk(screens, 3)
    assert [s["label"] for s in picked] == ["a|raw", "b|raw"]      # c is negative, a|ew5 dupes
    assert [s["label"] for s in s114.select_topk(screens, 1)] == ["a|raw"]


def test_fit_offset_holds_the_market_coefficient_at_one():
    rng = np.random.default_rng(3)
    offset = rng.normal(0.0, 1.0, 4000)
    x = rng.normal(0.0, 1.0, 4000)
    y = (rng.random(4000) < 1.0 / (1.0 + np.exp(-(offset + 0.3 + 0.8 * x)))).astype(float)
    design = np.column_stack([np.ones(4000), x])
    weights = s114.fit_offset(design, y, offset)
    assert weights[0] == pytest.approx(0.3, abs=0.15)
    assert weights[1] == pytest.approx(0.8, abs=0.15)
    shifted = s114.fit_offset(design, y, offset + 1.0)
    assert shifted[0] == pytest.approx(weights[0] - 1.0, abs=0.15), "the offset moved with a fit"


def test_screen_one_falls_back_to_the_null_on_a_missing_feature():
    rng = np.random.default_rng(5)
    frame = pd.DataFrame({"game": ["g%d" % (i // 100) for i in range(2000)],
                          "p_e4": rng.uniform(0.2, 0.8, 2000)})
    frame["y"] = (rng.random(2000) < frame["p_e4"]).astype(float)
    frame["x"] = rng.normal(0.0, 1.0, 2000)
    blind = frame.copy()
    blind["x"] = np.nan
    assert s114.screen_one(frame, blind, "x")["improvement"] == pytest.approx(0.0, abs=1e-12)


def test_uncharged_and_no_bar_moved():
    body = open(s114.__file__, encoding="ascii").read()
    for token in ("_charge_ledger", "backtest_runner", "backtest_fwer", "prereg_sha256",
                  "charge_tier", "data/registry"):
        assert token not in body, "S114 must not touch %s" % token
    assert "\nBAR = " not in body, "BAR must be imported from the S82 tier, never redefined"
    assert s114.BAR == BAR == 0.004
    assert s114.K_VALUES == (1, 3, 5, 10) and s114.Q_WITHIN == 0.05


def test_pbo_is_one_when_the_in_sample_winner_is_always_the_out_of_sample_loser():
    matrix = {"F1": {1: 1.0, 3: 0.0}, "F2": {1: 1.0, 3: 0.0},
              "F3": {1: 0.0, 3: 1.0}, "F4": {1: 0.0, 3: 1.0}}
    assert s114.pbo(matrix, (1, 3))["pbo"] == pytest.approx(1.0)
    agree = {f: {1: 1.0, 3: 0.0} for f in matrix}
    assert s114.pbo(agree, (1, 3))["pbo"] == pytest.approx(0.0)


def test_the_purge_holds_in_every_timestamp_spelling():
    """S125: `purge` compared stamp STRINGS to a strftime'd cut and ' ' sorts before 'T', so a
    space-separated spelling admitted a train game that settled 2 h before the fold."""
    train_ts = [pd.Timestamp("2026-07-05T21:00:00") + pd.Timedelta(minutes=15 * i) for i in range(8)]
    test_ts = [pd.Timestamp("2026-07-06T01:00:00") + pd.Timedelta(minutes=15 * i) for i in range(8)]

    def _frame(fmt):
        return pd.DataFrame([{"game": game, "ts": fmt(stamp), "y": 1.0, "p_e4": 0.5}
                             for game, stamps in (("TRAIN", train_ts), ("TEST", test_ts))
                             for stamp in stamps])

    for fmt in (lambda s: s.strftime("%Y-%m-%dT%H:%M:%SZ"), str, lambda s: s.isoformat()):
        rows = _frame(fmt)
        train, cut = s114.purge(rows, rows[rows["game"] == "TEST"])
        assert len(train) == 0 and cut == "2026-07-05T01:00:00Z", (fmt(train_ts[0]), cut)


def test_the_null_arm_is_fit_on_the_same_rows_as_the_k_arm(scored):
    """S126: `recal_null` was fit on the whole outer train window while `ensemble_fold` fit on
    the all-finite subset, so the published ladder compared ROW SETS as well as k. Every
    scored fold now publishes n_fit / n_null_fit / n_scored, and the two fit counts agree."""
    _rows, result = scored
    folds = [f for f in result["folds"] if f["status"] == "OK"]
    assert folds, "the walk-forward produced no scored fold"
    for fold in folds:
        for key, meta in fold["fits"].items():
            assert {"n_fit", "n_null_fit", "n_scored"} <= set(meta), (key, meta)
            if meta["status"] == "OK":
                assert meta["n_fit"] == meta["n_null_fit"], (fold["fold"], key, meta)


def test_every_k_arm_carries_its_own_null_series(scored):
    """The same-rows null must reach the archived differential, or the re-quote cannot see it."""
    _rows, result = scored
    series = result["series"]
    for k in s114.K_VALUES:
        assert "p_null_k%d" % k in series.columns
        arm, null = series["p_k%d" % k].to_numpy(), series["p_null_k%d" % k].to_numpy()
        fallback = arm == null            # the rows the arm could not score natively
        assert bool(fallback.any()) or bool((~fallback).any())
        assert np.isfinite(null).all()
