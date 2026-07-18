"""Statistics helpers for the 3a predictive-validity gate.

Spearman rho, the cluster-by-player paired bootstrap on the rho delta, and
the top-decile face-validity diagnostic. Split out of quality_validity_gate.py
to stay under the 300-LOC/file cap; pure statistics, no data loading.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

N_BOOTSTRAP = 2000
RNG_SEED = 20260704  # fixed seed, declared before any result was inspected


def spearman(x: pd.Series, y: pd.Series) -> float:
    # object-dtype inputs crash scipy/numpy corrcoef on the pod (numpy 2.x);
    # cast at the shared root so every caller is covered.
    rho, _ = spearmanr(np.asarray(x, dtype=float), np.asarray(y, dtype=float))
    return float(rho)


def paired_bootstrap_delta(tables: list[pd.DataFrame], n_boot: int = N_BOOTSTRAP,
                            seed: int = RNG_SEED) -> dict[str, float]:
    """Cluster-by-player paired bootstrap on mean-across-cutoffs
    rho(shooter) - rho(naive). Resample players WITH replacement (same
    resample applied to a player's rows across every cutoff they appear in,
    i.e. clustered), recompute per-cutoff Spearman rho for both rankings on
    the resampled set, average across cutoffs, take the delta."""
    rng = np.random.default_rng(seed)
    all_pids = sorted(set().union(*[set(t["player_id"]) for t in tables]))
    deltas = []
    for _ in range(n_boot):
        sample_pids = rng.choice(all_pids, size=len(all_pids), replace=True)
        cutoff_deltas = []
        for t in tables:
            idx = t.set_index("player_id")
            rows = []
            for pid in sample_pids:
                if pid in idx.index:
                    r = idx.loc[pid]
                    if isinstance(r, pd.DataFrame):
                        r = r.iloc[0]
                    rows.append(r)
            if len(rows) < 10:
                continue
            resampled = pd.DataFrame(rows)
            rho_s = spearman(resampled["shooter_pctile"], resampled["realized_ts_pct"])
            rho_n = spearman(resampled["naive_pctile"], resampled["realized_ts_pct"])
            if not (np.isnan(rho_s) or np.isnan(rho_n)):
                cutoff_deltas.append(rho_s - rho_n)
        if cutoff_deltas:
            deltas.append(float(np.mean(cutoff_deltas)))
    deltas = np.array(deltas)
    return {
        "mean_delta": float(np.mean(deltas)),
        "ci_lo": float(np.percentile(deltas, 2.5)),
        "ci_hi": float(np.percentile(deltas, 97.5)),
        "n_boot_effective": int(len(deltas)),
    }


def top_decile_diagnostic(table: pd.DataFrame, pctile_col: str) -> dict[str, float]:
    n = len(table)
    decile_n = max(1, n // 10)
    ranked = table.sort_values(pctile_col, ascending=False)
    top = ranked.head(decile_n)
    return {
        "top_decile_mean_realized_ts": float(top["realized_ts_pct"].mean()),
        "field_mean_realized_ts": float(table["realized_ts_pct"].mean()),
        "diff": float(top["realized_ts_pct"].mean() - table["realized_ts_pct"].mean()),
        "n_top_decile": int(decile_n),
    }
