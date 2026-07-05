"""scripts.platformkit.combo.stack_gate_pregame -- pregame stack-family judge.

PREREG_STACK_FAMILIES_2026-07-05.md MACHINERY clause: gate_detail_layer/gate_cross
are hard-wired to the in-game form sigmoid and cannot judge pregame N-feature
stacks. Substitute harness reproducing every layer, IMPORTING (never reimplementing):
L0 combo_base_guard.collinear_with_base_reason(tau=0.92) + improve.base_guard.
degenerate_base_reason; L1 combo.nested_cv.select_then_score (outer_score GATES,
never discarded); L2 Brier+log-loss unanimity vs the FITTED p_base stream; L4/L5
both-directions cross-corpus clustered DM (eval_gate.dm_test.diebold_mariano) at
eps_eff + replication floor; L6 fwer_budget.eps_eff/min_corpora_eff/fdr_budget;
planted-null + family-freeze harness-internal (wave-1; combo_bandit_state untouched).
Verdict mirrors ComboVerdict.to_dict() + coverage/caveats house style.

Calibration, not edge. NO $ / ROI anywhere. numpy + pandas + stdlib only. ASCII.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from scripts.platformkit.combo.combo_base_guard import collinear_with_base_reason
from scripts.platformkit.combo.fwer_budget import eps_eff, fdr_budget, min_corpora_eff
from scripts.platformkit.combo.nested_cv import select_then_score
from scripts.platformkit.combo.stack_fit import brier, logloss
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.improve.base_guard import degenerate_base_reason

MIN_NULLS = 20


@dataclass(frozen=True)
class StackRow:
    """One eval row: event_id, outcome, base prob, candidate prob, RAW added feats."""

    event_id: str
    y: float
    p_base: float
    p_candidate: float
    added_raw: Tuple[float, ...]  # raw (pre-standardization) added-feature values


@dataclass
class StackVerdict:
    verdict: str
    reason: str = ""
    layer: str = ""
    vs_close: str = "not_evaluated"
    proposal_only: bool = True
    detail: Dict[str, Any] = field(default_factory=dict)
    coverage: Dict[str, Any] = field(default_factory=dict)
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict, "reason": self.reason, "layer": self.layer,
            "vs_close": self.vs_close, "proposal_only": self.proposal_only,
            "detail": self.detail, "coverage": self.coverage,
            "caveats": list(self.caveats),
        }


def _rows_to_arrays(rows: Sequence[StackRow]) -> Dict[str, np.ndarray]:
    return {
        "event_id": np.array([r.event_id for r in rows], dtype=str),
        "y": np.array([r.y for r in rows], dtype=float),
        "p_base": np.array([r.p_base for r in rows], dtype=float),
        "p_candidate": np.array([r.p_candidate for r in rows], dtype=float),
        "added_raw": np.array([r.added_raw for r in rows], dtype=float),  # (n, k)
    }


# L0: collinearity + degenerate-base guards -------------------------------- #

def l0_guards(added_feature_col: np.ndarray, base_feature_cols: Mapping[str, np.ndarray],
             candidate_preds: np.ndarray, base_preds: np.ndarray, y: np.ndarray,
             p_close: Optional[np.ndarray] = None, tau: float = 0.92) -> Optional[str]:
    """Return an L0 reject reason, or None if both guards pass.

    Collinearity tests the ADDED feature column (mirrors combo_gate's `combo_vals
    = detail_a[combo_col]`) -- NOT the stacked probability, which is dominated by
    base features by construction and would spuriously reject every real stack.
    Degeneracy tests the full candidate-vs-base prediction streams (a different
    question: did the whole forecast collapse), per base_guard's own contract.
    """
    r = collinear_with_base_reason(added_feature_col, base_feature_cols, tau=tau)
    if r is not None:
        return f"L0_collinear: {r}"
    r = degenerate_base_reason(candidate_preds, base_preds, y, p_close=p_close)
    if r is not None:
        return f"L0_degenerate: {r}"
    return None


# L2: proper-score unanimity vs the FITTED p_base stream -------------------- #

@dataclass(frozen=True)
class L2Result:
    brier_base: float
    brier_stack: float
    logloss_base: float
    logloss_stack: float
    brier_wins: bool
    logloss_wins: bool
    unanimous: bool


def l2_unanimity(y: np.ndarray, p_base: np.ndarray, p_stack: np.ndarray) -> L2Result:
    """Brier AND log-loss must BOTH improve on the SAME (identical) rows."""
    br_b, br_s = brier(p_base, y), brier(p_stack, y)
    ll_b, ll_s = logloss(p_base, y), logloss(p_stack, y)
    bw, lw = br_s < br_b, ll_s < ll_b
    return L2Result(br_b, br_s, ll_b, ll_s, bw, lw, bw and lw)


# L4/L5: both-directions cross-corpus, clustered DM at eps_eff -------------- #

@dataclass(frozen=True)
class DirectionResult:
    direction: str
    n: int
    brier_base: float
    brier_stack: float
    dm_p: float
    dm_stat: float
    stack_beats_base: bool


def one_direction_dm(y: np.ndarray, p_base: np.ndarray, p_stack: np.ndarray,
                     event_ids: np.ndarray, eps: float, direction: str) -> DirectionResult:
    """Clustered-DM comparison of BASE vs STACK loss on one eval direction."""
    br_b, br_s = brier(p_base, y), brier(p_stack, y)
    d = (np.clip(p_base, 1e-6, 1 - 1e-6) - y) ** 2 - (np.clip(p_stack, 1e-6, 1 - 1e-6) - y) ** 2
    dm = diebold_mariano(d, event_ids)
    beats = bool((br_s < br_b) and (dm.p_value < eps))
    return DirectionResult(direction, len(y), br_b, br_s, dm.p_value, dm.dm_stat, beats)


def cross_corpus_both_directions(
    corpus_a: Sequence[StackRow], corpus_b: Sequence[StackRow], eps: float,
) -> Tuple[DirectionResult, DirectionResult]:
    """A->B and B->A directions; each corpus already carries its OWN fitted p_base/p_stack."""
    aa = _rows_to_arrays(corpus_a)
    bb = _rows_to_arrays(corpus_b)
    a_to_b = one_direction_dm(bb["y"], bb["p_base"], bb["p_candidate"], bb["event_id"],
                             eps, "A_train_B_eval")
    b_to_a = one_direction_dm(aa["y"], aa["p_base"], aa["p_candidate"], aa["event_id"],
                             eps, "B_train_A_eval")
    return a_to_b, b_to_a


# Planted-null orchestration (harness-internal; NEVER touches combo_bandit_state) #

def planted_null_fdr(
    refit_and_score_fn: Callable[[np.random.Generator], bool],
    eps: float, k: int, n_draws: int = MIN_NULLS, base_seed: int = 0,
) -> Dict[str, Any]:
    """Run >=20 within-corpus permutation draws through the IDENTICAL pipeline.
    `refit_and_score_fn(rng)` permutes ONLY the added column(s), refits, returns
    True iff the shuffled stack ships at the SAME bars a real candidate must
    clear. fdr_hat=n_ship/n_run; freezes if fdr_hat > fdr_budget(eps,k) OR any
    draw ships (prereg: any null ship freezes the family)."""
    n_draws = max(MIN_NULLS, int(n_draws))
    n_ship = 0
    for i in range(n_draws):
        if bool(refit_and_score_fn(np.random.default_rng(base_seed + i * 7919))):
            n_ship += 1
    budget = fdr_budget(eps, k)
    fdr_hat = n_ship / float(n_draws)
    frozen = bool(n_ship > 0 or fdr_hat > budget)
    return {"n_draws": n_draws, "n_ship": n_ship, "fdr_hat": round(fdr_hat, 6),
            "budget": round(budget, 6), "family_frozen": frozen}


# Full judge: assembles every layer into one StackVerdict ------------------ #

def judge_stack_family(
    *, name: str, corpora: Sequence[Sequence[StackRow]], corpus_labels: Sequence[str],
    base_feature_cols: Mapping[str, np.ndarray], k_cum: int, n_corpora_available: int,
    nested_cv_select_fn: Optional[Callable] = None, nested_cv_score_fn: Optional[Callable] = None,
    nested_cv_game_ids: Optional[Sequence[Any]] = None,
    planted_null_fn: Optional[Callable[[np.random.Generator], bool]] = None,
    p_close: Optional[np.ndarray] = None, close_brier: Optional[float] = None,
    stack_brier_vs_close: Optional[float] = None, seed_stability_p10: Optional[float] = None,
) -> StackVerdict:
    """Assemble L0->L6 into one honest StackVerdict. `corpora` are already-fitted
    (p_base, p_candidate) StackRow lists, one per corpus (>=2 for L4/L5).
    nested_cv_*/planted_null_fn are NOT optional (prereg L1/L3) -- omitting
    them returns VOID, never a silent pass."""
    eps = eps_eff(0.05, k_cum)
    min_corp = min_corpora_eff(n_corpora_available, k_cum)
    caveats: List[str] = [
        f"eps_eff={eps:.6f} at k_cum={k_cum}; min_corpora_eff={min_corp}.",
        "Brier/log-loss computed against the FITTED p_base stream on identical rows "
        "(never a base-rate constant, never gate_combo aux_proper_scores).",
    ]

    if len(corpora) < 2:
        return StackVerdict("NOT_TESTABLE", "fewer than 2 corpora supplied", "L4",
                            caveats=caveats + ["cannot run cross-corpus without >=2 corpora"])

    # L0 on the first corpus: each ADDED feature column vs base_feature_cols + degeneracy.
    first = _rows_to_arrays(corpora[0])
    n_added = first["added_raw"].shape[1] if first["added_raw"].ndim == 2 else 0
    for j in range(n_added):
        col = np.nan_to_num(first["added_raw"][:, j], nan=0.0)  # neutral for corr test only
        l0_reason = l0_guards(col, base_feature_cols, first["p_candidate"], first["p_base"], first["y"])
        if l0_reason is not None:
            return StackVerdict("REJECT", l0_reason, "L0", caveats=caveats)

    # L1/L3: frozen-outer-holdout selection + convergence -- NOT OPTIONAL (prereg).
    if nested_cv_select_fn is None or nested_cv_score_fn is None or nested_cv_game_ids is None:
        return StackVerdict("VOID", "L1/L3 nested-CV selection not supplied -- verdict "
                            "is VOID per prereg (variant selection MUST go through "
                            "select_then_score)", "L1", caveats=caveats)
    nested = select_then_score(nested_cv_select_fn, nested_cv_score_fn, nested_cv_game_ids)
    # outer_score MUST gate here (mirrors combo_gate.py L1) -- never computed-and-discarded.
    if not np.isfinite(nested.outer_score) or nested.outer_score < 0.0:
        r = (f"L1 sealed-holdout score={nested.outer_score:.6f}: stack does not beat "
            f"base on the frozen outer holdout ({nested.n_holdout_games} games)")
        return StackVerdict("REJECT", r, "L1", caveats=caveats)
    caveats.append(f"L1 nested-CV: selected on {nested.n_inner_games} inner games, "
                   f"SEALED-HOLDOUT score={nested.outer_score:.6f} (>=0, gates here) on "
                   f"{nested.n_holdout_games} frozen holdout games.")

    if seed_stability_p10 is None:
        return StackVerdict("VOID", "L3 seed-stability (>=5 refits, p10 check) not "
                            "supplied -- verdict is VOID per prereg", "L3", caveats=caveats)
    if seed_stability_p10 < 0.0:
        return StackVerdict("REJECT", f"L3 seed-stability failed: p10(delta)={seed_stability_p10:.6f} < 0",
                            "L3", caveats=caveats)
    caveats.append(f"L3 seed-stability: p10(stack-vs-base delta)={seed_stability_p10:.6f} >= 0.")

    # L2: unanimity within EACH corpus.
    l2_results = [l2_unanimity(a["y"], a["p_base"], a["p_candidate"])
                 for a in (_rows_to_arrays(c) for c in corpora)]
    if not all(r.unanimous for r in l2_results):
        return StackVerdict("REJECT", "L2 Brier/log-loss unanimity failed on >=1 corpus",
                            "L2", detail={"l2_per_corpus": [r.__dict__ for r in l2_results]},
                            caveats=caveats)
    caveats.append("L2 unanimity: Brier AND log-loss both improve on every corpus supplied.")

    # L4/L5: both-directions cross-corpus at eps_eff, replication floor.
    dir_results: List[DirectionResult] = []
    n_replicated_corpora = 0
    for i in range(len(corpora) - 1):
        a_to_b, b_to_a = cross_corpus_both_directions(corpora[i], corpora[i + 1], eps)
        dir_results += [a_to_b, b_to_a]
        if a_to_b.stack_beats_base and b_to_a.stack_beats_base:
            n_replicated_corpora += 1
    both_directions_ok = all(d.stack_beats_base for d in dir_results)
    replication_ok = n_replicated_corpora >= min_corp - 1

    # Planted-null + family-freeze (harness-internal, wave-1). NOT optional: no
    # planted-null lane -> VOID, never a silent SHIP (mirrors L1/L3's "not optional").
    if planted_null_fn is None:
        return StackVerdict("VOID", "planted-null lane not supplied -- verdict is VOID, "
                            "cannot certify FDR-clean per prereg", "PLANTED_NULL", caveats=caveats)
    null_result = planted_null_fdr(planted_null_fn, eps, k_cum)
    caveats.append(f"planted-null: n_draws={null_result['n_draws']} "
                   f"fdr_hat={null_result['fdr_hat']} budget={null_result['budget']}.")
    if null_result.get("family_frozen"):
        return StackVerdict("REJECT", "family_frozen: a planted-null draw shipped OR "
                            "fdr_hat exceeded budget", "FDR",
                            detail={"planted_null": null_result}, caveats=caveats)

    vs_close = "not_evaluated"
    if close_brier is not None and stack_brier_vs_close is not None:
        vs_close = "MATCH" if abs(stack_brier_vs_close - close_brier) < 1e-3 else (
            "BEAT" if stack_brier_vs_close < close_brier else "BEHIND")
        caveats.append(f"vs-close: stack Brier {stack_brier_vs_close:.5f} vs close "
                       f"Brier {close_brier:.5f} -> {vs_close}. Beating the close is "
                       f"NOT claimed from a single corpus.")

    detail = {
        "l2_per_corpus": [r.__dict__ for r in l2_results],
        "directions": [d.__dict__ for d in dir_results],
        "n_replicated_pairs": n_replicated_corpora,
        "min_corpora_eff": min_corp,
        "planted_null": null_result,
        "eps_eff": eps,
        "corpus_labels": list(corpus_labels),
    }

    if both_directions_ok and replication_ok:
        r = "all layers passed: L0/L1/L2/L3/L4/L5/L6/FDR"
        return StackVerdict("SHIP", r, "L5", vs_close=vs_close, detail=detail, caveats=caveats)
    if any(d.stack_beats_base for d in dir_results):
        r = "stack beat base in >=1 direction but not full replication at the required floor"
        return StackVerdict("PARTIAL", r, "L5", vs_close=vs_close, detail=detail, caveats=caveats)
    r = "stack did not beat base in any cross-corpus direction"
    return StackVerdict("REJECT", r, "L5", vs_close=vs_close, detail=detail, caveats=caveats)


__all__ = [
    "StackRow", "StackVerdict", "l0_guards", "L2Result", "l2_unanimity",
    "DirectionResult", "one_direction_dm", "cross_corpus_both_directions",
    "planted_null_fdr", "judge_stack_family", "MIN_NULLS",
]
