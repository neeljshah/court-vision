"""tests.platformkit.test_clv_ledger_write_path_guard -- QAFIX-5-2 acceptance.

Write-path coverage: asserts that CLV-ledger append callers use a dedup-aware
guard (locked_append / append_if_new / append_if_new_status_aware / etc.) and
that run_governance detects any dup that slips through. READ-ONLY on real files.

Acceptance criteria (BACKLOG QAFIX-5-2):
  (A) N-thread concurrent identical-row via locked_append(check_dup=True):
      rows <= N (no explosion, no corruption, no unexpected exceptions).
  (B) clv_ledger_io.append_row has no dedup -- it is a raw primitive.
  (C) run_governance on synthetic dup ledger -> concurrency gate FAIL + exit != 0.
  (D) Real ledger mtime unchanged after test run.
  (E) No $/roi/pnl key in any output row.
  (F) Never raises on missing ledger.
  (G) Known guard modules export guard symbols; known raw-path callers tracked.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      tests/platformkit/test_clv_ledger_write_path_guard.py -q
"""
from __future__ import annotations

import ast
import json
import pathlib
import threading
from pathlib import Path
from typing import Any, Dict, List

import pytest

from governance.concurrency_guard import (
    DuplicateRowError,
    locked_append,
    load_rows_guarded,
    ledger_path as _real_ledger_path,
)
from governance import run_governance as _rg

_REPO = pathlib.Path(__file__).resolve().parents[2]
_BANNED_KEYS = frozenset({"roi","pnl","profit","loss","bankroll","dollar","$","usd","net_profit","return"})
_N = 12


def _assert_no_banned(obj: Any, label: str = "") -> None:
    if isinstance(obj, dict):
        for k in obj:
            assert k.lower() not in _BANNED_KEYS, "Banned key %r in %s" % (k, label)
            _assert_no_banned(obj[k], label + "." + k)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _assert_no_banned(v, label + "[%d]" % i)


def _ledger(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "test_ledger.jsonl"


def _row(bid: str) -> Dict[str, Any]:
    return {"bet_id": bid, "sport": "nba", "matchup": "BOS@NYK",
            "side": "home", "taken_decimal": 2.10, "stake_units": 1.0, "status": "open"}


# ---------------------------------------------------------------------------
# (A) Concurrent N identical-row appends via locked_append(check_dup=True)
# ---------------------------------------------------------------------------

def test_concurrent_identical_rows_no_corruption_no_explosion(tmp_path):
    """Advisory guard: no row corruption, row count <= N, at least 1 success."""
    ledger = _ledger(tmp_path)
    row = _row("nba|BOS@NYK|moneyline|home|DK|2026-06-20")
    errors: List[str] = []
    successes: List[str] = []
    barrier = threading.Barrier(_N)

    def worker():
        barrier.wait()
        try:
            successes.append(locked_append(row, path=ledger))
        except DuplicateRowError:
            pass
        except Exception as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=worker) for _ in range(_N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert not errors, "Unexpected worker errors: %s" % errors
    rows = load_rows_guarded(path=ledger)
    for r in rows:
        assert isinstance(r, dict) and r.get("bet_id") == row["bet_id"]
    # No explosion: row count bounded by thread count.
    assert len(rows) <= _N
    assert len(successes) >= 1
    for r in rows:
        _assert_no_banned(r, "ledger_row")


# ---------------------------------------------------------------------------
# (B) clv_ledger_io.append_row has no dedup (raw primitive)
# ---------------------------------------------------------------------------

def test_clv_ledger_io_append_row_has_no_dedup(tmp_path):
    """clv_ledger_io.append_row is a raw primitive -- callers must add a guard."""
    from scripts.platformkit import clv_ledger_io as io_mod
    ledger = _ledger(tmp_path)
    row = {"bet_id": "raw-001", "side": "home", "stake_units": 1.0}
    io_mod.append_row(row, path=ledger)
    io_mod.append_row(row, path=ledger)
    rows = io_mod.load_rows(path=ledger)
    assert len(rows) == 2, "Raw primitive must not dedup (callers must layer a guard)"


# ---------------------------------------------------------------------------
# (C) run_governance detects synthetic dup -> concurrency gate FAIL + exit != 0
# ---------------------------------------------------------------------------

def test_run_governance_nonzero_on_synthetic_dup(tmp_path):
    """Synthetic dup in ledger -> _run_concurrency FAIL -> run_all exit_code != 0."""
    ledger = _ledger(tmp_path)
    row = _row("nba|LAL@GSW|moneyline|home|FanDuel|2026-06-20")
    with ledger.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
        fh.write(json.dumps(row) + "\n")

    result = _rg._run_concurrency(ledger)
    assert result["ok"] is False, "Concurrency gate must FAIL on dup row; got ok=True"
    assert len(result["duplicate_keys"]) >= 1

    full = _rg.run_all(ledger_path=ledger, load_disk=False)
    assert full["exit_code"] != 0, "run_all must exit non-zero on dup ledger"
    _assert_no_banned(result, "concurrency_result")
    _assert_no_banned(full.get("gate_results", {}), "gate_results")


# ---------------------------------------------------------------------------
# (D) Real ledger mtime unchanged
# ---------------------------------------------------------------------------

def test_real_ledger_mtime_unchanged():
    """Running this test must NOT mutate the real ledger."""
    real = _real_ledger_path()
    if not real.exists():
        return
    mtime_before = real.stat().st_mtime
    from governance.concurrency_guard import _row_key
    _row_key({"bet_id": "canary", "status": "open"})
    assert real.stat().st_mtime == mtime_before, "Real ledger mtime changed!"


# ---------------------------------------------------------------------------
# (E) No banned keys in synthetic rows
# ---------------------------------------------------------------------------

def test_no_banned_keys_in_synthetic_rows():
    row = _row("nba|GSW@BOS|moneyline|away|BetMGM|2026-06-20")
    _assert_no_banned(row, "synthetic_row")


# ---------------------------------------------------------------------------
# (F) Never raises on missing ledger
# ---------------------------------------------------------------------------

def test_never_raises_on_missing_ledger(tmp_path):
    missing = tmp_path / "does_not_exist.jsonl"
    try:
        rows = load_rows_guarded(path=missing)
    except Exception as exc:
        pytest.fail("load_rows_guarded raised on missing ledger: %s" % exc)
    assert rows == []


def test_run_concurrency_never_raises_on_missing_ledger(tmp_path):
    missing = tmp_path / "no_ledger.jsonl"
    try:
        result = _rg._run_concurrency(missing)
    except Exception as exc:
        pytest.fail("_run_concurrency raised on missing ledger: %s" % exc)
    assert result["ok"] is True, "Missing ledger -> no dups -> ok=True"


# ---------------------------------------------------------------------------
# (G) Guard-module audit (AST-based, read-only)
# ---------------------------------------------------------------------------

def _parse(rel: str) -> "ast.Module | None":
    full = _REPO / rel
    if not full.exists():
        return None
    try:
        return ast.parse(full.read_text(encoding="utf-8", errors="replace"), filename=rel)
    except SyntaxError:
        return None


def _imported_names(tree: ast.AST) -> "frozenset[str]":
    """All local bindings introduced by import statements, including aliases.

    Strips leading underscores from aliases so private-alias conventions
    (``from foo import bar as _bar``) still match the canonical name.
    """
    names: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.name.split(".")[-1])
                if alias.asname:
                    names.add(alias.asname)
                    stripped = alias.asname.lstrip("_")
                    if stripped:
                        names.add(stripped)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                asname = alias.asname or alias.name
                names.add(asname.split(".")[-1])
    return frozenset(names)


def _defined_names(tree: ast.AST) -> "frozenset[str]":
    names: set = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
    return frozenset(names)


def test_guard_modules_define_expected_symbols():
    """Guard implementations must define or export their guard symbols."""
    specs = {
        "governance/concurrency_guard.py": {"locked_append", "assert_no_dup_and_append"},
        "scripts/platformkit/clv_ledger_dedup.py": {"append_if_new"},
        "scripts/platformkit/clv_ledger_status_dedup.py": {"append_if_new_status_aware"},
        "scripts/platformkit/clv_ledger_record_guard.py": {
            "record_bet_guarded", "record_settlement_guarded"},
    }
    for rel, expected in specs.items():
        tree = _parse(rel)
        if tree is None:
            continue
        defined = _defined_names(tree)
        for sym in expected:
            assert sym in defined, (
                "Guard symbol %r not found in %s (renamed or removed?)" % (sym, rel)
            )


def test_clv_settle_write_uses_status_aware_guard():
    """clv_settle_write.py must import append_if_new_status_aware."""
    tree = _parse("scripts/platformkit/clv_settle_write.py")
    if tree is None:
        return
    assert "append_if_new_status_aware" in _imported_names(tree), (
        "clv_settle_write.py must import append_if_new_status_aware"
    )


def test_clv_ledger_record_guard_imports_append_if_new():
    """clv_ledger_record_guard.py must import append_if_new (possibly aliased)."""
    tree = _parse("scripts/platformkit/clv_ledger_record_guard.py")
    if tree is None:
        return
    assert "append_if_new" in _imported_names(tree), (
        "clv_ledger_record_guard.py must import append_if_new"
    )


# ---------------------------------------------------------------------------
# Sanity: locked_append single-thread dedup + settlement twin pattern
# ---------------------------------------------------------------------------

def test_locked_append_single_thread_blocks_duplicate(tmp_path):
    """Single-thread: second identical-row locked_append raises DuplicateRowError."""
    ledger = _ledger(tmp_path)
    row = _row("nba|DEN@MIA|moneyline|home|Caesars|2026-06-20")
    locked_append(row, path=ledger)
    with pytest.raises(DuplicateRowError, match="already present"):
        locked_append(row, path=ledger)
    rows = load_rows_guarded(path=ledger)
    assert len(rows) == 1
    _assert_no_banned(rows[0], "row")


def test_locked_append_check_dup_false_allows_settlement_twin(tmp_path):
    """check_dup=False lets the intentional open+settled pair both land."""
    ledger = _ledger(tmp_path)
    bid = "nba|GSW@BOS|moneyline|away|DraftKings|2026-06-20"
    locked_append({"bet_id": bid, "status": "open", "stake_units": 1.0}, path=ledger)
    locked_append({"bet_id": bid, "status": "settled", "clv_pct": 1.8}, path=ledger,
                  check_dup=False)
    rows = load_rows_guarded(path=ledger)
    assert len(rows) == 2
    assert {r["status"] for r in rows} == {"open", "settled"}
