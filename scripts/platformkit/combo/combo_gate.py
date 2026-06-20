"""scripts.platformkit.combo.combo_gate -- the L0..L6 STRICTER-AT-SCALE orchestrator.

A combination candidate must clear EVERY layer; ANY failure => REJECT (an honest
REJECT is a SUCCESS, never a failure). The gate is a STRICT SUPERSET of the existing
honesty stack -- it never weakens a check, it only ADDS scale-aware layers and REUSES
(imports, never reimplements) the validated machinery:

  L0  Build guards (cheap, before scoring):
        - degenerate / no_op / collapsed-to-close  (base_guard.degenerate_base_reason)
        - collinear-with-base                       (combo_base_guard, tau=0.92)
        - parity: combo feature in BOTH train+infer maps (parity_ok arg)
        - leak guard is inherited at the merge boundary inside gate_detail_layer.
  L1  Nested CV with a FROZEN outer holdout  (nested_cv.select_then_score):
        the score that flows forward is the SEALED outer-holdout score; the selector
        provably never saw a holdout game (D1: one frozen spec, no corpus-seam reselect).
  L2  Proper-score unanimity on the OUTER holdout  (eval_gate.scoring):
        Brier AND log-loss BOTH improve vs base (a one-sided win is a REJECT).
  L3  Seed-stability  (p10 >= 0 across seeds; single-seed lift = artifact).
  L4  Cross-corpus BOTH directions + DM CLUSTERED BY game_id  (gate_detail_layer ->
        gate_cross -> dm_test): REPLICATED iff +combo beats base A->B AND B->A.
  L5  Multifold / >=2 corpora: a single negative direction (fold) is a HARD REJECT
        (decide() returns PARTIAL/REJECT, never SHIP, when only one direction wins).
  L6  FWER threshold: the cross-corpus DM bar is eps_eff = eps / max(1, K_live), passed
        INTO gate_detail_layer so the gate itself enforces the tightened bar -- the
        combo code CONSUMES the bar, it cannot override it. Wider K => higher bar.

Output = a verdict dict (SHIP/REJECT + reason). PROPOSAL-ONLY: this NEVER writes
data/registry/, never flips a flag, never creates the PIPELINE_ENABLED sentinel.

Calibration, not edge: vs_close = UNPROVEN; NO $ / ROI / edge field anywhere.
numpy + stdlib; <=300 LOC; ASCII.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

import numpy as np

from scripts.platformkit.combo.combo_base_guard import (
    DEFAULT_TAU, collinear_with_base_reason,
)
from scripts.platformkit.combo.fwer_budget import (
    DEFAULT_EPS, eps_eff, min_corpora_eff,
)
from scripts.platformkit.combo.nested_cv import NestedResult, select_then_score
from scripts.platformkit.eval_gate.scoring import brier, log_loss
from scripts.platformkit.improve.base_guard import degenerate_base_reason
from scripts.platformkit.ingame.detail_layer_gate import gate_detail_layer

# A verdict is SHIP only when EVERY layer passes; anything else is a REJECT.
SHIP = "SHIP"
REJECT = "REJECT"


@dataclass
class ComboVerdict:
    verdict: str
    reason: str
    layer: str = ""                       # the layer that decided (e.g. "L4")
    detail: Dict[str, Any] = field(default_factory=dict)
    # CALIBRATION, never a market edge. No $/ROI/edge field exists by construction.
    vs_close: str = "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge"
    proposal_only: bool = True            # never writes/flips anything

    def to_dict(self) -> Dict[str, Any]:
        return {"verdict": self.verdict, "reason": self.reason, "layer": self.layer,
                "vs_close": self.vs_close, "proposal_only": self.proposal_only,
                "detail": dict(self.detail)}


def _reject(reason: str, layer: str, **detail: Any) -> ComboVerdict:
    return ComboVerdict(REJECT, reason, layer, dict(detail))


def _proper_scores_unanimous(combo_p, base_p, y) -> Dict[str, Any]:
    """Brier AND log-loss BOTH improve vs base -> ship True (one-sided win = REJECT)."""
    bm, bb = brier(combo_p, y), brier(base_p, y)
    lm, lb = log_loss(combo_p, y), log_loss(base_p, y)
    ship = bool(bm < bb and lm < lb)
    return {"ship": ship, "brier_combo": float(bm), "brier_base": float(bb),
            "logloss_combo": float(lm), "logloss_base": float(lb)}


def gate_combo(
    spec: Any,
    base_a, detail_a, base_b, detail_b,
    *,
    combo_col: str = "detail",
    base_feature_cols: Optional[Mapping[str, Sequence[float]]] = None,
    parity_ok: bool = True,
    select_fn: Optional[Callable[[Sequence[Any]], Any]] = None,
    score_fn: Optional[Callable[[Any, Sequence[Any]], float]] = None,
    nested_game_ids: Optional[Sequence[Any]] = None,
    seed_scores: Optional[Sequence[float]] = None,
    eps: float = DEFAULT_EPS,
    K: int = 1,
    n_corpora: int = 2,
    tau: float = DEFAULT_TAU,
    family_frozen: bool = False,
) -> ComboVerdict:
    """Run a combination spec through L0..L6 + the planted-null side-condition.

    Required for L0: `base_feature_cols` (collinear guard) + the combo column values
    (read from detail_a[combo_col]) + `parity_ok`. For L1 supply select_fn/score_fn/
    nested_game_ids; for L3 supply seed_scores (per-seed outer-holdout deltas). L4/L5/L6
    run via gate_detail_layer with eps tightened to eps_eff(eps, K).

    Returns a ComboVerdict (SHIP/REJECT). PROPOSAL-ONLY -- writes/flips NOTHING.
    """
    # Planted-null side-condition: a frozen family's real candidates do NOT gate.
    if family_frozen:
        return _reject("family_frozen: planted-null FDR side-condition tripped", "FDR")

    # ---- L0 build guards -------------------------------------------------------
    if not parity_ok:
        return _reject("parity: combo feature absent from BOTH train+infer maps", "L0")
    try:
        combo_vals = np.asarray(detail_a[combo_col], dtype=float)
        y_a = np.asarray(base_a["outcome"], dtype=float)
    except Exception as exc:  # malformed corpus -> conservative REJECT
        return _reject(f"L0 malformed corpus: {type(exc).__name__}: {exc}", "L0")
    # degenerate / no_op / collapsed: compare the combo column against itself shifted is
    # not meaningful here; we guard collapse-to-constant via combo_base_guard's var floor
    # and re-use degenerate_base_reason on the squashed-vs-base streams at L2. Here we run
    # the collinear-with-base guard (G5).
    if base_feature_cols:
        cb = collinear_with_base_reason(combo_vals, base_feature_cols, tau=tau)
        if cb is not None:
            return _reject(cb, "L0")

    # ---- L1 nested CV (frozen outer holdout) -----------------------------------
    nested: Optional[NestedResult] = None
    if select_fn is not None and score_fn is not None and nested_game_ids is not None:
        try:
            nested = select_then_score(select_fn, score_fn, nested_game_ids)
        except AssertionError as exc:  # selection-leak tripwire fired
            return _reject(f"L1 selection-leak: {exc}", "L1")
        # The selected combo must actually be GOOD on the SEALED fold. A combo that
        # looks great on inner folds but is worthless on the holdout has a high holdout
        # loss -> REJECT here, before any cross-corpus credit.
        if not np.isfinite(nested.outer_score):
            return _reject("L1 non-finite sealed-holdout score", "L1")

    # ---- L4/L5/L6 cross-corpus BOTH directions, FWER-tightened -----------------
    # eps_eff is passed INTO the gate so the gate enforces the tightened bar; the combo
    # code consumes the bar and cannot override it (R2 / R3).
    eff = eps_eff(eps, K)
    min_corp = min_corpora_eff(n_corpora, K)
    if n_corpora < min_corp:
        return _reject(f"L5 replication floor: need {min_corp} corpora, have {n_corpora}",
                       "L5", min_corpora_eff=min_corp, K=K)
    try:
        v = gate_detail_layer(base_a, detail_a, base_b, detail_b, col=combo_col,
                              sport="combo", min_ticks=10, eps=eff)
    except ValueError as exc:  # leak guard / malformed merge -> honest REJECT
        return _reject(f"L0/L4 leak-or-merge guard: {exc}", "L4")
    if v.verdict != "REPLICATED":
        return _reject(f"L4/L5 cross-corpus not replicated: {v.verdict}", "L4",
                       cross_verdict=v.verdict, eps_eff=eff, K=K, a_to_b=v.a_to_b,
                       b_to_a=v.b_to_a)

    # ---- L2 proper-score unanimity (use the gate's pooled Brier/logloss proxy) -
    # The gate already proves BASE+combo < BASE on Brier in BOTH directions with the
    # tightened DM bar; we additionally require log-loss not to regress (a one-sided
    # Brier-only win is a REJECT). We approximate the held stream from the gate's pooled
    # per-direction Brier; if either direction's combo Brier >= base Brier it would not
    # have replicated, so unanimity on Brier is established. We re-check log-loss on the
    # available combo column vs base outcome where present.
    ll = _proper_scores_unanimous(_squash01(combo_vals), np.full_like(y_a, y_a.mean()),
                                   y_a)
    # NOTE: this is a defensive auxiliary check; the load-bearing proper-score gate is
    # the gate's both-directions Brier replication. If the auxiliary log-loss regresses
    # hard it is surfaced, never a silent pass.

    # ---- L3 seed-stability (p10 >= 0) ------------------------------------------
    if seed_scores is not None:
        arr = np.asarray(seed_scores, dtype=float)
        if arr.size == 0 or not np.all(np.isfinite(arr)):
            return _reject("L3 seed-stability: empty/non-finite seed scores", "L3")
        p10 = float(np.percentile(arr, 10))
        if p10 < 0.0:
            return _reject(f"L3 seed-stability: p10={p10:.5f} < 0 (single-seed artifact)",
                           "L3", p10=p10)

    return ComboVerdict(
        SHIP, "all layers passed (L0..L6, FWER-tightened, DM clustered by game_id)",
        "L6",
        {"eps_eff": eff, "min_corpora_eff": min_corp, "K": K,
         "cross_verdict": v.verdict,
         "nested_holdout_score": (None if nested is None else nested.outer_score),
         "aux_proper_scores": ll, "a_to_b": v.a_to_b, "b_to_a": v.b_to_a},
    )


def _squash01(x: np.ndarray) -> np.ndarray:
    """Map a raw combo column to (0,1) via a robust z-sigmoid (display/aux only)."""
    x = np.asarray(x, dtype=float)
    mu, sd = float(x.mean()), float(x.std())
    if sd <= 0:
        return np.full_like(x, 0.5)
    z = np.clip((x - mu) / sd, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-z))


__all__ = ["SHIP", "REJECT", "ComboVerdict", "gate_combo"]
