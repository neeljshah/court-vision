"""LANE positional-weights gate (weight-hierarchy step 2, Fable-designed).

Hypothesis under test: a big's shooting stats should weigh differently than
a guard's when forecasting future shooting quality -- i.e. a PER-POSGROUP
reweighting of (ts_pct, efg_pct, ft_pct) beats the position-blind naive
composite (0.55*ts_pct + 0.30*efg_pct + 0.15*ft_pct).

Design (pre-registered, frozen before any group weight was fit):
    candidate = per-posgroup weights (w_ts, w_efg, w_ft), one triple per
        posgroup g in {guard, forward, center}, each triple constrained
        non-negative and summing to 1 (3-simplex). Fit on TRAIN (pre-cutoff)
        folds ONLY, maximizing Spearman rho vs future-30d realized TS%
        WITHIN that group, pooled across the TRAIN folds.
    prediction = within-group weighted composite of pre-T (ts_pct, efg_pct,
        ft_pct), then percentile-ranked WITHIN the pooled cutoff population
        (matches naive_pctile's own normalization) for the overall rank.
    baseline = naive_pctile (position-blind, already computed leak-free by
        quality_validity_gate.rank_at_cutoff).
Fitting/statistics machinery lives in positional_weight_stats.py (kept
separate to stay under the 300-LOC/file cap).

Walk-forward: leave-one-fold-out over the floor-clearing 2024-25 cutoffs
(fit on the OTHER folds, score the held-out fold) -- same convention as
composition_gate.py.

PLANTED NULL (mandatory): shuffle posgroup labels across players WITHIN
each cutoff, refit per-group weights on the shuffled labels the same way,
rerun the same walk-forward + bootstrap. A comparable improvement under
the shuffle means the win is a flexibility artifact (9 free params vs the
naive's 0) -- NOT the positional-fit hypothesis. Expect this outcome
honestly per the brief.

ADOPT ONLY IF: positional beats naive with paired-bootstrap CI excluding 0
(overall OR a pre-registered posgroup cell) AND sign holds >=3/4 folds AND
replicates on 2025-26 AND the planted null dies. Naive stays canonical on
any other outcome -- REJECT/NOT_TESTABLE is a recorded success, not a
failure.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.platformkit.weights.positional_weight_io import (
    POSGROUPS,
    MIN_COVERAGE_PCT,
    cutoff_tables_with_position,
    qualifier_coverage,
    replication_table_with_position,
)
from scripts.platformkit.weights.positional_weight_stats import (
    bootstrap_delta,
    fit_all_group_weights,
    fold_eval,
    leave_one_fold_out,
    predict_positional,
    shuffle_posgroup_within_cutoff,
    sign_holds,
)

N_BOOT = 500
BOOT_SEED = 20260704
NULL_SEED = 20260705


@dataclass
class PositionalWeightGateResult:
    verdict: str = "PENDING"
    reason: str = ""
    coverage: dict = field(default_factory=dict)
    ok_cutoffs: list[str] = field(default_factory=list)
    per_fold: list[dict] = field(default_factory=list)
    bootstrap_overall: dict = field(default_factory=dict)
    bootstrap_per_group: dict = field(default_factory=dict)
    sign_holds_overall: str = "0/0"
    sign_holds_per_group: dict = field(default_factory=dict)
    fitted_weights_all_folds: dict = field(default_factory=dict)
    replication: dict = field(default_factory=dict)
    planted_null_bootstrap_overall: dict = field(default_factory=dict)
    planted_null_dies: bool | None = None
    rows: pd.DataFrame | None = None


def _export_rows(ok_cutoffs: list[str], tables: list[pd.DataFrame],
                  fit_all: dict[str, np.ndarray]) -> pd.DataFrame:
    """Reprocess-harness input schema: corpus_id/fold_id/event_id/p_variant/
    p_base/outcome (diagnostic export; not part of the walk-forward verdict
    computed above)."""
    rows = []
    for cutoff, t in zip(ok_cutoffs, tables):
        pred = predict_positional(t, fit_all)
        for i, pid in enumerate(t["player_id"]):
            rows.append({
                "corpus_id": "nba_2024_25_boxscore", "fold_id": cutoff,
                "event_id": f"{pid}-{cutoff}", "p_variant": float(pred.iloc[i]),
                "p_base": float(t["naive_pctile"].iloc[i]),
                "outcome": float(t["realized_ts_pct"].iloc[i]),
            })
    return pd.DataFrame(rows)


def run_gate() -> PositionalWeightGateResult:
    cov = qualifier_coverage()
    if cov["coverage_pct"] < MIN_COVERAGE_PCT:
        return PositionalWeightGateResult(
            verdict="INSUFFICIENT_COVERAGE",
            reason=f"329-qualifier position coverage {cov['coverage_pct']:.4f} < {MIN_COVERAGE_PCT} floor",
            coverage=cov,
        )

    tables, ok_cutoffs = cutoff_tables_with_position()
    if len(tables) < 2:
        return PositionalWeightGateResult(
            verdict="NOT_TESTABLE",
            reason=f"only {len(tables)} fold(s) clear the floor; leave-one-fold-out needs >=2",
            coverage=cov, ok_cutoffs=ok_cutoffs,
        )

    per_fold = leave_one_fold_out(tables, ok_cutoffs)
    weights_per_fold = [{g: np.array(w) for g, w in f["weights"].items()} for f in per_fold]

    holds_o, n_o = sign_holds(per_fold, ["overall"])
    holds_g = {g: sign_holds(per_fold, ["per_group", g]) for g in POSGROUPS}

    boot_overall = bootstrap_delta(tables, weights_per_fold, N_BOOT, BOOT_SEED)
    boot_group = {g: bootstrap_delta(tables, weights_per_fold, N_BOOT, BOOT_SEED, group=g)
                  for g in POSGROUPS}

    fit_all = fit_all_group_weights(tables)  # for replication + row export
    rep_table = replication_table_with_position()
    if rep_table is None:
        replication = {"cutoff": "2025-12-01", "status": "SKIPPED_BELOW_FLOOR"}
    else:
        rep_eval = fold_eval(rep_table, fit_all)
        replication = {"cutoff": "2025-12-01", "status": "OK", "n_players": len(rep_table), **rep_eval}

    # planted null: shuffle posgroup labels within each cutoff, refit, rerun
    null_rng = np.random.default_rng(NULL_SEED)
    null_tables = [shuffle_posgroup_within_cutoff(t, null_rng) for t in tables]
    null_per_fold = leave_one_fold_out(null_tables, ok_cutoffs)
    null_weights_per_fold = [{g: np.array(w) for g, w in f["weights"].items()} for f in null_per_fold]
    null_boot_overall = bootstrap_delta(null_tables, null_weights_per_fold, N_BOOT, BOOT_SEED)

    ci_excludes_0_overall = np.isfinite(boot_overall["ci_lo"]) and boot_overall["ci_lo"] > 0
    winning_group_cells = [g for g in POSGROUPS
                            if np.isfinite(boot_group[g]["ci_lo"]) and boot_group[g]["ci_lo"] > 0]
    win_locus = ci_excludes_0_overall or bool(winning_group_cells)

    sign_ok_overall = n_o > 0 and (holds_o / n_o) >= 0.75
    sign_ok_group = any(n > 0 and (h / n) >= 0.75 for g, (h, n) in holds_g.items())
    sign_ok = sign_ok_overall or sign_ok_group

    rep_delta = replication["overall"]["delta"] if replication.get("status") == "OK" else None
    replicates = replication.get("status") == "OK" and rep_delta is not None and rep_delta > 0

    null_dies = not (np.isfinite(null_boot_overall["ci_lo"]) and null_boot_overall["ci_lo"] > 0)

    if win_locus and sign_ok and replicates and null_dies:
        verdict = "SHIP"
        reason = "positional weighting beats naive (CI excludes 0), sign holds, replicates 2025-26, planted null dies"
    elif win_locus and sign_ok and replicates and not null_dies:
        verdict = "NOT_TESTABLE"
        reason = "positional weighting beats naive but planted null shows comparable improvement -> flexibility artifact (9-vs-3 params)"
    elif replication.get("status") != "OK":
        verdict = "NOT_TESTABLE"
        reason = "2025-26 replication corpus SKIPPED_BELOW_FLOOR -- cannot test the replication clause"
    else:
        verdict = "REJECT"
        reason = "naive stays canonical: win/sign/replication conditions not jointly satisfied"

    rows_df = _export_rows(ok_cutoffs, tables, fit_all)

    return PositionalWeightGateResult(
        verdict=verdict, reason=reason, coverage=cov, ok_cutoffs=ok_cutoffs,
        per_fold=per_fold, bootstrap_overall=boot_overall, bootstrap_per_group=boot_group,
        sign_holds_overall=f"{holds_o}/{n_o}",
        sign_holds_per_group={g: f"{h}/{n}" for g, (h, n) in holds_g.items()},
        fitted_weights_all_folds={g: w.tolist() for g, w in fit_all.items()},
        replication=replication,
        planted_null_bootstrap_overall=null_boot_overall,
        planted_null_dies=null_dies,
        rows=rows_df,
    )


VERDICT_PATH = "data/domains/basketball_nba/positional_weight_verdict.json"
ROWS_PATH = "data/domains/basketball_nba/positional_weight_rows.parquet"


def write_outputs(g: PositionalWeightGateResult, verdict_path: str = VERDICT_PATH,
                   rows_path: str = ROWS_PATH) -> dict:
    doc = {
        "component": "positional_weight_gate", "sport": "basketball_nba",
        "hypothesis": "per-posgroup (guard/forward/center) reweighting of "
                       "(ts_pct, efg_pct, ft_pct) beats the position-blind "
                       "naive composite forecasting future-30d realized TS%",
        "verdict": g.verdict, "verdict_reason": g.reason,
        "coverage": g.coverage, "ok_cutoffs": g.ok_cutoffs,
        "per_fold": g.per_fold,
        "bootstrap_delta_ci_overall": g.bootstrap_overall,
        "bootstrap_delta_ci_per_group": g.bootstrap_per_group,
        "sign_holds_overall": g.sign_holds_overall,
        "sign_holds_per_group": g.sign_holds_per_group,
        "fitted_weights_all_2024_25_folds_diagnostic": g.fitted_weights_all_folds,
        "replication_2025_26": g.replication,
        "planted_null_bootstrap_overall": g.planted_null_bootstrap_overall,
        "planted_null_dies": g.planted_null_dies,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "honest_note": "calibration/predictive-validity comparison only; naive composite "
                        "(0.55*ts_pct+0.30*efg_pct+0.15*ft_pct) stays canonical unless "
                        "verdict=SHIP; INSUFFICIENT_COVERAGE/NOT_TESTABLE/REJECT are "
                        "recorded successes, not failures; per-group fitted weights are "
                        "a REPORTED diagnostic, never a fitting target (e.g. higher ft "
                        "weight for centers would be basketball-plausible but is never "
                        "targeted post-hoc)",
        "edge_claimed": False,
    }
    p = Path(verdict_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=1), encoding="ascii")
    if g.rows is not None and not g.rows.empty:
        rp = Path(rows_path)
        rp.parent.mkdir(parents=True, exist_ok=True)
        g.rows.to_parquet(rp, index=False)
    return doc


if __name__ == "__main__":
    result = run_gate()
    print(f"VERDICT: {result.verdict} -- {result.reason}")
    print(f"coverage={result.coverage}")
    print(f"ok_cutoffs={result.ok_cutoffs}")
    print(f"sign_holds overall={result.sign_holds_overall} per_group={result.sign_holds_per_group}")
    print(f"bootstrap_overall={result.bootstrap_overall}")
    print(f"bootstrap_per_group={result.bootstrap_per_group}")
    print(f"replication={result.replication}")
    print(f"planted_null_dies={result.planted_null_dies}")
    print(f"fitted_weights_all_folds={result.fitted_weights_all_folds}")
    doc = write_outputs(result)
    print(f"wrote verdict to {VERDICT_PATH}")
    if result.rows is not None and not result.rows.empty:
        print(f"wrote {len(result.rows)} rows to {ROWS_PATH}")
