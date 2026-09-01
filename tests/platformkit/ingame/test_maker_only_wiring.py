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


def _iso(dt_):
    return dt_.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_stale_state_blocks_entry(tmp_path):
    # Wiring proof for the entry-side gate: mlb ceiling = 5s, src_ts 10s old.
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    ledger, grade = tmp_path / "ledger.jsonl", tmp_path / "grade"
    stale = _tick(src_ts=_iso(now - timedelta(seconds=10)))
    d = dt.on_tick("mlb", "401860100", stale, now=now, ledger_path=ledger,
                   grade_dir=grade, maker_adapter=PaperMakerAdapter())
    assert d["action"] == "no_bet"
    assert d["reason"] == "stale_state"
    assert d["position"] is None
    assert not ledger.exists()


def test_stale_state_blocks_fill_then_fresh_tick_fills(tmp_path):
    # The FILL decision itself must honor the same freshness ceiling as entry.
    now, ledger, grade, first = _start(tmp_path)
    stale_cross = _tick(0.60, src_ts=_iso(now - timedelta(seconds=10)))
    held = dt.on_tick("mlb", "401860100", stale_cross, now=now + timedelta(seconds=1),
                      position=first["position"], ledger_path=ledger, grade_dir=grade)
    assert held["action"] == "resting"
    assert held["reason"] == "maker_stale_state"
    assert not ledger.exists()
    filled = dt.on_tick("mlb", "401860100", _tick(0.60), now=now + timedelta(seconds=2),
                        position=held["position"], ledger_path=ledger, grade_dir=grade)
    assert filled["action"] == "bet"
    assert ledger.exists()


def test_suspension_cancels_resting_quote(tmp_path):
    # kickoff/void: a crossing price during a terminal/suspended game state must
    # CANCEL the resting order, never record a retroactive fill.
    now, ledger, grade, first = _start(tmp_path)
    suspended = _tick(0.60, state={"status": "final"})
    d = dt.on_tick("mlb", "401860100", suspended, now=now + timedelta(seconds=1),
                   position=first["position"], ledger_path=ledger, grade_dir=grade)
    assert d["action"] == "no_bet"
    assert d["reason"] == "maker_cancelled_suspended"
    assert d["position"] is None
    assert not ledger.exists()


def test_market_status_suspension_cancels_directly():
    adapter = PaperMakerAdapter()
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    q = adapter.quote("mlb", "401860100", "home", 0.65, units={},
                      tick={"ticker": "KXTEST", "tick_p50_sec": 10.0}, now=now)
    assert q["status"] == "resting"
    ev2 = adapter.advance({"maker_quote": q, "status": "resting"},
                          {"yes_home_prob": 0.60, "market_status": "suspended"},
                          now=now + timedelta(seconds=1))
    assert ev2["status"] == "cancelled_suspended"


def test_default_ledger_blocked_without_writer_identity(tmp_path, monkeypatch):
    # One-writer guard: an unsanctioned host must never append the SHARED ledger.
    from scripts.platformkit.execution import writer_identity as wi
    from scripts.platformkit.ingame import paper_ingame as pi
    now, ledger, grade, first = _start(tmp_path)
    monkeypatch.setattr(wi, "default_ledger_write_allowed", lambda: False)

    def _boom(*a, **k):
        raise AssertionError("shared-ledger write attempted by non-writer")

    monkeypatch.setattr(pi, "record_ingame_bet", _boom)
    d = dt.on_tick("mlb", "401860100", _tick(0.60), now=now + timedelta(seconds=1),
                   position=first["position"], ledger_path=None, grade_dir=grade)
    assert d["action"] == "no_bet"
    assert d["reason"] == "not_ledger_writer"
    assert d["position"] is None


def test_event_reactive_entry_gated_by_measured_latency(tmp_path, monkeypatch):
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    ledger, grade = tmp_path / "ledger.jsonl", tmp_path / "grade"
    monkeypatch.setattr(dt._latsb, "event_reactive_supported",
                        lambda sport, grade_dir=None: False)
    d = dt.on_tick("mlb", "401860100", _tick(event_reactive=True), now=now,
                   ledger_path=ledger, grade_dir=grade,
                   maker_adapter=PaperMakerAdapter())
    assert d["action"] == "no_bet"
    assert d["reason"] == "event_reactive_not_supported"
    monkeypatch.setattr(dt._latsb, "event_reactive_supported",
                        lambda sport, grade_dir=None: True)
    d2 = dt.on_tick("mlb", "401860100", _tick(event_reactive=True), now=now,
                    ledger_path=ledger, grade_dir=grade,
                    maker_adapter=PaperMakerAdapter())
    assert d2["action"] == "resting"
