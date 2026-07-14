"""Fixture-math integrity test for the CLV trial aggregation layer. Proves:
CLV-units correctness (reuses shadow_ledger.grade_row, not reimplemented),
same-book vs cross-venue suspect filtering, and bootstrap CI computation --
on a synthetic set of predictions + KNOWN closes, so the expected numbers can
be hand-verified.
"""
from __future__ import annotations

from scripts.platformkit.live_edge.clv.clv_trial import (
    aggregate_trial, clv_distribution, conditioned_delta, market_family,
    same_book_split, selection_policy, verdict_label)
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
