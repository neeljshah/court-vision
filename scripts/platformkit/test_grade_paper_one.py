"""Regression tests for grade_paper_one fee netting (R2b).

Direction under test: recorded unit results go DOWN for fee-bearing fills
(fees SUBTRACT, never inflate); legacy maker rows that cannot resolve a fee
grade GROSS but are COUNTED, never silent. Units only -- no dollars.
"""
from __future__ import annotations

from scripts.platformkit import grade_paper_one as gpo
from scripts.platformkit.execution.venue_fees import fee_kalshi_maker

_GAME = {"home_score": 100, "away_score": 90}


def _bet(**over):
    base = {"sport": "nba", "side": "home", "matchup": "AAA@BBB",
            "taken_decimal": 2.0, "stake_units": 1.0, "taken_book": "paper"}
    base.update(over)
    return base


def test_fee_bearing_fill_nets_below_gross(tmp_path):
    fee = 0.01
    bet = _bet(taken_book="paper_ingame_maker",
               exec_gate={"execution_mode": "maker_only", "maker_fee_units": fee})
    settled = gpo.grade_one(bet, _GAME, _line_store_base=tmp_path)
    gross = gpo._unit_result("win", 2.0, 1.0)
    assert settled["fee_source"] == "recorded"
    assert settled["fee_units"] == fee
    assert settled["unit_result"] == round(gross - fee, 6)
    assert settled["unit_result"] < gross  # fees reduce, never inflate


def test_fee_subtracts_on_loss_too():
    # Charged at fill regardless of outcome: a loss gets MORE negative.
    assert gpo._unit_result("loss", 2.0, 1.0, fee_units=0.01) == -1.01
    assert gpo._unit_result("loss", 2.0, 1.0, fee_units=0.01) < gpo._unit_result("loss", 2.0, 1.0)
    # A negative stamp is a magnitude, never a credit.
    assert gpo._unit_result("win", 2.0, 1.0, fee_units=-0.01) == 0.99


def test_legacy_maker_row_counted_not_silent(tmp_path):
    before = gpo.gross_legacy_rows()
    bet = _bet(taken_book="paper_ingame_maker")  # no fee stamp, no venue
    settled = gpo.grade_one(bet, _GAME, _line_store_base=tmp_path)
    assert settled["fee_source"] == "gross_legacy"
    assert settled["fee_units"] == 0.0
    assert settled["unit_result"] == gpo._unit_result("win", 2.0, 1.0)  # gross
    assert gpo.gross_legacy_rows() == before + 1


def test_legacy_maker_row_with_venue_recomputes(tmp_path):
    bet = _bet(taken_book="paper_ingame_maker", venue="kalshi")
    settled = gpo.grade_one(bet, _GAME, _line_store_base=tmp_path)
    expect = fee_kalshi_maker(1.0, 0.5)  # size=1, price=1/2.0
    assert expect > 0.0
    assert settled["fee_source"] == "venue_fees"
    assert settled["fee_units"] == round(expect, 6)
    assert settled["unit_result"] == round(gpo._unit_result("win", 2.0, 1.0) - expect, 6)


def test_zero_fee_row_unchanged(tmp_path):
    before = gpo.gross_legacy_rows()
    settled = gpo.grade_one(_bet(), _GAME, _line_store_base=tmp_path)
    assert settled["fee_source"] == "no_fee"
    assert settled["fee_units"] == 0.0
    assert settled["unit_result"] == 1.0  # (2.0 - 1) * 1u, exactly as before
    assert gpo.gross_legacy_rows() == before  # non-maker rows never counted
