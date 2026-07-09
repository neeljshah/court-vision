"""Per-file test for rung6_composite: as-of leak-freeness + composite shape + attach.
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/pitch_engine/test_rung6_composite.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb.pitch_engine import rung6_composite as r6
from domains.mlb.pitch_engine.game_sim import BaseOutTransition
from domains.mlb.pitch_engine.pa_chain import _PA_IX


def _pa(evix, date, batter, pitcher, gpk, half="Top"):
    return {"game_pk": gpk, "date": date, "inning": 1, "inning_topbot": half,
            "at_bat_number": 1, "batter": batter, "pitcher": pitcher, "evix": evix,
            "base_out_state": 0, "base_mask": 0, "outs_start": 0, "runs": 0,
            "pa_evt": "HR", "game_date": date, "home_team": "SF", "away_team": "LAD"}


def test_asof_is_strictly_prior():
    # batter 1 hits HR (evix 7) on d1, walks (evix 2) on d2. as-of d1 = empty; d2 sees d1.
    rows = [_pa(_PA_IX["HR"], "2025-04-01", 1, 9, 100),
            _pa(_PA_IX["BB"], "2025-04-02", 1, 9, 101)]
    pa = pd.DataFrame(rows)
    tbl = r6._asof_counts(pa, "batter")
    assert (1, "2025-04-01") not in tbl or tbl[(1, "2025-04-01")].sum() == 0
    prior_d2 = tbl[(1, "2025-04-02")]
    assert prior_d2[_PA_IX["HR"]] == 1 and prior_d2.sum() == 1  # only d1 counted


def test_tilt_and_dist_normalize():
    league = np.ones(8) / 8
    b = r6._dist(np.array([10.0, 0, 0, 0, 0, 0, 0, 0]), league)  # heavy OUT batter
    assert abs(b.sum() - 1.0) < 1e-9 and b[0] > league[0]
    t = r6._tilt(b, league, league)  # neutral pitcher -> stays like batter
    assert abs(t.sum() - 1.0) < 1e-9 and np.argmax(t) == 0


def test_composite_stronger_home_leans_positive():
    # build a tiny 1-game target where the home lineup is all sluggers, away all outs.
    league = np.ones(8) / 8
    trans = _toy_trans()
    bat_asof, pit_asof = {}, {}
    slug = np.zeros(8); slug[_PA_IX["HR"]] = 470.0; slug[_PA_IX["OUT"]] = 30.0  # mostly HR
    weak = np.zeros(8); weak[_PA_IX["OUT"]] = 500.0        # always OUT
    for b in range(1, 10):
        bat_asof[(b, "2025-05-01")] = slug.copy()          # home batters 1..9
        bat_asof[(b + 100, "2025-05-01")] = weak.copy()    # away batters 101..109
    g = pd.DataFrame([{"game_pk": 5, "date": "2025-05-01", "home_team": "SF",
                       "away_team": "LAD", "inning": 1,
                       "inning_topbot": "Bot" if b < 100 else "Top",
                       "at_bat_number": i, "batter": b, "pitcher": 999}
                      for i, b in enumerate(list(range(101, 110)) + list(range(1, 10)))])
    table = r6.build_composite_table(g, g, bat_asof, pit_asof, league, trans, n_sims=200)
    assert len(table) == 1
    assert table["p_home"].iloc[0] > 0.9        # sluggers at home crush
    assert table["composite"].iloc[0] > 0.0     # logit positive


def test_attach_train_missing_is_neutral():
    table = pd.DataFrame([{"date": "2025-05-01", "home": "SF", "away": "LAD",
                           "composite": 1.5, "p_home": 0.8}])
    df = pd.DataFrame([{"date": "2025-05-01", "home_team": "SF", "away_team": "LAD"},
                       {"date": "2025-05-01", "home_team": "NYY", "away_team": "BOS"}])
    out = r6.attach_composite_train(df, table)
    assert out["has_composite"].tolist() == [True, False]
    assert out["pa_composite"].iloc[0] == 1.5 and out["pa_composite"].iloc[1] == 0.0


def test_lookup_utc_rollover_plus_minus_one_day():
    td = {("2025-05-02", "SF", "LAD"): 0.7}
    # a tick parsed to the day before still resolves (UTC rollover landmine)
    assert r6._lookup_dated(td, "2025-05-01", "SF", "LAD") == 0.7
    assert r6._lookup_dated(td, "2025-05-09", "SF", "LAD") is None


def _toy_trans() -> BaseOutTransition:
    # hand-built semantically-correct base-out transition (empty bases only):
    # OUT advances outs 0->1->2->inning-over; HR scores 1 and keeps bases empty.
    OUT, HR, OVER = _PA_IX["OUT"], _PA_IX["HR"], 24
    a = lambda r, n: (np.array([r], np.int16), np.array([n], np.int16))
    cell = {0 * 8 + OUT: a(0, 1), 1 * 8 + OUT: a(0, 2), 2 * 8 + OUT: a(0, OVER),
            0 * 8 + HR: a(1, 0), 1 * 8 + HR: a(1, 1), 2 * 8 + HR: a(1, 2)}
    by_evt = {OUT: a(0, OVER), HR: a(1, 0)}
    return BaseOutTransition(cell, by_evt, min_cell=1)


if __name__ == "__main__":
    test_asof_is_strictly_prior()
    test_tilt_and_dist_normalize()
    test_composite_stronger_home_leans_positive()
    test_attach_train_missing_is_neutral()
    test_lookup_utc_rollover_plus_minus_one_day()
    print("ok")
