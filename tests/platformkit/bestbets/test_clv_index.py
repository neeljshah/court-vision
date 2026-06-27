"""test_clv_index.py -- per-file tests for BB-Q4 clv_index.

Acceptance criteria (from BACKLOG BB-Q4-clv-index):
  - 3 graded rows indexed -> hit returns clv_pct + clv_is_proxy.
  - Key absent -> clv_status INSUFFICIENT_DATA, clv_is_proxy True.
  - Ungraded rows silently ignored (not indexed).
  - No $ field in any output.

Run: python -m pytest tests/platformkit/bestbets/test_clv_index.py -q
"""
from __future__ import annotations

import sys
import pathlib

_REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))

from scripts.platformkit.bestbets.clv_index import (
    build_clv_index,
    load_clv_index,
    lookup,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_GRADED_ROWS = [
    {
        "game_id": "G001",
        "market_type": "moneyline",
        "side": "home",
        "graded": True,
        "clv_pct": 3.21,
        "beat_close": True,
        "clv_status": "graded",
        "clv_is_proxy": False,
    },
    {
        "game_id": "G001",
        "market_type": "spread",
        "side": "away",
        "graded": True,
        "clv_pct": -1.50,
        "beat_close": False,
        "clv_status": "graded",
        "clv_is_proxy": False,
    },
    {
        "game_id": "G002",
        "market_type": "total",
        "side": "over",
        "graded": True,
        "clv_pct": 0.80,
        "beat_close": True,
        "clv_status": "graded",
        "clv_is_proxy": True,
    },
]

_UNGRADED_ROW = {
    "game_id": "G003",
    "market_type": "moneyline",
    "side": "home",
    "graded": False,
    "clv_pct": 9.99,
    "clv_status": "graded",
    "clv_is_proxy": False,
}

_OPEN_ROW = {
    "game_id": "G004",
    "market_type": "moneyline",
    "side": "home",
    # no 'graded' key at all; clv_pct is None
    "clv_pct": None,
}

# ---------------------------------------------------------------------------
# Core acceptance tests
# ---------------------------------------------------------------------------

def test_three_graded_rows_indexed():
    """KEY ACCEPTANCE: 3 graded rows -> index has 3 entries, each hit returns
    clv_pct and clv_is_proxy."""
    idx = build_clv_index(_GRADED_ROWS)
    assert len(idx) == 3


def test_hit_returns_clv_pct():
    """Hit on a known key returns the stored clv_pct."""
    idx = build_clv_index(_GRADED_ROWS)
    result = lookup(idx, "G001", "moneyline", "home")
    assert result["clv_pct"] == 3.21


def test_hit_returns_clv_is_proxy():
    """Hit returns clv_is_proxy from the stored row."""
    idx = build_clv_index(_GRADED_ROWS)
    result = lookup(idx, "G001", "moneyline", "home")
    assert result["clv_is_proxy"] is False


def test_hit_returns_beat_close():
    """Hit returns beat_close correctly for positive and negative CLV rows."""
    idx = build_clv_index(_GRADED_ROWS)
    r_pos = lookup(idx, "G001", "moneyline", "home")
    r_neg = lookup(idx, "G001", "spread", "away")
    assert r_pos["beat_close"] is True
    assert r_neg["beat_close"] is False


def test_hit_proxy_row():
    """A graded row with clv_is_proxy=True is indexed and returned correctly."""
    idx = build_clv_index(_GRADED_ROWS)
    result = lookup(idx, "G002", "total", "over")
    assert result["clv_pct"] == 0.80
    assert result["clv_is_proxy"] is True


def test_miss_returns_insufficient_data():
    """KEY ACCEPTANCE: absent key -> clv_status=INSUFFICIENT_DATA, clv_is_proxy=True."""
    idx = build_clv_index(_GRADED_ROWS)
    result = lookup(idx, "G999", "moneyline", "home")
    assert result["clv_status"] == "INSUFFICIENT_DATA"
    assert result["clv_is_proxy"] is True
    assert result["clv_pct"] is None
    assert result["beat_close"] is None


def test_miss_on_empty_index():
    """Empty index always returns INSUFFICIENT_DATA."""
    idx = build_clv_index([])
    result = lookup(idx, "G001", "moneyline", "home")
    assert result["clv_status"] == "INSUFFICIENT_DATA"
    assert result["clv_is_proxy"] is True


# ---------------------------------------------------------------------------
# Ungraded rows ignored
# ---------------------------------------------------------------------------

def test_ungraded_row_not_indexed():
    """KEY ACCEPTANCE: row with graded=False must be silently ignored."""
    idx = build_clv_index([_UNGRADED_ROW])
    assert len(idx) == 0
    result = lookup(idx, "G003", "moneyline", "home")
    assert result["clv_status"] == "INSUFFICIENT_DATA"


def test_open_row_no_clv_pct_not_indexed():
    """Row with clv_pct=None (open/ungraded) must not appear in the index."""
    idx = build_clv_index([_OPEN_ROW])
    assert len(idx) == 0


def test_mixed_rows_only_graded_indexed():
    """Mix of graded + ungraded: only graded rows appear in index."""
    rows = _GRADED_ROWS + [_UNGRADED_ROW, _OPEN_ROW]
    idx = build_clv_index(rows)
    # Only the 3 graded rows should be in the index
    assert len(idx) == 3
    # G003 (ungraded) is absent
    assert lookup(idx, "G003", "moneyline", "home")["clv_status"] == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Key normalisation
# ---------------------------------------------------------------------------

def test_key_case_insensitive():
    """market_type and side are lowercased so MixedCase and UPPER both hit."""
    idx = build_clv_index(_GRADED_ROWS)
    r1 = lookup(idx, "G001", "Moneyline", "Home")
    r2 = lookup(idx, "G001", "MONEYLINE", "HOME")
    assert r1["clv_pct"] == 3.21
    assert r2["clv_pct"] == 3.21


def test_key_strips_whitespace():
    """Leading/trailing whitespace in game_id/market_type/side is stripped."""
    idx = build_clv_index(_GRADED_ROWS)
    result = lookup(idx, " G001 ", " moneyline ", " home ")
    assert result["clv_pct"] == 3.21


# ---------------------------------------------------------------------------
# Last-write-wins for duplicate keys
# ---------------------------------------------------------------------------

def test_duplicate_key_last_write_wins():
    """When two rows share the same (game_id, market_type, side) the later row wins."""
    rows = [
        {
            "game_id": "G010",
            "market_type": "moneyline",
            "side": "home",
            "graded": True,
            "clv_pct": 1.00,
            "beat_close": True,
            "clv_status": "graded",
            "clv_is_proxy": False,
        },
        {
            "game_id": "G010",
            "market_type": "moneyline",
            "side": "home",
            "graded": True,
            "clv_pct": 5.55,
            "beat_close": True,
            "clv_status": "graded",
            "clv_is_proxy": False,
        },
    ]
    idx = build_clv_index(rows)
    assert len(idx) == 1
    result = lookup(idx, "G010", "moneyline", "home")
    assert result["clv_pct"] == 5.55


# ---------------------------------------------------------------------------
# No banned output keys
# ---------------------------------------------------------------------------

def test_no_dollar_fields_on_hit():
    """No dollar / roi / pnl key in any hit result."""
    idx = build_clv_index(_GRADED_ROWS)
    result = lookup(idx, "G001", "moneyline", "home")
    banned = {"dollar", "roi", "pnl", "profit", "return", "revenue", "usd"}
    for key in result.keys():
        assert key.lower() not in banned, f"Banned key '{key}' in hit result"


def test_no_dollar_fields_on_miss():
    """No dollar / roi / pnl key in a miss result."""
    idx = build_clv_index([])
    result = lookup(idx, "X", "Y", "Z")
    banned = {"dollar", "roi", "pnl", "profit", "return", "revenue", "usd"}
    for key in result.keys():
        assert key.lower() not in banned, f"Banned key '{key}' in miss result"


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------

def test_non_dict_rows_skipped():
    """Non-dict items in the row list must not raise."""
    rows: list = [None, "bad", 42, _GRADED_ROWS[0]]
    idx = build_clv_index(rows)  # type: ignore[arg-type]
    assert len(idx) == 1


def test_lookup_returns_copy_not_reference():
    """Mutating the returned dict must not affect the index."""
    idx = build_clv_index(_GRADED_ROWS)
    r = lookup(idx, "G001", "moneyline", "home")
    r["clv_pct"] = 9999.0
    r2 = lookup(idx, "G001", "moneyline", "home")
    assert r2["clv_pct"] == 3.21


# ---------------------------------------------------------------------------
# load_clv_index: degrades to empty index when ledger absent
# ---------------------------------------------------------------------------

def test_load_clv_index_empty_when_no_ledger(monkeypatch):
    """load_clv_index must return {} and not raise when load_rows returns []."""
    import scripts.platformkit.clv_ledger_io as io_mod
    monkeypatch.setattr(io_mod, "load_rows", lambda **_: [])
    idx = load_clv_index()
    assert isinstance(idx, dict)
    assert len(idx) == 0


def test_load_clv_index_degrades_on_error(monkeypatch):
    """load_clv_index must return {} and not raise when load_rows raises."""
    import scripts.platformkit.clv_ledger_io as io_mod

    def boom(**_):
        raise OSError("ledger gone")

    monkeypatch.setattr(io_mod, "load_rows", boom)
    idx = load_clv_index()
    assert isinstance(idx, dict)
    assert len(idx) == 0


def test_load_clv_index_uses_graded_rows(monkeypatch):
    """load_clv_index indexes only graded rows from the ledger."""
    import scripts.platformkit.clv_ledger_io as io_mod
    monkeypatch.setattr(io_mod, "load_rows", lambda **_: _GRADED_ROWS + [_UNGRADED_ROW])
    idx = load_clv_index()
    assert len(idx) == 3
    # Ungraded row absent
    assert lookup(idx, "G003", "moneyline", "home")["clv_status"] == "INSUFFICIENT_DATA"
