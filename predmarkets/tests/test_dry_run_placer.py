"""Tests for predmarkets.dry_run_placer — ledger semantics, no network."""

from __future__ import annotations

import csv
import os

import pytest

from predmarkets.dry_run_placer import (
    LEDGER_COLS,
    _grade_row,
    _read_rows,
    place_dry_run_batch,
    settle_ledger,
    summarize_ledger,
)


def _make_edge(market_id: str, side: str = "YES", stake: float = 10.0,
               price: float = 0.40, model_prob: float = 0.60,
               venue: str = "polymarket", category: str = "Crypto") -> dict:
    return {
        "venue": venue,
        "market_id": market_id,
        "question": f"Q for {market_id}",
        "category": category,
        "side": side,
        "model_prob": model_prob,
        "edge_pp": model_prob - price,
        "price": price,
        "stake_dollars": stake,
        "expected_value_dollars": stake * (model_prob * (1 - price) / price - (1 - model_prob)),
        "kelly_used": 0.10,
        "confidence": 0.5,
        "model_name": "test",
        "reasoning": "test",
    }


def test_place_writes_pending_rows(tmp_path) -> None:
    ledger = str(tmp_path / "ledger.csv")
    report = place_dry_run_batch([_make_edge("M1"), _make_edge("M2", side="NO")], ledger)
    assert report["placed"] == 2
    assert report["total_rows_in_ledger"] == 2
    rows = _read_rows(ledger)
    assert all(r["status"] == "dry-run-pending" for r in rows)
    assert set(rows[0].keys()) == set(LEDGER_COLS)


def test_place_skips_zero_stake(tmp_path) -> None:
    ledger = str(tmp_path / "ledger.csv")
    report = place_dry_run_batch([
        _make_edge("M1", stake=0.0),
        _make_edge("M2", stake=10.0),
    ], ledger)
    assert report["placed"] == 1
    assert report["skipped_zero_stake"] == 1


def test_place_dedupes(tmp_path) -> None:
    ledger = str(tmp_path / "ledger.csv")
    place_dry_run_batch([_make_edge("M1")], ledger)
    report = place_dry_run_batch([_make_edge("M1"), _make_edge("M1", side="NO")], ledger)
    # Same venue + market_id + side dedupes; flipped side is allowed.
    assert report["placed"] == 1
    assert report["skipped_duplicate"] == 1


def test_grade_row_win() -> None:
    row = {
        "side": "YES",
        "stake_dollars": "10.00",
        "price": "0.40",
        "status": "dry-run-pending",
    }
    _grade_row(row, {"resolved": True, "yes_won": True, "closed_time": "2026-05-30T00:00:00Z"})
    assert row["status"] == "WIN"
    # 10 staked at 0.40 -> 25 contracts -> $25 payout -> $15 profit
    assert row["actual_payout"] == "25.00"
    assert row["profit"] == "+15.00"


def test_grade_row_loss() -> None:
    row = {
        "side": "YES",
        "stake_dollars": "10.00",
        "price": "0.40",
        "status": "dry-run-pending",
    }
    _grade_row(row, {"resolved": True, "yes_won": False, "closed_time": "x"})
    assert row["status"] == "LOSS"
    assert row["profit"] == "-10.00"


def test_grade_row_void_when_yes_won_unknown() -> None:
    row = {"side": "NO", "stake_dollars": "10", "price": "0.5", "status": "dry-run-pending"}
    _grade_row(row, {"resolved": True, "yes_won": None, "closed_time": "x"})
    assert row["status"] == "VOID"


def test_settle_grades_resolved_only(tmp_path) -> None:
    ledger = str(tmp_path / "ledger.csv")
    place_dry_run_batch([
        _make_edge("M_resolved_yes", side="YES", stake=10.0, price=0.40),
        _make_edge("M_resolved_no",  side="YES", stake=10.0, price=0.40),
        _make_edge("M_open",         side="YES", stake=10.0, price=0.40),
    ], ledger)

    class _FakePM:
        def get_market(self, mid):
            data = {
                "M_resolved_yes": {"closed": True, "outcomePrices": ["1", "0"], "closedTime": "t"},
                "M_resolved_no":  {"closed": True, "outcomePrices": ["0", "1"], "closedTime": "t"},
                "M_open":         {"closed": False, "outcomePrices": ["0.5", "0.5"]},
            }
            return data[mid]

    clients = {"polymarket": _FakePM()}
    report = settle_ledger(ledger, clients)
    assert report["checked"] == 3
    assert report["graded"] == 2
    assert report["still_pending"] == 1

    rows = _read_rows(ledger)
    by_id = {r["market_id"]: r for r in rows}
    assert by_id["M_resolved_yes"]["status"] == "WIN"
    assert by_id["M_resolved_no"]["status"] == "LOSS"
    assert by_id["M_open"]["status"] == "dry-run-pending"


def test_summary_breaks_down_by_model(tmp_path) -> None:
    ledger = str(tmp_path / "ledger.csv")
    e1 = _make_edge("M1", side="YES", stake=10.0, price=0.40)
    e1["model_name"] = "crypto_threshold_gbm"
    e2 = _make_edge("M2", side="YES", stake=10.0, price=0.40)
    e2["model_name"] = "crypto_threshold_gbm"
    e3 = _make_edge("M3", side="YES", stake=10.0, price=0.40, category="Politics")
    e3["model_name"] = "llm_claude/claude-haiku-4-5-20251001"
    place_dry_run_batch([e1, e2, e3], ledger)

    class _FakePM:
        def get_market(self, mid):
            d = {
                "M1": {"closed": True, "outcomePrices": ["1", "0"]},  # WIN
                "M2": {"closed": True, "outcomePrices": ["0", "1"]},  # LOSS
                "M3": {"closed": True, "outcomePrices": ["1", "0"]},  # WIN
            }
            return d[mid]

    settle_ledger(ledger, {"polymarket": _FakePM()})
    summary = summarize_ledger(ledger)
    by_model = summary["by_model"]
    assert "crypto_threshold_gbm" in by_model
    assert by_model["crypto_threshold_gbm"]["wins"] == 1
    assert by_model["crypto_threshold_gbm"]["losses"] == 1
    assert by_model["llm_claude/claude-haiku-4-5-20251001"]["wins"] == 1
    by_cat = summary["by_category"]
    assert "Crypto" in by_cat
    assert "Politics" in by_cat


def test_summary_rolls_up_pnl(tmp_path) -> None:
    ledger = str(tmp_path / "ledger.csv")
    place_dry_run_batch([
        _make_edge("M1", side="YES", stake=10.0, price=0.40),
        _make_edge("M2", side="YES", stake=10.0, price=0.40),
        _make_edge("M3", side="YES", stake=10.0, price=0.40),
    ], ledger)

    class _FakePM:
        def get_market(self, mid):
            d = {
                "M1": {"closed": True, "outcomePrices": ["1", "0"]},  # WIN  +$15
                "M2": {"closed": True, "outcomePrices": ["0", "1"]},  # LOSS -$10
                "M3": {"closed": False, "outcomePrices": ["0.5", "0.5"]},  # pending
            }
            return d[mid]

    settle_ledger(ledger, {"polymarket": _FakePM()})
    summary = summarize_ledger(ledger)
    assert summary["graded"] == 2
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert summary["pnl_dollars"] == pytest.approx(5.0)
    assert summary["staked_dollars"] == pytest.approx(20.0)
    assert summary["roi"] == pytest.approx(0.25)
    assert summary["hit_rate"] == pytest.approx(0.5)
