"""Focused paper-maker wiring tests; no live orders or capture are started."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.platformkit.execution.paper_maker import PaperMakerAdapter
from scripts.platformkit.ingame import inplay_daytrader as dt
from scripts.platformkit.ingame import inplay_edge_signal as sig


def _tick(home: float = 0.55, **extra):
    out = {"model_prob": 0.65, "yes_home_prob": home, "yes_away_prob": 0.50,
           "is_liquid": True, "is_fresh": True, "calibration_justified": True,
           "ticker": "KXTEST", "tick_p50_sec": 10.0}
    out.update(extra)
    return out


def _start(tmp_path):
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    ledger, grade = tmp_path / "ledger.jsonl", tmp_path / "grade"
    first = dt.on_tick("mlb", "401860100", _tick(), now=now, ledger_path=ledger,
                       grade_dir=grade, maker_adapter=PaperMakerAdapter())
    assert first["action"] == "resting"
    assert not ledger.exists()
    return now, ledger, grade, first


def test_fill_on_subsequent_cross_records_maker_lifecycle(tmp_path):
    now, ledger, grade, first = _start(tmp_path)
    filled = dt.on_tick("mlb", "401860100", _tick(0.60), now=now + timedelta(seconds=1),
                        position=first["position"], ledger_path=ledger, grade_dir=grade)
    assert filled["action"] == "bet"
    assert filled["reason"] == "maker_fill_cross"
    audit = filled["placement"]["exec_gate"]
    assert audit["clv_series"] == "paper_ingame_maker"
    assert filled["placement"]["taken_book"] == "paper_ingame_maker"
    assert audit["maker_fee_units"] > 0.0
    assert audit["order_state"] == "FILLED"
    assert [stamp[1] for stamp in audit["order_lifecycle"]][-1] == "FILLED"
    assert filled["placement"]["executed"] is False
    assert ledger.exists()


def test_no_cross_never_records_a_bet(tmp_path):
    now, ledger, grade, first = _start(tmp_path)
    resting = dt.on_tick("mlb", "401860100", _tick(0.70), now=now + timedelta(seconds=1),
                         position=first["position"], ledger_path=ledger, grade_dir=grade)
    assert resting["action"] == "resting"
    assert resting["reason"] == "maker_resting"
    assert not ledger.exists()


def test_ttl_expiry_cancels_without_record(tmp_path):
    now, ledger, grade, first = _start(tmp_path)
    expired = dt.on_tick("mlb", "401860100", _tick(0.60), now=now + timedelta(seconds=30),
                         position=first["position"], ledger_path=ledger, grade_dir=grade)
    assert expired["action"] == "no_bet"
    assert expired["reason"] == "maker_ttl_expired"
    assert expired["position"] is None
    assert not ledger.exists()


def test_maker_fee_is_applied_before_tier_threshold(monkeypatch):
    monkeypatch.setattr(sig, "kalshi_fee_per_contract", lambda price, side: 1.0)
    ev = sig.evaluate(model_prob=0.65, yes_home_prob=0.55, yes_away_prob=0.50,
                      calibration_justified=True, is_liquid=True, is_fresh=True)
    assert ev["gross_ev"] > 0.0
    assert ev["maker_fee_units"] == 1.0
    assert ev["ev"] < 0.0
    assert ev["action"] == "no_bet"
    assert ev["reason"] == "below_floor"
