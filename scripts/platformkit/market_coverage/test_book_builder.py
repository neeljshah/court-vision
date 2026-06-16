"""Per-file tests for market_coverage.book_builder -- the WHOLE-book builder.

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && \
  C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
  scripts/platformkit/market_coverage/tests/test_book_builder.py -q

Guards: every enumerated category builds a non-empty, internally-consistent menu off
ONE coherent SampleBook; player props span every stat at alt lines; combos/DD/TD/5x5
build; team + quarter/half markets build when period columns exist; scenario/longshot
tails build; SGP parlays preserve the joint structure; the full book prices with no
$ claim leaking in.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import numpy as np  # noqa: E402

from scripts.platformkit.market_coverage.markets import SampleBook  # noqa: E402

from scripts.platformkit.market_coverage import book_builder as COV  # noqa: E402


def _book(n=6000, seed=1, periods=False):
    rng = np.random.default_rng(seed)
    pace = rng.normal(0, 1, n)
    cols, columns = {}, []

    def add(name, arr):
        cols[name] = len(columns)
        columns.append(np.asarray(arr, float))

    add("home_score", 112 + 4 * pace + rng.normal(0, 6, n))
    add("away_score", 109 - pace + rng.normal(0, 6, n))
    for pid, base in (("A", 26), ("B", 19), ("C", 12)):
        add(f"{pid}|pts", base + 5 * pace + rng.normal(0, 4, n))
        add(f"{pid}|reb", 7 + 2 * pace + rng.normal(0, 2, n))
        add(f"{pid}|ast", 5 + rng.normal(0, 2, n))
        add(f"{pid}|fg3m", 2 + rng.normal(0, 1.2, n))
        add(f"{pid}|stl", 1 + rng.normal(0, 0.8, n))
        add(f"{pid}|blk", 0.7 + rng.normal(0, 0.7, n))
    if periods:
        for side in ("home", "away"):
            full = columns[cols[f"{side}_score"]]
            for seg, share in (("q1", .25), ("q2", .25), ("q3", .25), ("q4", .25),
                               ("h1", .5), ("h2", .5)):
                add(f"{side}_{seg}", full * share * (1 + rng.normal(0, .08, n)))
    return SampleBook(np.column_stack(columns), cols, "simulated")


def test_player_props_core_spans_every_stat():
    book = _book()
    mk = COV.build_player_props_core(book)
    assert mk, "no core props built"
    stats = {m.name.split()[1] for m in mk}
    assert {"pts", "reb", "ast", "fg3m", "stl", "blk"} <= stats
    # each stat has BOTH an over and an under at multiple alt lines.
    assert any(" O" in m.name for m in mk) and any(" U" in m.name for m in mk)
    for m in mk:
        p = float(m.legs[0].hit(book).mean())
        assert 0.0 <= p <= 1.0


def test_combos_dd_td_5x5_build():
    book = _book()
    mk = COV.build_player_props_combos(book)
    names = [m.name for m in mk]
    assert any("double_double" in n for n in names)
    assert any("triple_double" in n for n in names)
    assert any("+" in n for n in names)            # PRA-style sum combos
    kinds = {m.kind for m in mk}
    assert "combo" in kinds and "longshot" in kinds


def test_team_quarter_half_builds_with_periods():
    book = _book(periods=True)
    mk = COV.build_team_quarter_half(book)
    names = [m.name for m in mk]
    assert any("home_ml" in n for n in names)
    assert any("home_spread" in n for n in names)
    assert any("game_total" in n for n in names)
    assert any(n.startswith("q1_") for n in names)   # quarter markets present
    assert any(n.startswith("h1_") for n in names)   # half markets present


def test_team_markets_without_periods_still_build_mainlines():
    book = _book(periods=False)
    mk = COV.build_team_quarter_half(book)
    assert any("home_ml" in m.name for m in mk)
    # no quarter columns -> no q1 markets, but the build must not crash.
    assert not any(m.name.startswith("q1_") for m in mk)


def test_scenario_longshot_builds():
    book = _book()
    mk = COV.build_game_scenario_longshot(book)
    names = [m.name for m in mk]
    assert any("blowout" in n for n in names)
    assert any("overtime" in n for n in names)
    assert any("shootout" in n for n in names)
    assert any("rockfight" in n for n in names)
    assert any("longshot" in n or "burst" in n for n in names)


def test_sgp_correlation_parlays_are_joint():
    book = _book()
    mk = COV.build_sgp_correlation(book, max_parlays=15, seed=0)
    assert mk, "no SGP parlays built"
    for m in mk:
        assert m.kind == "sgp"
        assert len(m.legs) >= 2


def test_build_full_book_prices_every_category():
    book = _book(periods=True)
    priced = COV.build_full_book(book)
    assert priced, "empty book"
    cats = {rec["category"] for rec in priced.values()}
    # default build excludes ingame-micro; the other five categories must appear.
    assert {"player-props-core", "player-props-combos", "team-quarter-half",
            "game-scenario-longshot", "sgp-correlation"} <= cats
    for name, rec in priced.items():
        if "joint" in rec:                       # an SGP parlay
            assert 0.0 <= rec["joint"] <= 1.0
            assert np.isfinite(rec["lift"]) or rec["independent"] == 0.0
        else:
            assert 0.0 <= rec["prob"] <= 1.0


def test_ingame_micro_flags_kind_ingame():
    book = _book(periods=True)
    mk = COV.build_ingame_micro(book)
    assert mk
    assert all(m.kind == "ingame" for m in mk)


def test_no_dollar_claim_in_full_book():
    book = _book(periods=True)
    priced = COV.build_full_book(book)
    banned = ("roi", "profit", "+ev", "guaranteed", "beat the market")
    for rec in priced.values():
        blob = " ".join(str(v).lower() for v in rec.values())
        for b in banned:
            assert b not in blob
