"""Generic predictive-validity harness: for any claim-family metric, a
walk-forward FORWARD-OUTCOME test at its natural grain vs a declared naive
baseline. Predictions VALIDATE the intelligence -- NOT vs the market close.

A MetricTest declares, per family/metric: a list of cutoffs, how far forward
to look, floors, and three as-of callbacks (metric_asof/baseline_asof/
forward_outcome). run_metric_test() builds one fold per cutoff (inner-join on
entity_id, floor on n_forward, skip the fold below the entity floor), then
pools across folds: mean Spearman rho for both metric and baseline, sign_holds
(delta>0 count), a clustered (by entity) paired bootstrap on the rho delta
(reusing domains.basketball_nba.quality_validity_stats.paired_bootstrap_delta
-- its column-name contract is player_id/shooter_pctile/naive_pctile/
realized_ts_pct, so folds are renamed onto those names before the call; the
correlation math does not care what the columns are named), plus a small
single-arm bootstrap for rho_metric_mean's own CI (paired_bootstrap_delta only
returns the two-arm delta, not a raw-skill CI -- a metric can beat baseline
while both are weak, so that number is reported too).

CLI-less: see run_nba.py for the NBA v1 menu + CLI wrapper.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

from domains.basketball_nba.quality_validity_stats import paired_bootstrap_delta
from domains.basketball_nba.quality_validity_stats import spearman as _spearman

N_BOOTSTRAP = 2000
RNG_SEED = 20260717  # fixed, declared before any predictive_validity result was inspected


@dataclass
class MetricTest:
    family: str
    sport: str
    metric_name: str
    baseline_name: str
    cutoffs: list[str]
    forward_games: int
    min_forward_games: int
    min_entities_per_fold: int
    metric_asof: Callable[[str], pd.DataFrame]
    baseline_asof: Callable[[str], pd.DataFrame]
    forward_outcome: Callable[[str], pd.DataFrame]
    caveat: str = ""


def _build_fold(test: MetricTest, cutoff: str) -> dict[str, Any]:
    m = test.metric_asof(cutoff).rename(columns={"value": "metric_value"})
    b = test.baseline_asof(cutoff).rename(columns={"value": "baseline_value"})
    o = test.forward_outcome(cutoff)  # entity_id, outcome, n_forward

    merged = m.merge(b, on="entity_id", how="inner").merge(o, on="entity_id", how="inner")
    merged = merged[merged["n_forward"] >= test.min_forward_games]
    if len(merged) < test.min_entities_per_fold:
        return {"cutoff": cutoff, "status": "SKIPPED_BELOW_FLOOR", "n_entities": int(len(merged))}

    rho_metric = _spearman(merged["metric_value"], merged["outcome"])
    rho_baseline = _spearman(merged["baseline_value"], merged["outcome"])
    return {
        "cutoff": cutoff, "status": "OK", "n_entities": int(len(merged)),
        "rho_metric": rho_metric, "rho_baseline": rho_baseline,
        "delta": rho_metric - rho_baseline, "table": merged,
    }


def _bootstrap_single_rho(tables: list[pd.DataFrame], value_col: str, outcome_col: str,
                           n_boot: int = N_BOOTSTRAP, seed: int = RNG_SEED) -> dict[str, float]:
    """Clustered-by-entity bootstrap CI for the mean rho(value_col, outcome)
    ITSELF (not a delta) -- paired_bootstrap_delta only exposes the two-arm
    delta, so raw forward skill needs this small single-arm variant. Same
    resample-by-entity-id-with-replacement scheme, generalized off the
    hardcoded player_id/shooter_pctile column names so it works for any
    MetricTest's fold tables."""
    rng = np.random.default_rng(seed)
    all_ids = sorted(set().union(*[set(t["entity_id"]) for t in tables]))
    means = []
    for _ in range(n_boot):
        pick = rng.choice(all_ids, size=len(all_ids), replace=True)
        fold_rhos = []
        for t in tables:
            idx = t.set_index("entity_id")
            rows = []
            for eid in pick:
                if eid in idx.index:
                    r = idx.loc[eid]
                    if isinstance(r, pd.DataFrame):
                        r = r.iloc[0]
                    rows.append(r)
            if len(rows) < 10:
                continue
            resampled = pd.DataFrame(rows)
            rho = _spearman(resampled[value_col], resampled[outcome_col])
            if not np.isnan(rho):
                fold_rhos.append(rho)
        if fold_rhos:
            means.append(float(np.mean(fold_rhos)))
    arr = np.array(means)
    if len(arr) == 0:
        return {"mean": float("nan"), "ci_lo": float("nan"), "ci_hi": float("nan"), "n_boot_effective": 0}
    return {
        "mean": float(np.mean(arr)), "ci_lo": float(np.percentile(arr, 2.5)),
        "ci_hi": float(np.percentile(arr, 97.5)), "n_boot_effective": int(len(arr)),
    }


def _verdict(n_folds: int, bootstrap_delta: dict[str, Any], sign_holds: int) -> str:
    if n_folds < 2 or not bootstrap_delta or bootstrap_delta.get("n_boot_effective", 0) == 0:
        return "UNDERPOWERED"
    need = math.ceil(0.75 * n_folds)
    if bootstrap_delta["ci_lo"] > 0 and sign_holds >= need:
        return "PREDICTIVE_VERIFIED"
    return "DESCRIPTIVE_ONLY"


def run_metric_test(test: MetricTest, n_boot: int = N_BOOTSTRAP, seed: int = RNG_SEED) -> dict[str, Any]:
    """Run every cutoff fold, pool across the OK ones, return the full result
    dict (per_cutoff strips the raw fold "table" -- not JSON-safe -- before
    it's handed to a caller that serializes this to disk)."""
    folds = [_build_fold(test, c) for c in test.cutoffs]
    ok = [f for f in folds if f["status"] == "OK"]
    n_folds = len(ok)

    mean_rho_metric = float(np.mean([f["rho_metric"] for f in ok])) if ok else float("nan")
    mean_rho_baseline = float(np.mean([f["rho_baseline"] for f in ok])) if ok else float("nan")
    sign_holds = sum(1 for f in ok if f["delta"] > 0)

    bootstrap_delta: dict[str, Any] = {}
    bootstrap_metric: dict[str, Any] = {}
    if n_folds >= 2:
        renamed = [
            f["table"].rename(columns={
                "entity_id": "player_id", "metric_value": "shooter_pctile",
                "baseline_value": "naive_pctile", "outcome": "realized_ts_pct",
            })
            for f in ok
        ]
        bootstrap_delta = paired_bootstrap_delta(renamed, n_boot=n_boot, seed=seed)
        bootstrap_metric = _bootstrap_single_rho(
            [f["table"] for f in ok], "metric_value", "outcome", n_boot=n_boot, seed=seed,
        )

    verdict = _verdict(n_folds, bootstrap_delta, sign_holds)

    return {
        "family": test.family, "sport": test.sport,
        "metric_name": test.metric_name, "baseline_name": test.baseline_name,
        "verdict": verdict,
        "mean_rho_metric": mean_rho_metric, "mean_rho_baseline": mean_rho_baseline,
        "rho_metric_bootstrap": bootstrap_metric,
        "bootstrap_delta_ci": bootstrap_delta,
        "sign_holds_folds": sign_holds, "n_folds": n_folds,
        "per_cutoff": [{k: v for k, v in f.items() if k != "table"} for f in folds],
        "forward_games": test.forward_games,
        "caveat": test.caveat,
    }
