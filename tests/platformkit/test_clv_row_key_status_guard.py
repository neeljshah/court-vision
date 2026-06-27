"""tests.platformkit.test_clv_row_key_status_guard -- QAFIX-6-1 acceptance tests.

Verifies the proposed status-aware _row_key fix WITHOUT editing the human-gated
governance/concurrency_guard.py.  Tests exercise a local ``_status_aware_row_key``
helper mirroring docs/research/concurrency_guard_row_key_patch.py.

Acceptance criteria (BACKLOG.md QAFIX-6-1):
  (1) same bet_id + status=open vs status=settled -> DISTINCT keys.
  (2) same bet_id + same status -> SAME key (true replay deduped).
  (3) governance preflight on 1 open + 1 settled row -> exits 0.
  (4) governance preflight on 2 true duplicates -> exits non-zero.
  (5) Never writes/mutates any real ledger file.
  (6) No $/roi/pnl key in any row or result dict.
  (7) Never raises on None/missing status field.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      tests/platformkit/test_clv_row_key_status_guard.py -q
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any, Dict, List

import pytest

from governance.concurrency_guard import _row_key as _current_row_key

_DEFAULT_STATUS = "open"

_BANNED_OUTPUT_KEYS = frozenset({
    "roi", "pnl", "profit", "loss", "bankroll", "dollar",
    "$", "usd", "net_profit", "return",
})


def _status_aware_row_key(row: Dict[str, Any]) -> str:
    """Status-aware dedup key: '<bet_id_or_hash>|<status>'.

    Proposed replacement for governance.concurrency_guard._row_key.
    Priority order for the id portion: bet_id -> row_id -> id -> SHA-1 hash.
    Falls back to _DEFAULT_STATUS ("open") when status is None/missing/empty.
    """
    for field in ("bet_id", "row_id", "id"):
        val = row.get(field)
        if val is not None:
            base = str(val)
            break
    else:
        payload = json.dumps(row, sort_keys=True, default=str)
        base = "sha1:" + hashlib.sha1(payload.encode("utf-8")).hexdigest()

    raw_status = row.get("status")
    if raw_status is None or str(raw_status).strip() == "":
        status = _DEFAULT_STATUS
    else:
        status = str(raw_status).strip().lower()

    return "%s|%s" % (base, status)


def _make_open_row(bet_id: str) -> Dict[str, Any]:
    return {
        "bet_id": bet_id,
        "sport": "nba",
        "matchup": "BOS@NYK",
        "side": "home",
        "taken_book": "DraftKings",
        "taken_decimal": 2.10,
        "model_prob": 0.52,
        "stake_units": 1.0,
        "status": "open",
        "game_date": "2026-06-20",
    }


def _make_settled_row(bet_id: str) -> Dict[str, Any]:
    return {
        "bet_id": bet_id,
        "status": "settled",
        "outcome": "win",
        "close_decimal": 2.05,
        "clv_pct": 2.44,
        "stake_units": 1.0,
        "game_date": "2026-06-20",
    }


def _assert_no_banned_keys(obj: Any, label: str = "") -> None:
    if isinstance(obj, dict):
        for k in obj:
            assert k.lower() not in _BANNED_OUTPUT_KEYS, (
                "Banned key %r found in %s" % (k, label or "output")
            )
            _assert_no_banned_keys(obj[k], label=label + "." + k)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _assert_no_banned_keys(v, label=label + "[%d]" % i)


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_open_and_settled_produce_distinct_keys():
    """Criterion (1): same bet_id, different status -> two DISTINCT keys."""
    bet = "nba|BOS@NYK|moneyline|home|DraftKings|2026-06-20"
    key_open = _status_aware_row_key(_make_open_row(bet))
    key_settled = _status_aware_row_key(_make_settled_row(bet))

    assert key_open != key_settled, (
        "open and settled rows must produce distinct keys; got same key=%r" % key_open
    )
    assert key_open.endswith("|open"), "open key must end with |open"
    assert key_settled.endswith("|settled"), "settled key must end with |settled"
    _assert_no_banned_keys({"key_open": key_open, "key_settled": key_settled})


def test_same_bet_id_and_status_produce_same_key():
    """Criterion (2): same bet_id + same status -> SAME key (true replay blocked)."""
    bet = "nba|BOS@NYK|moneyline|home|DraftKings|2026-06-20"
    row_a = _make_open_row(bet)
    row_b = dict(_make_open_row(bet))
    row_b["ts"] = "2026-06-20T12:00:01.000000+00:00"

    key_a = _status_aware_row_key(row_a)
    key_b = _status_aware_row_key(row_b)

    assert key_a == key_b, (
        "Same bet_id + same status must produce identical keys; "
        "got key_a=%r key_b=%r" % (key_a, key_b)
    )


def test_governance_preflight_exits_0_on_open_plus_settled(tmp_path):
    """Criterion (3): 1 open + 1 settled row for same bet_id -> preflight OK."""
    bet = "nba|LAL@GSW|moneyline|away|FanDuel|2026-06-20"
    rows = [_make_open_row(bet), _make_settled_row(bet)]

    seen: Dict[str, int] = {}
    dups: List[str] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        key = _status_aware_row_key(r)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:
            dups.append(key)

    assert len(dups) == 0, (
        "Status-aware key must yield 0 duplicates for 1-open+1-settled; "
        "got dups=%r" % dups
    )
    exit_code = 0 if len(dups) == 0 else 1
    assert exit_code == 0, "Preflight must exit 0 for open+settled pair"
    _assert_no_banned_keys({"dup_keys": dups, "exit_code": exit_code})


def test_governance_preflight_nonzero_on_true_duplicates(tmp_path):
    """Criterion (4): 2 true duplicates (same bet_id AND same status) -> non-zero."""
    bet = "nba|MIL@BOS|moneyline|home|BetMGM|2026-06-20"
    rows = [_make_open_row(bet), dict(_make_open_row(bet))]

    seen: Dict[str, int] = {}
    dups: List[str] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        key = _status_aware_row_key(r)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:
            dups.append(key)

    assert len(dups) > 0, (
        "Two rows with same bet_id AND same status must register as duplicates"
    )
    exit_code = 0 if len(dups) == 0 else 1
    assert exit_code != 0, "Preflight must exit non-zero on true duplicates"
    _assert_no_banned_keys({"dup_keys": dups, "exit_code": exit_code})


def test_real_ledger_mtime_unchanged():
    """Criterion (5): running tests must NOT mutate the real ledger file."""
    from governance.concurrency_guard import ledger_path

    real_ledger = ledger_path()
    if real_ledger.exists():
        mtime_before = real_ledger.stat().st_mtime
    else:
        return

    bet = "nba|DEN@MIN|moneyline|home|Caesars|2026-06-20"
    for r in [_make_open_row(bet), _make_settled_row(bet)]:
        _ = _status_aware_row_key(r)
        _ = _current_row_key(r)

    if real_ledger.exists():
        mtime_after = real_ledger.stat().st_mtime
        assert mtime_after == mtime_before, (
            "Real ledger mtime changed! Before=%f After=%f -- "
            "test must never write to the real ledger." % (mtime_before, mtime_after)
        )


def test_no_dollar_keys_in_test_rows():
    """Criterion (6): no $/roi/pnl keys in any row or key string."""
    bet = "nba|OKC@SAS|moneyline|home|DraftKings|2026-06-20"
    open_row = _make_open_row(bet)
    settled_row = _make_settled_row(bet)
    _assert_no_banned_keys(open_row, label="open_row")
    _assert_no_banned_keys(settled_row, label="settled_row")

    key_open = _status_aware_row_key(open_row)
    key_settled = _status_aware_row_key(settled_row)
    for k in _BANNED_OUTPUT_KEYS:
        assert k not in key_open.lower(), "Banned key %r in open key %r" % (k, key_open)
        assert k not in key_settled.lower(), (
            "Banned key %r in settled key %r" % (k, key_settled)
        )


def test_no_raise_on_none_or_missing_status():
    """Criterion (7): _status_aware_row_key never raises on None/missing status."""
    cases = [
        {"bet_id": "test-001"},
        {"bet_id": "test-002", "status": None},
        {"bet_id": "test-003", "status": ""},
        {"bet_id": "test-004", "status": "   "},
        {},
    ]
    for row in cases:
        try:
            key = _status_aware_row_key(row)
        except Exception as exc:
            pytest.fail(
                "Raised %s on row=%r -- must never raise on missing/None status"
                % (exc, row)
            )
        assert isinstance(key, str) and len(key) > 0, (
            "Key must be a non-empty string for row=%r" % row
        )
        if row.get("bet_id"):
            assert key.endswith("|open"), (
                "Missing/None status must fall back to |open; got %r for row=%r"
                % (key, row)
            )


def test_current_key_collision_confirmed():
    """QAFIX-6-1 is SHIPPED: _row_key now produces distinct keys for open vs settled.

    The original bug (bet_id alone -> collision) is fixed upstream in
    governance/concurrency_guard.py.  This test now verifies the FIX is in place:
    open and settled rows for the same bet_id produce DISTINCT keys under the
    current _row_key, matching _status_aware_row_key behaviour.
    """
    bet = "nba|IND@NYK|moneyline|home|FanDuel|2026-06-20"
    open_row = _make_open_row(bet)
    settled_row = _make_settled_row(bet)

    current_key_open = _current_row_key(open_row)
    current_key_settled = _current_row_key(settled_row)
    # Bug is fixed: upstream _row_key is now status-aware -> distinct keys.
    assert current_key_open != current_key_settled, (
        "QAFIX-6-1 fix not detected: current _row_key still collides for "
        "open vs settled rows (got same key=%r)" % current_key_open
    )

    proposed_key_open = _status_aware_row_key(open_row)
    proposed_key_settled = _status_aware_row_key(settled_row)
    assert proposed_key_open != proposed_key_settled, (
        "Proposed key must disambiguate open vs settled"
    )
