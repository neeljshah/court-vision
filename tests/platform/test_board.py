"""tests/platform/test_board.py — unit tests for scripts.platformkit.frontend.board.

Coverage: HONEST_NOTE · row schema · probs in [0,1] · edge_vs_market DIAGNOSTIC ·
absent corpus → [] · to_json round-trip · window filter (cap + date window) ·
line-shop EV math (fair_prob=0.5 -> ev=0.05) + honest label · no banned words.

Run:  python -m pytest tests/platform/test_board.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import numpy as np
import pytest

from scripts.platformkit.frontend.board import (
    HONEST_NOTE, LINE_SHOP_NOTE, LINE_SHOP_EV_LABEL,
    _apply_window, _bundle_to_rows, _compute_line_shop_ev,
    _SPORT_REGISTRY, build_all_board, build_board, to_json,
)

_EXPECTED_KEYS = {
    "sport", "date", "home", "away", "model_prob", "market_fair_prob",
    "edge_vs_market", "best_book", "best_line", "line_shop_ev",
    "line_shop_note", "clv_placeholder", "calibration_tag", "honest_note",
}
_BANNED = ("guaranteed", "beat the market", "+EV edge", "profit", "lock")
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_bundle(n=5, has_market=True, has_closing=True, books=None):
    rng = np.random.default_rng(42)
    b = MagicMock()
    b.signal_col = rng.uniform(0.35, 0.65, size=n)
    b.target = rng.integers(0, 2, size=n).astype(float)
    b.dates = [f"2024-{i+1:02d}-01" for i in range(n)]
    b.lines = rng.uniform(0.40, 0.60, size=n) if has_market else None
    b.closing = rng.uniform(0.41, 0.59, size=n) if has_closing else None
    b.books = books
    return b


def _row(date="2024-06-01"):
    return {
        "sport": "s", "date": date, "home": None, "away": None,
        "model_prob": 0.55, "market_fair_prob": 0.50,
        "edge_vs_market": {"value": 0.05, "label": "DIAGNOSTIC — not a bet signal; markets are efficient"},
        "best_book": None, "best_line": None, "line_shop_ev": None,
        "line_shop_note": LINE_SHOP_NOTE, "clv_placeholder": None,
        "calibration_tag": "calibrated", "honest_note": HONEST_NOTE,
    }


# --- HONEST_NOTE ---

def test_honest_note_present():
    assert isinstance(HONEST_NOTE, str) and len(HONEST_NOTE) > 20

def test_honest_note_no_edge_claims():
    low = HONEST_NOTE.lower()
    for w in _BANNED:
        assert w.lower() not in low

def test_honest_note_contains_no_model_edge():
    assert "no model edge" in HONEST_NOTE.lower()


# --- _bundle_to_rows schema + values ---

def test_bundle_to_rows_schema():
    rows = _bundle_to_rows("test_sport", _make_bundle(n=3), "calibrated")
    assert len(rows) == 3
    for r in rows:
        assert _EXPECTED_KEYS == set(r.keys()), (
            f"Missing: {_EXPECTED_KEYS - set(r.keys())}  Extra: {set(r.keys()) - _EXPECTED_KEYS}")

def test_bundle_to_rows_probs_in_range():
    rows = _bundle_to_rows("test_sport", _make_bundle(n=10), "calibrated")
    for r in rows:
        if r["model_prob"] is not None:
            assert 0.0 <= r["model_prob"] <= 1.0
        if r["market_fair_prob"] is not None:
            assert 0.0 <= r["market_fair_prob"] <= 1.0

def test_bundle_to_rows_market_none_when_absent():
    rows = _bundle_to_rows("s", _make_bundle(has_market=False, has_closing=False), "c")
    assert all(r["market_fair_prob"] is None for r in rows)

def test_bundle_to_rows_edge_vs_market_diagnostic():
    rows = _bundle_to_rows("s", _make_bundle(n=3), "c")
    for r in rows:
        ev = r["edge_vs_market"]
        assert isinstance(ev, dict)
        assert "DIAGNOSTIC" in ev["label"]
        assert ev["value"] is None or isinstance(ev["value"], float)

def test_bundle_to_rows_edge_none_when_market_absent():
    rows = _bundle_to_rows("s", _make_bundle(has_market=False, has_closing=False), "c")
    assert all(r["edge_vs_market"]["value"] is None for r in rows)

def test_bundle_to_rows_single_book_defaults():
    rows = _bundle_to_rows("s", _make_bundle(n=2, books=None), "c")
    for r in rows:
        assert r["clv_placeholder"] is None
        assert r["line_shop_ev"] is None
        assert r["line_shop_note"] == LINE_SHOP_NOTE

def test_bundle_to_rows_no_banned_words():
    rows = _bundle_to_rows("s", _make_bundle(n=5), "c")
    low = json.dumps(rows).lower()
    for w in _BANNED:
        assert w.lower() not in low


# --- absent corpus / unknown sport ---

def test_build_board_absent_corpus_empty(tmp_path):
    assert build_board("basketball_nba", repo_root=tmp_path) == []

def test_build_board_unknown_sport_empty(tmp_path):
    assert build_board("cricket_unknownsport", repo_root=tmp_path) == []

def test_build_all_board_all_empty_when_no_corpus(tmp_path):
    board = build_all_board(repo_root=tmp_path)
    assert isinstance(board, dict)
    for sid in _SPORT_REGISTRY:
        assert sid in board
        assert board[sid] == []


# --- to_json ---

def test_to_json_writes_valid_json(tmp_path):
    rows = _bundle_to_rows("s", _make_bundle(n=4), "c")
    out = tmp_path / "board.json"
    to_json({"s": rows}, out)
    loaded = json.loads(out.read_text())
    assert len(loaded["s"]) == 4
    for r in loaded["s"]:
        assert "DIAGNOSTIC" in r["edge_vs_market"]["label"]


# --- Task 1: Window filter ---

def test_window_max_rows_caps():
    rows = [_row(f"2024-{m:02d}-01") for m in range(1, 13)]
    assert len(_apply_window(rows, None, 5, False)) <= 5

def test_window_max_rows_keeps_most_recent():
    dates = ["2024-01-01", "2024-04-01", "2024-07-01", "2024-10-01", "2024-12-01"]
    result = _apply_window([_row(d) for d in dates], None, 3, False)
    result_dates = {r["date"] for r in result}
    assert "2024-12-01" in result_dates
    assert "2024-10-01" in result_dates
    assert "2024-07-01" in result_dates
    assert "2024-01-01" not in result_dates

def test_window_max_rows_restored_asc():
    dates = ["2024-01-01", "2024-04-01", "2024-07-01", "2024-10-01"]
    result = _apply_window([_row(d) for d in dates], None, 3, False)
    rd = [r["date"] for r in result]
    assert rd == sorted(rd)

def test_window_last_n_days_date_range():
    dates = ["2024-01-01", "2024-10-01", "2024-11-01", "2024-12-01"]
    result = _apply_window([_row(d) for d in dates], 60, None, False)
    rds = {r["date"] for r in result}
    assert "2024-01-01" not in rds
    assert "2024-12-01" in rds
    assert "2024-11-01" in rds

def test_window_last_n_days_priority_over_max_rows():
    dates = ["2024-01-01", "2024-11-01", "2024-12-01"]
    result = _apply_window([_row(d) for d in dates], 45, 1, False)
    rds = {r["date"] for r in result}
    assert "2024-11-01" in rds and "2024-12-01" in rds and "2024-01-01" not in rds

def test_window_future_only_highest_priority():
    dates = ["2024-01-01", "2024-06-01", "2024-12-01"]
    result = _apply_window([_row(d) for d in dates], 1, 10, True)
    assert result == []  # corpus max=2024-12-01; nothing is > it

def test_window_no_filter_returns_all():
    rows = [_row(f"2024-{m:02d}-01") for m in range(1, 7)]
    assert len(_apply_window(rows, None, None, False)) == len(rows)

def test_window_empty_input():
    assert _apply_window([], 7, 100, False) == []


# --- Task 2: Line-shop EV ---

def test_lineshop_ev_math():
    """fair_prob=0.5 -> fair_decimal=2.0; best_line=2.10 -> ev=0.05 exactly."""
    books = [{"book": "A", "decimal_odds": 1.90}, {"book": "B", "decimal_odds": 2.10}]
    best_book, best_line, ev, note = _compute_line_shop_ev(books, 0.5)
    assert best_book == "B"
    assert best_line == 2.10
    assert ev is not None and abs(ev - 0.05) < 1e-9

def test_lineshop_ev_label_not_model_edge():
    books = [{"book": "A", "decimal_odds": 2.05}, {"book": "B", "decimal_odds": 1.95}]
    _, _, _, note = _compute_line_shop_ev(books, 0.5)
    assert "not a model edge" in note.lower()
    assert "line-shopping" in note.lower()

def test_lineshop_ev_none_when_no_market():
    books = [{"book": "A", "decimal_odds": 2.05}, {"book": "B", "decimal_odds": 1.95}]
    _, _, ev, _ = _compute_line_shop_ev(books, None)
    assert ev is None

def test_lineshop_single_book_fallback():
    best_book, _, ev, note = _compute_line_shop_ev([{"book": "A", "decimal_odds": 2.0}], 0.5)
    assert best_book is None and ev is None and note == LINE_SHOP_NOTE

def test_bundle_multibook_ev_end_to_end():
    """Verify EV math through _bundle_to_rows: closing=0.5, best=2.10 -> ev=0.05."""
    b = MagicMock()
    b.signal_col = np.array([0.55])
    b.target = np.array([1.0])
    b.dates = ["2024-06-01"]
    b.lines = None
    b.closing = np.array([0.5])
    b.books = [[{"book": "FD", "decimal_odds": 2.10}, {"book": "DK", "decimal_odds": 1.90}]]
    rows = _bundle_to_rows("s", b, "calibrated")
    r = rows[0]
    assert r["best_book"] == "FD"
    assert r["best_line"] == 2.10
    assert abs(r["line_shop_ev"] - 0.05) < 1e-9
    assert "not a model edge" in r["line_shop_note"].lower()

def test_lineshop_label_no_banned_words():
    books = [{"book": "A", "decimal_odds": 2.10}, {"book": "B", "decimal_odds": 1.90}]
    _, _, _, note = _compute_line_shop_ev(books, 0.5)
    low = note.lower()
    for w in ("guaranteed", "beat the market", "profit", "lock"):
        assert w not in low


# --- Real corpus smoke (skip if absent) ---

@pytest.mark.parametrize("sport_id", list(_SPORT_REGISTRY.keys()))
def test_real_corpus_smoke(sport_id):
    reg = _SPORT_REGISTRY[sport_id]
    primary = _REPO_ROOT / reg["corpus_dir"] / reg["primary_parquet"]
    if not primary.exists():
        pytest.skip(f"Corpus absent: {primary}")
    rows = build_board(sport_id, repo_root=_REPO_ROOT)
    assert len(rows) > 0
    assert len(rows) <= 200  # default window
    for r in rows:
        assert _EXPECTED_KEYS == set(r.keys())
        if r["model_prob"] is not None:
            assert 0.0 <= r["model_prob"] <= 1.0
        assert "DIAGNOSTIC" in r["edge_vs_market"]["label"]
    low = json.dumps(rows).lower()
    for w in _BANNED:
        assert w.lower() not in low
