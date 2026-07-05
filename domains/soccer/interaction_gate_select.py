"""domains.soccer.interaction_gate_select -- A1-S L1/L3/planted-null helpers.

L1 sealed-holdout SELECTION between S1 (soccer_xg_pace_sot_regime) and S2
(soccer_xg_supremacy_sot_confirm) -- one frozen spec, never both surviving
(PREREG_AMENDMENT_A1_2026-07-05.md "L1/L3 per V1 JUDGMENT-4"). L3 >=5
bootstrap-refit seed-stability on the SELECTED spec. Planted-null permutes
the SOT columns WITHIN-league so the regime/agree indicator + product terms
(recomputed FROM the permuted columns) are destroyed while xG + base stay
intact. Split out of interaction_gate.py purely to stay under the 300-LOC
cap (interaction_gate.py owns run()/main()/per-league orchestration; this
module owns the L1/L3/null MECHANICS that plug into judge_stack_family).

Calibration only; NO $/edge. ASCII; <=300 LOC.
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

from domains.soccer import interaction_gate_math as gm
from scripts.platformkit.combo import stack_fit as sf
from scripts.platformkit.combo.stack_gate_pregame import StackRow

CANDIDATES: Tuple[str, ...] = ("S1", "S2")


def fit_and_score_league(df: pd.DataFrame, cand: str) -> List[StackRow]:
    """Expanding-window mid-split (TRAIN=first half); NO reselect at the seam.
    Identical shape to home_sot_replication_gate.fit_and_score_league."""
    splits = sf.expanding_window_splits(len(df), initial_train_frac=0.5, n_folds=1)
    tr_idx, te_idx = splits[0].train_idx, splits[0].test_idx
    train, test = df.iloc[tr_idx], df.iloc[te_idx]
    base_fit = gm.fit_base(train)
    p_base_test = gm.score_base(test, base_fit)
    if cand == "S1":
        cand_fit, cand_std, cand_extra = gm.s1_fit(train)
        p_cand = gm.s1_score(test, cand_fit, cand_std, cand_extra, p_base_test)
        raw1, raw2 = gm.s1_raw_ingredients(test)
    else:
        cand_fit, cand_std = gm.s2_fit(train)
        p_cand = gm.s2_score(test, cand_fit, cand_std, p_base_test)
        raw1, raw2 = gm.s2_raw_ingredients(test)
    y = test["target_over25"].to_numpy(float)
    eids = test["event_id"].astype(str).to_numpy()
    return [StackRow(event_id=str(eids[i]), y=float(y[i]), p_base=float(p_base_test[i]),
                     p_candidate=float(p_cand[i]), added_raw=(float(raw1[i]), float(raw2[i])))
            for i in range(len(test))]


def select_fn_between_s1_s2(league_frames: Dict[str, Dict[str, pd.DataFrame]]):
    """L1 sealed-holdout SELECTION closure -- decides S1 vs S2 using ONLY the
    game_ids the nested-CV harness hands it (inner folds only; never the
    frozen outer holdout). Picks whichever candidate has the better mean
    sealed-INNER Brier delta across all leagues' rows restricted to those
    inner ids."""

    def _select(inner_game_ids: Sequence[str]) -> str:
        inner_set = set(str(g) for g in inner_game_ids)
        best_cand, best_delta = "S1", -np.inf
        for cand in CANDIDATES:
            deltas = []
            for lg, lf in league_frames[cand].items():
                rows = fit_and_score_league(lf, cand)
                held = [r for r in rows if r.event_id in inner_set]
                if not held:
                    continue
                pb = np.array([r.p_base for r in held])
                pc = np.array([r.p_candidate for r in held])
                yy = np.array([r.y for r in held])
                deltas.append(sf.brier(pb, yy) - sf.brier(pc, yy))
            mean_delta = float(np.mean(deltas)) if deltas else -np.inf
            if mean_delta > best_delta:
                best_cand, best_delta = cand, mean_delta
        return best_cand

    return _select


def score_fn_for_selected(rows_by_cand: Dict[str, List[StackRow]]):
    """score_fn scores whichever spec select_fn picked, on the FROZEN outer
    holdout ONLY (mirrors home_sot_replication_gate._make_nested_cv_fns)."""

    def _score(spec: str, holdout_game_ids: Sequence[str]) -> float:
        by_id = {r.event_id: r for r in rows_by_cand[spec]}
        held = [by_id[g] for g in holdout_game_ids if g in by_id]
        if not held:
            return float("nan")
        p_base = np.array([r.p_base for r in held])
        p_cand = np.array([r.p_candidate for r in held])
        y = np.array([r.y for r in held])
        return sf.brier(p_base, y) - sf.brier(p_cand, y)

    return _score


def seed_stability_p10(df: pd.DataFrame, cand: str) -> float:
    """L3: >=5 bootstrap refits of TRAIN rows; p10 of the held-out stack-vs-
    base delta (mirrors home_sot_replication_gate._seed_stability_p10)."""
    splits = sf.expanding_window_splits(len(df), initial_train_frac=0.5, n_folds=1)
    tr_idx, te_idx = splits[0].train_idx, splits[0].test_idx
    train_full, test = df.iloc[tr_idx].reset_index(drop=True), df.iloc[te_idx]

    def _one(rng: np.random.Generator) -> float:
        resampled = train_full.iloc[sf.bootstrap_resample_rows(len(train_full), rng)]
        base_fit = gm.fit_base(resampled)
        p_base = gm.score_base(test, base_fit)
        if cand == "S1":
            cand_fit, cand_std, cand_extra = gm.s1_fit(resampled)
            p_cand = gm.s1_score(test, cand_fit, cand_std, cand_extra, p_base)
        else:
            cand_fit, cand_std = gm.s2_fit(resampled)
            p_cand = gm.s2_score(test, cand_fit, cand_std, p_base)
        y = test["target_over25"].to_numpy(float)
        return sf.brier(p_base, y) - sf.brier(p_cand, y)

    deltas = sf.bootstrap_refit_deltas(_one, n_refits=5, base_seed=71)
    return float(np.percentile(deltas, 10))


def plant_null_fn(league_frames: Dict[str, pd.DataFrame], cand: str):
    """A1 planted-null: permute the SOT columns WITHIN-league; the regime/
    agree indicator + product terms are RECOMPUTED FROM THE PERMUTED columns
    (xG and base columns stay intact) so the interaction term is destroyed
    while a spurious main-effect leak cannot survive. Ships iff ANY league's
    shuffled stack beats base on its own test half."""

    def _plant(rng: np.random.Generator) -> bool:
        any_ship = False
        for lg, lf in league_frames.items():
            shuf = lf.copy()
            perm = rng.permutation(len(shuf))
            shuf["home_sot_for_l10"] = shuf["home_sot_for_l10"].to_numpy()[perm]
            shuf["away_sot_for_l10"] = shuf["away_sot_for_l10"].to_numpy()[perm]
            null_rows = fit_and_score_league(shuf, cand)
            if not null_rows:
                continue
            br_b = sf.brier(np.array([r.p_base for r in null_rows]),
                            np.array([r.y for r in null_rows]))
            br_c = sf.brier(np.array([r.p_candidate for r in null_rows]),
                            np.array([r.y for r in null_rows]))
            any_ship = any_ship or bool(br_c < br_b)
        return any_ship

    return _plant


__all__ = ["CANDIDATES", "fit_and_score_league", "select_fn_between_s1_s2",
           "score_fn_for_selected", "seed_stability_p10", "plant_null_fn"]
