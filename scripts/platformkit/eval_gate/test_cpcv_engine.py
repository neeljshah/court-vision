"""Tests for the CPCV engine: golden parity, redaction parity, purge/embargo, vintage."""
from __future__ import annotations

from datetime import datetime

import pytest

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.walkforward import walk_forward


def _state(game_id, ts, home, away, x, outcome):
    return {
        "game_id": game_id, "state_ts": ts, "home": home, "away": away,
        "features": {"x": x},
        "feature_avail": {"x": ts[:10] + "T00:00:00"},  # same-day, strictly before state_ts
        "devig_close_prob": 0.5, "truth_wp": 0.5, "outcome": outcome,
    }


def _series(n=20):
    """n strictly time-ordered states, distinct teams per game (no team purge)."""
    return [
        _state(f"g{i}", f"2024-05-{i + 1:02d}T19:00:00", f"H{i}", f"V{i}",
               x=i / (n - 1), outcome=1 if i / (n - 1) >= 0.5 else 0)
        for i in range(n)
    ]


def _brier(records):
    return sum((r["p_model"] - r["y"]) ** 2 for r in records) / len(records)


def _capture(sink):
    """Predictor that records the exact view it was handed, keyed by game_id."""
    def _predict(train, test, select_inside):
        sink.setdefault(test["game_id"], test)
        return 0.5
    return _predict


def test_golden_parity_brier_ranking():
    # Both predictors ignore train entirely, so they are leak-free by
    # construction under either harness and the ranking is comparable.
    states = _series()

    def good(train, test, select_inside):
        return test["features"]["x"]

    def bad(train, test, select_inside):
        return 0.5

    wf_good = walk_forward(states, good).records
    wf_bad = walk_forward(states, bad).records
    cpcv_good = cpcv_evaluate(states, good, n_groups=8, n_test_groups=2, embargo_days=1)
    cpcv_bad = cpcv_evaluate(states, bad, n_groups=8, n_test_groups=2, embargo_days=1)

    assert _brier(wf_good) < _brier(wf_bad)
    assert _brier(cpcv_good) < _brier(cpcv_bad)

    # predictor ignores train -> per-game prediction must match exactly
    # across both harnesses, not just its Brier ranking.
    wf_p = {r["game_id"]: r["p_model"] for r in wf_good}
    assert all(r["p_model"] == wf_p[r["game_id"]] for r in cpcv_good)


def test_redaction_parity_field_by_field():
    # cpcv_engine hand-copies walk_forward's redaction tuple, so compare the
    # ACTUAL view each harness hands the predictor, key by key and value by
    # value. A Brier-only parity check cannot see this drift.
    states = _series()
    wf_views, cp_views = {}, {}
    walk_forward(states, _capture(wf_views))
    cpcv_evaluate(states, _capture(cp_views), n_groups=8, n_test_groups=2, embargo_days=1)

    assert set(wf_views) == set(cp_views) == {s["game_id"] for s in states}
    for game_id, wf_view in wf_views.items():
        assert wf_view == cp_views[game_id], f"redacted view drifted for {game_id}"

    # non-vacuity: the source state carries all three graded keys, and BOTH
    # harnesses drop exactly those three -- nothing more, nothing less.
    source = states[0]
    expected = {"outcome", "devig_close_prob", "truth_wp"}
    assert expected <= set(source)
    assert set(source) - set(wf_views["g0"]) == expected
    assert set(source) - set(cp_views["g0"]) == expected


def test_embargo_purges_near_dates_both_sides():
    # 6 distinct consecutive days, one game each, distinct teams. A CPCV train
    # set straddles the test block, so this proves BOTH sides are embargoed.
    days = [f"2024-04-0{d}T19:00:00" for d in range(1, 7)]
    states = [_state(f"g{d}", days[d - 1], f"H{d}", f"V{d}", x=0.5, outcome=d % 2)
              for d in range(1, 7)]
    embargo_days = 1
    sides = []

    def cheater(train, test, select_inside):
        test_date = datetime.fromisoformat(test["state_ts"]).date()
        sides.extend(
            (datetime.fromisoformat(t["state_ts"]).date() - test_date).days for t in train
        )
        return 0.5

    records = cpcv_evaluate(states, cheater, n_groups=6, n_test_groups=1,
                            embargo_days=embargo_days)
    assert len(records) == 6
    assert sides, "train sets were all empty -- the assertion below would be vacuous"
    assert all(abs(d) > embargo_days for d in sides)


def test_same_team_purge_survives_the_day_window():
    # g0 and g2 are 47h apart (inside walk_forward's 48h same-team purge) but 2
    # calendar days apart, so the 1-day embargo window alone would NOT drop it.
    states = [
        _state("g0", "2024-07-01T19:00:00", "AAA", "BBB", x=0.5, outcome=1),
        _state("g1", "2024-07-02T19:00:00", "CCC", "DDD", x=0.5, outcome=0),
        _state("g2", "2024-07-03T18:00:00", "AAA", "EEE", x=0.5, outcome=1),
        _state("g3", "2024-07-04T19:00:00", "FFF", "GGG", x=0.5, outcome=0),
    ]
    trains = {}

    def record_train(train, test, select_inside):
        trains[test["game_id"]] = {t["game_id"] for t in train}
        return 0.5

    cpcv_evaluate(states, record_train, n_groups=4, n_test_groups=1, embargo_days=1)
    # g1 is 1 day out (embargo), g2 shares AAA within 48h (team purge), g3 is 3
    # days out with no shared team -- so it is the only row that may train.
    assert trains["g0"] == {"g3"}


def test_future_feature_avail_raises():
    bad = _state("bad", "2024-06-01T19:00:00", "A", "B", x=0.5, outcome=0)
    bad["feature_avail"] = {"x": "2024-06-02T00:00:00"}  # AFTER state_ts: leak
    good = _state("good", "2024-06-02T19:00:00", "C", "D", x=0.5, outcome=1)

    with pytest.raises(AssertionError, match="LEAK"):
        cpcv_evaluate([bad, good], lambda tr, te, si: 0.5,
                      n_groups=2, n_test_groups=1, embargo_days=1)
