"""Tests for beat_the_line -- realized vs close-implied win rate scoreboard (6.4).

Per-file: python -m pytest scripts/platformkit/econ/test_beat_the_line.py -q
"""
from __future__ import annotations

from scripts.platformkit.econ import beat_the_line as B


def _row(bet_id, channel, taken_decimal, unit_result, closing_home=2.0,
         side="home", venue=None, settled_at="2026-06-25T00:00:00Z",
         event_id=None):
    r = {"bet_id": bet_id, "channel": channel, "status": "settled",
         "clv_status": "true_close", "clv_pct": 1.0,
         "unit_result": unit_result, "taken_decimal": taken_decimal,
         "stake_units": 1.0, "settled_at": settled_at, "sport": "mlb",
         "closing_decimal_home": closing_home, "closing_decimal_away": 2.0,
         "side": side, "fair_close_prob": 1.0 / closing_home if side == "home" else 0.5,
         "event_id": event_id or bet_id}
    if venue is not None:
        r["venue"] = venue
    return r


def test_small_n_reports_insufficient_data():
    led = [_row("b%d" % i, "paper_pm", 2.0, 1.0) for i in range(3)]
    report = B.beat_the_line(led)
    ch = report["channels"]["paper_pm"]
    assert ch["realized_win_rate"] is None
    assert "INSUFFICIENT_DATA" in ch["verdict"]


def test_clearly_positive_excess_case():
    # close-implied ~50% win rate (fair_close_prob=0.5 for every bet since
    # closing_home=2.0 -> devig-free implied 0.5), but this channel wins ~90%
    # of the time -- a clear, large positive excess.
    led = []
    for i in range(30):
        won = i < 27  # 27/30 = 90% realized wins
        led.append(_row("b%d" % i, "paper_pm", 2.0,
                         1.0 if won else -1.0, closing_home=2.0))
    report = B.beat_the_line(led)
    ch = report["channels"]["paper_pm"]
    assert ch["realized_win_rate"] == 0.9
    assert ch["excess"] > 0.3
    assert ch["excess_significant"] is True
    assert "POSITIVE" in ch["verdict"]


def test_clearly_negative_excess_case():
    led = []
    for i in range(30):
        won = i < 3  # 3/30 = 10% realized wins vs ~50% implied
        led.append(_row("b%d" % i, "paper_pm", 2.0,
                         1.0 if won else -1.0, closing_home=2.0))
    report = B.beat_the_line(led)
    ch = report["channels"]["paper_pm"]
    assert ch["realized_win_rate"] == 0.1
    assert ch["excess"] < -0.3
    assert ch["excess_significant"] is True
    assert "NEGATIVE" in ch["verdict"]


def test_weekly_breakdown_present():
    led = [
        _row("b1", "paper_pm", 2.0, 1.0, settled_at="2026-06-01T00:00:00Z"),
        _row("b2", "paper_pm", 2.0, -1.0, settled_at="2026-06-08T00:00:00Z"),
    ]
    report = B.beat_the_line(led)
    ch = report["channels"]["paper_pm"]
    assert isinstance(ch["weekly"], dict)
    assert len(ch["weekly"]) == 2  # two distinct ISO weeks


def test_after_cost_units_present_when_costable():
    led = [_row("b%d" % i, "paper_pm", 2.0, 1.0, venue="kalshi") for i in range(15)]
    report = B.beat_the_line(led)
    ch = report["channels"]["paper_pm"]
    assert ch["after_cost_units"] is not None
    assert ch["after_cost_units"] < ch["cumulative_units"]  # costs eat into gross


def test_no_measurable_rows_yields_empty_channels():
    led = [{"bet_id": "x", "channel": "paper", "status": "settled",
            "clv_status": "no_close", "clv_pct": None, "unit_result": 1.0,
            "settled_at": "2026-06-25T00:00:00Z"}]
    report = B.beat_the_line(led)
    assert report["channels"] == {}


def test_render_does_not_raise():
    led = [_row("b%d" % i, "paper_pm", 2.0, 1.0) for i in range(3)]
    report = B.beat_the_line(led)
    text = B.render(report)
    assert "BEAT THE LINE" in text
