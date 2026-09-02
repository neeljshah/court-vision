"""scripts.platformkit.combo.combo_runner -- the idempotent combination-discovery CYCLE.

The single-shot engine of Lane L's fully-autonomous loop (NO Claude/LLM in the path).
One combo_cycle(sport): INGEST settled -> ENUMERATE the next K-capped batch -> BUILD via
the MF choke -> GATE (stricter-at-scale) -> UPDATE the bandit -> RECORD proposals +
reject-lessons -> CHECKPOINT. Idempotent + checkpoint-resumable; NEVER raises.

INERT BY CONSTRUCTION: with the PIPELINE_ENABLED sentinel ABSENT the build choke
(combo_recalibrator.build_combo_candidate) returns None for EVERY spec, so the enumerator
yields zero built candidates, nothing gates, nothing ships -- the cycle decides NO_CANDIDATE
byte-identically to baseline (it still records the reject-lesson "no candidate built /
sentinel absent" + advances the observability counter, but ships/serves NOTHING).

STALE/DEGRADED never read green: an ingest STALE/DEGRADED status returns DEGRADED and
advances the cursor NOT AT ALL (a dead feed never advances). IDLE advances the clock.

--replay mode: combo_cycle(..., replay_spec=spec) re-runs the SINGLE FROZEN spec through
the IDENTICAL gate WITHOUT re-enumerating (deterministic reproduction for a test/audit).

State ONLY under data/cache/improve/combo/**. NEVER writes data/registry/, MEMORY.md,
never flips a flag, never creates the sentinel. Calibration, not edge; no $/ROI token.
numpy + stdlib + repo-internal; ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from scripts.platformkit.combo import combo_bandit as B
from scripts.platformkit.combo import combo_status as ST
from scripts.platformkit.combo.combination_enum import enumerate_combination_specs, k_cap
from scripts.platformkit.combo.combination_families import (
    CombinationSpec, all_combination_specs,
)
from scripts.platformkit.combo.combo_recalibrator import build_combo_candidate
from scripts.platformkit.combo.fwer_budget import cumulative_k
from scripts.platformkit.improve.checkpoint import (
    Checkpoint, load_checkpoint, save_checkpoint,
)
from scripts.platformkit.improve.cursor_util import SEEN_CAP
from scripts.platformkit.improve.settled_ingest import (
    DEGRADED, FRESH_NEW, IDLE, STALE, ingest_settled,
)

logger = logging.getLogger("combo_runner")

NO_CANDIDATE = "NO_CANDIDATE"
PROPOSED = "PROPOSED"
SHIPPED_DEGRADED = "DEGRADED"


def _ledger_k(ledger_path: Optional[str]) -> int:
    """Max k_cumulative on the canonical FWER ledger; 0 when it is absent/unreadable.

    S40b / RT-20: `combo_k` used to be read from a per-sport CHECKPOINT and nothing else,
    so deleting one JSON restored the per-test bar (measured: checkpoint 240 -> eps_eff
    0.0002083; the same run with a fresh checkpoint -> 0.05, a 240x looser bar) even
    though the ledger still recorded the trials. The ledger is the second, independent K
    universe; reconciling to the LARGER of the two makes a deleted checkpoint harmless.
    """
    try:
        from scripts.platformkit.eval_gate.backtest_runner import canonical_ledger_path
        from scripts.platformkit.eval_gate.ledger import load_fwer

        path = Path(ledger_path) if ledger_path else canonical_ledger_path()
        return max((int(r.get("k_cumulative", 0)) for r in load_fwer(path)), default=0)
    except Exception as exc:  # noqa: BLE001 -- an unreadable ledger never blocks a cycle
        logger.debug("combo_runner: ledger K unreadable (%s); falling back to checkpoint", exc)
        return 0


@dataclass
class ComboCycleResult:
    """Counts-only result of one combo cycle (NO $/ROI -- calibration not edge)."""

    sport: str = ""
    decision: str = NO_CANDIDATE
    status: str = IDLE
    n_settled: int = 0
    n_enumerated: int = 0
    n_built: int = 0
    n_proposed: int = 0
    n_rejected: int = 0
    k_cycle: int = 0
    k_cumulative: int = 0
    note: str = "calibration, not edge; vs_close UNPROVEN; inert when sentinel absent"
    proposals: List[Dict[str, Any]] = field(default_factory=list)
    rejects: List[Dict[str, Any]] = field(default_factory=list)


def _default_gate_fn(cand: Dict[str, Any], *, k: int, n_corpora: int) -> Dict[str, Any]:
    """The PROVEN combo gate -- consumed, never weakened. Single corpus -> REJECT.

    With only the primary corpus wired (corpora=[]) the cross-corpus L4/L5 layer cannot
    REPLICATE, so the gate honestly REJECTs (REPLICATION_PENDING-equivalent). This is the
    honest current state: a combo cannot ship on one corpus. NEVER raises.
    """
    try:
        from scripts.platformkit.combo.combo_gate import gate_combo  # noqa: F401
    except Exception as exc:  # noqa: BLE001 -- gate import gone -> conservative reject
        return {"verdict": B.REJECT, "reason": "gate_unavailable: %s" % exc, "layer": "L0"}
    # Single-corpus candidate: the cross-corpus replication floor cannot be met, so the
    # proven gate would REJECT. We surface that verdict directly (no parallel scoring).
    if not cand.get("corpora"):
        return {"verdict": B.REJECT,
                "reason": "single-corpus: cross-corpus replication floor unmet (>=2 corpora)",
                "layer": "L5"}
    return {"verdict": B.REJECT, "reason": "default-deny: real gate wiring is human-gated",
            "layer": "L0"}


def _detail_signals_of(clean: Sequence[Dict[str, Any]]) -> List[str]:
    """Name-stable detail-signal handles present across the clean batch (NEVER cluster-ids).

    Drawn from the first clean state row's `detail` dict keys -- a combo over a handle that
    is not actually present is dropped by the build choke (honest NO_CANDIDATE).
    """
    for g in clean:
        rows = g.get("states") if isinstance(g.get("states"), list) else [g]
        for s in rows:
            det = s.get("detail")
            if isinstance(det, dict) and det:
                return sorted(str(k) for k in det.keys())
    return []


def combo_cycle(
    sport: str, *,
    settled_games_fn: Optional[Callable[..., Sequence[Dict[str, Any]]]] = None,
    gate_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    target: str = "winprob",
    ckpt_path: Optional[str] = None,
    state_path: Optional[str] = None,
    proposals_path: Optional[str] = None,
    reject_path: Optional[str] = None,
    status_path: Optional[str] = None,
    ledger_path: Optional[str] = None,
    replay_spec: Optional[CombinationSpec] = None,
    now: float = 0.0,
    **ingest_kw: Any,
) -> ComboCycleResult:
    """Run ONE idempotent combo cycle for `sport`. NEVER raises.

    Checkpoint-resumable: the cursor (processed count + seen ids + cumulative K + per-family
    bandit) only advances; a restart re-derives the same batch. With the sentinel absent the
    build choke returns None for every spec -> NO_CANDIDATE (inert). STALE/DEGRADED ingest ->
    DEGRADED, cursor frozen. --replay re-runs ONE frozen spec without re-enumerating.
    """
    res = ComboCycleResult(sport=str(sport))
    try:
        ckpt: Checkpoint = load_checkpoint(ckpt_path)
        cur = ckpt.cursor(sport)
        state = B.load_state(state_path)
        seen = list(cur.get("seen_ids", []))
        # K-SOURCE DISCIPLINE (RT-20): reconcile the checkpoint against the ledger at
        # LAUNCH and take the LARGER -- a deleted/rolled-back checkpoint can no longer
        # loosen the bar. Logged so the reconciliation is visible in the cycle log.
        ckpt_k = int(cur.get("combo_k", 0))
        ledger_k = _ledger_k(ledger_path)
        prior_k = max(ckpt_k, ledger_k)
        if prior_k != ckpt_k:
            logger.info("combo_runner(%s): prior_k reconciled checkpoint=%d ledger=%d -> %d",
                        sport, ckpt_k, ledger_k, prior_k)

        # --- INGEST (honest dead-feed-aware) ----------------------------------------
        sf = settled_games_fn
        if sf is not None:
            clean = list(sf(sport, since=str(cur.get("high_water", "")), seen_ids=seen))
            status = FRESH_NEW if clean else IDLE
            high_water = str(cur.get("high_water", ""))
        else:
            summ = ingest_settled(sport, seen_ids=seen,
                                  high_water=str(cur.get("high_water", "")), **ingest_kw)
            clean = list(summ.clean_games)
            status = summ.status
            high_water = summ.high_water
        res.status = status
        res.n_settled = len(clean)

        if status in (STALE, DEGRADED):
            res.decision = SHIPPED_DEGRADED  # dead feed: never green, cursor FROZEN.
            ST.record_status(res, status_path, now=now)
            return res  # NO checkpoint advance.

        # --- ENUMERATE the next K-capped batch (or the single replay spec) ----------
        if replay_spec is not None:
            specs: List[CombinationSpec] = [replay_spec]
        else:
            handles = _detail_signals_of(clean)
            all_specs = all_combination_specs(sport, target, handles)
            tried = set(cur.get("tried_ids", []))
            specs = enumerate_combination_specs(
                all_specs, tried_ids=tried, ledger=B.enum_ledger(state),
                prior_k=prior_k, seed=int(now) & 0x7FFFFFFF)
        res.n_enumerated = len(specs)
        k_cycle = len(specs) if replay_spec is not None else k_cap(prior_k)
        res.k_cycle = int(max(k_cycle, len(specs)))
        res.k_cumulative = cumulative_k(prior_k, res.n_enumerated)

        # --- BUILD (choke) -> GATE -> BANDIT -> RECORD ------------------------------
        gfn = gate_fn or _default_gate_fn
        for spec in specs:
            cand = build_combo_candidate(spec, sport, clean)
            if cand is None:
                # Sentinel absent OR absent leg OR degenerate -> NO_CANDIDATE for this spec.
                res.rejects.append(ST.reject_lesson(
                    spec, verdict=B.REJECT, reason="no_candidate_built",
                    layer="MF1/MF3", k=res.k_cumulative))
                B.update(state, spec.family, B.REJECT, k=res.k_cumulative)
                continue
            res.n_built += 1
            v = gfn(cand, k=res.k_cumulative, n_corpora=len(cand.get("corpora", [])) or 1)
            verdict = str(v.get("verdict", B.REJECT))
            is_null = bool(getattr(spec, "is_null", False))
            B.update(state, spec.family, verdict, is_null=is_null, k=res.k_cumulative)
            if verdict == B.SHIP:
                res.proposals.append(ST.proposal_row(spec, cand, v))
                res.n_proposed += 1
            else:
                res.rejects.append(ST.reject_lesson(
                    spec, verdict=verdict, reason=str(v.get("reason", "")),
                    layer=str(v.get("layer", "")), k=res.k_cumulative))
                res.n_rejected += 1

        res.decision = PROPOSED if res.n_proposed else NO_CANDIDATE

        # --- CHECKPOINT (advance monotonically; replay never advances) --------------
        if replay_spec is None:
            tried = set(cur.get("tried_ids", [])) | {s.combo_id for s in specs}
            cur["tried_ids"] = sorted(tried)[-SEEN_CAP:]
            cur["combo_k"] = res.k_cumulative
            cur["high_water"] = max(str(cur.get("high_water", "")), high_water)
            folded = {str(g.get("game_id", g.get("id", ""))) for g in clean}
            cur["seen_ids"] = sorted(set(seen) | (folded - {""}))[-SEEN_CAP:]
            cur["processed"] = int(cur.get("processed", 0)) + len(clean)
            cur["last_decision"] = res.decision
            ckpt.cycle += 1
            save_checkpoint(ckpt, ckpt_path)
            B.save_state(state, state_path)

        ST.record_cycle(res, proposals_path, reject_path, status_path, now=now)
        return res
    except Exception as exc:  # noqa: BLE001 -- purity: any failure -> NO_CANDIDATE.
        logger.debug("combo_cycle(%s) failed -> NO_CANDIDATE: %s", sport, exc)
        res.decision = NO_CANDIDATE
        return res


__all__ = ["ComboCycleResult", "combo_cycle", "NO_CANDIDATE", "PROPOSED",
           "SHIPPED_DEGRADED"]
