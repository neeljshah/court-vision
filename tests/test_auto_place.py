"""tests/test_auto_place.py — R17_J3 acceptance tests for the auto-placement engine.

Covers each safety gate, the daily counter, the urgent-alert side effect,
the ledger-dedupe gate, and the dry-run-by-default invariant.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.auto_place_daemon as apd


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #
def _good_bet(**overrides):
    """Default valid bet that passes every safety gate."""
    base = {
        "player": "Keldon Johnson",
        "stat": "reb",
        "side": "OVER",
        "book": "pin",
        "line": 3.5,
        "odds": 157,
        "model_q10": 2.13,
        "model_q50": 5.17,
        "model_q90": 8.68,
        "model_prob": 0.7395,
        "implied_prob": 0.3891,
        "edge_pct": 35.04,
        "ev_per_dollar": 0.9005,
        "kelly_stake_$": 50.0,
        "kelly_pct_used": 5.0,
        "stale": False,
        "line_move": "",
    }
    base.update(overrides)
    return base


@pytest.fixture
def now_pretip():
    """Now value 2 hours before the SAS/OKC tip (30min buffer easily met)."""
    return _dt.datetime(2026, 5, 26, 22, 30, 0, tzinfo=_dt.timezone.utc)


@pytest.fixture
def tip_off_utc():
    return _dt.datetime(2026, 5, 27, 0, 30, 0, tzinfo=_dt.timezone.utc)


@pytest.fixture
def injuries_ok():
    return {apd._name_key("Keldon Johnson"): "AVAILABLE"}


# --------------------------------------------------------------------------- #
# 1. Edge gate                                                                #
# --------------------------------------------------------------------------- #
def test_gate_edge_blocks_below_floor():
    ok, reason = apd.gate_edge(_good_bet(edge_pct=4.0), 0.08)
    assert ok is False
    assert "edge_pct" in reason

    ok, _ = apd.gate_edge(_good_bet(edge_pct=12.0), 0.08)
    assert ok is True


# --------------------------------------------------------------------------- #
# 2. model_confirmed / sigma gate                                             #
# --------------------------------------------------------------------------- #
def test_gate_model_confirmed_passes_with_q50_deviation():
    """Keldon line=3.5, q50=5.17, sigma=(8.68-2.13)/2.563=2.55 -> dev = 0.65 >= 0.5sigma."""
    ok, reason = apd.gate_model_confirmed(_good_bet())
    assert ok is True, reason


def test_gate_model_confirmed_blocks_when_q50_too_close_to_line():
    bet = _good_bet(model_q10=3.0, model_q50=3.6, model_q90=4.0, line=3.5)
    # sigma = (4.0-3.0)/2.563 ~= 0.39 -> dev = 0.1/0.39 ~= 0.26 < 0.5
    ok, reason = apd.gate_model_confirmed(bet)
    assert ok is False
    assert "sigma" in reason

    # middle/arb override always passes
    ok2, _ = apd.gate_model_confirmed({**bet, "model_confirmed": True})
    assert ok2 is True


# --------------------------------------------------------------------------- #
# 3. line_validator gate                                                      #
# --------------------------------------------------------------------------- #
def test_gate_line_validator_passes_real_bet():
    ok, reason = apd.gate_line_validator(_good_bet(), use_snapshot=False)
    assert ok is True, reason


def test_gate_line_validator_blocks_extreme_odds():
    ok, reason = apd.gate_line_validator(_good_bet(odds=900), use_snapshot=False)
    assert ok is False
    assert "max_odds_abs" in reason or "implied_prob" in reason or "|odds|" in reason


def test_gate_line_validator_blocks_stale():
    ok, reason = apd.gate_line_validator(_good_bet(stale=True), use_snapshot=False)
    assert ok is False
    assert "stale" in reason


def test_gate_line_validator_blocks_quantile_crossing():
    # q90 < q50 — the live SAS/OKC Wembanyama BLK UNDER row exhibits this.
    bet = _good_bet(model_q10=0.0, model_q50=2.04, model_q90=1.14)
    ok, reason = apd.gate_line_validator(bet, use_snapshot=False)
    assert ok is False
    assert "quantile" in reason


# --------------------------------------------------------------------------- #
# 4. bankroll / exposure gate                                                 #
# --------------------------------------------------------------------------- #
def test_gate_bankroll_per_bet_cap():
    ok, reason = apd.gate_bankroll(
        _good_bet(**{"kelly_stake_$": 100.0}),
        bankroll=1000.0, per_bet_cap=0.05, daily_cap=0.25,
        existing_daily_exposure=0.0,
    )
    assert ok is False
    assert "per-bet" in reason


def test_gate_bankroll_daily_cap():
    ok, reason = apd.gate_bankroll(
        _good_bet(**{"kelly_stake_$": 50.0}),
        bankroll=1000.0, per_bet_cap=0.05, daily_cap=0.25,
        existing_daily_exposure=220.0,
    )
    assert ok is False
    assert "daily" in reason


def test_gate_bankroll_passes_within_caps():
    ok, _ = apd.gate_bankroll(
        _good_bet(),  # stake $50, bankroll $1000 -> 5%
        bankroll=1000.0, per_bet_cap=0.05, daily_cap=0.25,
        existing_daily_exposure=0.0,
    )
    assert ok is True


# --------------------------------------------------------------------------- #
# 5. dedupe gate                                                              #
# --------------------------------------------------------------------------- #
def test_gate_dedupe_blocks_open_duplicate():
    bet = _good_bet()
    open_rows = [{
        "bet_id": "OLD123",
        "player": "Keldon Johnson",
        "stat": "reb",
        "side": "OVER",
        "book": "pin",
        "line": "3.5",
        "status": "open",
    }]
    ok, reason = apd.gate_dedupe(bet, open_rows)
    assert ok is False
    assert "OLD123" in reason


def test_gate_dedupe_passes_when_different_book():
    bet = _good_bet(book="fd")
    open_rows = [{
        "bet_id": "OLD123",
        "player": "Keldon Johnson",
        "stat": "reb",
        "side": "OVER",
        "book": "pin",
        "line": "3.5",
        "status": "open",
    }]
    ok, _ = apd.gate_dedupe(bet, open_rows)
    assert ok is True


# --------------------------------------------------------------------------- #
# 6. tip_time gate                                                            #
# --------------------------------------------------------------------------- #
def test_gate_tip_time_blocks_when_too_close(tip_off_utc):
    now = tip_off_utc - _dt.timedelta(minutes=15)
    ok, reason = apd.gate_tip_time(_good_bet(), tip_off_utc, 30, now=now)
    assert ok is False
    assert "until tip" in reason


def test_gate_tip_time_passes_with_buffer(tip_off_utc, now_pretip):
    ok, _ = apd.gate_tip_time(_good_bet(), tip_off_utc, 30, now=now_pretip)
    assert ok is True


def test_gate_tip_time_blocks_without_tipoff():
    now = _dt.datetime(2026, 5, 26, 22, 30, tzinfo=_dt.timezone.utc)
    ok, reason = apd.gate_tip_time(_good_bet(), None, 30, now=now)
    assert ok is False
    assert "tipoff" in reason


# --------------------------------------------------------------------------- #
# 7. injury gate                                                              #
# --------------------------------------------------------------------------- #
def test_gate_injury_blocks_OUT():
    ok, reason = apd.gate_injury(
        _good_bet(),
        {apd._name_key("Keldon Johnson"): "OUT"},
    )
    assert ok is False
    assert "OUT" in reason


def test_gate_injury_blocks_DOUBTFUL():
    ok, _ = apd.gate_injury(
        _good_bet(),
        {apd._name_key("Keldon Johnson"): "DOUBTFUL"},
    )
    assert ok is False


def test_gate_injury_passes_PROBABLE_or_missing():
    ok, _ = apd.gate_injury(_good_bet(), {apd._name_key("Keldon Johnson"): "PROBABLE"})
    assert ok is True
    # missing player -> treat as AVAILABLE
    ok2, _ = apd.gate_injury(_good_bet(), {})
    assert ok2 is True


# --------------------------------------------------------------------------- #
# Daily counter                                                               #
# --------------------------------------------------------------------------- #
def test_evaluate_tick_respects_daily_counter(tip_off_utc, now_pretip):
    # 3 identical-looking-but-distinct bets; daily_bets_remaining=2 -> only 2 pass
    live = {
        "ranked_bets": [
            _good_bet(book="pin", odds=157, edge_pct=35.0),
            _good_bet(book="fd", odds=190, edge_pct=39.5),
            _good_bet(book="bov", odds=165, edge_pct=36.2),
        ]
    }
    results = apd.evaluate_tick(
        live,
        bankroll=1000.0, per_bet_cap=0.05, daily_cap=0.25,
        confidence_floor=0.08,
        tip_off_utc=tip_off_utc, min_pre_tip_min=30,
        injuries={apd._name_key("Keldon Johnson"): "AVAILABLE"},
        open_rows=[],
        daily_bets_remaining=2,
        now=now_pretip,
        top_n=5,
        use_snapshot_validator=False,
    )
    passed = [r for r in results if r["all_passed"]]
    assert len(passed) == 2, [r["blocked_by"] for r in results]
    # The 3rd is blocked by daily counter (or daily_cap exposure)
    assert results[2]["all_passed"] is False


# --------------------------------------------------------------------------- #
# Urgent alert side effect                                                    #
# --------------------------------------------------------------------------- #
def test_append_urgent_creates_file_and_format(tmp_path):
    p = tmp_path / "URGENT_BETS.md"
    now = _dt.datetime(2026, 5, 26, 22, 30, tzinfo=_dt.timezone.utc)
    apd.append_urgent(_good_bet(), now, dry_run=False, path=str(p))
    txt = p.read_text(encoding="utf-8")
    assert "PLACE THIS NOW" in txt
    assert "Keldon Johnson" in txt
    assert "REB" in txt and "OVER" in txt
    assert "+157" in txt
    assert "$50" in txt
    # second call appends, header only once
    apd.append_urgent(_good_bet(), now, dry_run=False, path=str(p))
    txt2 = p.read_text(encoding="utf-8")
    assert txt2.count("URGENT BETS — auto-placement alerts") == 1
    assert txt2.count("PLACE THIS NOW") == 2


def test_append_urgent_dry_run_marker(tmp_path):
    p = tmp_path / "URGENT_BETS.md"
    apd.append_urgent(_good_bet(), _dt.datetime(2026, 5, 26, tzinfo=_dt.timezone.utc),
                      dry_run=True, path=str(p))
    assert "[DRY-RUN]" in p.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Full evaluator: happy path                                                  #
# --------------------------------------------------------------------------- #
def test_evaluate_tick_passes_keldon_REB_OVER(tip_off_utc, now_pretip, injuries_ok):
    live = {"ranked_bets": [_good_bet()]}
    results = apd.evaluate_tick(
        live,
        bankroll=1000.0, per_bet_cap=0.05, daily_cap=0.25,
        confidence_floor=0.08,
        tip_off_utc=tip_off_utc, min_pre_tip_min=30,
        injuries=injuries_ok, open_rows=[], daily_bets_remaining=5,
        now=now_pretip, top_n=5,
        use_snapshot_validator=False,
    )
    assert len(results) == 1
    assert results[0]["all_passed"] is True, results[0]["gates"]


def test_evaluate_tick_blocks_wembanyama_quantile_crossing(tip_off_utc, now_pretip):
    """The actual live row: Wembanyama BLK UNDER 2.5, q10=0, q50=2.04, q90=1.14 — crossed."""
    live = {"ranked_bets": [
        {
            **_good_bet(),
            "player": "Victor Wembanyama", "stat": "blk", "side": "UNDER",
            "line": 2.5, "book": "bov", "odds": 205,
            "model_q10": 0.0, "model_q50": 2.04, "model_q90": 1.14,
            "model_prob": 0.844, "edge_pct": 51.62, "kelly_stake_$": 50.0,
            "stale": True,
        }
    ]}
    results = apd.evaluate_tick(
        live,
        bankroll=1000.0, per_bet_cap=0.05, daily_cap=0.25,
        confidence_floor=0.08,
        tip_off_utc=tip_off_utc, min_pre_tip_min=30,
        injuries={apd._name_key("Victor Wembanyama"): "AVAILABLE"},
        open_rows=[], daily_bets_remaining=5,
        now=now_pretip, top_n=5,
        use_snapshot_validator=False,
    )
    assert results[0]["all_passed"] is False
    blocked = results[0]["blocked_by"]
    assert "line_validator" in blocked


# --------------------------------------------------------------------------- #
# Dry-run is default                                                          #
# --------------------------------------------------------------------------- #
def test_cli_default_is_dry_run():
    """Argparse should default --live to False (i.e. dry-run is default)."""
    args = apd._build_parser().parse_args(["--slate", "sas_okc_2026-05-26", "--max-ticks", "0"])
    assert args.live is False


def test_cli_live_flag_enables_live():
    args = apd._build_parser().parse_args(["--slate", "sas_okc_2026-05-26", "--live"])
    assert args.live is True


# --------------------------------------------------------------------------- #
# _cheap_pre_checks standalone                                                #
# --------------------------------------------------------------------------- #
def test_cheap_pre_checks_accepts_real_bet():
    ok, _ = apd._cheap_pre_checks(_good_bet())
    assert ok is True


def test_cheap_pre_checks_rejects_crossed_quantiles():
    ok, reason = apd._cheap_pre_checks(
        _good_bet(model_q10=0.0, model_q50=2.04, model_q90=1.14)
    )
    assert ok is False
    assert "quantile" in reason
