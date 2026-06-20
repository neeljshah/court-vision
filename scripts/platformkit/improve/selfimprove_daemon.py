"""scripts.platformkit.improve.selfimprove_daemon -- always-on, checkpoint-resumable
self-improvement DAEMON. Glue only: it orchestrates the existing 5-gate ratchet and
recalibration; it adds NO new math.

ONE CYCLE (run_cycle, idempotent):
  1. settled_games_fn(name, since=high_water) -> NEW settled games (the cursor is an
     id/date HIGH-WATER key, not a count, + game_id dedup; a restart never reprocesses
     and never SKIPS an unseen game).
  2. recalibrate_fn(name, settled, window) -> a CANDIDATE dict the gate consumes:
     {base_preds, cand_preds, y, kind, fold_results, corpora, stability_*,
      train_features, infer_features, artifact, payload, oos_improves(bool),
      held_out_check(callable)}.
  3. gate_fn(candidate) -> a VERDICT dict {ship, gate_results, reasons}. Defaults to
     the real improve.ratchet_state.evaluate_candidate (the 5 gates, no promotion).
  4. SHIP iff: gate ship==True AND candidate OOS improves AND replicated on >= 2
     corpora. Else if exactly one corpus replicates -> REPLICATION_PENDING (never
     SHIP on one corpus). Else REJECT.
  5. On SHIP: stage a versioned artifact + atomic-swap `current`; then run the
     held-out check and AUTO-ROLLBACK if it regressed. On non-SHIP: append a
     reject_ledger row. Always emit a PROPOSAL row (data/cache/improve/proposals.jsonl).
  6. Advance + persist the checkpoint cursor.

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

# Staging / ledger / proposal I/O + the corpus-replication count live in the sibling
# selfimprove_stage module (keeps this file <=300 LOC). Re-exported here so callers
# and tests that reach for daemon._count_replicated_corpora / _append_jsonl still work.
_append_jsonl = _stage.append_jsonl
_count_replicated_corpora = _stage.count_replicated_corpora
_default_gate_fn = _stage.default_gate_fn

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
            "shipped_version": self.shipped_version,
            "rolled_back_to": self.rolled_back_to, "n_new": self.n_new,
            "n_corpora_replicated": self.n_corpora_replicated,
        }


from scripts.platformkit.improve.cursor_util import (  # noqa: E402
    advance as _advance, game_id as _game_id, key as _key,
)


def _call_source(fn: Callable[..., Sequence[Dict[str, Any]]], name: str,
                 high_water: str, seen_ids: set) -> Sequence[Dict[str, Any]]:
    """Call the settled-games source, passing seen_ids when it accepts it.

    The PRIMARY dedup is seen_ids, so a source that supports it (the real
    settled_finals.settled_since provider) gets the full seen set and can surface an
    out-of-order late final. Older/injected sources that take only `since` still work
    (we fall back), and the daemon re-dedups by seen_ids afterwards regardless.
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
              min_corpora: int = 2) -> CycleResult:
    """Run ONE idempotent self-improvement cycle for `name`. Never raises.

    Every dependency is injectable for offline testing; defaults use the real
    ratchet + artifact store + checkpoint.
    """
    t = time.time() if now is None else float(now)
    gate_fn = gate_fn or _default_gate_fn
    proposals_path = proposals_path or DEFAULT_PROPOSALS
    reject_path = reject_path or DEFAULT_REJECT_LEDGER
    status_path = status_path or DEFAULT_STATUS
    ck = load_checkpoint(ckpt_path)
    cur = ck.cursor(name)
    # PRIMARY fold guard = seen_ids (game_ids already folded), NOT the high-water key:
    # that key encodes SCHEDULED commence time, so a game that finals OUT OF ORDER
    # (earlier commence + later final) has key < high-water and a key filter would
    # WRONGLY SKIP it. We fold iff game_id not in seen_ids; high_water is display/order.
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

    # --- 2. recalibrate -> candidate -----------------------------------------
    try:
        candidate = recalibrate_fn(name, settled, window)
    except Exception as exc:  # noqa: BLE001
        _status("recalibrate_error", error=str(exc)[:200])
        # advance the cursor anyway so a permanently-bad batch is not retried forever
        _advance(cur, new_hw, folded_ids)
        cur["last_decision"] = ERROR
        save_checkpoint(ck, ckpt_path)
        return CycleResult(name, ERROR, ["recalibrate_fn raised: %s" % exc], n_new=n_new)

    if not candidate:  # cold start / inert (flag-off) / not enough data -> NO_CANDIDATE
        # SI-P0-03: a NO_CANDIDATE / INERT cycle must NOT advance the cursor. These games
        # were never actually folded into any candidate, so marking them consumed (seen_ids
        # AND/OR the high-water `since` the feed filters by) would PERMANENTLY skip them once
        # the recalibrator lands + the human PIPELINE_ENABLED sentinel is created -- the very
        # games consumed while inert would never be re-considered. We persist last_decision
        # only and leave BOTH seen_ids and high_water untouched so the batch re-surfaces next
        # cycle. (An ALL-deduped/empty batch is handled by the n_new==0 branch above, which
        # safely advances high_water; here n_new>0 so we must not.)
        cur["last_decision"] = NO_CANDIDATE
        save_checkpoint(ck, ckpt_path)
        _status("no_candidate", n_new=n_new)
        return CycleResult(name, NO_CANDIDATE,
                           ["recalibrate produced no candidate (cold start/inert)"],
                           n_new=n_new)

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

    # --- 4. SHIP decision: 5-gate unanimous AND OOS-improves AND >=2 corpora --
    decision = REJECT
    if gate_ship and oos_improves and n_rep >= min_corpora:
        decision = SHIP
    elif gate_ship and oos_improves and n_rep == 1:
        decision = REPLICATION_PENDING
        reasons.append("replicated on 1 corpus; need >= %d -- not shipped" % min_corpora)
    else:
        if not gate_ship:
            reasons.append("5-gate verdict did not pass unanimously")
        if not oos_improves:
            reasons.append("candidate does not improve OOS")
        if n_rep < min_corpora:
            reasons.append("replicated on %d/%d corpora" % (n_rep, min_corpora))

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

    return CycleResult(name, decision, reasons, shipped_version, rolled_to,
                       n_new, n_rep)


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

    Runs run_cycle for each name per tick. `max_cycles` (per name) bounds offline
    tests; `should_stop()` brakes cleanly. A per-name run_cycle never raises, so one
    dead source can never stop the loop. Returns the CycleResults gathered.
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
