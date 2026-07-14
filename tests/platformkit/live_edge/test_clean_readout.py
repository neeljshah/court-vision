"""Integrity test for clean_readout: synthetic ledger rows with a KNOWN
taken/close -> KNOWN clv_pct, correct filtering (true_close-not-suspect only,
proxy/no_close excluded, suspect excluded), and a sane CI/verdict."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from scripts.platformkit.live_edge.clv.clean_readout import (clean_readout,
                                                               render)


def _row(bet_id, sport, clv_pct, clv_status, side="home", taken=2.0,
          close_home=2.0, close_away=2.0, status="settled"):
    return {
        "bet_id": bet_id, "sport": sport, "status": status,
        "clv_status": clv_status, "clv_pct": clv_pct,
        "side": side, "taken_decimal": taken,
        "closing_decimal_home": close_home, "closing_decimal_away": close_away,
        "settled_at": "2026-07-14T00:00:00",
    }


def _known_clv_pct(taken_decimal, close_home, close_away, side="home"):
    """Mirror clv_ledger.compute_clv's math directly (no devig needed when
    home/away closes are already the fair two-way prices we hand in)."""
    taken_p = 1.0 / taken_decimal
    fair_close = (1.0 / close_home) if side == "home" else (1.0 / close_away)
    return (fair_close - taken_p) / taken_p * 100.0


def test_known_clv_value_recovered():
    # taken 2.10 (implied .476), close 2.00 (implied .50) -> beat the close.
    clv = _known_clv_pct(2.10, 2.00, 2.00)
    rows = [_row("b1", "mlb", clv, "true_close", taken=2.10,
                 close_home=2.00, close_away=2.00)]
    board = clean_readout(rows)
    assert board["breakdown"]["n_clean_same_book"] == 1
    assert board["overall"]["n"] == 1
    assert abs(board["overall"]["mean_clv_pct"] - round(clv, 4)) < 1e-6


def test_proxy_and_no_close_excluded_from_headline():
    rows = [
        _row("b1", "mlb", 5.0, "true_close"),
        _row("b2", "mlb", 999.0, "proxy"),      # would blow up the mean if leaked
        _row("b3", "mlb", None, "no_close"),
        _row("b4", "mlb", 5.0, "true_close", status="open"),  # not settled
    ]
    board = clean_readout(rows)
    bd = board["breakdown"]
    assert bd["n_clean_same_book"] == 1
    assert bd["n_proxy_excluded"] == 1
    assert bd["n_no_close_excluded"] == 1
    assert board["overall"]["mean_clv_pct"] == 5.0


def test_suspect_off_market_row_excluded():
    # taken 12.0 vs close 2.0 on the same side -> is_clv_suspect True (ratio 6x).
    rows = [
        _row("b1", "mlb", 5.0, "true_close"),
        _row("b2", "mlb", 400.0, "true_close", taken=12.0,
             close_home=2.0, close_away=2.0),
    ]
    board = clean_readout(rows)
    bd = board["breakdown"]
    assert bd["n_true_close"] == 2
    assert bd["n_suspect_excluded"] == 1
    assert bd["n_clean_same_book"] == 1
    assert board["overall"]["mean_clv_pct"] == 5.0


def test_dedup_by_bet_id_keeps_latest():
    rows = [
        _row("b1", "mlb", 1.0, "true_close"),
        {**_row("b1", "mlb", 9.0, "true_close"), "settled_at": "2026-07-15T00:00:00"},
    ]
    board = clean_readout(rows)
    assert board["breakdown"]["n_settled"] == 1
    assert board["overall"]["mean_clv_pct"] == 9.0


def test_per_sport_split_and_verdict_insufficient_when_thin():
    rows = [_row("b1", "mlb", 3.0, "true_close"),
            _row("b2", "wnba", 2.0, "true_close")]
    board = clean_readout(rows)
    assert set(board["per_sport"]) == {"mlb", "wnba"}
    assert board["per_sport"]["mlb"]["verdict"] == "INSUFFICIENT_DATA"
    assert board["overall"]["verdict"] == "INSUFFICIENT_DATA"


def test_edge_claimed_always_false_and_render_runs():
    rows = [_row("b1", "mlb", 3.0, "true_close")]
    board = clean_readout(rows)
    assert board["edge_claimed"] is False
    assert board["provisional"] is True
    md = render(board)
    assert "edge_claimed=False" in md
    assert "PROVISIONAL" in md


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
