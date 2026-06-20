"""scripts.platformkit.survivor_corners_combo_gate -- SURVIVOR-SCRUTINY run of the
soccer as-of DISCIPLINE family {corners, fouls, yellow, red, sot_ratio} through the
PROVEN combo_gate harness (COMBO WAVE 0), so that the single-fold "diff_corners_asof
beats EW-Poisson" claim is forced past selection-multiplicity, selection-on-test,
single-fold, and seed-instability all at once.

WHY THIS FILE (reuse, NOT reinvent): the gate_run_soccer_espn28 lane found
diff_corners_asof beat the EW-Poisson base on a SINGLE 50/50 chronological fold per
corpus, in BOTH directions, on 2 corpora -- but corners is 1-of-5 candidates tested
(SELECTION MULTIPLICITY), it was one fold, and the 5-split stability was never
independently re-verified. Those are exactly the leaks combo_gate / nested_cv /
fwer_budget / planted_null_fdr / combo_base_guard were built to control. This module
adds NO new scoring math: it bridges the REAL 25,834-match football-data corpus +
match_stats.parquet into the combo machinery's contract and reports the honest verdict.

THE BRIDGE (pregame -> the gate's in-game state contract, a pure relabel, no new fit):
  game_id      = event_id (one tick/match -> DM clustering is per-match, the honest
                 pregame default; no per-state SE inflation to correct).
  state_diff   = logit(p_poisson)  (the leak-free EW-Poisson BASE signal). With
                 frac_elapsed = 1.0 the gate's BASE = sigmoid((a+b)*logit(p_poisson))
                 is a TRAIN-only recalibration of the SAME Poisson base the lane used.
  p0 (detail)  = the candidate as-of diff feature, squashed to [0,1] by the gate's
                 fixed per-row transform; the gate fits its blend weight on TRAIN only.
  outcome      = y_home.
So BASE = recalibrated Poisson, BASE+detail = Poisson + as-of feature, scored on a
held-out corpus with DM + the degenerate-base guard + graceful-degrade -- the full
L0..L6 stack, identical to what the planted nulls traverse.

SELECTION HAPPENS INSIDE THE INNER FOLD (nested_cv.select_then_score): select_fn picks
the best of the 5 candidates by INNER-fold Brier-delta (it is handed ONLY inner
game_ids, wrapped in a SelectSpy that RAISES if it ever sees an outer-fold game);
score_fn scores the FROZEN selected candidate ONCE on the sealed outer fold. The score
that flows forward is the sealed-outer-fold score, never a selection score.

FWER TIGHTENS WITH K: K = 5 candidates x 2 directions x 2 corpora = 20 -> eps_eff =
eps / K. Corners must clear the cumulative-K bar, not the naive single-test bar.

PROPOSAL-ONLY: writes NOTHING to data/registry/, flips NO flag, creates NO sentinel,
never pushes. CALIBRATION only (held-out home-win Brier) -- NO $/ROI/edge field; vs_close
stays UNPROVEN. numpy/pandas + the combo modules; ASCII; <=300 LOC. A truthful
DOWNGRADE_TO_ARTIFACT is a SUCCESS; the bar is NEVER weakened to keep the survivor.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.combo.combo_base_guard import (
    DEFAULT_TAU, collinear_with_base_reason,
)
from scripts.platformkit.combo.combo_gate import SHIP, gate_combo
from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS, eps_eff
from scripts.platformkit.combo.nested_cv import select_then_score
from scripts.platformkit.combo.planted_null_fdr import run_family_nulls
from scripts.platformkit.survivor_corners_corpus import (
    CORPUS_A, CORPUS_B, FAMILY, MATCHES, MATCH_STATS, TARGET,
    aligned, build_corpus, detail_frame, seed_split_deltas, split_brier_delta,
)

_FAMILY = FAMILY
_TARGET = TARGET
# K = 5 candidates x both directions x 2 corpora -- the cumulative selection surface.
_K_LIVE = len(_FAMILY) * 2 * 2          # = 20


def _nested_corners(base: pd.DataFrame) -> Tuple[float, str]:
    """Nested-CV on ONE corpus: select the best family member on INNER folds, score the
    FROZEN pick ONCE on the sealed outer fold. Returns (outer_brier_delta, selected_col).

    select_fn is handed ONLY inner game_ids (SelectSpy raises if it ever sees an outer
    game); it scores each candidate by inner-fold Brier-delta and returns the best column.
    score_fn then scores that FROZEN column on the sealed outer fold -- the score that
    flows forward is the sealed-outer-fold Brier-delta, NEVER a selection score.
    """
    recs = base.to_dict("records")
    by_gid = {str(r["game_id"]): r for r in recs}
    gids = list(by_gid.keys())

    def _delta_on(col: str, sel_gids: Sequence[str]) -> float:
        rows = [by_gid[g] for g in sel_gids if not pd.isna(by_gid[g][col])]
        if len(rows) < 200:
            return float("nan")
        sub = (pd.DataFrame(rows)
               .sort_values("game_id", kind="mergesort").reset_index(drop=True))
        return split_brier_delta(sub, col)

    def select_fn(inner_gids: Sequence[str]) -> str:
        best_col, best = _TARGET, -np.inf
        for c in _FAMILY:
            d = _delta_on(c, inner_gids)
            if np.isfinite(d) and d > best:
                best, best_col = d, c
        return best_col

    def score_fn(col: str, holdout_gids: Sequence[str]) -> float:
        # nested_cv minimizes the score; we return NEGATIVE Brier-delta so the sealed
        # fold's loss is minimal when the feature genuinely helps (one scored call).
        d = _delta_on(col, holdout_gids)
        return float(-d) if np.isfinite(d) else float("inf")

    res = select_then_score(select_fn, score_fn, gids, n_folds=5, holdout_fold=0)
    outer_delta = -res.outer_score if np.isfinite(res.outer_score) else float("nan")
    return float(outer_delta), str(res.selected_spec)


@dataclass
class SurvivorReport:
    target: str = _TARGET
    K: int = _K_LIVE
    eps_eff: float = 0.0
    nested_delta_a: float = float("nan")
    nested_delta_b: float = float("nan")
    nested_selected_a: str = ""
    nested_selected_b: str = ""
    gate_verdict: str = ""
    gate_layer: str = ""
    cross_a_to_b: Dict[str, Any] = field(default_factory=dict)
    cross_b_to_a: Dict[str, Any] = field(default_factory=dict)
    seed_mean: float = float("nan")
    seed_p10: float = float("nan")
    split_deltas: List[float] = field(default_factory=list)
    split_all_positive: bool = False
    null_rejects: bool = False
    null_fdr_hat: float = 1.0
    null_frozen: bool = True
    collinear_tau: float = DEFAULT_TAU
    collinear_reason: Optional[str] = None
    verdict: str = "INSUFFICIENT_DATA"
    deciding_stat: str = ""
    vs_close: str = "UNPROVEN -- CALIBRATION only (held-out home-win Brier), not edge"
    proposal_only: bool = True


def run(eps: float = DEFAULT_EPS, seeds: Sequence[int] = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
        splits: Sequence[float] = (0.4, 0.5, 0.6),
        matches: Optional[pd.DataFrame] = None,
        match_stats: Optional[pd.DataFrame] = None,
        n_nulls: int = 20) -> SurvivorReport:
    """Run the FULL 5-candidate family through the combo machinery; verdict for corners."""
    from domains.soccer.asof_discipline_features import build_asof_disc_frame
    if matches is None:
        matches = pd.read_parquet(MATCHES)
    if match_stats is None:
        match_stats = pd.read_parquet(MATCH_STATS)
    matches = matches.copy()
    matches["event_id"] = matches["event_id"].astype(str)
    layer = build_asof_disc_frame(match_stats)
    layer["event_id"] = layer["event_id"].astype(str)

    corp_a = build_corpus(CORPUS_A, matches, match_stats, layer)
    corp_b = build_corpus(CORPUS_B, matches, match_stats, layer)

    rep = SurvivorReport(eps_eff=eps_eff(eps, _K_LIVE))

    # ---- L1 nested-CV per corpus (selection INSIDE inner folds) -----------------
    rep.nested_delta_a, rep.nested_selected_a = _nested_corners(corp_a)
    rep.nested_delta_b, rep.nested_selected_b = _nested_corners(corp_b)

    # ---- collinear-with-base guard (corners vs the EW-Poisson base signal) -------
    al = aligned(corp_a, _TARGET)
    rep.collinear_reason = collinear_with_base_reason(
        al[_TARGET].to_numpy(float),
        {"logit_p_poisson": al["state_diff"].to_numpy(float)}, tau=rep.collinear_tau)

    # ---- the FULL combo gate for corners at the K-tightened bar ------------------
    det_a, det_b = detail_frame(corp_a, _TARGET), detail_frame(corp_b, _TARGET)
    ba = aligned(corp_a, _TARGET)[["game_id", "asof_idx", "state_diff",
                                   "frac_elapsed", "outcome"]]
    bb = aligned(corp_b, _TARGET)[["game_id", "asof_idx", "state_diff",
                                   "frac_elapsed", "outcome"]]
    v = gate_combo(_TARGET, ba, det_a, bb, det_b, combo_col="detail",
                   base_feature_cols={"logit_p_poisson": ba["state_diff"].to_numpy()},
                   parity_ok=True, eps=eps, K=_K_LIVE, n_corpora=2, tau=rep.collinear_tau)
    rep.gate_verdict, rep.gate_layer = v.verdict, v.layer
    rep.cross_a_to_b = dict(v.detail.get("a_to_b") or {})
    rep.cross_b_to_a = dict(v.detail.get("b_to_a") or {})

    # ---- seed-ensemble + multi-split stability (corpus A, the survivor's home) ---
    ss = seed_split_deltas(corp_a, _TARGET, seeds, splits)
    seed_arr = np.asarray(ss["seed"], float)
    if seed_arr.size:
        rep.seed_mean = float(seed_arr.mean())
        rep.seed_p10 = float(np.percentile(seed_arr, 10))
    rep.split_deltas = [round(d, 7) for d in ss["split"]]
    rep.split_all_positive = bool(ss["split"]) and all(d > 0 for d in ss["split"])

    # ---- planted-null FDR through the IDENTICAL gate -----------------------------
    fdr = run_family_nulls("soccer_discipline", n=max(20, int(n_nulls)),
                           eps=eps, K=_K_LIVE)
    rep.null_rejects = bool(fdr.n_shipped == 0)
    rep.null_fdr_hat, rep.null_frozen = float(fdr.fdr_hat), bool(fdr.frozen)

    rep.verdict, rep.deciding_stat = _decide(rep)
    return rep


def _decide(r: SurvivorReport) -> Tuple[str, str]:
    """The honest verdict. The bar is NEVER weakened; any failed layer downgrades."""
    if r.collinear_reason is not None:
        return "DOWNGRADE_TO_ARTIFACT", f"collinear_with_base: {r.collinear_reason}"
    if not r.null_rejects or r.null_frozen:
        return ("DOWNGRADE_TO_ARTIFACT",
                f"planted-null FDR FROZEN (fdr_hat={r.null_fdr_hat}) -> family untrustworthy")
    if r.gate_verdict != SHIP:
        return ("DOWNGRADE_TO_ARTIFACT",
                f"combo_gate={r.gate_verdict}@{r.gate_layer} (FWER-tightened eps_eff="
                f"{r.eps_eff:.5f}, K={r.K}) -- did not clear the cross-corpus bar")
    if not (np.isfinite(r.nested_delta_a) and np.isfinite(r.nested_delta_b)
            and r.nested_delta_a > 0 and r.nested_delta_b > 0):
        return ("DOWNGRADE_TO_ARTIFACT",
                f"nested-CV sealed-fold delta not +ve both corpora "
                f"(A={r.nested_delta_a}, B={r.nested_delta_b})")
    if not (np.isfinite(r.seed_p10) and r.seed_p10 >= 0.0):
        return "DOWNGRADE_TO_ARTIFACT", f"seed p10={r.seed_p10} < 0 (single-seed artifact)"
    if not r.split_all_positive:
        return ("DOWNGRADE_TO_ARTIFACT",
                f"multi-split not all +ve ({r.split_deltas})")
    return ("CONFIRMED_SURVIVOR",
            f"cleared L0..L6 @ eps_eff={r.eps_eff:.5f} K={r.K}; nested A/B +ve; "
            f"seed p10={r.seed_p10:.6f}; nulls reject (fdr_hat={r.null_fdr_hat})")


def summarize(r: SurvivorReport) -> str:
    lines = [
        "SURVIVOR-SCRUTINY: diff_corners_asof in family {corners,fouls,yellow,red,sot_ratio}",
        f"nested-CV sealed-outer-fold Brier-delta: A(E0/E1)={r.nested_delta_a:+.6f} "
        f"(picked {r.nested_selected_a}); B(SP1/I1)={r.nested_delta_b:+.6f} "
        f"(picked {r.nested_selected_b})",
        f"FWER-tightened bar: eps_eff={r.eps_eff:.5f}  K={r.K}  "
        f"combo_gate={r.gate_verdict}@{r.gate_layer}",
        f"  A->B: {r.cross_a_to_b.get('brier_delta')} (DM p {r.cross_a_to_b.get('dm_p')}, "
        f"beats={r.cross_a_to_b.get('prior_beats_base')})",
        f"  B->A: {r.cross_b_to_a.get('brier_delta')} (DM p {r.cross_b_to_a.get('dm_p')}, "
        f"beats={r.cross_b_to_a.get('prior_beats_base')})",
        f"seed-ensemble Brier-delta: mean={r.seed_mean:+.6f}  p10={r.seed_p10:+.6f}",
        f"multi-split stability ({len(r.split_deltas)} splits): {r.split_deltas}  "
        f"all_positive={r.split_all_positive}",
        f"planted-null FDR: nulls_reject={r.null_rejects}  fdr_hat={r.null_fdr_hat}  "
        f"frozen={r.null_frozen}",
        f"collinearity tau={r.collinear_tau} -> "
        f"{'OK (orthogonal to base)' if r.collinear_reason is None else r.collinear_reason}",
        f"VERDICT: {r.verdict}  | deciding: {r.deciding_stat}",
        f"vs_close: {r.vs_close}  (proposal_only={r.proposal_only}; no $/flag/registry)",
    ]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    print(summarize(run()))
    return 0


__all__ = ["SurvivorReport", "run", "summarize", "main",
           "SHIP", "_FAMILY", "_TARGET", "_K_LIVE"]

if __name__ == "__main__":
    raise SystemExit(main())
