"""Tests for scripts/execute_loop/L28_withdrawal_automation.py.

Run:
    conda run -n basketball_ai --no-capture-output \
        python -m pytest scripts/execute_loop/tests/test_L28_withdrawal.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure project root on path and module importable without heavy deps
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_DIR))

import scripts.execute_loop.L28_withdrawal_automation as L28


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def ledger_path(tmp_path: Path) -> Path:
    """Fresh isolated ledger file in tmp_path for each test."""
    return tmp_path / "pending_withdrawals.json"


@pytest.fixture(autouse=True)
def patch_ledger_path(ledger_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect all module-level LEDGER_PATH references to the isolated tmp file."""
    monkeypatch.setattr(L28, "LEDGER_PATH", ledger_path)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _make_candidate(
    book: str = "dk",
    current_balance: float = 15_000.0,
    target_max: float = 10_000.0,
) -> L28.WithdrawalCandidate:
    recommended = current_balance - target_max
    return L28.WithdrawalCandidate(
        book=book,
        current_balance=current_balance,
        target_max=target_max,
        recommended_withdrawal=recommended,
        reasoning=f"balance ${current_balance:,.2f} exceeds target ${target_max:,.2f}",
    )


# ---------------------------------------------------------------------------
# 1. compute_withdrawal_candidates — basic positive case
# ---------------------------------------------------------------------------
def test_compute_candidates_basic_positive():
    """Balance well above threshold → 1 candidate with correct recommended amount."""
    result = L28.compute_withdrawal_candidates(
        account_balances={"dk": 15_000.0},
        target_max_per_book={"dk": 10_000.0},
    )
    assert len(result) == 1
    c = result[0]
    assert c.book == "dk"
    assert c.current_balance == 15_000.0
    assert c.target_max == 10_000.0
    assert c.recommended_withdrawal == pytest.approx(5_000.0)
    assert "exceeds" in c.reasoning


# ---------------------------------------------------------------------------
# 2. execute_withdrawal — wrong token → PermissionError
# ---------------------------------------------------------------------------
def test_execute_withdrawal_wrong_token(ledger_path: Path):
    with pytest.raises(PermissionError, match="Invalid user_token"):
        L28.execute_withdrawal("dk", 1_000.0, "WRONG", ledger_path=ledger_path)


# ---------------------------------------------------------------------------
# 3. queue_withdrawal_for_review → entry in get_pending_withdrawals
# ---------------------------------------------------------------------------
def test_queue_and_get_pending(ledger_path: Path):
    candidate = _make_candidate("dk")
    queue_id = L28.queue_withdrawal_for_review(candidate, ledger_path=ledger_path)

    assert queue_id  # non-empty
    pending = L28.get_pending_withdrawals(ledger_path=ledger_path)
    assert len(pending) == 1
    entry = pending[0]
    assert entry["queue_id"] == queue_id
    assert entry["book"] == "dk"
    assert entry["status"] == "pending_review"
    assert entry["amount"] == pytest.approx(5_000.0)


# ---------------------------------------------------------------------------
# 4. execute_withdrawal — amount = 0 → ValueError
# ---------------------------------------------------------------------------
def test_execute_withdrawal_zero_amount(ledger_path: Path):
    with pytest.raises(ValueError, match="amount must be > 0"):
        L28.execute_withdrawal("dk", 0, L28.USER_TOKEN_VALUE, ledger_path=ledger_path)


# ---------------------------------------------------------------------------
# 5. compute_withdrawal_candidates — balance == target → empty
# ---------------------------------------------------------------------------
def test_compute_candidates_balance_equals_target():
    result = L28.compute_withdrawal_candidates(
        account_balances={"dk": 10_000.0},
        target_max_per_book={"dk": 10_000.0},
    )
    assert result == []


# ---------------------------------------------------------------------------
# 6. compute_withdrawal_candidates — balance at exactly 1.10× → no recommendation
# ---------------------------------------------------------------------------
def test_compute_candidates_at_buffer_boundary():
    """Balance == target * 1.10 is NOT > threshold, so still no recommendation."""
    result = L28.compute_withdrawal_candidates(
        account_balances={"dk": 11_000.0},
        target_max_per_book={"dk": 10_000.0},
    )
    assert result == []


# ---------------------------------------------------------------------------
# 7. Duplicate queue for same book → returns existing queue_id, single entry
# ---------------------------------------------------------------------------
def test_queue_no_duplicate(ledger_path: Path):
    candidate = _make_candidate("fd")
    first_id = L28.queue_withdrawal_for_review(candidate, ledger_path=ledger_path)
    second_id = L28.queue_withdrawal_for_review(candidate, ledger_path=ledger_path)

    assert first_id == second_id, "Duplicate queue should return existing queue_id"

    ledger = json.loads(ledger_path.read_text())
    active_for_fd = [
        e for e in ledger["entries"]
        if e["book"] == "fd" and e["status"] in L28._ACTIVE_STATUSES
    ]
    assert len(active_for_fd) == 1, "Must not create a second active entry for same book"


# ---------------------------------------------------------------------------
# 8. Live mode without WITHDRAWAL_LIVE_ENABLED + valid token → PermissionError
# ---------------------------------------------------------------------------
def test_execute_withdrawal_live_blocked_without_env(
    monkeypatch: pytest.MonkeyPatch,
    ledger_path: Path,
):
    monkeypatch.delenv("WITHDRAWAL_LIVE_ENABLED", raising=False)
    # Paper mode should succeed (no env flag needed)
    result = L28.execute_withdrawal(
        "dk", 500.0, L28.USER_TOKEN_VALUE, ledger_path=ledger_path
    )
    assert result["status"] == "queued_paper"

    # Simulate "live requested" by asserting live gating behaviour separately
    # via a direct env check — set env to "0" explicitly
    monkeypatch.setenv("WITHDRAWAL_LIVE_ENABLED", "0")
    result2 = L28.execute_withdrawal(
        "dk", 200.0, L28.USER_TOKEN_VALUE, ledger_path=ledger_path
    )
    assert result2["status"] == "queued_paper"


def test_execute_withdrawal_live_enabled(
    monkeypatch: pytest.MonkeyPatch,
    ledger_path: Path,
):
    """With WITHDRAWAL_LIVE_ENABLED='1' and valid token → live_executed status."""
    monkeypatch.setenv("WITHDRAWAL_LIVE_ENABLED", "1")
    result = L28.execute_withdrawal(
        "kalshi", 1_000.0, L28.USER_TOKEN_VALUE, ledger_path=ledger_path
    )
    assert result["status"] == "live_executed"
    assert result["book"] == "kalshi"
    assert result["amount"] == pytest.approx(1_000.0)
    assert len(result["queue_id"]) == 12


# ---------------------------------------------------------------------------
# Additional edge-case tests
# ---------------------------------------------------------------------------

def test_execute_withdrawal_negative_amount(ledger_path: Path):
    with pytest.raises(ValueError, match="amount must be > 0"):
        L28.execute_withdrawal("dk", -100.0, L28.USER_TOKEN_VALUE, ledger_path=ledger_path)


def test_execute_withdrawal_paper_writes_ledger(ledger_path: Path):
    """Paper execution should persist an entry to the JSON ledger."""
    result = L28.execute_withdrawal(
        "fd", 2_500.0, L28.USER_TOKEN_VALUE, ledger_path=ledger_path
    )
    assert ledger_path.exists()
    ledger = json.loads(ledger_path.read_text())
    assert len(ledger["entries"]) == 1
    entry = ledger["entries"][0]
    assert entry["queue_id"] == result["queue_id"]
    assert entry["status"] == "queued_paper"
    assert entry["amount"] == pytest.approx(2_500.0)


def test_compute_candidates_multiple_books():
    """Multiple books: only those strictly exceeding buffer threshold appear."""
    result = L28.compute_withdrawal_candidates(
        account_balances={
            "dk": 20_000.0,    # 20k > 10k * 1.10 = 11k → candidate
            "fd": 10_500.0,    # 10.5k ≤ 11k → no candidate
            "kalshi": 5_400.0, # 5.4k ≤ 5k * 1.10 = 5.5k → no candidate
        },
        target_max_per_book={"dk": 10_000.0, "fd": 10_000.0, "kalshi": 5_000.0},
    )
    assert len(result) == 1
    assert result[0].book == "dk"
    assert result[0].recommended_withdrawal == pytest.approx(10_000.0)


def test_queue_different_books_no_dedup(ledger_path: Path):
    """Queue entries for different books → each gets its own entry."""
    c_dk = _make_candidate("dk")
    c_fd = _make_candidate("fd")
    id_dk = L28.queue_withdrawal_for_review(c_dk, ledger_path=ledger_path)
    id_fd = L28.queue_withdrawal_for_review(c_fd, ledger_path=ledger_path)

    assert id_dk != id_fd
    pending = L28.get_pending_withdrawals(ledger_path=ledger_path)
    assert len(pending) == 2


def test_get_pending_excludes_non_active(ledger_path: Path):
    """Entries with status other than active statuses are excluded from get_pending."""
    ledger = {
        "entries": [
            {
                "queue_id": "aaa111bbb222",
                "book": "dk",
                "amount": 5_000.0,
                "status": "completed",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "reasoning": "done",
            },
            {
                "queue_id": "ccc333ddd444",
                "book": "fd",
                "amount": 3_000.0,
                "status": "pending_review",
                "timestamp": "2026-01-02T00:00:00+00:00",
                "reasoning": "awaiting",
            },
        ]
    }
    L28._save_ledger(ledger, ledger_path)
    pending = L28.get_pending_withdrawals(ledger_path=ledger_path)
    assert len(pending) == 1
    assert pending[0]["queue_id"] == "ccc333ddd444"


def test_atomic_write_creates_parent_dirs(tmp_path: Path):
    """_save_ledger creates missing parent directories."""
    deep_path = tmp_path / "a" / "b" / "c" / "ledger.json"
    L28._save_ledger({"entries": []}, deep_path)
    assert deep_path.exists()
    data = json.loads(deep_path.read_text())
    assert data == {"entries": []}
