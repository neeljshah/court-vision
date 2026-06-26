"""Per-file test for activity_sources._paper (twin-aware n_open).

Run: python -m pytest scripts/platformkit/test_activity_sources.py -q

Covers:
  (a) plain open bet                          -> counted in n_open
  (b) open + settled twin (same bet_id)       -> NOT counted in n_open
  (c) settled-only bet                        -> NOT in n_open
  (d) n_settled is still the raw settled row count (unchanged)

Hermetic: no network, no real ledger, no data/ reads.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.platformkit.activity_sources import _paper


def _write_ledger(path: Path, rows: list) -> None:
    """Write rows as JSONL to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _fe(tmp_path: Path) -> Path:
    """Return a fake frontend dir with clv_ledger.jsonl written."""
    fe = tmp_path / "data" / "frontend"
    fe.mkdir(parents=True, exist_ok=True)
    return fe


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def rows_mixed():
    """Three scenarios: plain open, open+settled twin, settled-only."""
    return [
        # (a) plain open -- no settled twin anywhere
        {"bet_id": "plain-open-001", "status": "open", "sport": "nba",
         "channel": "paper", "market_type": "spread"},
        # (b1) open half of a twin pair
        {"bet_id": "twin-pair-002", "status": "open", "sport": "mlb",
         "channel": "paper", "market_type": "moneyline"},
        # (b2) settled half of the same twin pair -> (b1) must NOT appear in n_open
        {"bet_id": "twin-pair-002", "status": "settled", "sport": "mlb",
         "channel": "paper", "market_type": "moneyline"},
        # (c) settled-only bet -- no open counterpart
        {"bet_id": "settled-only-003", "status": "settled", "sport": "nba",
         "channel": "paper", "market_type": "total"},
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_n_open_twin_aware(tmp_path, rows_mixed):
    """Only plain-open-001 is truly open; twin-pair-002 open has a settled twin."""
    fe = _fe(tmp_path)
    _write_ledger(fe / "clv_ledger.jsonl", rows_mixed)
    result = _paper(fe)
    assert result["present"] is True
    assert result["n_open"] == 1, (
        "Expected 1 truly-open bet (plain-open-001); got %d" % result["n_open"]
    )


def test_n_settled_raw(tmp_path, rows_mixed):
    """n_settled must still be the raw count of all settled rows (2 in fixture)."""
    fe = _fe(tmp_path)
    _write_ledger(fe / "clv_ledger.jsonl", rows_mixed)
    result = _paper(fe)
    # twin-pair-002 settled + settled-only-003 -> 2 settled rows
    assert result["n_settled"] == 2, (
        "Expected 2 raw settled rows; got %d" % result["n_settled"]
    )


def test_n_total(tmp_path, rows_mixed):
    """n_total must equal all rows regardless of status."""
    fe = _fe(tmp_path)
    _write_ledger(fe / "clv_ledger.jsonl", rows_mixed)
    result = _paper(fe)
    assert result["n_total"] == 4


def test_empty_ledger(tmp_path):
    """Empty ledger -> present=False; n_open key not emitted (early return)."""
    fe = _fe(tmp_path)
    # No clv_ledger.jsonl written; _read_jsonl returns [] on OSError.
    result = _paper(fe)
    assert result["present"] is False
    # The early-return branch omits n_open (no rows to count).
    assert "n_open" not in result


def test_all_open_no_twins(tmp_path):
    """All open, no settled twins -> all counted."""
    rows = [
        {"bet_id": "a1", "status": "open", "sport": "nba",
         "channel": "paper", "market_type": "spread"},
        {"bet_id": "a2", "status": "open", "sport": "nba",
         "channel": "paper", "market_type": "total"},
    ]
    fe = _fe(tmp_path)
    _write_ledger(fe / "clv_ledger.jsonl", rows)
    result = _paper(fe)
    assert result["n_open"] == 2


def test_all_have_settled_twins(tmp_path):
    """Every open has a settled twin -> n_open == 0."""
    rows = [
        {"bet_id": "x1", "status": "open", "sport": "nba",
         "channel": "paper", "market_type": "spread"},
        {"bet_id": "x1", "status": "settled", "sport": "nba",
         "channel": "paper", "market_type": "spread"},
        {"bet_id": "x2", "status": "open", "sport": "mlb",
         "channel": "paper", "market_type": "moneyline"},
        {"bet_id": "x2", "status": "settled", "sport": "mlb",
         "channel": "paper", "market_type": "moneyline"},
    ]
    fe = _fe(tmp_path)
    _write_ledger(fe / "clv_ledger.jsonl", rows)
    result = _paper(fe)
    assert result["n_open"] == 0
    assert result["n_settled"] == 2
