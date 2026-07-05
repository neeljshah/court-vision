"""scripts.platformkit.combo.batch_gate -- one-process declarative batch runner.

`run_batch(candidate_specs, sport)`: loads the cached corpus (corpus_cache),
applies the null_floor prescreen, and routes survivors through
stack_gate_pregame.judge_stack_family with the family's pinned K/eps (the
CALLER supplies K_cum from its own prereg/amendment -- this module NEVER
hardcodes a bar; it imports fwer_budget only to compute eps_eff from the
caller's K_cum for the prescreen-reject verdict's caveats). Emits ALL verdict
JSONs + reject_ledger rows in ONE process.

A candidate spec is a DECLARATIVE dict:
  {"name": str, "features": [column names in the cached corpus], "family": str,
   "k_cum": int, "corpus_units": [unit names to use as cross-corpus pairs] (optional,
   default = every unit present)}
No fitting logic of its own -- pure orchestration over stack_fit (feature
assembly + fit/score) and stack_gate_pregame (judge), generalized to an
arbitrary feature-name list.

Calibration, not edge. NO $/ROI anywhere. numpy + pandas + stdlib only. ASCII.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.combo import stack_fit as sf
from scripts.platformkit.combo.batch_gate_rules import plant_null_for_spec, remap_replicated_weak
from scripts.platformkit.combo.corpus_cache import load_gate_corpus
from scripts.platformkit.combo.fwer_budget import eps_eff
from scripts.platformkit.combo.nested_cv import select_then_score
from scripts.platformkit.combo.null_floor import prescreen_verdict
from scripts.platformkit.combo.stack_gate_pregame import StackRow, judge_stack_family
from scripts.platformkit.reject_ledger import record

_REPO = Path(__file__).resolve().parents[3]
_OUT_DIR = _REPO / "data" / "cache" / "combo" / "batch_verdicts"


@dataclass(frozen=True)
class CandidateSpec:
    name: str
    features: Sequence[str]
    family: str
    k_cum: int
    corpus_units: Optional[Sequence[str]] = None
    same_source_pair: bool = False  # caller-declared: True => SHIP remapped to REPLICATED_WEAK
    components: Optional[Mapping[str, Sequence[str]]] = None  # product feature -> underlying cols


def _spec_from_dict(d: Dict[str, Any]) -> CandidateSpec:
    return CandidateSpec(name=d["name"], features=tuple(d["features"]), family=d["family"],
                         k_cum=int(d["k_cum"]), corpus_units=tuple(d["corpus_units"])
                         if d.get("corpus_units") else None,
                         same_source_pair=bool(d.get("same_source_pair", False)),
                         components={k: tuple(v) for k, v in d["components"].items()}
                         if d.get("components") else None)


def _fit_and_score_unit(unit_df: pd.DataFrame, features: Sequence[str]) -> List[StackRow]:
    """Expanding-window mid-split fit: base=[1, logit(p_base)]; candidate adds
    z(each feature). NO reselect at the seam. Mirrors every wave-1 runner."""
    df = unit_df[unit_df["p_base"].notna() & unit_df["y"].notna()].reset_index(drop=True)
    splits = sf.expanding_window_splits(len(df), initial_train_frac=0.5, n_folds=1)
    tr_idx, te_idx = splits[0].train_idx, splits[0].test_idx
    train, test = df.iloc[tr_idx], df.iloc[te_idx]

    base_logit_tr = sf.logit(train["p_base"].to_numpy(float))
    y_tr = train["y"].to_numpy(float)
    base_fit = sf.fit_logistic(sf.build_design([base_logit_tr]), y_tr)

    added_tr_raw = train[list(features)].to_numpy(float)
    added_std = sf.fit_standardizer(added_tr_raw)
    added_tr_z = sf.standardize(added_tr_raw, added_std)
    X_tr = sf.build_design([base_logit_tr] + [added_tr_z[:, i] for i in range(len(features))])
    cand_fit = sf.fit_logistic(X_tr, y_tr)

    base_logit_te = sf.logit(test["p_base"].to_numpy(float))
    p_base = sf.predict_proba(sf.build_design([base_logit_te]), base_fit.weights)
    added_te_raw = test[list(features)].to_numpy(float)
    added_te_z = sf.standardize(added_te_raw, added_std)
    X_te = sf.build_design([base_logit_te] + [added_te_z[:, i] for i in range(len(features))])
    p_cand_raw = sf.predict_proba(X_te, cand_fit.weights)
    raw_cols = [test[c].to_numpy(float) for c in features]
    p_cand = sf.score_with_fallback(raw_cols, p_base, p_cand_raw)

    rows: List[StackRow] = []
    for i in range(len(test)):
        rows.append(StackRow(
            event_id=str(test.iloc[i]["event_id"]), y=float(test.iloc[i]["y"]),
            p_base=float(p_base[i]), p_candidate=float(p_cand[i]),
            added_raw=tuple(float(test.iloc[i][c]) for c in features)))
    return rows


def _prescreen_delta(rows: Sequence[StackRow]) -> float:
    if not rows:
        return float("nan")
    p_base = np.array([r.p_base for r in rows])
    p_cand = np.array([r.p_candidate for r in rows])
    y = np.array([r.y for r in rows])
    return sf.brier(p_base, y) - sf.brier(p_cand, y)


def _rows_delta_on_games(by_id: Dict[str, StackRow], game_ids: Sequence[str]) -> float:
    return _prescreen_delta([by_id[g] for g in game_ids if g in by_id])


def _nested_cv_fns(rows: Sequence[StackRow], cand_name: str):
    """Single-candidate select/score -- `_select` is a constant since there is
    nothing else to choose among (multi-candidate real selection: see below)."""
    by_id = {r.event_id: r for r in rows}

    def _select(inner_game_ids):
        return cand_name

    def _score(spec, holdout_game_ids) -> float:
        return _rows_delta_on_games(by_id, holdout_game_ids)

    return _select, _score


def _nested_cv_fns_multi(rows_by_candidate: Mapping[str, Sequence[StackRow]], judged_name: str):
    """REAL cross-candidate L1 selection: `_select` argmaxes EVERY candidate's
    inner-fold Brier-delta-vs-base (an actual choice, never a constant),
    scored ONLY on the frozen outer holdout (select_then_score's contract). If
    the shared pick != `judged_name`, `_score` returns NaN -- judge_stack_
    family's `outer_score<0.0` gate treats NaN as failing, an honest L1 REJECT
    for the candidate that lost selection, never a silent pass-through."""
    by_id_by_cand = {name: {r.event_id: r for r in rs} for name, rs in rows_by_candidate.items()}

    def _select(inner_game_ids: Sequence[str]) -> str:
        deltas = {name: _rows_delta_on_games(by_id, inner_game_ids)
                 for name, by_id in by_id_by_cand.items()}
        finite = {n: d for n, d in deltas.items() if np.isfinite(d)}
        return max(finite, key=finite.get) if finite else next(iter(by_id_by_cand))

    def _score(spec: str, holdout_game_ids: Sequence[str]) -> float:
        if spec != judged_name:
            return float("nan")  # this candidate lost the selection -- honest L1 REJECT
        return _rows_delta_on_games(by_id_by_cand[spec], holdout_game_ids)

    return _select, _score


def _seed_stability_p10(unit_df: pd.DataFrame, features: Sequence[str], seed: int = 99) -> float:
    df = unit_df[unit_df["p_base"].notna() & unit_df["y"].notna()].reset_index(drop=True)
    splits = sf.expanding_window_splits(len(df), initial_train_frac=0.5, n_folds=1)
    tr_idx, te_idx = splits[0].train_idx, splits[0].test_idx
    train_full, test = df.iloc[tr_idx].reset_index(drop=True), df.iloc[te_idx]

    def _one(rng: np.random.Generator) -> float:
        resampled = train_full.iloc[sf.bootstrap_resample_rows(len(train_full), rng)]
        base_logit_tr = sf.logit(resampled["p_base"].to_numpy(float))
        y_tr = resampled["y"].to_numpy(float)
        base_fit = sf.fit_logistic(sf.build_design([base_logit_tr]), y_tr)
        added_raw = resampled[list(features)].to_numpy(float)
        std = sf.fit_standardizer(added_raw)
        added_z = sf.standardize(added_raw, std)
        cand_fit = sf.fit_logistic(
            sf.build_design([base_logit_tr] + [added_z[:, i] for i in range(len(features))]), y_tr)
        base_logit_te = sf.logit(test["p_base"].to_numpy(float))
        p_base = sf.predict_proba(sf.build_design([base_logit_te]), base_fit.weights)
        added_te_z = sf.standardize(test[list(features)].to_numpy(float), std)
        p_cand_raw = sf.predict_proba(
            sf.build_design([base_logit_te] + [added_te_z[:, i] for i in range(len(features))]),
            cand_fit.weights)
        raw_cols = [test[c].to_numpy(float) for c in features]
        p_cand = sf.score_with_fallback(raw_cols, p_base, p_cand_raw)
        y = test["y"].to_numpy(float)
        return sf.brier(p_base, y) - sf.brier(p_cand, y)

    deltas = sf.bootstrap_refit_deltas(_one, n_refits=5, base_seed=seed)
    return float(np.percentile(deltas, 10))


def run_batch(candidate_specs: Sequence[Dict[str, Any]], sport: str,
             write_ledger: bool = True) -> Dict[str, Dict[str, Any]]:
    """Load cached corpus; prescreen each spec; judge survivors; emit verdicts.

    Returns {candidate_name: verdict_dict}. verdict_dict for a prescreen
    reject has verdict='REJECT', layer='FDR_PRESCREEN'; survivors carry the
    full judge_stack_family verdict shape. L1 selection across >=2 surviving
    specs sharing a primary corpus_unit is a REAL argmax choice (see
    `_nested_cv_fns_multi`); a lone survivor falls back to the single-
    candidate selector (nothing to choose among).
    """
    corpus = load_gate_corpus(sport)
    units = sorted(corpus["corpus_unit"].dropna().unique().tolist())
    results: Dict[str, Dict[str, Any]] = {}

    # Pass 1: prescreen every spec; collect PROCEED survivors' fitted rows.
    survivors: Dict[str, CandidateSpec] = {}
    rows_per_unit_by_spec: Dict[str, Dict[str, List[StackRow]]] = {}
    primary_unit_by_spec: Dict[str, str] = {}
    for raw_spec in candidate_specs:
        spec = _spec_from_dict(raw_spec)
        use_units = list(spec.corpus_units) if spec.corpus_units else units
        use_units = [u for u in use_units if u in units]
        if len(use_units) < 2:
            v = {"verdict": "NOT_TESTABLE", "reason": "fewer than 2 corpus_units available",
                "layer": "L4", "proposal_only": True}
            results[spec.name] = v
            if write_ledger:
                record(sport, f"{spec.family}__{spec.name}", v["verdict"], v["reason"],
                      source="funnel_gate", metrics={"layer": v["layer"]})
            continue

        rows_per_unit = {u: _fit_and_score_unit(corpus[corpus["corpus_unit"] == u], spec.features)
                         for u in use_units}
        primary_unit = use_units[0]
        primary_rows = rows_per_unit[primary_unit]
        primary_delta = _prescreen_delta(primary_rows)

        try:
            n_extra = len(spec.features)
            pre = prescreen_verdict(sport, primary_unit, n_extra, primary_delta)
        except (FileNotFoundError, KeyError):
            pre = "PROCEED"  # no floor cached -- never block on a missing prescreen table

        if pre == "REJECT":
            eps = eps_eff(0.05, spec.k_cum)
            v = {"verdict": "REJECT", "layer": "FDR_PRESCREEN",
                "reason": f"prescreen: held-out delta {primary_delta:.6f} <= matched noise-floor "
                          f"p99 on corpus_unit={primary_unit!r}; full ceremony skipped",
                "detail": {"eps_eff": eps, "primary_unit": primary_unit, "delta": primary_delta},
                "proposal_only": True}
            results[spec.name] = v
            if write_ledger:
                record(sport, f"{spec.family}__{spec.name}", v["verdict"], v["reason"],
                      source="funnel_gate", metrics={"layer": v["layer"]})
            continue

        survivors[spec.name] = spec
        rows_per_unit_by_spec[spec.name] = rows_per_unit
        primary_unit_by_spec[spec.name] = primary_unit

    # Pass 2: ABOVE the floor gains nothing -- full ceremony is mandatory. Group
    # survivors sharing a primary_unit so the L1 selector can REALLY choose among them.
    by_primary_unit: Dict[str, List[str]] = {}
    for name, pu in primary_unit_by_spec.items():
        by_primary_unit.setdefault(pu, []).append(name)

    for spec_name, spec in survivors.items():
        rows_per_unit = rows_per_unit_by_spec[spec_name]
        primary_unit = primary_unit_by_spec[spec_name]
        primary_rows = rows_per_unit[primary_unit]
        game_ids = [r.event_id for r in primary_rows]
        cohort = by_primary_unit[primary_unit]
        if len(cohort) >= 2:
            rows_by_cand = {n: rows_per_unit_by_spec[n][primary_unit] for n in cohort}
            nested_select_fn, nested_score_fn = _nested_cv_fns_multi(rows_by_cand, spec_name)
        else:
            nested_select_fn, nested_score_fn = _nested_cv_fns(primary_rows, spec_name)
        # L0 compares vs `first["added_raw"]` = the TEST-split rows only
        # (StackRow.added_raw comes from `test` in _fit_and_score_unit) --
        # base_feature_cols MUST match that same slice, else l0_guards sees a
        # shape mismatch and every candidate REJECTs at L0 regardless of real
        # collinearity (fixed: was previously the full-unit-length slice).
        primary_df = corpus[corpus["corpus_unit"] == primary_unit]
        primary_df = primary_df[primary_df["p_base"].notna() & primary_df["y"].notna()]
        primary_te_idx = sf.expanding_window_splits(len(primary_df), 0.5, 1)[0].test_idx
        base_logit_primary = sf.logit(primary_df["p_base"].to_numpy(float))[primary_te_idx]

        verdict = judge_stack_family(
            name=spec_name, corpora=list(rows_per_unit.values()),
            corpus_labels=list(rows_per_unit.keys()),
            base_feature_cols={"base_logit": base_logit_primary},
            k_cum=spec.k_cum, n_corpora_available=len(rows_per_unit),
            nested_cv_select_fn=nested_select_fn, nested_cv_score_fn=nested_score_fn,
            nested_cv_game_ids=game_ids,
            planted_null_fn=lambda rng, u=primary_unit, f=spec.features, c=spec.components:
                plant_null_for_spec(corpus[corpus["corpus_unit"] == u], f, c, rng,
                                    _fit_and_score_unit, _prescreen_delta),
            seed_stability_p10=_seed_stability_p10(corpus[corpus["corpus_unit"] == primary_unit],
                                                   spec.features),
        )
        if spec.components is not None and any(f not in spec.components for f in spec.features):
            verdict.caveats.append(
                "clause 4 (PREREG_AMENDMENT_A2): components declared for some but not all "
                "features -- undeclared features used the direct-permute-the-column fallback.")
        verdict = remap_replicated_weak(verdict, spec.same_source_pair)
        results[spec.name] = verdict.to_dict()
        if write_ledger:
            record(sport, f"{spec.family}__{spec.name}", verdict.verdict, verdict.reason,
                  source="funnel_gate", metrics={"layer": verdict.layer, "vs_close": verdict.vs_close})

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUT_DIR / f"{sport}_batch_{int(time.time())}.json"
    out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    return results


__all__ = ["CandidateSpec", "run_batch"]
