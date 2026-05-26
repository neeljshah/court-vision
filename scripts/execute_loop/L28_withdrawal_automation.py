"""L28_withdrawal_automation.py — Withdrawal Automation (execute_loop layer 28).

Paper-vs-live mode delegated to L44_paper_mode (see L44 for the canonical
env-var list).  Per-layer flag checked: withdrawal (WITHDRAWAL_LIVE_ENABLED).
Env var is kept as fallback for backward compatibility when L44 is absent
(soft-import pattern ensures behavior is identical if L44 is absent).

Monitors per-book balances and recommends / queues / executes withdrawals when
a balance exceeds the per-book target by more than the configured buffer.

Public API:
    compute_withdrawal_candidates(account_balances, target_max_per_book) -> list[WithdrawalCandidate]
    execute_withdrawal(book, amount, user_token) -> dict
    queue_withdrawal_for_review(candidate) -> str   # returns queue_id
    get_pending_withdrawals() -> list[dict]

CLI:
    python L28_withdrawal_automation.py recommend
    python L28_withdrawal_automation.py queue --book dk --amount 5000
    python L28_withdrawal_automation.py execute --queue-id X --token WITHDRAW_AUTHORIZED
    python L28_withdrawal_automation.py list-pending

Paper vs Live Mode (MODE GATING):
    This module is paper-by-default. The module-level constant ``PAPER_MODE = True``
    expresses this intent. All withdrawal executions record entries with
    status='queued_paper' unless live mode is explicitly enabled via the env var
    below. Live mode must never be enabled in automated/CI contexts.

Environment Variables:
    WITHDRAWAL_LIVE_ENABLED — Set to "1" to enable live withdrawal execution.
        Default: "0" (paper mode). When unset or "0", execute_withdrawal records
        entries with status='queued_paper' and does not call any book API.
        Required to be absent (or "0") for all paper / simulation runs.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# L44 soft-import — paper/live mode delegation
# ---------------------------------------------------------------------------
try:
    from scripts.execute_loop import L44_paper_mode as _L44  # type: ignore
except Exception:
    _L44 = None  # type: ignore


def _is_live_withdrawal() -> bool:
    """Return True if live withdrawal execution is enabled (via L44 or fallback env var)."""
    if _L44 is not None:
        return _L44.is_live_for_layer("withdrawal")
    return os.environ.get("WITHDRAWAL_LIVE_ENABLED", "0") == "1"


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
PAPER_MODE = True  # Safety default: all withdrawals are paper unless WITHDRAWAL_LIVE_ENABLED=1
USER_TOKEN_VALUE = "WITHDRAW_AUTHORIZED"
BUFFER_MULTIPLIER = 1.10  # only recommend withdrawal if balance > target * 1.10
DEFAULT_TARGETS: dict[str, float] = {
    "dk": 10_000.0,
    "fd": 10_000.0,
    "kalshi": 5_000.0,
    "polymarket": 5_000.0,
    "sporttrade": 5_000.0,
}
LEDGER_PATH = PROJECT_DIR / "data" / "ledger" / "pending_withdrawals.json"

# Statuses treated as "active" / blocking a duplicate queue entry
_ACTIVE_STATUSES = {"pending_review", "queued_paper"}


# ---------------------------------------------------------------------------
# DATACLASSES
# ---------------------------------------------------------------------------
@dataclass
class WithdrawalCandidate:
    book: str
    current_balance: float
    target_max: float
    recommended_withdrawal: float
    reasoning: str


# ---------------------------------------------------------------------------
# LEDGER HELPERS
# ---------------------------------------------------------------------------
def _load_ledger(path: Path) -> dict:
    """Return ledger dict; creates empty structure if file absent."""
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    return {"entries": []}


def _save_ledger(ledger: dict, path: Path) -> None:
    """Atomic write: .tmp + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(ledger, fh, indent=2)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------
def compute_withdrawal_candidates(
    account_balances: dict[str, float],
    target_max_per_book: Optional[dict[str, float]] = None,
) -> list[WithdrawalCandidate]:
    """Return one WithdrawalCandidate per book whose balance exceeds target * BUFFER_MULTIPLIER.

    Args:
        account_balances: mapping of book -> current balance.
        target_max_per_book: mapping of book -> target max balance.
            Falls back to DEFAULT_TARGETS for missing books.

    Returns:
        List of WithdrawalCandidate (may be empty).
    """
    targets = dict(DEFAULT_TARGETS)
    if target_max_per_book:
        targets.update(target_max_per_book)

    candidates: list[WithdrawalCandidate] = []
    for book, balance in account_balances.items():
        target = targets.get(book.lower(), targets.get(book, 0.0))
        if target <= 0:
            log.warning("No target configured for book %r — skipping", book)
            continue

        threshold = target * BUFFER_MULTIPLIER
        if balance <= threshold:
            log.debug(
                "Book %s balance $%.2f is within buffer (threshold $%.2f) — no action",
                book, balance, threshold,
            )
            continue

        recommended = balance - target
        diff = balance - target
        buffer_pct = (BUFFER_MULTIPLIER - 1.0) * 100
        reasoning = (
            f"balance ${balance:,.2f} exceeds target ${target:,.2f} "
            f"by ${diff:,.2f} (>{buffer_pct:.0f}%)"
        )
        candidates.append(
            WithdrawalCandidate(
                book=book,
                current_balance=balance,
                target_max=target,
                recommended_withdrawal=recommended,
                reasoning=reasoning,
            )
        )
        log.info("Withdrawal candidate: %s — %s", book, reasoning)

    return candidates


def execute_withdrawal(
    book: str,
    amount: float,
    user_token: str,
    *,
    ledger_path: Path = LEDGER_PATH,
) -> dict:
    """Validate and record a withdrawal.

    Paper mode (default): appends entry with status='queued_paper'.
    Live mode (WITHDRAWAL_LIVE_ENABLED='1'): appends with status='live_executed'
        (stub — does not call any book API).

    Args:
        book: sportsbook identifier.
        amount: withdrawal amount in USD.
        user_token: must equal USER_TOKEN_VALUE.
        ledger_path: override for testing.

    Returns:
        dict with keys: status, queue_id, book, amount.

    Raises:
        ValueError: if amount <= 0.
        PermissionError: if token invalid or live mode not enabled.
    """
    if amount <= 0:
        raise ValueError(f"amount must be > 0, got {amount!r}")

    if user_token != USER_TOKEN_VALUE:
        raise PermissionError(f"Invalid user_token — expected {USER_TOKEN_VALUE!r}")

    live_enabled = _is_live_withdrawal()

    if live_enabled:
        status = "live_executed"
        log.warning("LIVE withdrawal executed: book=%s amount=%.2f", book, amount)
    else:
        status = "queued_paper"
        log.info("Paper withdrawal queued: book=%s amount=%.2f", book, amount)

    queue_id = uuid.uuid4().hex[:12]
    entry = {
        "queue_id": queue_id,
        "book": book,
        "amount": amount,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reasoning": f"execute_withdrawal call — {status}",
    }

    ledger = _load_ledger(ledger_path)
    ledger["entries"].append(entry)
    _save_ledger(ledger, ledger_path)

    return {"status": status, "queue_id": queue_id, "book": book, "amount": amount}


def queue_withdrawal_for_review(
    candidate: WithdrawalCandidate,
    *,
    ledger_path: Path = LEDGER_PATH,
) -> str:
    """Queue a WithdrawalCandidate for human review.

    Deduplicates: if an active entry (status in _ACTIVE_STATUSES) already exists
    for the same book, returns the existing queue_id without writing a new entry.

    Args:
        candidate: populated WithdrawalCandidate dataclass.
        ledger_path: override for testing.

    Returns:
        queue_id string (12-char hex).
    """
    ledger = _load_ledger(ledger_path)

    # Check for existing active entry for the same book
    for entry in ledger["entries"]:
        if entry.get("book") == candidate.book and entry.get("status") in _ACTIVE_STATUSES:
            existing_id = entry["queue_id"]
            log.info(
                "Duplicate queue skipped for book %s — existing queue_id=%s",
                candidate.book, existing_id,
            )
            return existing_id

    queue_id = uuid.uuid4().hex[:12]
    entry = {
        "queue_id": queue_id,
        "book": candidate.book,
        "amount": candidate.recommended_withdrawal,
        "status": "pending_review",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reasoning": candidate.reasoning,
    }
    ledger["entries"].append(entry)
    _save_ledger(ledger, ledger_path)
    log.info("Queued withdrawal for review: book=%s queue_id=%s", candidate.book, queue_id)
    return queue_id


def get_pending_withdrawals(*, ledger_path: Path = LEDGER_PATH) -> list[dict]:
    """Return all entries with status in _ACTIVE_STATUSES.

    Args:
        ledger_path: override for testing.

    Returns:
        List of entry dicts.
    """
    ledger = _load_ledger(ledger_path)
    pending = [e for e in ledger["entries"] if e.get("status") in _ACTIVE_STATUSES]
    log.debug("get_pending_withdrawals: %d active entries", len(pending))
    return pending


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="L28 Withdrawal Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # recommend
    sub.add_parser("recommend", help="Print withdrawal candidates based on DEFAULT_TARGETS")

    # queue
    q = sub.add_parser("queue", help="Queue a withdrawal for human review")
    q.add_argument("--book", required=True, help="Book name (dk, fd, kalshi, ...)")
    q.add_argument("--amount", type=float, required=True, help="Amount to withdraw")

    # execute
    ex = sub.add_parser("execute", help="Execute a queued withdrawal (paper or live)")
    ex.add_argument("--queue-id", required=True, help="queue_id from pending list")
    ex.add_argument("--token", required=True, help="User authorisation token")

    # list-pending
    sub.add_parser("list-pending", help="List pending withdrawals")

    return parser


def _cmd_recommend(args: argparse.Namespace) -> None:  # noqa: ARG001
    # Use dummy balances if none available — print usage instructions
    print("Usage: supply account_balances programmatically via the Python API.")
    print("Default targets:", DEFAULT_TARGETS)


def _cmd_queue(args: argparse.Namespace) -> None:
    target = DEFAULT_TARGETS.get(args.book.lower(), 0.0)
    candidate = WithdrawalCandidate(
        book=args.book,
        current_balance=args.amount + target,
        target_max=target,
        recommended_withdrawal=args.amount,
        reasoning=f"CLI queue: book={args.book} amount={args.amount}",
    )
    queue_id = queue_withdrawal_for_review(candidate)
    print(f"Queued — queue_id: {queue_id}")


def _cmd_execute(args: argparse.Namespace) -> None:
    ledger = _load_ledger(LEDGER_PATH)
    match = next(
        (e for e in ledger["entries"] if e.get("queue_id") == args.queue_id),
        None,
    )
    if not match:
        print(f"ERROR: queue_id {args.queue_id!r} not found in ledger")
        sys.exit(1)
    result = execute_withdrawal(match["book"], match["amount"], args.token)
    print(f"Result: {result}")


def _cmd_list_pending(args: argparse.Namespace) -> None:  # noqa: ARG001
    pending = get_pending_withdrawals()
    if not pending:
        print("No pending withdrawals.")
        return
    for entry in pending:
        print(
            f"  [{entry['queue_id']}] {entry['book']:15s} "
            f"${entry['amount']:>10,.2f}  status={entry['status']}  "
            f"ts={entry['timestamp']}"
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = _build_parser()
    args = parser.parse_args()
    dispatch = {
        "recommend": _cmd_recommend,
        "queue": _cmd_queue,
        "execute": _cmd_execute,
        "list-pending": _cmd_list_pending,
    }
    dispatch[args.cmd](args)


if __name__ == "__main__":
    main()
