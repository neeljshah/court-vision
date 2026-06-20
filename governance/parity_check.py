"""governance.parity_check -- train==inference parity as a HARD governance gate.

Milestone-10 wrapper over the vetted ``improve.parity_check.parity_ok`` (M8). The
inner function is a pure, never-raising comparator that returns the divergences
and zero-reads between a candidate's train-time and inference-time feature dicts.
This governance layer turns that report into a BLOCKING decision: ANY divergence
or zero-read fails the gate. The train==inference invariant is the most expensive
bug class (a feature wired into training but silently reading 0.0 at inference),
so at the governance boundary it is fail-closed, not advisory.

Supports a single candidate (one train/infer feature-dict pair) or a batch of
candidates; the batch verdict is the AND over every candidate -- one divergence
anywhere BLOCKS the whole stack.

DECISION-ONLY: never authorizes a bet, never moves money, never writes anything,
never flips a flag. Returns a verdict dict; the caller (run_governance) decides.
No edge / $ field anywhere.

INVARIANTS: build only under governance/; <=300 LOC; ASCII; no I/O; stdlib + the
improve.parity_check reuse.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence, Tuple

from improve.parity_check import parity_ok

PARITY_GATE_VERSION = "governance.parity_check.v1"


def check_candidate(
    train_features: Mapping[str, float],
    infer_features: Mapping[str, float],
    *,
    name: str = "candidate",
    tol: float = 1e-9,
) -> Dict[str, Any]:
    """Gate one candidate's train-vs-inference feature dicts. BLOCKS on divergence.

    Parameters
    ----------
    train_features, infer_features:
        Feature dicts captured at train time and inference time for the SAME
        observation, keyed identically.
    name:
        Label for this candidate (surfaced in the verdict for diagnosis).
    tol:
        Absolute tolerance passed through to ``parity_ok`` (default 1e-9).

    Returns
    -------
    dict with keys:
        ``ok``          -- True only if parity holds (no mismatch, no zero-read).
        ``name``        -- echoed candidate label.
        ``blocked``     -- not ok.
        ``mismatches``  -- every diverging key (from parity_ok).
        ``zero_reads``  -- the subset that are silent-zero wiring bugs.
        ``version``     -- PARITY_GATE_VERSION.

    Never raises: ``parity_ok`` is itself never-raising and returns ok=False with a
    descriptive entry on any internal error, so the gate cannot go falsely green.
    """
    report = parity_ok(dict(train_features), dict(infer_features), tol=tol)
    ok = bool(report.get("ok"))
    return {
        "ok": ok,
        "name": name,
        "blocked": not ok,
        "mismatches": report.get("mismatches", []),
        "zero_reads": report.get("zero_reads", []),
        "version": PARITY_GATE_VERSION,
    }


CandidatePair = Tuple[Mapping[str, float], Mapping[str, float]]


def check_candidates(
    candidates: Sequence[CandidatePair] | Mapping[str, CandidatePair],
    *,
    tol: float = 1e-9,
) -> Dict[str, Any]:
    """Gate a batch of candidates. The verdict is the AND over all of them.

    *candidates* may be a sequence of ``(train_features, infer_features)`` pairs
    (auto-named "candidate[i]") or a mapping ``name -> (train, infer)``. ANY
    divergence or zero-read anywhere BLOCKS the whole batch (fail-closed).

    Returns
    -------
    dict with keys:
        ``ok``            -- True only if EVERY candidate passes.
        ``blocked``       -- not ok.
        ``n_candidates``  -- count audited.
        ``per_candidate`` -- list of per-candidate verdicts (from check_candidate).
        ``failures``      -- the subset of per_candidate verdicts that blocked.
        ``version``       -- PARITY_GATE_VERSION.

    A malformed batch is itself a blocking failure (never false-green).
    """
    per: List[Dict[str, Any]] = []
    try:
        items = _normalize(candidates)
    except Exception as exc:
        return {
            "ok": False,
            "blocked": True,
            "n_candidates": 0,
            "per_candidate": [],
            "failures": [{"ok": False, "name": "<bad batch>",
                          "blocked": True, "mismatches": [],
                          "zero_reads": [], "error": str(exc)[:200],
                          "version": PARITY_GATE_VERSION}],
            "version": PARITY_GATE_VERSION,
        }

    for name, (train, infer) in items:
        per.append(check_candidate(train, infer, name=name, tol=tol))

    failures = [v for v in per if not v["ok"]]
    return {
        "ok": len(failures) == 0,
        "blocked": len(failures) > 0,
        "n_candidates": len(per),
        "per_candidate": per,
        "failures": failures,
        "version": PARITY_GATE_VERSION,
    }


def _normalize(
    candidates: Sequence[CandidatePair] | Mapping[str, CandidatePair],
) -> List[Tuple[str, CandidatePair]]:
    """Coerce supported batch shapes into a list of (name, (train, infer))."""
    if isinstance(candidates, Mapping):
        return [(str(name), _as_pair(pair)) for name, pair in candidates.items()]
    out: List[Tuple[str, CandidatePair]] = []
    for i, pair in enumerate(candidates):
        out.append((f"candidate[{i}]", _as_pair(pair)))
    return out


def _as_pair(pair: Any) -> CandidatePair:
    """Validate that *pair* is a (train_features, infer_features) 2-tuple of dicts."""
    if not isinstance(pair, (tuple, list)) or len(pair) != 2:
        raise TypeError("each candidate must be a (train, infer) pair")
    train, infer = pair
    if not isinstance(train, Mapping) or not isinstance(infer, Mapping):
        raise TypeError("train and infer features must each be a mapping")
    return train, infer


__all__ = [
    "check_candidate",
    "check_candidates",
    "PARITY_GATE_VERSION",
]
