"""Tests for after_cost_scoreboard -- after-cost channel P&L (6.3).

Per-file: python -m pytest scripts/platformkit/econ/test_after_cost_scoreboard.py -q
"""
from __future__ import annotations

from scripts.platformkit.econ import after_cost_scoreboard as A


def _row(bet_id, channel, clv_status="true_close", clv_pct=1.0,
         unit_result=1.0, taken_decimal=2.0, stake_units=1.0, venue=None,
         status="settled", settled_at="2026-06-25T00:00:00Z"):
    r = {"bet_id": bet_id, "channel": channel, "status": status,
         "clv_status": clv_status, "clv_pct": clv_pct,
         "unit_result": unit_result, "taken_decimal": taken_decimal,
         "stake_units": stake_units, "settled_at": settled_at, "sport": "mlb",
         "closing_decimal_home": 2.0, "side": "home"}
    if venue is not None:
        r["venue"] = venue
    return r


def test_after_cost_units_kalshi_row():
    row = _row("b1", "paper_pm", taken_decimal=2.0, unit_result=1.0,
                stake_units=1.0, venue="kalshi")
    rec = A.after_cost_units(row)
    assert rec is not None
    assert rec["venue"] == "kalshi"
    # price = 1/2.0 = 0.5 -> round-trip breakeven fee at p=0.5 is 0.04 (2*0.02)
    assert rec["cost_units"] > 0.0
    assert rec["after_cost_units"] == rec["gross_units"] - rec["cost_units"]


def test_after_cost_units_defaults_venue_for_paper_pm():
    row = _row("b1", "paper_pm", venue=None)  # no explicit venue field
    rec = A.after_cost_units(row)
    assert rec is not None
    assert rec["venue"] == "kalshi"  # observed-default fallback


def test_after_cost_units_unknown_channel_no_venue_returns_none():
    row = _row("b1", "some_unknown_channel", venue=None)
    rec = A.after_cost_units(row)
    assert rec is None  # never guesses a venue


def test_after_cost_units_bad_decimal_returns_none():
    row = _row("b1", "paper_pm", taken_decimal=0.5, venue="kalshi")
    assert A.after_cost_units(row) is None


def test_after_cost_units_never_raises_on_missing_unit_result():
    row = _row("b1", "paper_pm", venue="kalshi")
    del row["unit_result"]
    assert A.after_cost_units(row) is None


def test_scoreboard_aggregates_channel():
    led = [
        _row("b1", "paper_pm", taken_decimal=2.0, unit_result=1.0, venue="kalshi"),
        _row("b2", "paper_pm", taken_decimal=2.0, unit_result=-1.0, venue="kalshi"),
    ]
    board = A.scoreboard(led)
    ch = board["channels"]["paper_pm"]
    assert ch["n_measurable"] == 2
    assert ch["n_costed"] == 2
    assert ch["gross_units"] == 0.0  # +1 -1
    assert ch["after_cost_units"] < 0.0  # costs push net below gross


def test_scoreboard_excludes_non_measurable_rows():
    led = [
        _row("b1", "paper", clv_status="no_close", clv_pct=None, venue=None),
    ]
    board = A.scoreboard(led)
    assert board["channels"] == {}  # no_close row never enters after-cost calc


def test_scoreboard_sign_flip_detected():
    # gross barely positive, but costs push it negative
    led = [
        _row("b1", "paper_pm", taken_decimal=2.0, unit_result=0.01, venue="kalshi"),
    ]
    board = A.scoreboard(led)
    ch = board["channels"]["paper_pm"]
    assert ch["sign_flip"] is True


def test_render_does_not_raise_on_empty_board():
    board = A.scoreboard([])
    text = A.render(board)
    assert "AFTER-COST CHANNEL P&L" in text
