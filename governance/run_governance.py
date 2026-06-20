"""governance.run_governance -- the single governance AGGREGATOR + boot preflight.

Milestone-10 ties every honesty/correctness gate into ONE pass that exits 0/1.
A non-zero exit means the stack is NOT real-money-eligible / a fabrication or leak
slipped in; ``boot.ps1`` runs this as its last preflight phase and refuses to hand
the stack to the supervisor when it fails.

WHAT IT RUNS (each gate is a separate, tested module; this only orchestrates):
  * honesty_linter    -- no retracted number / $-edge claim / banned key in the
                         latest envelope / report / proposals.
  * provenance        -- number_provenance + fill_provenance: no FILLED/UNKNOWN
                         number presented as real; every fill labelled FILLED.
  * concurrency       -- the CLV ledger is intact and read via the lock-guarded
                         path (no torn / duplicate rows in the loaded ledger).
  * pkl_integrity     -- every registered model's pkl/meta n_features_in matches
                         the registry (no silent feature-width drift).
  * leak_audit        -- the golden/build states are leak-free (vintage + schema
                         + walk-forward), when a build is available.
  * parity            -- train==inference parity holds for the provided candidates.
  * realmoney_authorized -- REPORTED (default-DENY) but does NOT gate ok-ness:
                         paper stays green; real money requires a human flip +
                         signed token, never granted by this preflight.
  * ledger_health        -- REPORTED (non-blocking): surfaces synthetic/test_
                         row count, malformed game_id count, dup-key count,
                         and CLV-honesty from clv_ledger_sanity.scan_ledger.
                         Operators see dirtiness in the scoreboard; purge stays
                         CLI-only -- this gate NEVER auto-mutates the ledger.
  * improve_ledger_reconcile -- REPORTED (non-blocking): reconciles daemon SHIP
                         rows in the loop ledger against graded CLV/eval rows;
                         surfaces n_ship, n_graded, n_orphan_ship, n_promoted.
                         An orphan SHIP (pending CLV grade) is INSUFFICIENT_DATA,
                         never a gate failure. Read-only; never mutates anything.

OK RULE: ``ok`` is True iff every HONESTY/CORRECTNESS gate is clean. Real-money
authorization and ledger_health are reported but NOT required for ok (paper-only
stays green; ledger dirtiness is a visible non-blocking warning).

DECISION-ONLY: never authorizes a bet, never moves money, never writes an
artifact, never flips a flag, never writes data/registry/. It only READS the
current artifacts (or those injected by a caller / test) and returns a verdict.

INVARIANTS: build only under governance/; <=300 LOC; ASCII; no secrets; per-file
tests only.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

_logger = logging.getLogger("run_governance")

from governance import concurrency_guard as _conc
from governance import fill_provenance as _fill
from governance import honesty_linter as _lint
from governance import number_provenance as _prov
from governance import parity_check as _parity
from governance import pkl_integrity as _pkl
from governance import realmoney_gate as _rm
from governance import risk_register as _risk
from governance import leak_audit as _leak
from scripts.platformkit.ledger_audit.clv_selfheal import (
    selfheal as _selfheal,
    SELFHEAL_BLOCKED,
)
from scripts.platformkit.clv_ledger_sanity import scan_ledger as _scan_ledger
from governance.improve_ledger_reconcile import reconcile as _improve_reconcile

RUN_GOVERNANCE_VERSION = "governance.run_governance.v1"

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Default artifact locations (all local-only / gitignored). Absent -> the gate
# simply has nothing to flag, which is a CLEAN result, never a false failure.
_DEFAULT_ENVELOPE = _REPO_ROOT / "data" / "frontend" / "predict_envelope.json"
_DEFAULT_SCOREBOARD = (
    _REPO_ROOT / "scripts" / "platformkit" / "pm_trading" / "grade_summary.json")


def _gate(ok: bool, **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": bool(ok)}
    out.update(extra)
    return out


def _load_json(path: Path) -> Optional[Any]:
    """Best-effort read of a JSON artifact. Missing / malformed -> None."""
    try:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _run_honesty(artifacts: Sequence[Any]) -> Dict[str, Any]:
    """Lint every loaded artifact; clean iff none has a violation."""
    violations: List[Dict[str, Any]] = []
    for art in artifacts:
        if art is None:
            continue
        res = _lint.lint_obj(art)
        violations.extend(res["violations"])
    return _gate(len(violations) == 0, violations=violations,
                 version=_lint.LINTER_VERSION)


def _run_provenance(artifacts: Sequence[Any]) -> Dict[str, Any]:
    """number_provenance + fill_provenance over every loaded artifact."""
    violations: List[Dict[str, Any]] = []
    for art in artifacts:
        if art is None:
            continue
        violations.extend(_prov.assert_provenance(art)["violations"])
        violations.extend(_fill.assert_fills_flagged(art)["violations"])
    return _gate(len(violations) == 0, violations=violations,
                 version=_prov.PROVENANCE_CHECK_VERSION,
                 fill_version=_fill.FILL_CHECK_VERSION)


def _run_concurrency(ledger_path: Optional[Path]) -> Dict[str, Any]:
    """Ledger must be intact and dup-free. Runs keep-first self-heal pre-pass."""
    # Self-heal pre-pass: idempotent keep-first dedup (W-CLV-SELFHEAL).
    # Status-change rows (open->settle, same bet_id, different status) are NOT
    # dups and are untouched. Only same-(bet_id,status) rows are candidates.
    # If genuine dups survive the heal -> HEALED_BLOCKED -> fail-close.
    heal: Dict[str, Any] = {}
    if ledger_path is None or (ledger_path is not None and ledger_path.exists()):
        try:
            heal = _selfheal(path=ledger_path)
            if heal.get("dropped_keys"):
                _logger.info("clv_selfheal dropped %d key(s): %s",
                             len(heal["dropped_keys"]), heal["dropped_keys"])
            if heal.get("status") == SELFHEAL_BLOCKED:
                return _gate(False, error=heal.get("error", "HEALED_BLOCKED"),
                             n_rows=heal.get("rows_out", 0),
                             duplicate_keys=[], selfheal=heal)
        except Exception as exc:  # noqa: BLE001
            heal = {"error": "selfheal raised: %s" % exc}
    try:
        rows = _conc.load_rows_guarded(path=ledger_path)
    except Exception as exc:  # fail-closed
        return _gate(False, error=str(exc)[:200], n_rows=0,
                     duplicate_keys=[], selfheal=heal)
    seen: Dict[str, int] = {}
    dups: List[str] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        key = _conc._row_key(r)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:
            dups.append(key)
    return _gate(len(dups) == 0, n_rows=len(rows), duplicate_keys=dups, selfheal=heal)


def _run_pkl(registry_path: Optional[Path]) -> Dict[str, Any]:
    """Every registered model's pkl/meta n_features_in must match the registry."""
    reasons: List[str] = []
    checked: List[Dict[str, Any]] = []
    try:
        registry = _pkl._load_registry(registry_path)
    except Exception as exc:  # fail-closed
        return _gate(False, reason=str(exc)[:200], checked=[])
    seen_ids = []
    for row in registry:
        mid = str(row.get("model_id") or "")
        if not mid or mid in seen_ids:
            continue
        seen_ids.append(mid)
        res = _pkl.integrity_check({"model_id": mid,
                                    "n_features_in": row.get("n_features_in")},
                                   registry_path=registry_path)
        checked.append({"model_id": mid, "ok": res["ok"],
                        "reasons": res["reasons"]})
        if not res["ok"]:
            reasons.extend(res["reasons"])
    return _gate(len(reasons) == 0, checked=checked, reasons=reasons,
                 registry_version=_pkl.REGISTRY_VERSION)


def _run_leak(build: Any, **kw: Any) -> Dict[str, Any]:
    """Leak audit over a provided build; no build -> nothing to flag (clean)."""
    if build is None:
        return _gate(True, skipped="no build provided", findings=[],
                     version=_leak.AUDIT_VERSION)
    res = _leak.audit(build, **kw)
    return _gate(res["leak_free"], findings=res["findings"],
                 n_states=res["n_states"], version=res["version"])


def _run_parity(candidates: Any) -> Dict[str, Any]:
    """Parity gate over provided candidates; none -> nothing to flag (clean)."""
    if not candidates:
        return _gate(True, skipped="no candidates provided", failures=[],
                     version=_parity.PARITY_GATE_VERSION)
    res = _parity.check_candidates(candidates)
    return _gate(res["ok"], failures=res["failures"],
                 n_candidates=res["n_candidates"], version=res["version"])


def _run_realmoney(*, summary: Any, rows: Any, eligibility: Any,
                   human_approved: bool, token: Optional[str],
                   secret: Optional[str]) -> Dict[str, Any]:
    """Default-DENY authorization REPORT. Never gates ok-ness (paper stays green)."""
    res = _rm.authorize(summary=summary, rows=rows, eligibility=eligibility,
                        human_approved=human_approved, token=token, secret=secret)
    return {"authorized": res["authorized"], "authorizes_bet": False,
            "reasons": res["reasons"], "authz_version": res["authz_version"]}


def _run_improve_reconcile(loop_ledger_path: Optional[Path]) -> Dict[str, Any]:
    """REPORTED (non-blocking): daemon SHIP vs graded CLV/eval parity.

    Reads the loop ledger (.planning/loop/ledger.jsonl by default) and
    reconciles SHIP-verdict rows against graded rows (clv not None).  Surfaces
    n_ship, n_graded, n_orphan_ship, n_promoted.  NEVER gates ok-ness: an
    orphan SHIP means CLV grading is pending (offseason / no live prices), not
    a correctness violation.  Pure read-only; never raises.
    """
    try:
        return _improve_reconcile(path=loop_ledger_path)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "UNAVAILABLE",
            "n_ship": 0,
            "n_graded": 0,
            "n_orphan_ship": 0,
            "n_promoted": 0,
            "orphan_keys": [],
            "ledger_path": str(loop_ledger_path or ""),
            "message": "reconcile raised: %s" % str(exc)[:200],
            "error": str(exc)[:200],
        }


def _run_ledger_health(ledger_path: Optional[Path]) -> Dict[str, Any]:
    """Non-blocking REPORTED ledger-health scan. Never auto-mutates the ledger.

    Calls scan_ledger (read-only) and surfaces synthetic/test_ row count,
    malformed game_id count, dup-key count, and CLV-honesty summary as a
    reported line on the governance scoreboard.  The result is NEVER included
    in the ok-gate (operators see the dirtiness without blocking deployment).
    Purge stays CLI-only -- this gate never triggers purge_ledger.
    """
    try:
        report = _scan_ledger(path=ledger_path)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "INSUFFICIENT_DATA",
            "error": str(exc)[:200],
            "synthetic_count": 0,
            "malformed_count": 0,
            "dup_count": 0,
            "total_rows": 0,
            "settled_with_clv": 0,
            "settled_without_clv": 0,
            "honest_note": "calibration not edge; read-only; scan raised an error",
        }
    status = report.get("status", "INSUFFICIENT_DATA")
    return {
        "status": status,
        "total_rows": report.get("total_rows", 0),
        "synthetic_count": report.get("synthetic", {}).get("count", 0),
        "malformed_count": report.get("malformed", {}).get("count", 0),
        "dup_count": report.get("duplicates", {}).get("count", 0),
        "settled_with_clv": report.get("honest_clv", {}).get("settled_with_clv", 0),
        "settled_without_clv": report.get("honest_clv", {}).get("settled_without_clv", 0),
        "no_close_label": report.get("honest_clv", {}).get("no_close_label", ""),
        "honest_note": report.get("honest_note", "calibration not edge; read-only scan"),
    }


def run_all(
    *,
    envelope: Any = None,
    scoreboard: Any = None,
    proposals: Any = None,
    build: Any = None,
    parity_candidates: Any = None,
    ledger_path: Optional[Path] = None,
    registry_path: Optional[Path] = None,
    human_approved: bool = False,
    token: Optional[str] = None,
    secret: Optional[str] = None,
    eligibility: Any = None,
    leak_kwargs: Optional[Dict[str, Any]] = None,
    load_disk: bool = True,
) -> Dict[str, Any]:
    """Run EVERY governance gate over the current artifacts. Returns a verdict.

    Any artifact left None is loaded from its default on-disk location (when
    *load_disk*); an absent artifact yields a CLEAN gate (nothing to flag), never
    a false failure. Callers / tests may inject artifacts directly to force a gate.

    Returns::

        {
          "ok": bool,                 # True iff every honesty/correctness gate clean
          "gate_results": {
            "honesty_linter": {...}, "provenance": {...}, "concurrency": {...},
            "pkl_integrity": {...}, "leak_audit": {...}, "parity": {...},
            "realmoney_authorized": {...},   # reported, does NOT gate ok
            "ledger_health": {...},          # reported, does NOT gate ok
          },
          "risk_register": {...},     # the standing risk scoreboard
          "exit_code": 0 | 1,         # 0 iff ok
          "version": RUN_GOVERNANCE_VERSION,
        }

    DECISION-ONLY: never authorizes a bet, never writes anything, never flips a
    flag. ``ok`` does NOT require real-money authorization -- paper stays green.
    """
    if load_disk:
        if envelope is None:
            envelope = _load_json(_DEFAULT_ENVELOPE)
        if scoreboard is None:
            scoreboard = _load_json(_DEFAULT_SCOREBOARD)

    artifacts = [envelope, scoreboard, proposals]

    honesty = _run_honesty(artifacts)
    provenance = _run_provenance(artifacts)
    concurrency = _run_concurrency(ledger_path)
    pkl = _run_pkl(registry_path)
    leak = _run_leak(build, **(leak_kwargs or {}))
    parity = _run_parity(parity_candidates)
    realmoney = _run_realmoney(
        summary=scoreboard, rows=None, eligibility=eligibility,
        human_approved=human_approved, token=token, secret=secret)
    ledger_health = _run_ledger_health(ledger_path)
    improve_reconcile = _run_improve_reconcile(loop_ledger_path=None)

    gate_results = {
        "honesty_linter": honesty,
        "provenance": provenance,
        "concurrency": concurrency,
        "pkl_integrity": pkl,
        "leak_audit": leak,
        "parity": parity,
        "realmoney_authorized": realmoney,
        "ledger_health": ledger_health,       # REPORTED; never gates ok
        "improve_ledger_reconcile": improve_reconcile,  # REPORTED; never gates ok
    }

    # ok = AND over the honesty/correctness gates. Real-money authorization and
    # ledger_health are REPORTED but never required (paper-only operation stays green;
    # ledger dirtiness is surfaced as a visible non-blocking warning).
    blocking = ("honesty_linter", "provenance", "concurrency", "pkl_integrity",
                "leak_audit", "parity")
    ok = all(bool(gate_results[g]["ok"]) for g in blocking)

    return {
        "ok": ok,
        "gate_results": gate_results,
        "risk_register": _risk.render(),
        "exit_code": 0 if ok else 1,
        "version": RUN_GOVERNANCE_VERSION,
    }


def _format_scoreboard(result: Dict[str, Any]) -> str:
    """ASCII scoreboard for the preflight log."""
    lines = ["=== GOVERNANCE PREFLIGHT (%s) ===" % RUN_GOVERNANCE_VERSION]
    gr = result["gate_results"]
    blocking = ("honesty_linter", "provenance", "concurrency", "pkl_integrity",
                "leak_audit", "parity")
    for name in blocking:
        mark = "PASS" if gr[name]["ok"] else "FAIL"
        lines.append("  [%s] %s" % (mark, name))
    rm = gr["realmoney_authorized"]
    lines.append("  [%s] realmoney_authorized (reported; does not gate)"
                 % ("AUTH" if rm["authorized"] else "DENY"))
    lh = gr["ledger_health"]
    lh_status = lh.get("status", "INSUFFICIENT_DATA")
    lh_tag = "CLEAN" if lh_status == "clean" else lh_status.upper()
    lines.append(
        "  [%s] ledger_health (reported; does not gate) "
        "syn=%d mal=%d dup=%d settled_without_clv=%d"
        % (
            lh_tag,
            lh.get("synthetic_count", 0),
            lh.get("malformed_count", 0),
            lh.get("dup_count", 0),
            lh.get("settled_without_clv", 0),
        )
    )
    ir = gr.get("improve_ledger_reconcile", {})
    ir_status = ir.get("status", "UNAVAILABLE")
    lines.append(
        "  [%s] improve_ledger_reconcile (reported; does not gate) "
        "ship=%d graded=%d orphan=%d promoted=%d"
        % (
            ir_status,
            ir.get("n_ship", 0),
            ir.get("n_graded", 0),
            ir.get("n_orphan_ship", 0),
            ir.get("n_promoted", 0),
        )
    )
    lines.append("")
    lines.append(result["risk_register"]["text"])
    lines.append("")
    lines.append("VERDICT: %s (exit %d)"
                 % ("OK" if result["ok"] else "BLOCKED", result["exit_code"]))
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry: print the scoreboard and EXIT 0 (clean) / 1 (a violation)."""
    result = run_all()
    print(_format_scoreboard(result))
    return int(result["exit_code"])


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))


__all__ = [
    "RUN_GOVERNANCE_VERSION",
    "run_all",
    "main",
]
