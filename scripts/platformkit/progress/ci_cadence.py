"""scripts.platformkit.progress.ci_cadence -- THE CONDUCTOR (W4 measurement-only).

Runs ONE tick of the CONTINUOUS-IMPROVEMENT cadence by ORCHESTRATING the existing
substrate (improvement_finder, ci_state, schedule_policy, work_queue, selfimprove
5-gate ratchet, ci_regate, ci_survivor_recheck, progress_ledger). It conducts; it
does NOT reinvent any instrument.

THE STEPS (each in its OWN try/except DEGRADE-ISOLATED block; one failed step
degrades honestly and the cadence CONTINUES, status reflects DEGRADED, it NEVER
crashes or green-fakes):
  A snapshot durable state (ci_state.build_durable_state)
  B refresh backlog        (improvement_finder.discover + write_backlog)
  C choose next kind       (schedule_policy.SchedulePolicy.decide)
  D enqueue                (work_queue.enqueue -- ALLOWED_KINDS allowlist enforced)
  E auto-gate dequeued     (selfimprove_daemon.run_cycle -- INERT: sentinel-absent ->
                            recalibrate_fn=None -> NO_CANDIDATE; verdict recorded)
  F re-gate grown data + re-check survivors at wider K (ci_regate, ci_survivor_recheck)
  G append ONE progress_ledger row (progress_ledger.append_snapshot)
  H record the ship-path posture (the SHIP path is step E's auto-gate, which stays
    INERT/PROPOSAL-ONLY while the sentinel is absent; H spawns nothing)

NON-NEGOTIABLE RAILS: NEVER ships a model change, NEVER flips a flag, NEVER creates
data/cache/improve/PIPELINE_ENABLED, NEVER writes data/registry/, NEVER edits
MEMORY.md, NEVER arms autostart / real money / push. Every enqueue kind MUST be in
ALLOWED_KINDS. The ship path is selfimprove_runner which is INERT while the sentinel
is absent (-> NO_CANDIDATE, proposal-only). Exactly ONE progress_ledger row per run.
NO $ field anywhere; units/probability only; vs_close UNPROVEN; real-money DENY.
stdlib + repo-internal; ASCII; <=300 LOC.
"""
from __future__ import annotations

import datetime as _dt
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.autonomy.work_queue import ALLOWED_KINDS as _QUEUE_ALLOWED

logger = logging.getLogger("ci_cadence")

# The measurement-kind allowlist the cadence may EVER enqueue. Pinned to the queue's
# own constant so the two can never drift (a test asserts equality). A kind not in
# here is REFUSED before it can reach the queue (defense in depth + DisallowedKind).
ALLOWED_KINDS = frozenset(_QUEUE_ALLOWED)

HEARTBEAT_COMPONENT = "m8_ci_cadence"


class DisallowedKind(ValueError):
    """Raised internally if a step tries to enqueue a non-measurement kind."""


@dataclass
class StepStatus:
    name: str
    ok: bool = True
    detail: str = ""


@dataclass
class CadenceResult:
    """Structured result of one cadence tick (for tests + the progress router)."""
    overall: str = "ok"               # ok | degraded
    degraded: List[str] = field(default_factory=list)
    steps: List[StepStatus] = field(default_factory=list)
    enqueued_kind: Optional[str] = None
    decision_status: Optional[str] = None
    cycle_verdict: Optional[str] = None
    regate_status: Optional[str] = None
    n_survivor_demotions: int = 0
    progress_row: Optional[Dict[str, Any]] = None
    ship_proposal_only: bool = True
    engine_enabled: bool = False
    note: str = ("MEASUREMENT-ONLY: coverage/verdicts climb, MODEL STATIC; ship is "
                 "PROPOSAL-ONLY + INERT while the sentinel is absent; no $ / flag / "
                 "registry / MEMORY write; vs_close UNPROVEN; real-money DENY")

    def _step(self, name: str, ok: bool, detail: str = "") -> None:
        self.steps.append(StepStatus(name, ok, detail))
        if not ok:
            self.degraded.append(name)
            self.overall = "degraded"


def _beat(now: Optional[float]) -> None:
    """Liveness heartbeat for the supervised cadence. Never raises."""
    try:
        from ops.liveness import heartbeat  # noqa: PLC0415
        heartbeat(HEARTBEAT_COMPONENT, _now=now)
    except Exception as exc:  # noqa: BLE001 -- liveness must never sink the tick
        logger.debug("ci_cadence heartbeat skipped: %s", exc)


def _enforce_allowed(kind: str) -> None:
    if kind not in ALLOWED_KINDS:
        raise DisallowedKind(
            "kind %r not in measurement-only ALLOWED_KINDS %s"
            % (kind, sorted(ALLOWED_KINDS)))


@dataclass
class Deps:
    """Injected collaborators (real defaults; faked in tests)."""
    build_durable_state: Optional[Callable[..., Dict[str, Any]]] = None
    finder_discover: Optional[Callable[[], Any]] = None
    finder_write: Optional[Callable[[Any], None]] = None
    policy: Any = None
    queue: Any = None
    run_cycle: Optional[Callable[..., Any]] = None
    regate_select: Optional[Callable[..., Any]] = None
    survivor_select: Optional[Callable[..., Any]] = None
    survivor_recheck: Optional[Callable[..., Any]] = None
    append_snapshot: Optional[Callable[..., Dict[str, Any]]] = None
    build_snapshot: Optional[Callable[..., Dict[str, Any]]] = None
    pipeline_enabled: Optional[Callable[[], bool]] = None


def _default_deps() -> Deps:
    """Bind the REAL substrate lazily (kept out of import path for offline tests)."""
    from scripts.platformkit.progress import ci_state, ci_regate, ci_survivor_recheck
    from scripts.platformkit.meta import improvement_finder as _finder
    from scripts.platformkit.autonomy.schedule_policy import SchedulePolicy
    from scripts.platformkit.autonomy.work_queue import WorkQueue
    from scripts.platformkit.improve.selfimprove_daemon import run_cycle as _rc
    from scripts.platformkit.improve.pipeline_flag import pipeline_enabled as _pe
    from scripts.platformkit.progress import progress_ledger as _pl
    return Deps(
        build_durable_state=ci_state.build_durable_state,
        finder_discover=_finder.discover,
        finder_write=_finder.write_backlog,
        policy=SchedulePolicy(),
        queue=WorkQueue(),
        run_cycle=_rc,
        regate_select=ci_regate.select_regate_targets,
        survivor_select=ci_survivor_recheck.select_survivor_targets,
        survivor_recheck=ci_survivor_recheck.recheck_survivor,
        append_snapshot=_pl.append_snapshot,
        build_snapshot=_pl.build_snapshot,
        pipeline_enabled=_pe,
    )


def run_once(now: Optional[float] = None, *, deps: Optional[Deps] = None) -> CadenceResult:
    """Run ONE measurement-only cadence tick (steps A-H). NEVER raises out.

    Each step is degrade-isolated: a raising step is recorded ok=False and the
    cadence continues; the overall status becomes 'degraded' but a progress row is
    STILL appended (step G always runs). The ship path (H) is INERT/proposal-only.
    """
    d = deps or _default_deps()
    t = float(now) if now is not None else _dt.datetime.utcnow().timestamp()
    res = CadenceResult()
    _beat(t)

    # Honesty anchor: the sentinel is read but NEVER created here.
    try:
        res.engine_enabled = bool(d.pipeline_enabled()) if d.pipeline_enabled else False
    except Exception:  # noqa: BLE001
        res.engine_enabled = False

    # --- B refresh backlog (READ-ONLY discover+write) --------------------------------
    try:
        if d.finder_discover and d.finder_write:
            d.finder_write(d.finder_discover())
        res._step("B_backlog", True, "refreshed")
    except Exception as exc:  # noqa: BLE001
        res._step("B_backlog", False, "finder raised: %s" % type(exc).__name__)

    # --- A snapshot durable state ----------------------------------------------------
    durable: Dict[str, Any] = {}
    try:
        durable = d.build_durable_state(t) if d.build_durable_state else {}
        res._step("A_durable_state", True, "%d sports" % len(durable))
    except Exception as exc:  # noqa: BLE001
        res._step("A_durable_state", False, "state raised: %s" % type(exc).__name__)

    # --- C choose next measurement kind ----------------------------------------------
    decision = None
    try:
        if d.policy is not None:
            decision = d.policy.decide(durable, now=_as_dt(t))
            res.decision_status = getattr(decision, "status", None)
        res._step("C_decide", True, str(res.decision_status))
    except Exception as exc:  # noqa: BLE001
        res._step("C_decide", False, "policy raised: %s" % type(exc).__name__)

    # --- D enqueue (ALLOWED_KINDS allowlist enforced) --------------------------------
    try:
        task = getattr(decision, "task", None)
        if task is not None and d.queue is not None:
            _enforce_allowed(task.kind)            # refuse a forbidden kind up front
            d.queue.enqueue(task.kind, task.sport, dict(task.args or {}), now=t)
            res.enqueued_kind = task.kind
        res._step("D_enqueue", True, str(res.enqueued_kind))
    except Exception as exc:  # noqa: BLE001 -- DisallowedKind or queue error: isolate
        res._step("D_enqueue", False, "enqueue refused/failed: %s" % type(exc).__name__)

    # --- E lease + auto-gate (INERT: recalibrate_fn=None -> NO_CANDIDATE) -------------
    try:
        leased = d.queue.lease(now=t) if d.queue is not None else None
        if leased is not None and d.run_cycle is not None:
            cr = d.run_cycle(name=leased.sport,
                             settled_games_fn=_empty_settled,
                             recalibrate_fn=_inert_recalibrate,  # always None -> INERT
                             now=t)
            res.cycle_verdict = getattr(cr, "decision", None)
            d.queue.ack(leased.id)
        else:
            res.cycle_verdict = "NO_TASK"
        res._step("E_autogate", True, str(res.cycle_verdict))
    except Exception as exc:  # noqa: BLE001
        res._step("E_autogate", False, "run_cycle raised: %s" % type(exc).__name__)

    # --- F re-gate grown data + survivor re-check at wider K --------------------------
    try:
        if d.regate_select is not None:
            rg = d.regate_select(t)
            res.regate_status = getattr(rg, "status", None)
            for tk in getattr(rg, "targets", []) or []:
                _enforce_allowed(tk.kind)
                if d.queue is not None:
                    d.queue.enqueue(tk.kind, tk.sport, dict(tk.args or {}), now=t)
        if d.survivor_select is not None and d.survivor_recheck is not None:
            for st in d.survivor_select() or []:
                _enforce_allowed(st.kind)
                out = d.survivor_recheck(st, now=t)
                if getattr(out, "demoted", False):
                    res.n_survivor_demotions += 1
        res._step("F_regate_survivor", True,
                  "regate=%s demotions=%d" % (res.regate_status, res.n_survivor_demotions))
    except Exception as exc:  # noqa: BLE001
        res._step("F_regate_survivor", False, "regate/survivor raised: %s" % type(exc).__name__)

    # --- H ship-path status: PROPOSAL-ONLY while the sentinel is absent --------------
    # The ship path itself is the auto-gate already exercised in step E (run_cycle with
    # _inert_recalibrate -> None -> NO_CANDIDATE, byte-identical to the inert baseline).
    # Step H only RECORDS that posture; it spawns nothing and NEVER creates the sentinel.
    # ship_proposal_only is True whenever the sentinel is absent (engine_enabled False).
    res.ship_proposal_only = not res.engine_enabled
    res._step("H_ship_inert", True,
              "engine_enabled=%s proposal_only=%s"
              % (str(res.engine_enabled).lower(), str(res.ship_proposal_only).lower()))

    # --- G append EXACTLY ONE progress_ledger row (ALWAYS runs) ----------------------
    try:
        if d.append_snapshot is not None:
            snap = (d.build_snapshot(now=t) if d.build_snapshot else None)
            row = d.append_snapshot(snap, now=t) if snap is not None \
                else d.append_snapshot(now=t)
            res.progress_row = row
        res._step("G_progress_row", True, "appended")
    except Exception as exc:  # noqa: BLE001
        res._step("G_progress_row", False, "append raised: %s" % type(exc).__name__)

    return res


def _as_dt(ts: float) -> _dt.datetime:
    return _dt.datetime.utcfromtimestamp(float(ts))


def _empty_settled(name: str, *_a, **_kw) -> List[Dict[str, Any]]:
    """Measurement-only settled source for the auto-gate step (no fabricated games)."""
    return []


def _inert_recalibrate(name: str, settled, *_a, **_kw) -> None:
    """ALWAYS None -> NO_CANDIDATE. The ship path stays INERT; nothing is shipped."""
    return None


__all__ = ["run_once", "CadenceResult", "StepStatus", "Deps", "DisallowedKind",
           "ALLOWED_KINDS", "HEARTBEAT_COMPONENT"]
