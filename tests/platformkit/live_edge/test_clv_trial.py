"""Fixture-math integrity test for the CLV trial aggregation layer. Proves:
CLV-units correctness (reuses shadow_ledger.grade_row, not reimplemented),
same-book vs cross-venue suspect filtering, and bootstrap CI computation --
on a synthetic set of predictions + KNOWN closes, so the expected numbers can
be hand-verified.
"""
from __future__ import annotations

from scripts.platformkit.live_edge.clv.clv_trial import (
    aggregate_trial, clv_distribution, conditioned_delta, market_family,
    prob_point_clv, robust_clv_stats, robust_verdict_label, same_book_split,
    selection_policy, share_beating_close, stake_weighted_mean, trimmed_mean,
    verdict_label)
from scripts.platformkit.live_edge.shadow.shadow_ledger import grade_row


def _row(sport, market, book, uncond, cond, price):
    return {
        "ts": "t", "sport": sport, "game": "g", "market": market, "book": book,
        "unconditioned_pred": uncond, "conditioned_pred": cond,
        "market_price": price, "edge_claimed": False,
    }


def test_market_family_takes_last_dot_segment():
    assert market_family("pregame.moneyline") == "moneyline"
    assert market_family("mlb_ingame.base_out") == "base_out"
    assert market_family(None) == "unknown"


def test_grade_row_clv_units_known_values():
    # close moved UP from the captured price (0.50 -> 0.60): sign=+1.
    # clv_units(pred) = (pred - market_price) * sign.
    close = {"prob_home_devig": 0.60, "source": "kalshi", "ts": 1}
    row = _row("nba", "pregame.moneyline", "kalshi", 0.55, 0.58, 0.50)
    graded = grade_row(row, close)
    assert graded["unconditioned_clv_units"] == (0.55 - 0.50) * 1.0
    assert graded["conditioned_clv_units"] == (0.58 - 0.50) * 1.0
    assert graded["is_clv_suspect"] is False  # book == close_source


def test_same_book_split_flags_cross_venue():
    close = {"prob_home_devig": 0.60, "source": "kalshi", "ts": 1}
    same_row = grade_row(_row("nba", "pregame.moneyline", "kalshi", 0.55, 0.58, 0.50), close)
    cross_row = grade_row(_row("nba", "pregame.moneyline", "fanduel", 0.55, 0.58, 0.50), close)
    same, suspect = same_book_split([same_row, cross_row])
    assert same == [same_row]
    assert suspect == [cross_row]


def test_clv_distribution_matches_hand_computed_stats():
    vals = [1.0, 2.0, 3.0, 4.0]
    d = clv_distribution(vals)
    assert d["n"] == 4
    assert d["median"] == 2.5
    assert d["mean"] == 2.5
    # bootstrap CI must bracket the sample mean and never be pathological
    lo, hi = d["ci95"]
    assert lo <= 2.5 <= hi

    empty = clv_distribution([])
    assert empty == {"n": 0, "median": None, "iqr": [None, None], "mean": None,
                      "ci95": [None, None]}


def test_conditioned_delta_is_positive_when_conditioning_helps():
    close = {"prob_home_devig": 0.60, "source": "kalshi", "ts": 1}
    rows = [grade_row(_row("nba", "pregame.moneyline", "kalshi", 0.50, 0.58, 0.50), close)]
    delta = conditioned_delta(rows)
    # conditioned_clv (0.08) - unconditioned_clv (0.00) = 0.08
    assert delta["median"] == 0.08


def test_selection_policy_thresholds_on_pred_vs_price_divergence():
    close = {"prob_home_devig": 0.60, "source": "kalshi", "ts": 1}
    big_move = grade_row(_row("nba", "pregame.moneyline", "kalshi", 0.55, 0.58, 0.50), close)
    small_move = grade_row(_row("nba", "pregame.moneyline", "kalshi", 0.501, 0.502, 0.50), close)
    sel = selection_policy([big_move, small_move], threshold=0.03)
    assert sel["n_candidates"] == 2
    assert sel["n_selected"] == 1  # only big_move clears |0.58-0.50|=0.08 >= 0.03
    assert sel["n_selected_same_book"] == 1
    assert sel["n_selected_suspect"] == 0


def test_verdict_label_insufficient_data_below_min_n():
    assert verdict_label((0.01, 0.02), n=3) == "INSUFFICIENT_DATA"
    assert verdict_label((0.01, 0.02), n=20) == "AHEAD_OF_CLOSE (provisional)"
    assert verdict_label((-0.02, -0.01), n=20) == "BEHIND_CLOSE (provisional)"
    assert verdict_label((-0.01, 0.02), n=20) == "PAR_WITH_CLOSE (provisional)"


def test_aggregate_trial_end_to_end_fixture_and_never_claims_edge():
    close_a = {"prob_home_devig": 0.60, "source": "kalshi", "ts": 1}
    close_b = {"prob_home_devig": 0.45, "source": "fanduel", "ts": 2}
    rows = [
        grade_row(_row("nba", "pregame.moneyline", "kalshi", 0.55, 0.58, 0.50), close_a),
        grade_row(_row("nba", "pregame.moneyline", "espn:DraftKings", 0.50, 0.50, 0.50), close_a),
        grade_row(_row("mlb", "pregame.total", "fanduel", 0.40, 0.42, 0.41), close_b),
    ]
    board = aggregate_trial(rows)
    assert board["edge_claimed"] is False
    assert board["n_rows_total"] == 3
    assert board["n_same_book"] == 2  # kalshi/kalshi + fanduel/fanduel
    assert board["n_suspect_cross_venue"] == 1  # espn:DraftKings vs kalshi close
    assert "nba.moneyline" in board["families"]
    assert "mlb.total" in board["families"]
    assert set(board["per_sport"].keys()) == {"nba", "mlb"}


# ---------------------------------------------------------------------------
# Robust verdict -- the exact false-positive bug (longshot-skewed mean vs
# negative median) must NOT come back AHEAD.
# ---------------------------------------------------------------------------

def _longshot_skewed_population(n_losers=20, n_winners=1):
    """Mirrors the real 981-bet bug shape: most bets lose a little (median
    negative, most bets don't beat close), a couple of longshots win huge on
    a percent basis and drag the raw mean positive."""
    losers = [-3.0] * n_losers
    winners = [80.0] * n_winners
    return losers + winners


def test_share_beating_close_and_trimmed_mean_resist_longshot_skew():
    vals = _longshot_skewed_population()
    assert share_beating_close(vals) < 0.5
    # raw mean is dragged positive by the longshot; trimmed mean is not.
    assert (sum(vals) / len(vals)) > 0
    assert trimmed_mean(vals, trim=0.1) < 0


def test_stake_weighted_mean_matches_hand_computed():
    vals = [10.0, -10.0]
    weights = [3.0, 1.0]
    assert stake_weighted_mean(vals, weights) == 5.0  # (30-10)/4


def test_prob_point_clv_bounded_unlike_clv_pct():
    # a longshot taken at implied .05 vs fair close .10 has clv_pct=100% but
    # only 5 probability points -- prob_point_clv must stay bounded.
    assert prob_point_clv(fair_close_prob=0.10, taken_implied_prob=0.05) == 5.0


def test_robust_verdict_rejects_the_real_bug_shape_ahead_via_mean_skew():
    vals = _longshot_skewed_population()
    stats = robust_clv_stats(vals)
    verdict = robust_verdict_label(stats, min_n=5)
    # the legacy mean-CI verdict would call this AHEAD (mean > 0); the robust
    # verdict must not, because median<0 and share<50%.
    assert verdict != "AHEAD_OF_CLOSE (provisional)"
    assert verdict == "BEHIND_CLOSE (provisional)"


def test_robust_verdict_ahead_requires_all_four_conditions():
    # a genuinely robust win: most bets beat close, median positive, trimmed
    # CI excludes 0, probability-point agrees.
    vals = [2.0] * 15 + [-1.0] * 5
    pp = [1.5] * 15 + [-0.5] * 5
    stats = robust_clv_stats(vals, prob_point_values=pp)
    assert robust_verdict_label(stats, min_n=5) == "AHEAD_OF_CLOSE (provisional)"
