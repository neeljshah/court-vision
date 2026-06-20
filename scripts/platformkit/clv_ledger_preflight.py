"""scripts.platformkit.clv_ledger_preflight -- governance preflight integrity check.

TWO RESPONSIBILITIES (R6-3-clv-ledger-preflight-integrity):

  1. IDEMPOTENT DEDUP PREFLIGHT
     Call ``dedup_ledger(path, dry_run=False)`` on the on-disk CLV ledger BEFORE
     governance.run_governance reads it, eliminating the persistent dup-key P1 that
     blocked governance preflight across QA iters 2/4/5/6/7/8/9/11.
     - Atomic + backed-up (delegates to clv_ledger_dedup.dedup_ledger).
     - Idempotent: clean ledger -> status=no_change, nothing written.
     - The dedup key is BET_ID-ONLY (clv_ledger_dedup._first_occurrence_rows):
       the FIRST occurrence of any bet_id is kept; subsequent rows with the same
       bet_id -- regardless of status -- are treated as duplicates and removed.
       This means an open row and its settled twin that share one bet_id WILL be
       collapsed: the settled twin is discarded.  The STATUS-AWARE key lives in
       concurrency_guard._row_key, which the preflight dedup path does NOT invoke.
       The intended normal lifecycle is that the settlement writer uses a
       status-keyed variant (append_if_new_status_aware / record_settlement_guarded)
       so the settled row arrives with a distinct key; the preflight dedup then only
       sees TRUE REPLAYS (identical bet_id AND identical status) and removes those.

  2. WRITER-ROUTE AUDIT (read-only AST scan)
     Assert that every known ledger-writer module imports a governance-approved guard
     symbol (locked_append / append_if_new / append_if_new_status_aware /
     record_bet_guarded / record_settlement_guarded) rather than calling the raw
     clv_ledger.record_bet or clv_ledger_io.append_row directly (no bypass).
     - READ-ONLY: the audit never mutates any source file or the ledger.
     - Any writer that imports ONLY a raw primitive with NO guard companion is
       flagged as a bypass route.

PUBLIC API:
  run_preflight(ledger_path=None) -> dict
     Runs both checks and returns::

       {
         "ok": bool,         # True iff dedup succeeded AND all writers routed OK
         "dedup": {
           "status":         str,   # "ok"|"no_change"|"no_file"|"dry_run"|"error:X"
           "dups_removed":   int,
           "n_in":           int,
           "n_out":          int,
           "path":           str,
         },
         "writer_audit": {
           "writer_route_ok": bool,
           "bypasses":        list[str],   # writer files with raw-only paths
           "checked":         list[str],   # all writer files examined
         },
         "honest_note":  str,
       }

     No $ / pnl / roi field anywhere.  Never raises.

HONESTY INVARIANTS (binding):
  * UNITS ONLY -- no dollar / bankroll / pnl / roi field introduced or preserved.
  * dedup uses dry_run=False: the first run fixes the ledger; subsequent runs are
    no-ops.  The original is backed up (.bak) before any rewrite.
  * The writer audit is READ-ONLY on source files; it never auto-edits code.
  * Never auto-starts governance.run_governance -- that is the caller's job.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII; no secrets;
never claims an edge; never writes a dollar field.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/test_clv_ledger_preflight.py -q
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.clv_ledger_dedup import dedup_ledger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HONEST_NOTE = (
    "calibration not edge; no $ field; dedup uses bet_id-only key "
    "(first occurrence kept); an open+settled twin with shared bet_id is "
    "collapsed to the open row -- the settled twin must use a distinct "
    "status-keyed bet_id to survive preflight; idempotent re-run = no_change; "
    "writer audit is read-only."
)

# Approved guard symbols: any writer that imports or defines at least one of
# these is considered correctly routed (they all ultimately funnel through
# clv_ledger_io.append_row under an advisory OS lock).
_APPROVED_GUARDS: frozenset = frozenset({
    "locked_append",
    "assert_no_dup_and_append",
    "append_if_new",
    "append_if_new_status",          # clv_ledger_status_append variant
    "append_if_new_status_aware",    # clv_ledger_status_dedup variant
    "record_bet_guarded",
    "record_settlement_guarded",
})

# Raw primitives: importing ONLY these (no approved guard companion) is a bypass.
_RAW_PRIMITIVES: frozenset = frozenset({
    "append_row",   # clv_ledger_io.append_row -- the lock-guarded byte-level primitive
    "record_bet",   # clv_ledger.record_bet -- no dedup layer
})

# Known in-lane writer modules to audit (relative to repo root).
# This list covers every non-test file that imports a write primitive.
_WRITER_MODULES: List[str] = [
    "scripts/platformkit/clv_settle_write.py",
    "scripts/platformkit/clv_ledger_record_guard.py",
    "scripts/platformkit/clv_ledger_status_dedup.py",
    "scripts/platformkit/clv_ledger_status_append.py",
    "scripts/platformkit/pm_trading/paper_autobet.py",
    "scripts/platformkit/pm_trading/record_bet_policy.py",
    "scripts/platformkit/pm_trading/pm_paper_tick_runner.py",
    "scripts/platformkit/pm_trading/run_paper_today.py",
    "scripts/platformkit/ingame/paper_ingame.py",
]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_REPO = Path(__file__).resolve().parents[2]


def _parse_file(rel: str) -> "Optional[ast.Module]":
    """Parse a Python source file; return the AST or None on any error."""
    full = _REPO / rel
    if not full.exists():
        return None
    try:
        return ast.parse(full.read_text(encoding="utf-8", errors="replace"),
                         filename=rel)
    except SyntaxError:
        return None


def _imported_names(tree: ast.Module) -> "frozenset[str]":
    """Return all local names introduced by import statements in *tree*."""
    names: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.name.split(".")[-1])
                if alias.asname:
                    names.add(alias.asname.lstrip("_"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                asname = alias.asname or alias.name
                names.add(asname.split(".")[-1])
    return frozenset(names)


def _defined_names(tree: ast.Module) -> "frozenset[str]":
    """Return all function/class/variable names defined at any level in *tree*."""
    names: set = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
    return frozenset(names)


def _audit_writer(rel: str) -> "Optional[bool]":
    """Return True if the writer routes through an approved guard, False if raw-only.

    Returns None when the file does not exist (skip).

    A file is considered ROUTED-OK when it either:
      (a) imports an approved guard symbol, OR
      (b) DEFINES an approved guard symbol (i.e., it IS a guard module).

    A file is flagged as a bypass only when it imports a raw primitive AND
    neither imports nor defines any approved guard.
    """
    tree = _parse_file(rel)
    if tree is None:
        return None
    imported = _imported_names(tree)
    defined = _defined_names(tree)
    all_names = imported | defined
    has_guard = bool(all_names & _APPROVED_GUARDS)
    has_raw = bool(imported & _RAW_PRIMITIVES)
    if has_raw and not has_guard:
        return False   # bypass: raw primitive with no guard companion
    return True        # OK: uses or defines an approved guard (or no raw write)


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

def run_preflight(
    ledger_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run the CLV ledger preflight: dedup + writer-route audit.

    Parameters
    ----------
    ledger_path:
        Override the on-disk ledger path.  Defaults to the canonical
        data/frontend/clv_ledger.jsonl.

    Returns
    -------
    dict
        See module docstring for the full schema.  Never raises.
        No $ / pnl / roi field in the output.
    """
    try:
        # --- 1. Idempotent dedup (dry_run=False: commits the rewrite atomically) ---
        dedup_result = dedup_ledger(ledger_path, dry_run=False)
        dedup_section: Dict[str, Any] = {
            "status": str(dedup_result.get("status", "error: unknown")),
            "dups_removed": int(dedup_result.get("dups_removed", 0)),
            "n_in": int(dedup_result.get("rows_in", 0)),
            "n_out": int(dedup_result.get("rows_out", 0)),
            "path": str(dedup_result.get("path", "")),
        }
        dedup_ok = dedup_section["status"] in ("ok", "no_change", "no_file")

        # --- 2. Writer-route audit (read-only AST scan) -----------------------
        bypasses: List[str] = []
        checked: List[str] = []
        for rel in _WRITER_MODULES:
            result = _audit_writer(rel)
            if result is None:
                continue  # file absent; skip gracefully
            checked.append(rel)
            if result is False:
                bypasses.append(rel)

        writer_route_ok = len(bypasses) == 0
        writer_section: Dict[str, Any] = {
            "writer_route_ok": writer_route_ok,
            "bypasses": bypasses,
            "checked": checked,
        }

        ok = dedup_ok and writer_route_ok

        return {
            "ok": ok,
            "dedup": dedup_section,
            "writer_audit": writer_section,
            "honest_note": _HONEST_NOTE,
        }

    except Exception as exc:  # noqa: BLE001 -- preflight must never crash governance
        return {
            "ok": False,
            "dedup": {
                "status": "error: %s" % type(exc).__name__,
                "dups_removed": 0,
                "n_in": 0,
                "n_out": 0,
                "path": str(ledger_path or ""),
            },
            "writer_audit": {
                "writer_route_ok": False,
                "bypasses": [],
                "checked": [],
            },
            "honest_note": _HONEST_NOTE,
        }


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description=(
            "CLV ledger preflight: idempotent dedup + writer-route audit. "
            "Exits 0 on clean, 1 on any issue."
        )
    )
    ap.add_argument("--ledger", default=None, help="override ledger path")
    a = ap.parse_args(list(argv) if argv is not None else None)
    result = run_preflight(Path(a.ledger) if a.ledger else None)
    print(json.dumps(result, default=str, indent=2, ensure_ascii=True))
    return 0 if result["ok"] else 1


__all__ = ["run_preflight"]

if __name__ == "__main__":
    raise SystemExit(_main())
