"""Focused synthetic tests for the online Hedge combiner over K shadow arms."""
from __future__ import annotations

import math
from collections import defaultdict

import pytest

from scripts.platformkit.ingame import hedge_combiner as hc


def _fixture(n_dates: int = 4, games_per_date: int = 3, ticks_per_game: int = 2):
    """Multi-date, multi-game corpus. 'good' arm always correct; 'bad' always wrong."""
    ticks: list[dict[str, object]] = []
    for day in range(n_dates):
        date = "2026-01-%02d" % (day + 1)
        for gnum in range(games_per_date):
            game, outcome = "G%02d_%02d" % (day, gnum), float((day + gnum) % 2)
            for _ in range(ticks_per_game):
                ticks.append({"game": game, "date": date, "outcome": outcome, "market_prob": .5,
                              "in_window": True})
    good = [float(row["outcome"]) for row in ticks]
    bad = [1.0 - float(row["outcome"]) for row in ticks]
    return ticks, {"good": good, "bad": bad}


def _constant_loss_fixture(plan):
    """'steady' scores Brier 0.09 and 'worse' 0.25 on EVERY game, so the
    comparator's cumulative loss must equal 0.09 * rounds Hedge predicted."""
    ticks: list[dict[str, object]] = []
    for day, (date, n_games) in enumerate(plan):
        for gnum in range(n_games):
            outcome = float((day + gnum) % 2)
            ticks.append({"game": "G%02d_%02d" % (day, gnum), "date": date,
                          "outcome": outcome, "market_prob": .5, "in_window": True})
    steady = [0.7 if row["outcome"] == 1.0 else 0.3 for row in ticks]
    worse = [0.5] * len(ticks)
    return ticks, {"steady": steady, "worse": worse}


def test_uniform_start_reproduces_simple_average() -> None:
    state = hc.initial_state(["a", "b"], t_rounds=10)
    assert state.weights == (0.5, 0.5)
    assert hc.predict(state, {"a": 0.2, "b": 0.6}) == pytest.approx(0.4)


# (b) always-wrong arm loses weight monotonically; perfect arm gains it
def test_wrong_arm_loses_weight_monotonically() -> None:
    state = hc.initial_state(["perfect", "wrong"], t_rounds=20)
    trail = [state.weights[1]]
    for i in range(10):
        outcome = float(i % 2)
        state = hc.fold_settlement(state, "g%d" % i,
                                   {"perfect": [outcome], "wrong": [1.0 - outcome]}, outcome)
        trail.append(state.weights[1])
    assert all(w2 <= w1 + 1e-15 for w1, w2 in zip(trail, trail[1:]))
    assert trail[-1] < trail[0]
    assert state.weights[0] > state.weights[1]


# (c) fold_settlement is idempotent on a repeated game_id
def test_fold_settlement_idempotent() -> None:
    state = hc.initial_state(["a", "b"], t_rounds=5)
    once = hc.fold_settlement(state, "g1", {"a": [0.9], "b": [0.1]}, 1.0)
    twice = hc.fold_settlement(once, "g1", {"a": [0.0], "b": [0.99]}, 0.0)
    assert twice.weights == once.weights
    assert twice.games_folded == once.games_folded


# (d) a missing arm never fabricates a probability, and is never updated
def test_missing_arm_not_fabricated_and_left_unchanged() -> None:
    state = hc.initial_state(["a", "b"], t_rounds=5)
    assert hc.predict(state, {"a": 0.7, "b": None}) == pytest.approx(0.7)
    assert hc.predict(state, {"a": None, "b": None}) is None
    # "weight unchanged" cashes out as an update identical to a zero-loss one
    missing = hc.fold_settlement(state, "g1", {"a": [0.9]}, 1.0)          # 'b' absent
    zero_loss = hc.fold_settlement(state, "g1", {"a": [0.9], "b": [1.0]}, 1.0)  # 'b' perfect
    assert missing.weights == pytest.approx(zero_loss.weights)


def test_date_ordering_assert_fires_on_violation() -> None:
    with pytest.raises(AssertionError):
        hc._assert_prior_date("2026-01-05", "2026-01-01")
    hc._assert_prior_date("2026-01-01", "2026-01-05")  # no raise


def test_weights_sum_to_one_and_no_nan_under_zero_loss_ties() -> None:
    state = hc.initial_state(["a", "b", "c"], t_rounds=10)
    assert sum(state.weights) == pytest.approx(1.0)
    for i in range(5):
        state = hc.fold_settlement(state, "g%d" % i, {"a": [0.5], "b": [0.5], "c": [0.5]}, 0.5)
        assert sum(state.weights) == pytest.approx(1.0)
        assert not any(math.isnan(w) for w in state.weights)
    assert state.weights == pytest.approx((1 / 3, 1 / 3, 1 / 3))


def test_k_equals_one_degenerates_to_single_arm() -> None:
    state = hc.initial_state(["solo"], t_rounds=10)
    assert state.weights == (1.0,) and state.eta == 0.0
    assert hc.predict(state, {"solo": 0.37}) == pytest.approx(0.37)
    updated = hc.fold_settlement(state, "g1", {"solo": [0.9, 0.1]}, 1.0)
    assert updated.weights == (1.0,)
    assert hc.predict(updated, {"solo": 0.8}) == pytest.approx(0.8)


def test_nan_arm_prob_is_treated_as_absent_not_as_data() -> None:
    state = hc.initial_state(["a", "b"], t_rounds=5)
    assert hc.predict(state, {"a": 0.7, "b": float("nan")}) == pytest.approx(0.7)
    assert hc.predict(state, {"a": float("inf"), "b": float("nan")}) is None
    # a NaN tick must leave that arm's weight untouched, exactly like an absent arm
    poisoned = hc.fold_settlement(state, "g1", {"a": [0.9], "b": [float("nan")]}, 1.0)
    absent = hc.fold_settlement(state, "g1", {"a": [0.9]}, 1.0)
    assert poisoned.weights == pytest.approx(absent.weights)
    assert all(math.isfinite(w) for w in poisoned.weights)
    # a non-finite SETTLEMENT is corrupt input, not an absence -- it must raise
    with pytest.raises(ValueError):
        hc.fold_settlement(state, "g2", {"a": [0.9], "b": [0.1]}, float("nan"))


def test_evaluate_counts_dropped_nonfinite_arm_probs() -> None:
    ticks, arm_probs = _fixture(n_dates=4, games_per_date=2, ticks_per_game=2)
    arm_probs["bad"] = list(arm_probs["bad"])
    arm_probs["bad"][0] = float("nan")
    arm_probs["bad"][5] = float("nan")
    report = hc.evaluate(ticks, arm_probs, t_rounds=20, bootstrap_iterations=10)
    assert report["status"] == "OK"
    assert report["n_nonfinite_arm_probs_dropped"] == 2
    metrics = report["slices"]["all_ticks"]["metrics"]
    assert math.isfinite(metrics["hedge_brier"])


def test_multi_date_game_is_pinned_to_its_earliest_tick_date() -> None:
    """A game straddling midnight must not be scored with weights that already
    absorbed a settlement postdating its first tick."""
    ticks = [{"game": "S", "date": "2026-01-05", "outcome": 1.0, "market_prob": .5},
             {"game": "S", "date": "2026-01-04", "outcome": 1.0, "market_prob": .5}]
    games, _ = hc._group_games(ticks, {"a": [0.6, 0.6]}, ("a",))
    assert games["S"]["date"] == "2026-01-04"   # earliest, not first-seen


def test_conflicting_settled_outcomes_for_one_game_raise() -> None:
    ticks = [{"game": "S", "date": "2026-01-04", "outcome": 1.0, "market_prob": .5},
             {"game": "S", "date": "2026-01-04", "outcome": 0.0, "market_prob": .5}]
    with pytest.raises(ValueError):
        hc._group_games(ticks, {"a": [0.6, 0.6]}, ("a",))


def test_regret_sums_hedge_and_comparator_over_the_same_round_set() -> None:
    """Date 0 is burn-in (folded, never predicted) and the last date is predicted
    but never folded: iterating the FOLDED set charged the comparator 5 rounds and
    Hedge 2, driving regret negative."""
    plan = [("2026-01-01", 3), ("2026-01-02", 1), ("2026-01-03", 1), ("2026-01-04", 1)]
    ticks, arm_probs = _constant_loss_fixture(plan)
    report = hc.evaluate(ticks, arm_probs, t_rounds=10, bootstrap_iterations=10)
    regret = report["regret_vs_best_arm"]
    assert regret["status"] == "OK"
    assert regret["best_arm"] == "steady"
    assert regret["n_rounds"] == 3                      # dates 2, 3 and 4 -- not 2
    assert regret["cumulative_best_arm_loss"] == pytest.approx(3 * 0.09)
    # Hedge mixes 0.7 and 0.5, so by convexity it can never beat the best arm.
    assert regret["regret"] > 0.0
    assert regret["within_bound"]


def test_regret_round_count_matches_the_scored_games() -> None:
    plan = [("2026-01-01", 2), ("2026-01-02", 4), ("2026-01-03", 3)]
    ticks, arm_probs = _constant_loss_fixture(plan)
    report = hc.evaluate(ticks, arm_probs, t_rounds=10, bootstrap_iterations=10)
    regret = report["regret_vs_best_arm"]
    assert regret["n_rounds"] == 7                      # 4 + 3 scored, 2 burn-in
    assert regret["n_batches"] == 2                     # Hoeffding runs over
    # date-BATCHES (4^2 + 3^2 = 25), not over the 7 rounds
    assert regret["loss_range_squares"] == pytest.approx(25.0)
    assert regret["within_bound"]
    # burn-in already moved 'steady' off 1/K (it outscores 'worse' on date 0),
    # and the bound must charge that actual start weight, not a fresh uniform one
    assert regret["bound"] < hc.regret_bound(report["eta"], 0.5, regret["loss_range_squares"])


def test_arm_absent_on_some_rounds_cannot_win_the_hindsight_comparison() -> None:
    """A partly-absent arm accrues an unfairly small cumulative loss."""
    ticks, arm_probs = _fixture(n_dates=5, games_per_date=2, ticks_per_game=1)
    arm_probs["ghost"] = [None] * len(ticks)            # never emits anything
    report = hc.evaluate(ticks, arm_probs, t_rounds=20, bootstrap_iterations=10)
    regret = report["regret_vs_best_arm"]
    assert "ghost" not in regret["eligible_arms"]
    assert regret["best_arm"] == "good"


def test_no_comparable_arm_is_reported_not_silently_skipped() -> None:
    """Alternating arms cover every round between them, but neither covers all,
    so no fixed arm is a legitimate hindsight comparator."""
    ticks, _ = _fixture(n_dates=5, games_per_date=1, ticks_per_game=1)
    evens = [float(row["outcome"]) if i % 2 == 0 else None for i, row in enumerate(ticks)]
    odds = [float(row["outcome"]) if i % 2 else None for i, row in enumerate(ticks)]
    report = hc.evaluate(ticks, {"evens": evens, "odds": odds}, t_rounds=10,
                         bootstrap_iterations=5)
    regret = report["regret_vs_best_arm"]
    assert regret["status"] == "NO_COMPARABLE_ARM"
    assert regret["n_rounds"] == 4
    assert "NO_COMPARABLE_ARM" in hc.render(report)


def test_evaluate_regret_within_bound_of_best_arm() -> None:
    ticks, arm_probs = _fixture(n_dates=15, games_per_date=3, ticks_per_game=2)
    # t_rounds is PRE-REGISTERED, deliberately != the realized 45 games
    report = hc.evaluate(ticks, arm_probs, t_rounds=50, bootstrap_iterations=20)
    assert report["status"] == "OK"
    assert report["eta"] == pytest.approx(math.sqrt(8.0 * math.log(2) / 50))
    regret = report["regret_vs_best_arm"]
    assert regret["best_arm"] == "good"
    assert regret["within_bound"]
    assert regret["regret"] <= regret["bound"] + 1e-9


def _walk_predictions(ticks, arm_probs, t_rounds):
    """White-box replay of evaluate()'s loop -> (date, game, hedge_prob) per
    scored tick, to inspect the prediction sequence for lookahead."""
    names = tuple(arm_probs)
    games, _ = hc._group_games(ticks, arm_probs, names)
    by_date: dict[str, list[str]] = defaultdict(list)
    for gid, game in games.items():
        by_date[game["date"]].append(gid)
    dates = sorted(by_date)
    state, out = hc.initial_state(names, t_rounds), []
    for idx in range(1, len(dates)):
        for gid in sorted(by_date[dates[idx - 1]]):
            game = games[gid]
            state = hc.fold_settlement(
                state, gid, {n: p for n, p in game["arm_ticks"].items() if p}, game["outcome"])
        for gid in sorted(by_date[dates[idx]]):
            for i in games[gid]["indices"]:
                out.append((dates[idx], gid,
                            hc.predict(state, {n: arm_probs[n][i] for n in names})))
    return out


def test_anti_lookahead_shuffling_future_outcomes_preserves_past_predictions() -> None:
    ticks, arm_probs = _fixture(n_dates=6, games_per_date=2, ticks_per_game=2)
    before = _walk_predictions(ticks, arm_probs, t_rounds=12)

    # Mutate ONLY the post-hoc settlement label for a MIDDLE date (folded AND
    # scored), holding the already-emitted arm probabilities fixed.
    mutate_date = "2026-01-04"
    mutated = [dict(row) for row in ticks]
    for row in mutated:
        if row["date"] == mutate_date:
            row["outcome"] = 1.0 - float(row["outcome"])
    after = _walk_predictions(mutated, arm_probs, t_rounds=12)
    before_prefix = [p for (date, _, p) in before if date <= mutate_date]
    after_prefix = [p for (date, _, p) in after if date <= mutate_date]
    assert before_prefix == after_prefix  # bit-identical prefix
    # sanity: a LATER date's prediction DOES move, so this test could fail.
    before_future = [p for (date, _, p) in before if date > mutate_date]
    after_future = [p for (date, _, p) in after if date > mutate_date]
    assert before_future != after_future


# (1) regime switch: "a" perfect in the first half, "b" in the second. Hedge
# must stay within each segment's own best-in-hindsight regret bound.
def test_regime_switch_tracking_within_piecewise_regret_bound() -> None:
    t1 = t2 = 20
    total = t1 + t2
    state = hc.initial_state(["a", "b"], t_rounds=total)
    hedge_seg1 = hedge_seg2 = a_seg1 = b_seg2 = 0.0
    weight_b_at_seg2_start = None
    for g in range(total):
        outcome = float(g % 2)
        in_seg1 = g < t1
        a_prob = outcome if in_seg1 else (1.0 - outcome)   # a: perfect seg1, worst seg2
        b_prob = (1.0 - outcome) if in_seg1 else outcome   # b: worst seg1, perfect seg2
        if g == t1:
            weight_b_at_seg2_start = state.weights[1]
        hedge_pred = hc.predict(state, {"a": a_prob, "b": b_prob})
        loss = (hedge_pred - outcome) ** 2
        if in_seg1:
            hedge_seg1 += loss
            a_seg1 += (a_prob - outcome) ** 2
        else:
            hedge_seg2 += loss
            b_seg2 += (b_prob - outcome) ** 2
        state = hc.fold_settlement(state, "g%d" % g, {"a": [a_prob], "b": [b_prob]}, outcome)
    # segment 1 starts from uniform weights: start_weight is a plain 1/K.
    bound_seg1 = hc.regret_bound(state.eta, 0.5, t1)
    assert hedge_seg1 - a_seg1 <= bound_seg1 + 1e-9

    # segment 2 starts mid-run with b's ACTUAL (shrunk) weight, not a fresh 1/K
    # -- exactly the burn-in case regret_bound's start_weight covers.
    bound_seg2 = hc.regret_bound(state.eta, weight_b_at_seg2_start, t2)
    assert hedge_seg2 - b_seg2 <= bound_seg2 + 1e-9


def test_regret_bound_collapses_to_the_classical_tuned_form() -> None:
    """At the tuned eta and a uniform start, the bound is sqrt(T*ln(K)/2)."""
    k, t = 4, 60
    eta = math.sqrt(8.0 * math.log(k) / t)
    assert hc.regret_bound(eta, 1.0 / k, t) == pytest.approx(math.sqrt(t * math.log(k) / 2))
    assert hc.regret_bound(0.0, 1.0, 10) == 0.0          # K == 1 degenerate
    with pytest.raises(ValueError):
        hc.regret_bound(0.5, 0.0, 10)
