"""improve.ratchet_state -- the self-improvement FSM (Milestone-8 ratchet).

This module composes ALL the Milestone-8 gates into ONE ship decision and the
small state machine that drives a self-improvement cycle idempotently across
restarts. It is the single place where "may this recalibration go live?" is
answered, and it answers it the honest way:

    SHIP requires EVERY gate to pass, unanimously, out-of-sample:
        proper_score.ship  (Brier AND log-loss, or CRPS AND pinball -- no
                             one-sided win) AND
        seed_stability.stable  (multi-seed bootstrap p10 >= 0) AND
        multifold.replicated   (k-fold AND >= 2 independent corpora) AND
        parity.ok              (train==inference feature parity, no zero-reads) AND
        integrity_ok           (pkl feature-width parity vs meta)

    A partial pass is a REJECT. An honest REJECT is a SUCCESS; we NEVER ship to
    make a number move and there is NO dollar edge anywhere.

FSM:  IDLE -> CANDIDATE -> EVALUATING -> (SHIP | REJECT) -> IDLE
A JSON checkpoint persists the current state + the last candidate fingerprint so
a crashed/restarted loop resumes idempotently: a candidate already SHIPPED (its
version already promoted) or already REJECTED is not re-run, so we never double
-promote or double-log a ledger row. A repeatedly-rejecting candidate is held
under a backoff so the loop does not retry it every tick.

REUSE: every statistic comes from the existing gates (proper_score_gate,
seed_stability, multifold_guard, parity_check, calib_artifact, registry). This
module adds NO new math -- only the unanimous-AND decision, the FSM, and the
atomic checkpoint. stdlib + numpy-free; <=300 LOC; ASCII only.
"""
from __future__ import annotations

import json
import os
import pathlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

try:  # package import (normal)
    from improve.proper_score_gate import score_gate
    from improve.seed_stability import stable
    from improve.multifold_guard import replicated
    from improve.parity_check import parity_ok
    from improve.calib_artifact import CalibArtifact, integrity_ok
    from improve import registry
except ImportError:  # direct-script / per-file-test fallback
    from proper_score_gate import score_gate  # type: ignore
    from seed_stability import stable  # type: ignore
    from multifold_guard import replicated  # type: ignore
    from parity_check import parity_ok  # type: ignore
    from calib_artifact import CalibArtifact, integrity_ok  # type: ignore
    import registry  # type: ignore

# FSM states.
IDLE = "IDLE"
CANDIDATE = "CANDIDATE"
EVALUATING = "EVALUATING"
SHIP = "SHIP"
REJECT = "REJECT"

_REPO = pathlib.Path(__file__).resolve().parents[1]
_DEFAULT_CKPT = _REPO / "data" / "frontend" / "calib" / "_ratchet_state.json"

# A repeatedly-rejecting candidate is held for this many seconds before retry,
# so the loop does not burn a full gate evaluation on it every tick.
_DEFAULT_BACKOFF_SEC = 3600.0


@dataclass
class RatchetState:
    """Persisted FSM state. `state` is one of the module constants above.

    last_fingerprint : identity of the most recently evaluated candidate; lets a
                       restart recognise an already-decided candidate.
    last_decision    : "SHIP" / "REJECT" for that fingerprint (None if pending).
    shipped_version  : the registry version promoted on the last SHIP (idempotency).
    reject_until     : epoch seconds before which a re-presented rejected
                       fingerprint is skipped (backoff).
    """
    state: str = IDLE
    last_fingerprint: Optional[str] = None
    last_decision: Optional[str] = None
    shipped_version: Optional[int] = None
    reject_until: float = 0.0
    history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "last_fingerprint": self.last_fingerprint,
            "last_decision": self.last_decision,
            "shipped_version": self.shipped_version,
            "reject_until": self.reject_until,
            "history": self.history[-50:],  # bounded
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RatchetState":
        return cls(
            state=str(d.get("state", IDLE)),
            last_fingerprint=d.get("last_fingerprint"),
            last_decision=d.get("last_decision"),
            shipped_version=d.get("shipped_version"),
            reject_until=float(d.get("reject_until", 0.0) or 0.0),
            history=list(d.get("history") or []),
        )


def _atomic_write_json(path: pathlib.Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp.%d" % os.getpid())
    with open(tmp, "w", encoding="ascii") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)  # atomic on POSIX + Windows


def load_state(ckpt: Optional[str] = None) -> RatchetState:
    """Load the persisted FSM state; a missing/torn/garbage file -> fresh IDLE."""
    path = pathlib.Path(ckpt) if ckpt else _DEFAULT_CKPT
    if not path.exists():
        return RatchetState()
    try:
        return RatchetState.from_dict(json.loads(path.read_text(encoding="ascii")))
    except (OSError, ValueError, TypeError, KeyError):
        return RatchetState()


def save_state(st: RatchetState, ckpt: Optional[str] = None) -> pathlib.Path:
    """Persist the FSM state atomically (temp+fsync+os.replace -- never torn)."""
    path = pathlib.Path(ckpt) if ckpt else _DEFAULT_CKPT
    _atomic_write_json(path, json.dumps(st.to_dict(), sort_keys=True, indent=2))
    return path


def _all_pass(gate_results: Dict[str, Any]) -> bool:
    """Unanimous-AND: every gate must pass for a SHIP. A partial pass is REJECT."""
    ps = gate_results.get("proper_score") or {}
    ss = gate_results.get("seed_stability")
    mf = gate_results.get("multifold") or {}
    pc = gate_results.get("parity") or {}
    integ = gate_results.get("integrity")
    return bool(
        ps.get("ship") is True
        and getattr(ss, "stable", False) is True
        and mf.get("replicated") is True
        and pc.get("ok") is True
        and integ is True
    )


def _reasons(gate_results: Dict[str, Any]) -> List[str]:
    """Collect the dissenting reason(s) from every gate that did not pass."""
    out: List[str] = []
    ps = gate_results.get("proper_score") or {}
    if ps.get("ship") is not True:
        out += ["proper_score: " + r for r in (ps.get("reasons") or ["regressed"])]
    ss = gate_results.get("seed_stability")
    if getattr(ss, "stable", False) is not True:
        p10 = getattr(ss, "p10", None)
        out.append("seed_stability: p10=%s < 0 (unstable across seeds)" % (p10,))
    mf = gate_results.get("multifold") or {}
    if mf.get("replicated") is not True:
        out += ["multifold: " + r for r in (mf.get("reasons") or ["not replicated"])]
    pc = gate_results.get("parity") or {}
    if pc.get("ok") is not True:
        zr = pc.get("zero_reads") or []
        out.append("parity: %d mismatch(es), %d zero-read(s)"
                   % (len(pc.get("mismatches") or []), len(zr)))
    if gate_results.get("integrity") is not True:
        out.append("integrity: artifact failed feature-width parity vs meta")
    return out


def evaluate_candidate(
    base_preds: Any,
    cand_preds: Any,
    y: Any,
    *,
    kind: str = "prob",
    corpora: Sequence[Dict[str, Any]],
    fold_results: Sequence[Dict[str, Any]],
    stability_metric_fn: Callable[[Sequence, Sequence], float],
    stability_data: Sequence,
    train_features: Dict[str, float],
    infer_features: Dict[str, float],
    artifact: CalibArtifact,
    artifact_meta: Optional[Dict[str, Any]] = None,
    min_folds: int = 1,
    min_corpora: int = 2,
    seeds: Optional[Sequence[int]] = None,
    n_boot: int = 200,
    registry_root: Optional[str] = None,
    promote_on_ship: bool = True,
) -> Dict[str, Any]:
    """Run EVERY gate and return the unanimous ship decision (never raises).

    On SHIP, the artifact is saved + promoted to CURRENT atomically via the
    registry (only when promote_on_ship). On REJECT, the honest dissenting
    reasons are returned. A partial pass is ALWAYS a REJECT.

    Returns {ship, gate_results, reasons, shipped_version}.
    """
    gate_results: Dict[str, Any] = {}
    try:
        gate_results["proper_score"] = score_gate(base_preds, cand_preds, y, kind=kind)
    except Exception as exc:  # noqa: BLE001 -- gates are pure but stay defensive
        gate_results["proper_score"] = {"ship": False, "reasons": [str(exc)]}
    try:
        gate_results["seed_stability"] = stable(
            stability_metric_fn, stability_data, seeds=seeds, n_boot=n_boot)
    except Exception as exc:  # noqa: BLE001
        gate_results["seed_stability"] = None
        gate_results.setdefault("_errors", []).append("seed_stability: %s" % exc)
    try:
        gate_results["multifold"] = replicated(
            fold_results, min_folds=min_folds, min_corpora=min_corpora,
            corpus_results=corpora)
    except Exception as exc:  # noqa: BLE001
        gate_results["multifold"] = {"replicated": False, "reasons": [str(exc)]}
    try:
        gate_results["parity"] = parity_ok(train_features, infer_features)
    except Exception as exc:  # noqa: BLE001
        gate_results["parity"] = {"ok": False, "mismatches": [str(exc)], "zero_reads": []}
    try:
        gate_results["integrity"] = bool(integrity_ok(artifact, artifact_meta))
    except Exception as exc:  # noqa: BLE001
        gate_results["integrity"] = False
        gate_results.setdefault("_errors", []).append("integrity: %s" % exc)

    ship = _all_pass(gate_results)
    shipped_version: Optional[int] = None
    if ship and promote_on_ship:
        try:
            path = registry.save_version(artifact, root=registry_root)
            ver = int(pathlib.Path(path).stem[1:])  # v<N>.json -> N
            if registry.promote(artifact.kind, ver, root=registry_root):
                shipped_version = ver
            else:
                ship = False  # promotion blocked (integrity) -> honest REJECT
                gate_results.setdefault("_errors", []).append(
                    "registry.promote blocked (feature-width parity)")
        except Exception as exc:  # noqa: BLE001
            ship = False
            gate_results.setdefault("_errors", []).append("registry: %s" % exc)

    return {
        "ship": bool(ship),
        "gate_results": gate_results,
        "reasons": ([ "candidate passed every gate" ] if ship else _reasons(gate_results)),
        "shipped_version": shipped_version,
    }


def run_cycle(
    fingerprint: str,
    eval_kwargs: Dict[str, Any],
    *,
    ckpt: Optional[str] = None,
    backoff_sec: float = _DEFAULT_BACKOFF_SEC,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Drive the FSM for ONE candidate, idempotently across restarts.

    `fingerprint` uniquely identifies the candidate (e.g. a content hash). If the
    persisted state already DECIDED this fingerprint, we DO NOT re-evaluate
    (no double-promote, no double-ledger). A rejected fingerprint inside its
    backoff window is skipped. Otherwise we run evaluate_candidate(**eval_kwargs),
    persist the verdict, and return it.

    Returns {status, ship, decision, shipped_version, reasons, state}.
    status: "decided" | "skipped_already_decided" | "skipped_backoff".
    """
    t = time.time() if now is None else float(now)
    st = load_state(ckpt)

    # Idempotency: same candidate already decided -> do not re-run.
    if st.last_fingerprint == fingerprint and st.last_decision in (SHIP, REJECT):
        if st.last_decision == REJECT and t < st.reject_until:
            status = "skipped_backoff"
        else:
            status = "skipped_already_decided"
        return {
            "status": status, "ship": st.last_decision == SHIP,
            "decision": st.last_decision, "shipped_version": st.shipped_version,
            "reasons": ["fingerprint already decided: %s" % st.last_decision],
            "state": st.state,
        }

    # New candidate: advance through CANDIDATE -> EVALUATING and persist so a
    # crash mid-evaluation is observable on resume (idempotent re-run is safe
    # because evaluate is pure until the atomic promote).
    st.state = EVALUATING
    st.last_fingerprint = fingerprint
    st.last_decision = None
    save_state(st, ckpt)

    res = evaluate_candidate(**eval_kwargs)

    decision = SHIP if res["ship"] else REJECT
    st.state = decision
    st.last_decision = decision
    st.shipped_version = res.get("shipped_version")
    st.reject_until = (t + backoff_sec) if decision == REJECT else 0.0
    st.history.append({
        "fingerprint": fingerprint, "decision": decision,
        "shipped_version": st.shipped_version, "ts": t,
        "reasons": res["reasons"][:5],
    })
    st.state = IDLE  # cycle complete; ready for the next candidate
    save_state(st, ckpt)

    return {
        "status": "decided", "ship": res["ship"], "decision": decision,
        "shipped_version": res.get("shipped_version"),
        "reasons": res["reasons"], "state": st.state,
    }


__all__ = [
    "IDLE", "CANDIDATE", "EVALUATING", "SHIP", "REJECT",
    "RatchetState", "load_state", "save_state",
    "evaluate_candidate", "run_cycle",
]
