"""domains.tennis.interaction_gate -- Family A1-T (tennis_interactions_v1) runner.

PREREG_AMENDMENT_A1_2026-07-05.md Family A1-T: does adding a SURFACE-HOLD
INTERACTION term to the 1-feature pregame BASE [1, logit(p_elo)] improve
calibration? Two candidates, K_cum=2 for the whole family (K_prior=0):

  T1 tennis_surface_hold_regime: base + z(blended_hold_diff) +
     z(surface_hold_diff - blended_hold_diff)  (surface-specific residual
     over the blended overall-hold diff).
  T2 tennis_surface_serve_return_gap: base + z(surface_diff) +
     z(surface_diff * low_regime), low_regime = 1 iff BOTH players' surface
     hold% is below the TRAIN-ONLY tour-surface median.

Feature math + corpus assembly live in interaction_gate_math.py (LOC-split,
mirrors soccer's asof_reclaim_gate_math/_run precedent); this module owns
orchestration only: nested-CV binding, planted-null, seed-stability, and the
top-level run()/main()/CLI that judges both candidates via
stack_gate_pregame.judge_stack_family.

BASE Elo + row universe reused EXACTLY from asof_reclaim_gate (same
walk_forward_elo call, same matches.parquet/wta_matches.parquet). Rows
missing a surface-hold ingredient (Carpet/Unknown surface, or insufficient
prior matches) fall back to the base probability via
stack_fit.score_with_fallback, so base and candidate score IDENTICAL rows.

CORPORA: ATP (asof_hold.parquet universe, 30616) and WTA (asof_hold_wta.parquet
universe, 11270) -- genuinely independent tours, judged both directions.

CANDIDATE-ONLY / DEFAULT-OFF: reads parquets additively; touches no adapter,
predictor, or flag. NO $ / edge anywhere; a REJECT is an honest success.
No src.*/kernel.* imports.

CLI: python -m domains.tennis.interaction_gate
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.tennis.interaction_gate_math import (  # noqa: E402
    added_raw_for, build_corpus_frame, close_brier_for_frame, fit_base,
    fit_candidate, score_base, score_candidate,
)
from scripts.platformkit.combo import stack_fit as sf  # noqa: E402
from scripts.platformkit.combo.stack_gate_pregame import (  # noqa: E402
    StackRow, judge_stack_family,
)
from scripts.platformkit.reject_ledger import record  # noqa: E402

_ATP_MATCHES = _REPO / "data/domains/tennis/matches.parquet"
_ATP_HOLD = _REPO / "data/domains/tennis/asof_hold.parquet"
_WTA_MATCHES = _REPO / "data/domains/tennis/wta_matches.parquet"
_WTA_HOLD = _REPO / "data/domains/tennis/asof_hold_wta.parquet"
_VERDICT_OUT = _REPO / "data/domains/tennis/tennis_interactions_v1_verdict.json"

K_CUM = 2                        # T1 + T2, both new this cycle (K_prior=0)
CANDIDATES = ("tennis_surface_hold_regime", "tennis_surface_serve_return_gap")


def fit_and_score_corpus(df, candidate: str) -> List[StackRow]:
    """Expanding-window mid-split fit (TRAIN=first half); score held-out second half.

    T2's regime median is computed on TRAIN rows only, inside this split --
    never pooled with test. NO reselect at the seam.
    """
    splits = sf.expanding_window_splits(len(df), initial_train_frac=0.5, n_folds=1)
    tr_idx, te_idx = splits[0].train_idx, splits[0].test_idx
    train, test = df.iloc[tr_idx], df.iloc[te_idx]

    added_train, added_test = added_raw_for(candidate, train, test)
    base_fit = fit_base(train)
    valid_tr = np.all(np.isfinite(added_train), axis=1)
    cand_fit, added_std = fit_candidate(train[valid_tr.tolist()], added_train[valid_tr])

    p_base = score_base(test, base_fit)
    p_cand = score_candidate(test, cand_fit, added_std, added_test, p_base)

    rows: List[StackRow] = []
    for i in range(len(test)):
        rows.append(StackRow(
            event_id=str(test.iloc[i]["event_id"]), y=float(test.iloc[i]["target_p1_win"]),
            p_base=float(p_base[i]), p_candidate=float(p_cand[i]),
            added_raw=tuple(float(v) for v in added_test[i])))
    return rows


# --------------------------------------------------------------------------- #
# L1 nested-CV binding (deterministic single-spec select, real sealed score)
# --------------------------------------------------------------------------- #

def _make_nested_cv_fns(rows: Sequence[StackRow], cand_name: str):
    by_id = {r.event_id: r for r in rows}

    def _select(inner_game_ids: Sequence[str]):
        return cand_name

    def _score(spec, holdout_game_ids: Sequence[str]) -> float:
        held = [by_id[g] for g in holdout_game_ids if g in by_id]
        if not held:
            return float("nan")
        p_base = np.array([r.p_base for r in held])
        p_cand = np.array([r.p_candidate for r in held])
        y = np.array([r.y for r in held])
        return sf.brier(p_base, y) - sf.brier(p_cand, y)

    return _select, _score


def _seed_stability_p10(df, candidate: str) -> float:
    """L3: >=5 bootstrap-refits of TRAIN rows; p10 of held-out stack-vs-base delta."""
    splits = sf.expanding_window_splits(len(df), initial_train_frac=0.5, n_folds=1)
    tr_idx, te_idx = splits[0].train_idx, splits[0].test_idx
    train_full, test = df.iloc[tr_idx].reset_index(drop=True), df.iloc[te_idx]

    def _one(rng: np.random.Generator) -> float:
        resampled = train_full.iloc[sf.bootstrap_resample_rows(len(train_full), rng)]
        added_tr, added_te = added_raw_for(candidate, resampled, test)
        base_fit = fit_base(resampled)
        valid = np.all(np.isfinite(added_tr), axis=1)
        cand_fit, added_std = fit_candidate(resampled[valid.tolist()], added_tr[valid])
        p_base = score_base(test, base_fit)
        p_cand = score_candidate(test, cand_fit, added_std, added_te, p_base)
        y = test["target_p1_win"].to_numpy(float)
        return sf.brier(p_base, y) - sf.brier(p_cand, y)

    deltas = sf.bootstrap_refit_deltas(_one, n_refits=5, base_seed=99)
    return float(np.percentile(deltas, 10))


def _plant_null(df, candidate: str, rng: np.random.Generator) -> bool:
    """A1 PLANTED-NULL: permute the SURFACE-hold columns within-tour (blended
    hold + Elo intact); regime/residual recomputed from the PERMUTED columns."""
    shuffled = df.copy()
    surf_cols = [f"{p}_hold_pct_{s}_asof" for p in ("p1", "p2")
                for s in ("hard", "clay", "grass")]
    for c in surf_cols:
        if c in shuffled.columns:
            shuffled[c] = rng.permutation(shuffled[c].to_numpy())
    null_rows = fit_and_score_corpus(shuffled, candidate)
    if not null_rows:
        return False
    br_b = sf.brier(np.array([r.p_base for r in null_rows]), np.array([r.y for r in null_rows]))
    br_c = sf.brier(np.array([r.p_candidate for r in null_rows]), np.array([r.y for r in null_rows]))
    return bool(br_c < br_b)


# --------------------------------------------------------------------------- #
# Top-level: judge both candidates across ATP<->WTA
# --------------------------------------------------------------------------- #

def run() -> Dict[str, object]:
    atp = build_corpus_frame(_ATP_MATCHES, _ATP_HOLD)
    wta = build_corpus_frame(_WTA_MATCHES, _WTA_HOLD)
    close_atp, cov_atp = close_brier_for_frame(atp)
    close_wta, cov_wta = close_brier_for_frame(wta)

    results: Dict[str, object] = {
        "atp_n": len(atp), "wta_n": len(wta),
        "close_brier_atp": close_atp, "close_cov_atp": cov_atp,
        "close_brier_wta": close_wta, "close_cov_wta": cov_wta,
    }
    for cand_name in CANDIDATES:
        rows_atp = fit_and_score_corpus(atp, cand_name)
        rows_wta = fit_and_score_corpus(wta, cand_name)
        game_ids = [r.event_id for r in rows_atp]
        nested_select_fn, nested_score_fn = _make_nested_cv_fns(rows_atp, cand_name)

        te_idx_atp = sf.expanding_window_splits(len(atp), 0.5, 1)[0].test_idx
        base_elo_logit_atp = sf.logit(atp["p_elo"].to_numpy(float))[te_idx_atp]

        stack_brier_vs_close = sf.brier(
            np.array([r.p_candidate for r in rows_atp] + [r.p_candidate for r in rows_wta]),
            np.array([r.y for r in rows_atp] + [r.y for r in rows_wta]))
        close_combined = close_atp if np.isfinite(close_atp) else close_wta

        verdict = judge_stack_family(
            name=cand_name, corpora=[rows_atp, rows_wta], corpus_labels=["ATP", "WTA"],
            base_feature_cols={"elo_logit": base_elo_logit_atp},
            k_cum=K_CUM, n_corpora_available=2,
            nested_cv_select_fn=nested_select_fn, nested_cv_score_fn=nested_score_fn,
            nested_cv_game_ids=game_ids,
            planted_null_fn=lambda rng, c=cand_name: _plant_null(atp, c, rng),
            close_brier=close_combined if np.isfinite(close_combined) else None,
            stack_brier_vs_close=stack_brier_vs_close,
            seed_stability_p10=_seed_stability_p10(atp, cand_name),
        )
        results[cand_name] = verdict.to_dict()
        record("tennis", "tennis_interactions_v1__" + cand_name, verdict.verdict, verdict.reason,
              source="funnel_gate",
              metrics={"layer": verdict.layer, "vs_close": verdict.vs_close})
    return results


def main() -> int:
    import json
    res = run()
    _VERDICT_OUT.parent.mkdir(parents=True, exist_ok=True)
    _VERDICT_OUT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print("=" * 72)
    print("TENNIS INTERACTIONS v1 -- Family A1-T (tennis_interactions_v1)")
    print("=" * 72)
    print(f"atp_n={res['atp_n']} wta_n={res['wta_n']} "
         f"close_brier_atp={res['close_brier_atp']} close_brier_wta={res['close_brier_wta']}")
    for name in CANDIDATES:
        v = res[name]
        print(f"\n{name}: verdict={v['verdict']} layer={v['layer']} "
             f"vs_close={v['vs_close']}\n  reason={v['reason']}")
    print("\n(REJECT = honest success; calibration only; no edge ever claimed.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
