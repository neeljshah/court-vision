"""scripts.platformkit.improve.selfimprove_stage -- the SHIP/ROLLBACK staging,
reject-ledger + proposal-row emission, and corpus-replication count, split out of
selfimprove_daemon to keep each file <=300 LOC. Glue only: NO new math, NO new
decisions -- the daemon still owns the SHIP/REJECT verdict and the cursor advance.

Helpers:
  append_jsonl(path, rec)                  -- one ASCII jsonl row
  default_gate_fn(candidate)               -- real 5-gate verdict (no promotion)
  count_replicated_corpora(candidate)      -- DISTINCT all-positive corpora (deduped)
  stage_ship(name, candidate, store, root) -- version + atomic-swap + auto-rollback
  emit_reject(reject_path, ...)            -- a reject_ledger row
  emit_proposal(proposals_path, ...)       -- the PROPOSAL row (never MEMORY.md)

INVARIANTS: never edits MEMORY.md, never writes data/registry/, never flips a flag.
Calibration, not edge. ASCII; <=300 LOC.
"""
from __future__ import annotations

import pathlib
from typing import Any, Callable, Dict, Optional, Sequence, Tuple


def append_jsonl(path: pathlib.Path, rec: Dict[str, Any]) -> None:
    # Crash-safe append (read-modify-write + os.replace): a partial reject/proposal
    # line can never be left for the next loop read.
    from scripts.platformkit.io_atomic import append_jsonl_atomic
    append_jsonl_atomic(path, rec, encoding="ascii", sort_keys=True, default=str)


def call_recal(fn: Callable[..., Optional[Dict[str, Any]]], name: str,
               settled: Sequence[Dict[str, Any]], window: int,
               report: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Call recalibrate_fn, threading the out-of-band ``report`` dict when it is accepted.

    ``report`` lets the recalibrator distinguish a GENUINE no-candidate (evaluated -> declined)
    from a TRANSIENT failure (FeedDegradedError / exception -> bailed BEFORE evaluation). A fn
    that does not accept ``report`` is called exactly as before (report stays empty -> the
    daemon's fail-SAFE default treats an armed None as transient PRESERVE, never a silent skip).
    Return contract is UNCHANGED: still Optional[dict].
    """
    import inspect
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        params = {}
    if "report" in params or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return fn(name, settled, window, report=report)
    return fn(name, settled, window)


def default_gate_fn(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Real 5-gate verdict WITHOUT registry promotion (the daemon owns the swap)."""
    from improve.ratchet_state import evaluate_candidate
    return evaluate_candidate(
        candidate["base_preds"], candidate["cand_preds"], candidate["y"],
        kind=candidate.get("kind", "prob"),
        corpora=candidate.get("corpora", []),
        fold_results=candidate.get("fold_results", []),
        stability_metric_fn=candidate["stability_metric_fn"],
        stability_data=candidate.get("stability_data", []),
        train_features=candidate.get("train_features", {}),
        infer_features=candidate.get("infer_features", {}),
        artifact=candidate["artifact"],
        artifact_meta=candidate.get("artifact_meta"),
        min_folds=candidate.get("min_folds", 1),
        min_corpora=candidate.get("min_corpora", 2),
        promote_on_ship=False,  # the daemon's artifact_store owns versioning + swap
    )


def count_replicated_corpora(candidate: Dict[str, Any]) -> int:
    """How many DISTINCT corpora show an all-positive lift (primary + extras).

    A corpus counts only if it has >=1 fold and EVERY fold delta > 0 (the
    all-proper-scores rule). Mirrors the multifold guard's corpus test so the
    daemon's >=2-corpora gate agrees with the ratchet.

    DEDUP-BY-corpus_id FIX: the primary corpus (fold_results) may ALSO appear in the
    `corpora` list -- e.g. wired with corpus_id == the primary's id. Counting it in both
    double-counts one corpus and can wrongly clear the >=2-corpora gate on a SINGLE
    corpus. We therefore label the primary with a stable id and count each corpus_id at
    most ONCE.
    """
    def _all_pos(folds: Sequence[Dict[str, Any]]) -> bool:
        fs = [f for f in folds if isinstance(f, dict) and "delta" in f]
        return bool(fs) and all(float(f["delta"]) > 0.0 for f in fs)

    counted: set = set()
    primary_id = str(candidate.get("primary_corpus_id", "__primary__"))
    if _all_pos(candidate.get("fold_results", [])):
        counted.add(primary_id)
    for i, cr in enumerate(candidate.get("corpora", []) or []):
        if not isinstance(cr, dict) or not _all_pos(cr.get("folds", [])):
            continue
        cid = str(cr.get("corpus_id", "__extra_%d__" % i))
        counted.add(cid)  # a corpus that repeats the primary's id collapses to one
    return len(counted)


def stage_ship(name: str, candidate: Dict[str, Any], store: Any,
               store_root: Optional[str]) -> Tuple[Optional[int], Optional[int],
                                                    str, Optional[str]]:
    """Stage a versioned artifact, atomic-swap `current`, then run the held-out
    check and AUTO-ROLLBACK if it regressed.

    Returns (shipped_version, rolled_to, decision, reason). On a clean ship the
    decision stays "SHIP" with reason None; on a regression it flips to "REJECT"
    with a reason and rolled_to set. The daemon owns the constants, so the strings
    are returned and re-mapped there (no import cycle).
    """
    payload = dict(candidate.get("payload", {}))
    payload.setdefault("note", "calibration, not edge")
    shipped_version = store.stage_version(name, payload, root=store_root)
    store.swap_current(name, shipped_version, root=store_root)

    rolled_to: Optional[int] = None
    decision = "SHIP"
    reason: Optional[str] = None
    check = candidate.get("held_out_check")
    if callable(check):
        res = store.auto_rollback_if_regressed(
            name, lambda rec: bool(check(rec)), root=store_root)
        if res["regressed"]:
            rolled_to = res["rolled_to"]
            decision = "REJECT"
            reason = "auto-rollback: new artifact regressed held-out check"
    return shipped_version, rolled_to, decision, reason


def emit_reject(reject_path: pathlib.Path, *, ts: float, name: str,
                decision: str, reasons: Sequence[str], n_rep: int) -> None:
    """Append a reject_ledger row for any non-SHIP (or rolled-back) decision."""
    append_jsonl(reject_path, {
        "ts": ts, "name": name, "decision": decision,
        "reasons": list(reasons), "n_corpora_replicated": n_rep,
    })


def emit_proposal(proposals_path: pathlib.Path, *, ts: float, name: str,
                  decision: str, reasons: Sequence[str],
                  shipped_version: Optional[int], rolled_to: Optional[int],
                  n_new: int, n_rep: int) -> None:
    """Append the PROPOSAL row (NEVER MEMORY.md / data/registry)."""
    append_jsonl(proposals_path, {
        "ts": ts, "name": name, "decision": decision, "reasons": list(reasons)[:8],
        "shipped_version": shipped_version, "rolled_back_to": rolled_to,
        "n_new": n_new, "n_corpora_replicated": n_rep,
        "note": "calibration, not edge; PROPOSAL only -- never edits MEMORY.md",
    })


__all__ = [
    "append_jsonl", "call_recal", "default_gate_fn", "count_replicated_corpora",
    "stage_ship", "emit_reject", "emit_proposal",
]
