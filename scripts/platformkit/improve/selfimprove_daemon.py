"""scripts.platformkit.improve.selfimprove_daemon -- always-on, checkpoint-resumable
self-improvement DAEMON. Glue only: it orchestrates the existing 5-gate ratchet and
recalibration; it adds NO new math.

ONE CYCLE (run_cycle, idempotent):
  1. settled_games_fn(name, since=high_water) -> NEW settled games (cursor = id/date
     HIGH-WATER key + game_id dedup; a restart never reprocesses or SKIPS an unseen game).
  2. recalibrate_fn(name, settled, window[, report]) -> a CANDIDATE dict the gate consumes,
     or None. The optional out-of-band `report` {reason, transient} tells an EVALUATED
     decline apart from a pre-evaluation TRANSIENT bail (see step 6).
  3. gate_fn(candidate) -> a VERDICT dict {ship, gate_results, reasons}. Defaults to
     the real improve.ratchet_state.evaluate_candidate (the 5 gates, no promotion).
  4. SHIP iff: gate ship==True AND OOS improves AND replicated on >= min_corpora corpora
     (fixed 2, or an explicit override, or the FWER-aware floor from
     selfimprove_stage.effective_min_corpora -- never below 2). One corpus ->
     REPLICATION_PENDING (never SHIP on one corpus). Else REJECT.
  5. On SHIP: stage a versioned artifact + atomic-swap `current`; held-out AUTO-ROLLBACK if
     it regressed. On non-SHIP: append a reject_ledger row. Always emit a PROPOSAL row.
  6. Advance + persist the cursor -- but ONLY on a real fold: a SHIP/REJECT, or an armed
     GENUINE no-candidate (evaluated then declined). An INERT (flag-off) or TRANSIENT
     (FeedDegradedError / exception -> bailed before evaluation) cycle PRESERVES the cursor
     so the games retry, never silently skipped.

INVARIANTS: never edits MEMORY.md, never writes data/registry/, never flips a flag.
Per-source error isolation -- a dead source or a raising gate logs ONE status entry
and the loop continues (never crashes). Calibration, not edge. ASCII; <=300 LOC.
"""
from __future__ import annotations

import pathlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from scripts.platformkit.improve import artifact_store as store
from scripts.platformkit.improve import selfimprove_stage as _stage
from scripts.platformkit.improve.checkpoint import (
    load_checkpoint, save_checkpoint,
)
from scripts.platformkit.improve.cursor_util import (
    advance as _advance, game_id as _game_id, key as _key,
)

# Staging / ledger / I/O / corpus-count / recal-call live in the sibling selfimprove_stage
# module (keeps this file <=300 LOC). Re-exported so callers/tests still reach them here.
_append_jsonl = _stage.append_jsonl
_count_replicated_corpora = _stage.count_replicated_corpora
_default_gate_fn = _stage.default_gate_fn
_call_recal = _stage.call_recal

_REPO = pathlib.Path(__file__).resolve().parents[3]
_IMPROVE_DIR = _REPO / "data" / "cache" / "improve"
DEFAULT_PROPOSALS = _IMPROVE_DIR / "proposals.jsonl"
DEFAULT_REJECT_LEDGER = _IMPROVE_DIR / "reject_ledger.jsonl"
DEFAULT_STATUS = _IMPROVE_DIR / "status.jsonl"

SHIP = "SHIP"
REJECT = "REJECT"
REPLICATION_PENDING = "REPLICATION_PENDING"
NO_CANDIDATE = "NO_CANDIDATE"
ERROR = "ERROR"


@dataclass
class CycleResult:
    name: str
    decision: str
    reasons: List[str] = field(default_factory=list)
    shipped_version: Optional[int] = None
    rolled_back_to: Optional[int] = None
    n_new: int = 0
    n_corpora_replicated: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name, "decision": self.decision, "reasons": self.reasons,
            "shipped_version": self.shipped_version, "n_new": self.n_new,
            "rolled_back_to": self.rolled_back_to,
            "n_corpora_replicated": self.n_corpora_replicated}


def _pipeline_armed() -> bool:
    """True iff the human-only PIPELINE_ENABLED sentinel is present (FIX B cursor gate).

    Decides whether an armed GENUINE-decline NO_CANDIDATE may advance the cursor or PRESERVE
    it (inert -> re-surface once armed). Fail-SAFE: any error -> False (preserve). Never raises.
    """
    try:
        from scripts.platformkit.improve.pipeline_flag import pipeline_enabled
        return bool(pipeline_enabled())
    except Exception:  # noqa: BLE001 -- flag helper missing -> treat as inert (preserve)
        return False


def _call_source(fn: Callable[..., Sequence[Dict[str, Any]]], name: str,
                 high_water: str, seen_ids: set) -> Sequence[Dict[str, Any]]:
    """Call the settled-games source, passing seen_ids when it accepts it.

    PRIMARY dedup is seen_ids: a source that supports it gets the full seen set and can
    surface an out-of-order late final; older/injected `since`-only sources still work (we
    fall back), and the daemon re-dedups by seen_ids afterwards regardless.
    """
    import inspect
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        params = {}
    if "seen_ids" in params or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return fn(name, since=high_water, seen_ids=sorted(seen_ids))
    return fn(name, since=high_water)


def run_cycle(*, name: str, settled_games_fn: Callable[..., Sequence[Dict[str, Any]]],
              recalibrate_fn: Callable[..., Optional[Dict[str, Any]]],
              gate_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
              store_root: Optional[str] = None,
              ckpt_path: Optional[str] = None,
              proposals_path: Optional[pathlib.Path] = None,
              reject_path: Optional[pathlib.Path] = None,
              status_path: Optional[pathlib.Path] = None,
              now: Optional[float] = None,
              min_corpora: Optional[int] = None) -> CycleResult:
    """Run ONE idempotent self-improvement cycle for `name`. Never raises.

    Every dependency is injectable for offline testing; defaults use the real ratchet/store.
    `min_corpora`: explicit override, else the FWER-aware floor (stage.effective_min_corpora;
    never stricter than 2 with only 1-2 corpora available -- identical to today).
    """
    t = time.time() if now is None else float(now)
    gate_fn = gate_fn or _default_gate_fn
    proposals_path = proposals_path or DEFAULT_PROPOSALS
    reject_path = reject_path or DEFAULT_REJECT_LEDGER
    status_path = status_path or DEFAULT_STATUS
    ck = load_checkpoint(ckpt_path)
    cur = ck.cursor(name)
    # PRIMARY fold guard = seen_ids (game_ids folded), NOT the high-water key (which encodes
    # SCHEDULED commence -> an out-of-order late final would be WRONGLY SKIPPED). high_water
    # is display/order only.
    high_water = str(cur.get("high_water", "") or "")
    seen_ids = set(cur.get("seen_ids", []) or [])

    def _status(kind: str, **kw: Any) -> None:  # escalation, never silent fail
        _append_jsonl(status_path, {"ts": t, "name": name, "status": kind, **kw})

    # --- 1. ingest newly-settled (per-source isolation, dedup by game_id) -----
    try:
        raw = list(_call_source(settled_games_fn, name, high_water, seen_ids))
    except Exception as exc:  # noqa: BLE001 -- dead source: isolate + continue
        _status("source_error", error=str(exc)[:200])
        return CycleResult(name, ERROR, ["settled_games_fn raised: %s" % exc])

    settled = [g for g in raw if _game_id(g) not in seen_ids]
    batch_keys = [_key(g) for g in raw]
    new_hw = max([high_water] + batch_keys) if batch_keys else high_water
    n_new = len(settled)
    if n_new == 0:
        cur["high_water"] = new_hw  # advance past an all-deduped/empty batch
        _status("no_new_games")
        save_checkpoint(ck, ckpt_path)
        return CycleResult(name, NO_CANDIDATE, ["no newly-settled games"], n_new=0)

    window = n_new  # window descriptor for recalibrate_fn (count of NEW games)
    folded_ids = [_game_id(g) for g in settled]

    recal_report: Dict[str, Any] = {}  # 2. recalibrate; report = {reason, transient} channel
    try:
        candidate = _call_recal(recalibrate_fn, name, settled, window, recal_report)
    except Exception as exc:  # noqa: BLE001 -- recalibrate_fn raised: TRANSIENT (wave-2 fix)
        _status("recalibrate_error", error=str(exc)[:200])
        # Bailed BEFORE evaluation -> PRESERVE cursor, retry (was: advance -> silent skip).
        cur["last_decision"] = ERROR
        save_checkpoint(ck, ckpt_path)
        _status("recalibrate_transient", n_new=n_new, reason="recalibrate_fn raised")
        return CycleResult(name, ERROR, ["recalibrate_fn raised: %s" % exc], n_new=n_new)

    if not candidate:  # cold start / inert (flag-off) / degraded feed -> NO_CANDIDATE
        # SI-P0-03 + FIX B + wave-2 transient fix (see step 6 of the module docstring):
        # advance ONLY on an armed GENUINE evaluated decline; INERT and ARMED+TRANSIENT preserve.
        armed = _pipeline_armed()
        # ONLY a report POSITIVELY flagging transient=True blocks an armed advance (the REAL
        # recalibrators always set it); a report-less None keeps the prior FIX-B advance.
        transient = bool(recal_report.get("transient")) if recal_report else False
        genuine_decline = not transient
        rcode = str(recal_report.get("reason", "unknown"))
        if armed and genuine_decline:
            _advance(cur, new_hw, folded_ids)
            reason = "no candidate built (processed, declined: %s)" % rcode
        elif armed:  # transient OR unknown -> preserve + retry next cycle
            reason = "no candidate built (TRANSIENT: %s -- cursor preserved, retry)" % rcode
        else:
            reason = "no candidate built (inert: PIPELINE_ENABLED sentinel absent)"
        cur["last_decision"] = NO_CANDIDATE
        save_checkpoint(ck, ckpt_path)
        _status("no_candidate", n_new=n_new, armed=bool(armed),
                transient=bool(armed and not genuine_decline), reason=rcode)
        return CycleResult(name, NO_CANDIDATE, [reason], n_new=n_new)

    # --- 3. 5-gate verdict (isolated) ----------------------------------------
    try:
        verdict = gate_fn(candidate)
    except Exception as exc:  # noqa: BLE001 -- a raising gate must not crash the loop
        _status("gate_error", error=str(exc)[:200])
        _append_jsonl(reject_path, {"ts": t, "name": name, "decision": REJECT,
                                    "reasons": ["gate_fn raised: %s" % exc]})
        _advance(cur, new_hw, folded_ids)
        cur["last_decision"] = REJECT
        save_checkpoint(ck, ckpt_path)
        return CycleResult(name, REJECT, ["gate_fn raised: %s" % exc], n_new=n_new)

    gate_ship = bool(verdict.get("ship"))
    reasons = list(verdict.get("reasons", []))
    oos_improves = bool(candidate.get("oos_improves", False))
    n_rep = _count_replicated_corpora(candidate)
    eff_min_corpora = int(min_corpora) if min_corpora is not None \
        else _stage.effective_min_corpora(name, n_rep)
    # --- 4. SHIP decision: 5-gate unanimous AND OOS-improves AND >=min_corpora ---
    decision = REJECT
    if gate_ship and oos_improves and n_rep >= eff_min_corpora:
        decision = SHIP
    elif gate_ship and oos_improves and n_rep == 1:
        decision = REPLICATION_PENDING
        reasons.append("replicated on 1 corpus; need >= %d -- not shipped" % eff_min_corpora)
    else:
        if not gate_ship:
            reasons.append("5-gate verdict did not pass unanimously")
        if not oos_improves:
            reasons.append("candidate does not improve OOS")
        if n_rep < eff_min_corpora:
            reasons.append("replicated on %d/%d corpora" % (n_rep, eff_min_corpora))

    shipped_version: Optional[int] = None
    rolled_to: Optional[int] = None
    if decision == SHIP:
        # --- 5. stage + atomic-swap + auto-rollback (sibling selfimprove_stage) --
        shipped_version, rolled_to, sd, reason = _stage.stage_ship(
            name, candidate, store, store_root)
        if sd == "REJECT":  # held-out regression -> rolled back
            decision = REJECT
            if reason:
                reasons.append(reason)
    if decision != SHIP:
        _stage.emit_reject(reject_path, ts=t, name=name, decision=decision,
                           reasons=reasons, n_rep=n_rep)

    # --- 6. proposal (NEVER MEMORY.md / data/registry) + checkpoint advance ---
    _stage.emit_proposal(proposals_path, ts=t, name=name, decision=decision,
                         reasons=reasons, shipped_version=shipped_version,
                         rolled_to=rolled_to, n_new=n_new, n_rep=n_rep)
    _advance(cur, new_hw, folded_ids)
    cur["last_decision"] = decision
    cur["last_version"] = shipped_version if shipped_version is not None else cur.get("last_version")
    save_checkpoint(ck, ckpt_path)
    _status("cycle_done", decision=decision, n_new=n_new, n_corpora=n_rep)
    return CycleResult(name, decision, reasons, shipped_version, rolled_to, n_new, n_rep)


def run_forever(*, names: Sequence[str],
                settled_games_fn: Callable[..., Sequence[Dict[str, Any]]],
                recalibrate_fn: Callable[..., Optional[Dict[str, Any]]],
                gate_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
                clock: Optional[Callable[[], float]] = None,
                sleep: Optional[Callable[[float], None]] = None,
                interval_sec: float = 60.0,
                max_cycles: Optional[int] = None,
                should_stop: Optional[Callable[[], bool]] = None,
                store_root: Optional[str] = None,
                ckpt_path: Optional[str] = None,
                **cycle_kwargs: Any) -> List[CycleResult]:
    """Always-on loop. RESUMES from the checkpoint; interruptible; lossless.

    Runs run_cycle per name/tick. `max_cycles` bounds offline tests; `should_stop()` brakes
    cleanly; a per-name run_cycle never raises. Returns the CycleResults gathered.
    """
    clock = clock or time.time
    sleep = sleep or time.sleep
    results: List[CycleResult] = []
    tick = 0
    while True:
        if should_stop is not None and should_stop():
            break
        if max_cycles is not None and tick >= max_cycles:
            break
        for name in names:
            try:
                res = run_cycle(
                    name=name, settled_games_fn=settled_games_fn,
                    recalibrate_fn=recalibrate_fn, gate_fn=gate_fn,
                    store_root=store_root, ckpt_path=ckpt_path,
                    now=clock(), **cycle_kwargs)
            except Exception as exc:  # noqa: BLE001 -- defense in depth
                res = CycleResult(name, ERROR, ["run_cycle raised: %s" % exc])
            results.append(res)
        tick += 1
        if max_cycles is not None and tick >= max_cycles:
            break
        if should_stop is not None and should_stop():
            break
        sleep(interval_sec)
    return results


__all__ = [
    "CycleResult", "run_cycle", "run_forever",
    "SHIP", "REJECT", "REPLICATION_PENDING", "NO_CANDIDATE", "ERROR",
    "DEFAULT_PROPOSALS", "DEFAULT_REJECT_LEDGER", "DEFAULT_STATUS",
]
