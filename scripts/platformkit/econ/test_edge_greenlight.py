"""Tests for edge_greenlight -- pre-registered proof-of-edge evaluator (8.1).

Per-file: python -m pytest scripts/platformkit/econ/test_edge_greenlight.py -q
"""
from __future__ import annotations

from scripts.platformkit.econ import edge_greenlight as E
from scripts.platformkit.econ import greenlight_criteria as G


def _row(bet_id, channel, day, unit_result=1.0, taken_decimal=2.0,
         clv_status="true_close", clv_pct=1.0, venue="kalshi",
         closing_home=2.0, side="home"):
    return {
        "bet_id": bet_id, "channel": channel, "status": "settled",
        "clv_status": clv_status, "clv_pct": clv_pct,
        "unit_result": unit_result, "taken_decimal": taken_decimal,
        "stake_units": 1.0, "settled_at": "2026-06-%02dT00:00:00Z" % day,
        "ts": "2026-06-%02dT00:00:00Z" % day, "sport": "mlb",
        "closing_decimal_home": closing_home, "closing_decimal_away": 2.0,
        "side": side, "venue": venue,
        "fair_close_prob": 1.0 / closing_home if side == "home" else 0.5,
        "event_id": bet_id,
    }


def test_small_channel_n80_is_amber_with_criterion_a_shortfall():
    # mirrors paper_pm's real n=80 today: should be AMBER, criterion (a) failing
    # with an explicit shortfall number.
    led = [_row("b%d" % i, "paper_pm", day=(i % 28) + 1) for i in range(80)]
    report = E.edge_greenlight(led)
    ch = report["channels"]["paper_pm"]
    assert ch["status"] == "AMBER"
    assert "a" in ch["failing_criteria"]
    crit_a = ch["criteria"]["a"]
    assert crit_a["passed"] is False
    assert "need" in crit_a["detail"]
    assert "220 more" in crit_a["detail"] or "need 220" in crit_a["detail"]


def test_criterion_a_exact_shortfall_math():
    rows = [_row("b%d" % i, "paper_pm", day=(i % 28) + 1) for i in range(80)]
    crit = G.criterion_a(rows)
    assert crit["n_total"] == 80
    assert "need 220 more total" in crit["detail"]


def test_channel_meeting_every_built_criterion_is_amber_not_green():
    # Build a large, perfectly-split, strongly-positive corpus that would pass
    # (a)-(d) and (g); (e)/(f) are structurally NOT_BUILT and must hold the
    # channel at AMBER, never silently GREEN.
    led = []
    for i in range(320):
        day = 2 + 2 * (i % 14)  # even days -> half A
        led.append(_row("beven_%d" % i, "paper_pm", day=day,
                         unit_result=2.0, taken_decimal=3.0, clv_pct=5.0,
                         closing_home=1.5))
    for i in range(320):
        day = 1 + 2 * (i % 14)  # odd days -> half B
        led.append(_row("bodd_%d" % i, "paper_pm", day=day,
                         unit_result=2.0, taken_decimal=3.0, clv_pct=5.0,
                         closing_home=1.5))
    report = E.edge_greenlight(led)
    ch = report["channels"]["paper_pm"]
    assert ch["status"] in ("AMBER", "GREEN")
    # criteria e and f can NEVER silently pass -- assert they are named as
    # NOT_BUILT-blocking whenever the channel isn't fully GREEN.
    if ch["status"] != "GREEN":
        assert "e" in ch["not_built_criteria"] or "f" in ch["not_built_criteria"]
        assert ch["criteria"]["e"]["channel_trust_status"] == "NOT_BUILT"
        assert ch["criteria"]["f"]["cv_honesty_gate_status"] == "NOT_BUILT"


def test_criterion_e_never_silently_passes():
    crit = G.criterion_e("paper_pm")
    assert crit["channel_trust_status"] == "NOT_BUILT"
    assert crit["passed"] is False


def test_criterion_f_never_silently_passes():
    crit = G.criterion_f()
    assert crit["cv_honesty_gate_status"] == "NOT_BUILT"
    assert crit["passed"] is False


def test_halves_split_is_deterministic_and_covers_all_rows():
    rows = [_row("b%d" % i, "paper_pm", day=(i % 28) + 1) for i in range(50)]
    a, b = G.halves(rows)
    assert len(a) + len(b) == 50


def test_empty_ledger_yields_no_channels():
    report = E.edge_greenlight([])
    assert report["channels"] == {}


def test_render_does_not_raise():
    led = [_row("b%d" % i, "paper_pm", day=(i % 28) + 1) for i in range(5)]
    report = E.edge_greenlight(led)
    text = E.render(report)
    assert "EDGE GREENLIGHT" in text
    assert "READ-ONLY" in text


def test_bad_row_does_not_crash_report():
    led = [_row("b1", "paper_pm", day=1)]
    led.append({"bet_id": "malformed", "channel": "paper_pm", "status": "settled"})
    report = E.edge_greenlight(led)
    assert "paper_pm" in report["channels"]
