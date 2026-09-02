"""scripts.platformkit.combo.null_floor -- pure-noise held-out delta floor.

Per (sport, corpus_unit, n_extra_params in 1..MAX_EXTRA_PARAMS): fit M=40 permuted-noise
candidates through the IDENTICAL stack_fit path (same expanding-window split,
same standardizer, same fallback contract) as a real candidate would use, and
persist the held-out Brier-delta distribution (p50/p90/p99).

THE RAIL (binding, also encoded in batch_gate.py's prescreen):
  * A candidate's delta <= p99 of ITS matched floor -> the prescreen may
    AUTO-REJECT it (verdict=REJECT, layer=FDR_PRESCREEN), skipping the full
    ceremony. This is a CHEAP early exit for candidates indistinguishable
    from noise, never a SHIP shortcut.
  * A candidate ABOVE the floor gains NOTHING from clearing it. The full
    >=20-draw planted-null ceremony (stack_gate_pregame.planted_null_fdr)
    remains MANDATORY before any further layer credit. This module NEVER
    ships a candidate and NEVER substitutes for the real per-candidate
    planted-null lane inside judge_stack_family.

Noise columns are drawn N(0,1) per row (pure random, no relation to y or
p_base) -- this is a DIFFERENT null than judge_stack_family's permutation
null (which shuffles a REAL added column); null_floor answers "what delta can
sheer model flexibility produce with n_extra_params free columns", which is
exactly the prescreen question (is this candidate distinguishable from an
n_extra_params-parameter noise fit at all).

Calibration, not edge. NO $/ROI anywhere. numpy + stdlib only. ASCII.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

from scripts.platformkit.combo import stack_fit as sf

_REPO = Path(__file__).resolve().parents[3]
_CACHE_DIR = _REPO / "data" / "cache" / "combo"
M_DRAWS = 40
MAX_EXTRA_PARAMS = 4  # A2 nba_stack_box4 adds 4 columns -- extend the floor table to cover it


def _floor_path(sport: str) -> Path:
    return _CACHE_DIR / f"null_floor_{sport}.json"


def _one_noise_delta(y: np.ndarray, p_base: np.ndarray, n_extra: int,
                     rng: np.random.Generator) -> float:
    """Fit [1, logit(p_base), noise x n_extra] via the IDENTICAL stack_fit path;
    return held-out Brier delta (positive = the noise-stack 'beat' base)."""
    n = len(y)
    splits = sf.expanding_window_splits(n, initial_train_frac=0.5, n_folds=1)
    tr_idx, te_idx = splits[0].train_idx, splits[0].test_idx

    base_logit = sf.logit(p_base)
    noise = rng.standard_normal(size=(n, n_extra))
    std = sf.fit_standardizer(noise[tr_idx])
    noise_z = sf.standardize(noise, std)

    X_tr = sf.build_design([base_logit[tr_idx]] + [noise_z[tr_idx, i] for i in range(n_extra)])
    fit = sf.fit_logistic(X_tr, y[tr_idx])
    X_te = sf.build_design([base_logit[te_idx]] + [noise_z[te_idx, i] for i in range(n_extra)])
    p_noise = sf.predict_proba(X_te, fit.weights)

    br_base = sf.brier(p_base[te_idx], y[te_idx])
    br_noise = sf.brier(p_noise, y[te_idx])
    return br_base - br_noise  # >0 == the noise-stack held-out-beat base


def compute_null_floor_for_unit(y: np.ndarray, p_base: np.ndarray, n_extra: int,
                                m_draws: int = M_DRAWS, base_seed: int = 0) -> Dict[str, float]:
    """M draws of `_one_noise_delta`; return p50/p90/p99 + M + seed."""
    m_draws = max(1, int(m_draws))
    deltas = [_one_noise_delta(y, p_base, n_extra, np.random.default_rng(base_seed + i * 7919))
             for i in range(m_draws)]
    return {
        "p50": float(np.percentile(deltas, 50)), "p90": float(np.percentile(deltas, 90)),
        "p99": float(np.percentile(deltas, 99)), "m": m_draws, "base_seed": base_seed,
        "n_extra_params": n_extra,
    }


def build_null_floor(sport: str, corpus: pd.DataFrame, m_draws: int = M_DRAWS,
                     base_seed: int = 0) -> Dict[str, object]:
    """Per (corpus_unit, n_extra_params in 1..MAX_EXTRA_PARAMS): compute + persist the floor table."""
    table: Dict[str, Dict[str, Dict[str, float]]] = {}
    timings: Dict[str, float] = {}
    for unit in sorted(corpus["corpus_unit"].dropna().unique().tolist()):
        sub = corpus[corpus["corpus_unit"] == unit]
        valid = sub["y"].notna() & sub["p_base"].notna()
        sub = sub[valid]
        if len(sub) < 10:
            continue
        y = sub["y"].to_numpy(float)
        p_base = np.clip(sub["p_base"].to_numpy(float), 1e-6, 1 - 1e-6)
        table[unit] = {}
        t0 = time.perf_counter()
        for n_extra in range(1, MAX_EXTRA_PARAMS + 1):
            table[unit][str(n_extra)] = compute_null_floor_for_unit(
                y, p_base, n_extra, m_draws=m_draws, base_seed=base_seed)
        timings[unit] = time.perf_counter() - t0

    payload = {"sport": sport, "built_at": time.time(), "m_draws": m_draws,
              "base_seed": base_seed, "floors": table, "timings_sec": timings}
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _floor_path(sport).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_null_floor(sport: str) -> Dict[str, object]:
    p = _floor_path(sport)
    if not p.exists():
        raise FileNotFoundError(f"no null floor cached for {sport!r}; run build_null_floor first")
    return json.loads(p.read_text(encoding="utf-8"))


def prescreen_verdict(sport: str, corpus_unit: str, n_extra_params: int,
                      candidate_delta: float) -> str:
    """'REJECT' (candidate_delta <= matched p99 -- full ceremony skipped) or
    'PROCEED' (candidate ABOVE floor -- gains NOTHING, full ceremony still
    mandatory). Raises if no floor is cached for this (sport, unit, n_extra)."""
    payload = load_null_floor(sport)
    unit_table = payload.get("floors", {}).get(corpus_unit)
    if unit_table is None:
        raise KeyError(f"no null floor cached for {sport!r} corpus_unit={corpus_unit!r}")
    # S40b / RT-9: this used to CLAMP -- `min(max(1, n), MAX_EXTRA_PARAMS)` silently graded a
    # candidate against a floor built for FEWER free columns (measured: n_extra=12 -> table
    # key "4"), and a 4-column noise floor sits lower than a 12-column one, so the wider
    # candidate returned PROCEED. MAX_EXTRA_PARAMS is a labelled CEILING on what the table
    # covers; "no matched floor" is an honest stop, not a nearest-neighbour grade.
    n_extra = int(n_extra_params)
    if not 1 <= n_extra <= MAX_EXTRA_PARAMS:
        raise KeyError(
            f"no null floor for n_extra_params={n_extra}: the table covers 1..{MAX_EXTRA_PARAMS} "
            f"(MAX_EXTRA_PARAMS is a ceiling on coverage, not a clamp); rebuild the floor table "
            f"with MAX_EXTRA_PARAMS >= {n_extra} to grade this candidate"
        )
    entry = unit_table.get(str(n_extra))
    if entry is None:
        raise KeyError(f"no null floor cached for {sport!r} unit={corpus_unit!r} n_extra={n_extra}")
    return "REJECT" if candidate_delta <= entry["p99"] else "PROCEED"


__all__ = [
    "M_DRAWS", "MAX_EXTRA_PARAMS", "compute_null_floor_for_unit", "build_null_floor",
    "load_null_floor", "prescreen_verdict",
]
