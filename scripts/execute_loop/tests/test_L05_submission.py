"""test_L05_submission.py — Unit tests for L05_submission_engine.

All HTTP calls are mocked; no real network activity.

Run:
    conda run -n basketball_ai --no-capture-output \
        python -m pytest scripts/execute_loop/tests/test_L05_submission.py -v
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import types
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Project root on sys.path
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_DIR))

# Stub nba_api_headers_patch (L07 pulls it in)
_api_stub = types.ModuleType("src.data.nba_api_headers_patch")
sys.modules.setdefault("src.data.nba_api_headers_patch", _api_stub)

# Stub settle_tonight (L07 needs it at import time via lazy import — safe to leave)
_rlc = types.ModuleType("scripts.validation.real_lines_check")
_stn = types.ModuleType("scripts.validation.real_lines_check.settle_tonight")
_stn.fetch_boxscore_player_stats = MagicMock(return_value={})
sys.modules.setdefault("scripts.validation.real_lines_check", _rlc)
sys.modules.setdefault("scripts.validation.real_lines_check.settle_tonight", _stn)

# Stub requests so L05 import succeeds even if requests not installed
_requests_stub = types.ModuleType("requests")
_requests_stub.post = MagicMock()
_requests_stub.delete = MagicMock()
_requests_stub.Timeout = Exception
_requests_stub.RequestException = Exception
sys.modules.setdefault("requests", _requests_stub)

import scripts.execute_loop.L05_submission_engine as L05  # noqa: E402
import scripts.execute_loop.L07_pnl_ledger as L07  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_VALID_LINEUP = {
    "players": ["player_001", "player_002", "player_003", "player_004",
                "player_005", "player_006", "player_007", "player_008"],
    "entry_fee": 25.0,
}


def _fresh_contest_id() -> str:
    return f"contest_{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Redirect all ledger I/O to tmp_path; ensure paper mode; reset token buckets."""
    monkeypatch.setenv("SUBMISSION_MODE", "paper")
    monkeypatch.delenv("USER_TOKEN", raising=False)
    monkeypatch.delenv("DK_LIVE_ENABLED", raising=False)
    monkeypatch.delenv("FD_LIVE_ENABLED", raising=False)
    monkeypatch.delenv("DK_API_KEY", raising=False)
    monkeypatch.delenv("FD_API_KEY", raising=False)

    monkeypatch.setattr(L05, "_LEDGER_DIR", tmp_path)
    monkeypatch.setattr(L05, "_CACHE_FILE", tmp_path / "submission_cache.json")
    monkeypatch.setattr(L05, "_PAPER_FILE", tmp_path / "paper_submissions.json")

    # Redirect L07 ledger to same tmp_path
    monkeypatch.setattr(L07, "_LEDGER_DIR", tmp_path)
    monkeypatch.setattr(L07, "_BETS_FILE", tmp_path / "bets.parquet")
    monkeypatch.setattr(L07, "_BETS_CSV", tmp_path / "bets.csv")

    # Reset token buckets so each test starts with a full bucket
    L05._buckets.clear()

    yield


# ---------------------------------------------------------------------------
# Test 1 — paper submit returns PAPER_OK and L07 bet row written
# ---------------------------------------------------------------------------
def test_paper_submit_paper_ok_and_l07_row_written(tmp_path):
    """submit_lineup paper → status=PAPER_OK, submission_id starts with 'paper_'."""
    contest_id = _fresh_contest_id()
    result = L05.submit_lineup("dk", contest_id, _VALID_LINEUP)

    assert result.status == "PAPER_OK", f"status={result.status!r}"
    assert result.submission_id is not None
    assert result.submission_id.startswith("paper_")
    assert result.error_message is None
    assert result.book == "dk"
    assert result.contest_id == contest_id

    # L07 paper bet should exist
    bets = L07.get_open_bets()
    assert len(bets) >= 1
    bet = bets[0]
    assert bet.test_mode is True
    assert "dk" in bet.market
    assert bet.stake == pytest.approx(25.0)

    # paper_submissions.json written
    paper_path = L05._PAPER_FILE
    assert paper_path.exists()
    records = json.loads(paper_path.read_text())
    assert len(records) == 1
    assert records[0]["status"] == "PAPER_OK"


# ---------------------------------------------------------------------------
# Test 2 — same idempotency_key twice → cached result, no second L07 write
# ---------------------------------------------------------------------------
def test_idempotency_key_prevents_duplicate(tmp_path):
    """Same idempotency_key → second call returns cached result, L07 written once."""
    contest_id = _fresh_contest_id()
    ikey = "fixed-ikey-001"

    r1 = L05.submit_lineup("dk", contest_id, _VALID_LINEUP, idempotency_key=ikey)
    assert r1.status == "PAPER_OK"

    r2 = L05.submit_lineup("dk", contest_id, _VALID_LINEUP, idempotency_key=ikey)
    assert r2.status == "PAPER_OK"
    assert r2.submission_id == r1.submission_id, "Cached sub_id should match first"

    # Only one paper record and one L07 bet
    records = json.loads(L05._PAPER_FILE.read_text())
    assert len(records) == 1, f"Expected 1 paper record, got {len(records)}"

    bets = L07.get_open_bets()
    assert len(bets) == 1, f"Expected 1 L07 bet, got {len(bets)}"


# ---------------------------------------------------------------------------
# Test 3 — token bucket: 6th submission in rapid succession → RATE_LIMITED
# ---------------------------------------------------------------------------
def test_sixth_submission_rate_limited(tmp_path):
    """With bucket capacity=5, 6th rapid submission returns RATE_LIMITED."""
    # Drain the bucket to 0 tokens manually
    bucket = L05._get_bucket("dk")
    bucket.tokens = 0.0

    contest_id = _fresh_contest_id()
    # Build unique lineups so idempotency doesn't short-circuit
    lineup = {**_VALID_LINEUP, "players": [f"p_{i}" for i in range(8)]}
    result = L05.submit_lineup("dk", contest_id, lineup)

    assert result.status == "RATE_LIMITED", f"Expected RATE_LIMITED, got {result.status!r}"


# ---------------------------------------------------------------------------
# Test 4 — SUBMISSION_MODE=live without USER_TOKEN → PermissionError
# ---------------------------------------------------------------------------
def test_live_without_user_token_raises(monkeypatch):
    """submit_lineup with SUBMISSION_MODE=live, no USER_TOKEN → PermissionError."""
    monkeypatch.setenv("SUBMISSION_MODE", "live")
    monkeypatch.delenv("USER_TOKEN", raising=False)
    contest_id = _fresh_contest_id()

    with pytest.raises(PermissionError, match="live submission gates not satisfied"):
        L05.submit_lineup("dk", contest_id, _VALID_LINEUP)


# ---------------------------------------------------------------------------
# Test 5 — lineup missing players → REJECTED "invalid_lineup"
# ---------------------------------------------------------------------------
def test_missing_players_rejected():
    """Lineup without 'players' key → REJECTED with error_message='invalid_lineup'."""
    contest_id = _fresh_contest_id()
    bad_lineup = {"entry_fee": 25.0}  # no 'players'

    result = L05.submit_lineup("dk", contest_id, bad_lineup)

    assert result.status == "REJECTED"
    assert result.error_message == "invalid_lineup"


# ---------------------------------------------------------------------------
# Test 6 — cancel_submission with unknown id → False
# ---------------------------------------------------------------------------
def test_cancel_unknown_submission_id():
    """cancel_submission returns False for an unknown / paper id."""
    assert L05.cancel_submission("dk", "unknown_id_xyz") is False
    assert L05.cancel_submission("dk", "paper_abc123def456") is False


# ---------------------------------------------------------------------------
# Bonus Test 7 — submit_batch returns list of SubmissionResult
# ---------------------------------------------------------------------------
def test_submit_batch_returns_list():
    """submit_batch with 2 valid submissions returns 2 PAPER_OK results."""
    subs = [
        {"book": "dk", "contest_id": _fresh_contest_id(), "lineup": _VALID_LINEUP},
        {"book": "fd", "contest_id": _fresh_contest_id(), "lineup": _VALID_LINEUP},
    ]
    results = L05.submit_batch(subs)
    assert len(results) == 2
    for r in results:
        assert isinstance(r, L05.SubmissionResult)
        assert r.status == "PAPER_OK"


# ---------------------------------------------------------------------------
# Bonus Test 8 — submit_batch with invalid lineup in the middle
# ---------------------------------------------------------------------------
def test_submit_batch_partial_failure():
    """submit_batch: valid|invalid|valid → PAPER_OK|REJECTED|PAPER_OK."""
    subs = [
        {"book": "dk", "contest_id": _fresh_contest_id(), "lineup": _VALID_LINEUP},
        {"book": "dk", "contest_id": _fresh_contest_id(), "lineup": {"entry_fee": 10}},
        {"book": "fd", "contest_id": _fresh_contest_id(), "lineup": _VALID_LINEUP},
    ]
    results = L05.submit_batch(subs)
    assert results[0].status == "PAPER_OK"
    assert results[1].status == "REJECTED"
    assert results[1].error_message == "invalid_lineup"
    assert results[2].status == "PAPER_OK"


# ---------------------------------------------------------------------------
# Bonus Test 9 — auto-idempotency key is stable for same inputs
# ---------------------------------------------------------------------------
def test_auto_idempotency_key_stable():
    """Auto-key is deterministic for the same book|contest|players."""
    lineup = {"players": ["a", "b", "c"]}
    k1 = L05._auto_key("dk", "c123", lineup)
    k2 = L05._auto_key("dk", "c123", {"players": ["c", "a", "b"]})  # order-independent
    assert k1 == k2


# ---------------------------------------------------------------------------
# Bonus Test 10 — _check_live_gates passes when all env vars present
# ---------------------------------------------------------------------------
def test_live_gates_pass_when_all_vars_set(monkeypatch):
    """_check_live_gates does NOT raise when all live-mode env vars are present."""
    monkeypatch.setenv("SUBMISSION_MODE", "live")
    monkeypatch.setenv("USER_TOKEN", "tok_abc")
    monkeypatch.setenv("DK_LIVE_ENABLED", "1")
    monkeypatch.setenv("DK_API_KEY", "apikey_dk")

    # Should not raise
    L05._check_live_gates("dk")
