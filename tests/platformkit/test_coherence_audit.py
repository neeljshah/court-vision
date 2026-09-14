"""Per-file test for scripts.platformkit.execution.coherence_audit -- synthetic
jsonl fixtures only, no real venue capture (see NOT_VERIFIED in the module).
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_coherence_audit.py -q
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.execution import coherence_audit as ca
from scripts.platformkit.execution import venue_fees as fees


def _poly_row(cid, tok, mid, bid, ask, ts_ms, sport="tennis"):
    return {"record_type": "snapshot", "venue": "polymarket", "sport": sport,
            "condition_id": cid, "token_id": tok, "mid": mid,
            "best_bid": bid, "best_ask": ask, "ts_ms": ts_ms}


def _kalshi_row(event_ticker, ticker, yes_bid, yes_ask, ts_ms, no_bid=None, no_ask=None, sport="nba"):
    row = {"record_type": "snapshot", "venue": "kalshi", "sport": sport,
           "event_ticker": event_ticker, "ticker": ticker,
           "yes_bid": yes_bid, "yes_ask": yes_ask, "ts_ms": ts_ms}
    if no_bid is not None:
        row["no_bid"], row["no_ask"] = no_bid, no_ask
    return row


# ---------------------------------------------------------------------------
# Grouping rule: Kalshi ticker-suffix futures set + binary single-ticker set
# ---------------------------------------------------------------------------

def test_grouping_kalshi_multi_outcome_ticker_suffix():
    event = "KXNBAPTS-25SEP14-PLAYER"
    rows = [_kalshi_row(event, "%s-%d" % (event, strike), 0.21, 0.23, 1000)
            for strike in (15, 20, 25, 30, 35)]
    snaps = ca.build_snapshots(rows, "kalshi")
    assert len(snaps) == 1
    assert snaps[0]["set_id"] == "kalshi:multi:%s" % event
    assert len(snaps[0]["legs"]) == 5


def test_grouping_kalshi_binary_single_ticker_no_alignment_needed():
    rows = [_kalshi_row("KXNBAGAME-DENOKC", "KXNBAGAME-DENOKC-DEN", 0.60, 0.62, t,
                         no_bid=0.38, no_ask=0.40) for t in (1000, 2000)]
    snaps = ca.build_snapshots(rows, "kalshi")
    assert len(snaps) == 2  # one snapshot per row -- same-row yes/no, no cross-row alignment
    assert all(s["set_id"] == "kalshi:binary:KXNBAGAME-DENOKC-DEN" for s in snaps)
    assert all(len(s["legs"]) == 2 for s in snaps)


def test_grouping_polymarket_two_token_condition():
    rows = [_poly_row("cond-1", "tokA", 0.50, 0.49, 0.51, 1000),
            _poly_row("cond-1", "tokB", 0.50, 0.49, 0.51, 1000)]
    snaps = ca.build_snapshots(rows, "polymarket")
    assert len(snaps) == 1
    assert snaps[0]["set_id"] == "poly:cond-1"
    assert len(snaps[0]["legs"]) == 2


# ---------------------------------------------------------------------------
# Coherence math
# ---------------------------------------------------------------------------

def test_coherent_two_outcome_set_verdict_and_buy_all_negative_post_fee():
    rows = [_poly_row("cond-2", "tokA", 0.50, 0.49, 0.51, 1000),
            _poly_row("cond-2", "tokB", 0.50, 0.49, 0.51, 1000)]
    obs = ca.compute_metrics(ca.build_snapshots(rows, "polymarket")[0], "polymarket")
    assert obs["sum_mid"] == pytest.approx(1.00)
    assert obs["buy_all"] < 0
    assert obs["sell_all"] < 0
    verdict = ca.build_verdict([obs], "polymarket")
    assert verdict["verdict"] == "COHERENT"


def test_five_outcome_futures_residual_present_pre_fee_buy_all_negative_post_fee_hhi_reported():
    event = "KXNBACHAMP-25"
    mids = [0.22, 0.22, 0.22, 0.20, 0.20]  # sum = 1.06
    rows = [_kalshi_row(event, "%s-T%d" % (event, i), round(m - 0.01, 4), round(m + 0.01, 4), 1000, sport="nba")
            for i, m in enumerate(mids)]
    obs = ca.compute_metrics(ca.build_snapshots(rows, "kalshi")[0], "kalshi")
    assert obs["sum_mid"] == pytest.approx(1.06)
    assert obs["residual_mid"] == pytest.approx(0.06)
    assert obs["buy_all_pre_fee"] < 0  # residual present pre-fee (asks sum well above 1)
    assert obs["buy_all"] < 0  # post-fee still negative
    assert obs["hhi"] is not None and 0.0 < obs["hhi"] < 1.0
    assert obs["complete_set_fee_taker_approx"] == pytest.approx(fees._KALSHI_TAKER_COEF * (1.0 - obs["hhi"]))


def test_true_buy_all_opportunity_pre_fee_sign_and_post_fee_via_venue_fees():
    rows = [_poly_row("cond-3", "tokA", None, 0.44, 0.48, 1000),
            _poly_row("cond-3", "tokB", None, 0.45, 0.49, 1000)]  # sum_ask = 0.97
    obs = ca.compute_metrics(ca.build_snapshots(rows, "polymarket")[0], "polymarket")
    assert obs["sum_ask"] == pytest.approx(0.97)
    assert obs["buy_all_pre_fee"] == pytest.approx(0.03)
    assert obs["buy_all_pre_fee"] > 0  # a true pre-fee buy-all opportunity
    expected_fee = fees.fee_polymarket("taker", 1.0, 0.48) + fees.fee_polymarket("taker", 1.0, 0.49)
    assert obs["taker_fees_total"] == pytest.approx(expected_fee)
    assert obs["buy_all"] == pytest.approx(0.03 - expected_fee)


def test_alignment_window_drops_stale_member():
    rows = [
        _poly_row("cond-4", "tokA", 0.50, 0.49, 0.51, 0),
        _poly_row("cond-4", "tokA", 0.50, 0.49, 0.51, 5000),
        _poly_row("cond-4", "tokB", 0.50, 0.49, 0.51, 0),  # tokB has no point near ts=5000
    ]
    snaps = ca.build_snapshots(rows, "polymarket")
    assert len(snaps) == 1  # the ts=5000 anchor drops the WHOLE snapshot (tokB is 5000ms away, > 2s window)
    assert snaps[0]["anchor_ts_ms"] == 0


# ---------------------------------------------------------------------------
# CLI / file-loading integration
# ---------------------------------------------------------------------------

def test_run_end_to_end_over_jsonl_dir(tmp_path):
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    rows = [_poly_row("cond-5", "tokA", 0.50, 0.49, 0.51, 1000),
            _poly_row("cond-5", "tokB", 0.50, 0.49, 0.51, 1000)]
    (books_dir / "day1.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    report = ca.run([str(books_dir)], "polymarket")
    assert report["claim"] == "calibration_only"
    assert report["n_sets"] == 1
    assert report["n_snapshots"] == 1
    assert report["verdict"]["verdict"] == "COHERENT"
    assert report["not_verified"]  # non-empty NOT VERIFIED list carried through


def test_main_cli_writes_json_and_prints_no_trading_logic(tmp_path, capsys):
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    rows = [_poly_row("cond-6", "tokA", 0.50, 0.49, 0.51, 1000),
            _poly_row("cond-6", "tokB", 0.50, 0.49, 0.51, 1000)]
    (books_dir / "day1.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    out_dir = tmp_path / "out"
    rc = ca.main(["--books", str(books_dir), "--venue", "polymarket", "--out", str(out_dir)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "no trading logic; calibration/measurement only" in captured.out
    out_path = out_dir / "coherence_audit_polymarket.json"
    assert out_path.exists()
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["claim"] == "calibration_only"
    assert written["venue"] == "polymarket"
