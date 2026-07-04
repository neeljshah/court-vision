"""LANE composition (mission spine 3) -- situation-weighted blend gate.

Tests blend = w(s)*naive_z + (1-w(s))*quality_z vs naive ALONE, s=log1p(
FGA_to_date), ONE feature (hard flexibility cap). NOT a rematch of wave-29
overall (naive rho .4044 vs shooter_quality_v1 .2680, naive wins overall) --
asks whether the blend recovers value in the pre-registered low-sample
subpopulation (bottom tercile of FGA_to_date).

HARNESS (reused): domains.basketball_nba.quality_validity_gate for leak-free
per-cutoff tables (rank_at_cutoff), quality_validity_stats for Spearman rho.
Same 4 monthly 2024-25 cutoffs + 2025-26 replication cutoff as wave-29.

WALK-FORWARD: leave-one-fold-out over floor-clearing folds -- c0/c1 fit on
the OTHER OK folds only, never the held-out TEST fold (leak-free per fold).

ADOPT (binding, pre-registered): blend beats naive with bootstrap CI
excluding 0 on OVERALL or LOW-SAMPLE, AND sign holds >=3/4 folds, AND
replicates on 2025-26, AND the planted null dies. Naive stays canonical on
any other outcome -- REJECT/NOT_TESTABLE is a recorded success.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from domains.basketball_nba.quality_validity_gate import (
    CUTOFFS_2024_25,
    REPLICATION_CUTOFF,
    rank_at_cutoff,
)
from domains.basketball_nba.quality_indices import load_boxscores
from domains.basketball_nba.quality_validity_stats import spearman as _spearman

from scripts.platformkit.composition.composition_blend import (
    FitResult,
    blend_scores,
    fit_weight_params,
    low_sample_mask,
    shuffle_quality_within_cutoff,
)

N_BOOT = 500
BOOT_SEED = 20260704  # same convention as quality_validity_stats.RNG_SEED
NULL_SEED = 20260705  # distinct, fixed seed for the planted-null control


def _fold_rho_deltas(test_table: pd.DataFrame, fit: FitResult, subset_mask: pd.Series | None = None
                      ) -> dict[str, float] | None:
    """rho(blend) - rho(naive) on a held-out fold, restricted to subset_mask
    if given. Returns None if the (sub)population is too small to rank."""
    t = test_table if subset_mask is None else test_table[subset_mask]
    if len(t) < 10:
        return None
    blend = blend_scores(t, fit.c0, fit.c1)
    rho_blend = _spearman(blend, t["realized_ts_pct"])
    rho_naive = _spearman(t["naive_pctile"], t["realized_ts_pct"])
    if np.isnan(rho_blend) or np.isnan(rho_naive):
        return None
    return {"n": int(len(t)), "rho_blend": rho_blend, "rho_naive": rho_naive, "delta": rho_blend - rho_naive}


def _leave_one_fold_out(tables: list[pd.DataFrame], cutoffs: list[str]) -> dict[str, Any]:
    """For each fold, fit c0/c1 on the OTHER folds, score held-out fold
    overall + on its pre-registered low-sample subpopulation."""
    per_fold = []
    for i, cutoff in enumerate(cutoffs):
        train_tables = [tables[j] for j in range(len(tables)) if j != i]
        test_table = tables[i]
        fit = fit_weight_params(train_tables)
        overall = _fold_rho_deltas(test_table, fit)
        low_mask = low_sample_mask(test_table)
        low_sample = _fold_rho_deltas(test_table, fit, subset_mask=low_mask)
        per_fold.append({
            "cutoff": cutoff, "c0": fit.c0, "c1": fit.c1,
            "train_mean_rho": fit.train_mean_rho,
            "overall": overall, "low_sample": low_sample,
        })
    return {"per_fold": per_fold}


def _bootstrap_delta(tables: list[pd.DataFrame], fits: list[FitResult], n_boot: int = N_BOOT,
                      seed: int = BOOT_SEED, subset_fn=None) -> dict[str, float]:
    """Cluster-by-player paired bootstrap on mean-across-folds
    rho(blend)-rho(naive). Same convention as
    quality_validity_stats.paired_bootstrap_delta: c0/c1 fit ONCE per fold
    on the real leave-one-fold-out TRAIN split (`fits`, aligned to `tables`)
    and held fixed across resamples -- only the rho evaluation is
    bootstrapped (players resampled with replacement, clustered)."""
    rng = np.random.default_rng(seed)
    all_pids = sorted(set().union(*[set(t["player_id"]) for t in tables]))
    indexed = [t.set_index("player_id", drop=False) for t in tables]  # set once, not per resample
    deltas = []
    for _ in range(n_boot):
        sample_pids = rng.choice(all_pids, size=len(all_pids), replace=True)
        fold_deltas = []
        for idx, fit in zip(indexed, fits):
            present = idx.index.intersection(pd.unique(sample_pids))
            if len(present) == 0:
                continue
            counts = pd.Series(sample_pids).value_counts()
            reps = counts.reindex(present).astype(int)
            test = idx.loc[present].loc[idx.loc[present].index.repeat(reps.values)]
            if len(test) < 10:
                continue
            if subset_fn is not None:
                mask = subset_fn(test)
                test = test[mask]
                if len(test) < 10:
                    continue
            blend = blend_scores(test, fit.c0, fit.c1)
            rho_b = _spearman(blend, test["realized_ts_pct"])
            rho_n = _spearman(test["naive_pctile"], test["realized_ts_pct"])
            if not (np.isnan(rho_b) or np.isnan(rho_n)):
                fold_deltas.append(rho_b - rho_n)
        if fold_deltas:
            deltas.append(float(np.mean(fold_deltas)))
    arr = np.array(deltas)
    if len(arr) == 0:
        return {"mean_delta": float("nan"), "ci_lo": float("nan"), "ci_hi": float("nan"), "n_boot_effective": 0}
    return {"mean_delta": float(np.mean(arr)), "ci_lo": float(np.percentile(arr, 2.5)),
            "ci_hi": float(np.percentile(arr, 97.5)), "n_boot_effective": int(len(arr))}


def _replication_check(box: pd.DataFrame, fit_all: FitResult) -> dict[str, Any]:
    """2025-26 replication: fit c0/c1 on ALL 2024-25 OK folds (already done
    upstream), score the 2025-26 cutoff table if it clears the floor."""
    rep = rank_at_cutoff(box, REPLICATION_CUTOFF)
    if rep is None:
        return {"cutoff": REPLICATION_CUTOFF, "status": "SKIPPED_BELOW_FLOOR"}
    table = rep["table"]
    overall = _fold_rho_deltas(table, fit_all)
    low_mask = low_sample_mask(table)
    low_sample = _fold_rho_deltas(table, fit_all, subset_mask=low_mask)
    return {"cutoff": REPLICATION_CUTOFF, "status": "OK", "n_players": rep["n_players"],
            "overall": overall, "low_sample": low_sample}


@dataclass
class CompositionGateResult:
    ok_cutoffs: list[str] = field(default_factory=list)
    loo: dict = field(default_factory=dict)
    bootstrap_overall: dict = field(default_factory=dict)
    bootstrap_low_sample: dict = field(default_factory=dict)
    sign_holds_overall: str = "0/0"
    sign_holds_low_sample: str = "0/0"
    replication: dict = field(default_factory=dict)
    planted_null_bootstrap_overall: dict = field(default_factory=dict)
    planted_null_bootstrap_low_sample: dict = field(default_factory=dict)
    planted_null_dies: bool | None = None
    verdict: str = "PENDING"
    reason: str = ""


def _sign_holds_str(per_fold: list[dict], key: str) -> tuple[int, int]:
    holds, n = 0, 0
    for f in per_fold:
        d = f.get(key)
        if d is None:
            continue
        n += 1
        if d["delta"] > 0:
            holds += 1
    return holds, n


def run_gate() -> CompositionGateResult:
    box = load_boxscores()
    tables, ok_cutoffs = [], []
    for cutoff in CUTOFFS_2024_25:
        r = rank_at_cutoff(box, cutoff)
        if r is not None:
            tables.append(r["table"])
            ok_cutoffs.append(cutoff)

    if len(tables) < 2:
        return CompositionGateResult(
            ok_cutoffs=ok_cutoffs, verdict="NOT_TESTABLE",
            reason=f"only {len(tables)} fold(s) clear the floor; leave-one-fold-out needs >=2",
        )

    loo = _leave_one_fold_out(tables, ok_cutoffs)
    holds_o, n_o = _sign_holds_str(loo["per_fold"], "overall")
    holds_l, n_l = _sign_holds_str(loo["per_fold"], "low_sample")
    fits = [FitResult(c0=f["c0"], c1=f["c1"], train_mean_rho=f["train_mean_rho"]) for f in loo["per_fold"]]

    boot_overall = _bootstrap_delta(tables, fits)
    boot_low = _bootstrap_delta(tables, fits, subset_fn=low_sample_mask)

    fit_all = fit_weight_params(tables)
    replication = _replication_check(box, fit_all)

    # Planted null: shuffle shooter_pctile across players within each cutoff,
    # refit w on TRAIN (leave-one-fold-out, same as the real run), rerun the
    # SAME bootstrap machinery on the shuffled tables.
    null_rng = np.random.default_rng(NULL_SEED)
    null_tables = [shuffle_quality_within_cutoff(t, null_rng) for t in tables]
    null_loo = _leave_one_fold_out(null_tables, ok_cutoffs)
    null_fits = [FitResult(c0=f["c0"], c1=f["c1"], train_mean_rho=f["train_mean_rho"])
                 for f in null_loo["per_fold"]]
    null_boot_overall = _bootstrap_delta(null_tables, null_fits, seed=BOOT_SEED)
    null_boot_low = _bootstrap_delta(null_tables, null_fits, seed=BOOT_SEED, subset_fn=low_sample_mask)

    ci_excludes_0_overall = np.isfinite(boot_overall["ci_lo"]) and boot_overall["ci_lo"] > 0
    ci_excludes_0_low = np.isfinite(boot_low["ci_lo"]) and boot_low["ci_lo"] > 0
    win_locus = ci_excludes_0_overall or ci_excludes_0_low

    sign_ok = (n_o > 0 and holds_o / n_o >= 0.75) or (n_l > 0 and holds_l / n_l >= 0.75)

    rep_delta = None
    rep_block = replication.get("low_sample") or replication.get("overall")
    if rep_block is not None:
        rep_delta = rep_block["delta"]
    replicates = replication.get("status") == "OK" and rep_delta is not None and rep_delta > 0

    # Planted-null death check: null CI must NOT show a comparable
    # improvement in whichever locus (overall/low-sample) drove the win.
    null_ci_lo_relevant = (
        null_boot_overall["ci_lo"] if ci_excludes_0_overall else null_boot_low["ci_lo"]
    )
    null_dies = not (np.isfinite(null_ci_lo_relevant) and null_ci_lo_relevant > 0)

    if win_locus and sign_ok and replicates and null_dies:
        verdict = "SHIP"
        reason = "blend beats naive (CI excludes 0), sign holds, replicates 2025-26, planted null dies"
    elif win_locus and sign_ok and replicates and not null_dies:
        verdict = "NOT_TESTABLE"
        reason = "blend beats naive but planted null shows comparable improvement -> flexibility artifact"
    elif not replicates and replication.get("status") != "OK":
        verdict = "NOT_TESTABLE"
        reason = "2025-26 replication corpus SKIPPED_BELOW_FLOOR -- cannot test the replication clause"
    else:
        verdict = "REJECT"
        reason = "naive stays canonical: win/sign/replication conditions not jointly satisfied"

    return CompositionGateResult(
        ok_cutoffs=ok_cutoffs,
        loo=loo,
        bootstrap_overall=boot_overall,
        bootstrap_low_sample=boot_low,
        sign_holds_overall=f"{holds_o}/{n_o}",
        sign_holds_low_sample=f"{holds_l}/{n_l}",
        replication=replication,
        planted_null_bootstrap_overall=null_boot_overall,
        planted_null_bootstrap_low_sample=null_boot_low,
        planted_null_dies=null_dies,
        verdict=verdict,
        reason=reason,
    )


VERDICT_PATH = "data/domains/basketball_nba/composition_gate_verdict.json"


def write_verdict(g: CompositionGateResult, path: str = VERDICT_PATH) -> dict:
    """Verdict-artifact convention (matches data/domains/*/*_verdict.json
    shape used across the platform): flat JSON, component/verdict/reason,
    numeric fields, generated_at, honest_note, edge_claimed=false."""
    doc = {
        "component": "composition_gate_shooter_quality_v1_blend", "sport": "basketball_nba",
        "hypothesis": "situation-weighted blend (w(s)*naive_z + (1-w(s))*quality_z, "
                       "s=log1p(FGA_to_date)) beats naive OVERALL or on the pre-registered "
                       "low-sample subpopulation (bottom tercile of FGA_to_date)",
        "verdict": g.verdict, "verdict_reason": g.reason, "ok_cutoffs": g.ok_cutoffs,
        "sign_holds_overall": g.sign_holds_overall, "sign_holds_low_sample": g.sign_holds_low_sample,
        "bootstrap_delta_ci_overall": g.bootstrap_overall,
        "bootstrap_delta_ci_low_sample": g.bootstrap_low_sample,
        "replication_2025_26": g.replication,
        "planted_null_bootstrap_overall": g.planted_null_bootstrap_overall,
        "planted_null_bootstrap_low_sample": g.planted_null_bootstrap_low_sample,
        "planted_null_dies": g.planted_null_dies,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "honest_note": "calibration/predictive-validity comparison only; naive composite "
                        "(0.55*TS%+0.30*eFG%+0.15*FT%) stays canonical unless verdict=SHIP; "
                        "NOT_TESTABLE/REJECT are recorded successes, not failures",
        "edge_claimed": False,
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=1), encoding="ascii")
    return doc


if __name__ == "__main__":
    g = run_gate()
    print(f"VERDICT: {g.verdict} -- {g.reason}")
    print(f"ok_cutoffs={g.ok_cutoffs}")
    print(f"sign_holds overall={g.sign_holds_overall} low_sample={g.sign_holds_low_sample}")
    print(f"bootstrap_overall={g.bootstrap_overall}")
    print(f"bootstrap_low_sample={g.bootstrap_low_sample}")
    print(f"replication={g.replication}")
    print(f"planted_null_dies={g.planted_null_dies}")
    doc = write_verdict(g)
    print(f"wrote verdict to {VERDICT_PATH}")
