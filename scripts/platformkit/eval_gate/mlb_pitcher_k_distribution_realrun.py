"""S450 FIX 1e/1f: cpcv-derived FIT rows, date-validated folds, the
same-date-permutation null gate, and fold-aggregation/verdict helpers moved
from the CLI module under the LOC rail. Seal/ledger gating lives in
mlb_pitcher_k_distribution_seal.py (split out under the same rail).

(a) ``cpcv_derive_fit_rows``: the FIT-row set used to grid-fit r/beta comes
    from cpcv_engine.cpcv_splits + symmetric blocking (per-HOLDOUT-ROW cpcv
    scoring is mlb_pitcher_k_distribution_cpcv.py, AMENDMENT 6(a)).
(b) ``split_folds``: dates validated before folding; unassigned rows counted
    ``date_unavailable``/``outside_declared_corpora``, never dropped.
(c) The same-date-permutation null gate applied to the Arm C (C-vs-B) verdict,
    requiring a COMPLETE null denominator (AMENDMENT 6(b)).

Construct/fixture module -- no network, no data/ read.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pandas as pd

from scripts.platformkit.eval_gate import cpcv_engine
from scripts.platformkit.eval_gate.cpcv_tail_metrics import reliability_table
from scripts.platformkit.eval_gate.mlb_pitcher_k_distribution_arms import (
    K_LINES, MIN_FOLD_N,
)
from scripts.platformkit.eval_gate.mlb_pitcher_k_distribution_fit import (
    compute_null_losses, purge_fit_rows,
)
from scripts.platformkit.execution.entry_timing.study import cluster_boot_ci

ARMS = ("A", "B", "C")

DATE_UNAVAILABLE = "date_unavailable"
OUTSIDE_DECLARED_CORPORA = "outside_declared_corpora"


# ---------------------------------------------------- (b) cpcv-derived FIT

def cpcv_derive_fit_rows(fit_rows: List[dict], holdout_rows: List[dict],
                         n_groups: Optional[int] = None, n_test_groups: int = 1,
                         embargo_blocks: int = 1) -> Tuple[List[dict], Optional[int], int]:
    """AMENDMENT 5(b): FIT rows come from cpcv_engine.cpcv_splits (called for
    real via the module object -- a raising replacement propagates) over the
    combined FIT+holdout dates: a FIT row survives only if EVERY emitted path
    whose test block overlaps a holdout row still calls it train, restricted
    to the declared FIT rows, THEN purge_fit_rows' symmetric team/matchup
    blocking on top. Returns (kept_fit_rows, split_id, n_purged); split_id is
    the lowest matching path index, or None when cpcv_splits can't run (<2
    distinct dates -- falls back to symmetric-blocking-only)."""
    if not fit_rows or not holdout_rows:
        return list(fit_rows), None, 0
    combined = list(fit_rows) + list(holdout_rows)
    dates = [r["date"] for r in combined]
    n_unique = pd.Series(pd.to_datetime(dates, errors="coerce")).nunique()
    if n_unique < 2:
        kept, n_purged = purge_fit_rows(fit_rows, holdout_rows)
        return kept, None, n_purged
    groups = n_groups or max(2, min(8, n_unique))
    holdout_pos = set(range(len(fit_rows), len(combined)))
    fit_pos = set(range(len(fit_rows)))
    matched, candidates = [], []
    for path_id, (train_idx, test_idx) in enumerate(
            cpcv_engine.cpcv_splits(dates, n_groups=groups, n_test_groups=n_test_groups,
                                    embargo_blocks=embargo_blocks)):
        if set(int(i) for i in test_idx) & holdout_pos:
            matched.append(path_id)
            candidates.append(set(int(i) for i in train_idx))
    if not candidates:
        return [], None, len(fit_rows)
    safe = set.intersection(*candidates) & fit_pos
    cpcv_kept = [combined[i] for i in sorted(safe)]
    kept, _ = purge_fit_rows(cpcv_kept, holdout_rows)
    return kept, min(matched), len(fit_rows) - len(kept)


# ------------------------------------------------- (d) date-validated folds

def split_folds(rows: List[dict], fit_range, holdout_a_range, holdout_b_range,
                fold_labels: Tuple[str, str, str]) -> Tuple[Dict[str, List[dict]], Dict[str, int]]:
    """Every row's date is validated before folding; an unassigned row is
    counted, never dropped (invariant asserted below)."""
    ranges = dict(zip(fold_labels, (fit_range, holdout_a_range, holdout_b_range)))
    folds: Dict[str, List[dict]] = {label: [] for label in fold_labels}
    unassigned: Dict[str, int] = {}
    for row in rows:
        try:
            d = pd.Timestamp(row.get("date"))
            if pd.isna(d):
                raise ValueError("nat")
        except (TypeError, ValueError):
            unassigned[DATE_UNAVAILABLE] = unassigned.get(DATE_UNAVAILABLE, 0) + 1
            continue
        for label, (lo, hi) in ranges.items():
            if lo <= d <= hi:
                folds[label].append(row)
                break
        else:
            unassigned[OUTSIDE_DECLARED_CORPORA] = unassigned.get(OUTSIDE_DECLARED_CORPORA, 0) + 1
    assert sum(len(v) for v in folds.values()) + sum(unassigned.values()) == len(rows), \
        "row count invariant violated: some row neither folded nor counted"
    return folds, unassigned


# --------------------------------------------- (c) null-gated C-vs-B verdict

def mean_delta(scored: List[dict], arm_left: str, arm_right: str) -> Optional[float]:
    if not scored:
        return None
    diffs = [r["metrics"][arm_right]["crps"] - r["metrics"][arm_left]["crps"] for r in scored]
    return sum(diffs) / len(diffs)


def apply_null_gate_to_favor(fav: bool, real_delta_mean: Optional[float],
                             null_delta_mean: Optional[float]) -> bool:
    """Confirmed only if the REAL mean paired delta beats its own null;
    otherwise the null could not rule out chance and favour withdraws."""
    if not fav or real_delta_mean is None or null_delta_mean is None:
        return False
    return real_delta_mean < null_delta_mean


def verdict_for_pair_with_null(ci_a: dict, ci_b: dict, real_a, null_a, real_b, null_b) -> str:
    """Like verdict_for_pair, but favour also requires beating its null."""
    if ci_a["n"] < MIN_FOLD_N or ci_b["n"] < MIN_FOLD_N:
        return "INSUFFICIENT"
    if ci_a["lo"] is None or ci_a["hi"] is None or ci_b["lo"] is None or ci_b["hi"] is None:
        return "INSUFFICIENT"
    fav_a = apply_null_gate_to_favor(ci_a["hi"] < 0.0, real_a, null_a)
    fav_b = apply_null_gate_to_favor(ci_b["hi"] < 0.0, real_b, null_b)
    if fav_a and fav_b:
        return "ACCEPT"
    if fav_a or fav_b:
        return "SINGLE-WINDOW"
    return "NULL"


def _identity(entry: dict) -> tuple:
    return (entry["game_pk"], entry["player_id"], str(entry["date"]), entry.get("split_id"))


def _null_is_complete(scored: List[dict], assignments: List[dict]) -> bool:
    """AMENDMENT 7(b): completeness is IDENTITY + SPLIT-ID equality between
    the real scored set and the null assignments -- never merely equal
    lengths (two same-sized but different-identity sets must not pass)."""
    return {_identity(r) for r in scored} == {_identity(a) for a in assignments}


def compute_c_vs_b(train_dfs_a: List[pd.DataFrame], enriched_a: List[dict], scored_a: List[dict],
                   train_dfs_b: List[pd.DataFrame], enriched_b: List[dict], scored_b: List[dict],
                   r: float, beta: float, seed: int, ci_a: dict, ci_b: dict) -> Tuple[str, dict]:
    """Runs the null for real on both holdouts unconditionally (a raising
    replacement of permute_opp_k_rate_null propagates), using EACH ROW's own
    path-specific raw train_df (AMENDMENT 7(b), the identical state used for
    that row's real score -- never one shared gamelogs_df); returns (verdict,
    null_block) for the report's C_vs_B entry. The null must match the real
    scored set on IDENTITY AND SPLIT ID, not merely count -- a partial or
    mismatched null forces INSUFFICIENT, never a silently-narrower ACCEPT."""
    assign_a, deltas_a = compute_null_losses(train_dfs_a, enriched_a, scored_a, r, beta, seed=seed)
    assign_b, deltas_b = compute_null_losses(train_dfs_b, enriched_b, scored_b, r, beta, seed=seed)
    complete_a, complete_b = _null_is_complete(scored_a, assign_a), _null_is_complete(scored_b, assign_b)
    null_a = sum(deltas_a) / len(deltas_a) if deltas_a else None
    null_b = sum(deltas_b) / len(deltas_b) if deltas_b else None
    real_a, real_b = mean_delta(scored_a, "B", "C"), mean_delta(scored_b, "B", "C")
    if not (complete_a and complete_b):
        verdict = "INSUFFICIENT"
    else:
        verdict = verdict_for_pair_with_null(ci_a, ci_b, real_a, null_a, real_b, null_b)
    null_block = {
        "seed": seed,
        "holdout_2024": {"n": len(deltas_a), "n_real": len(scored_a), "complete": complete_a,
                         "mean_delta": null_a, "assignments": assign_a},
        "holdout_2025_2026": {"n": len(deltas_b), "n_real": len(scored_b), "complete": complete_b,
                              "mean_delta": null_b, "assignments": assign_b},
    }
    return verdict, null_block


# ----------------------------- fold-aggregation / verdict helpers (ex-CLI)

def aggregate_arm(scored: List[dict], arm: str) -> dict:
    n = len(scored)
    if n < MIN_FOLD_N:
        return {"n": n, "verdict": "INSUFFICIENT"}
    out = {"n": n}
    for metric in ("crps", "pinball_q10", "pinball_q50", "pinball_q90", "log_score"):
        out[f"mean_{metric}"] = sum(r["metrics"][arm][metric] for r in scored) / n
    k_lines: Dict[str, dict] = {}
    for k in K_LINES:
        key = str(k)
        probs = [r["metrics"][arm]["k_line"][key]["p_over"] for r in scored]
        outs = [r["metrics"][arm]["k_line"][key]["outcome"] for r in scored]
        briers = [r["metrics"][arm]["k_line"][key]["brier"] for r in scored]
        table = reliability_table(probs, outs, edges=(0.0, 1.0), min_n=MIN_FOLD_N)
        k_lines[key] = {"brier": sum(briers) / n, "reliability": table[0]}
    out["k_lines"] = k_lines
    return out


def paired_ci(scored: List[dict], arm_left: str, arm_right: str, seed: int, n_boot: int) -> dict:
    """95% CI for mean(CRPS_right - CRPS_left), game-DATE clustered bootstrap
    (hi < 0 means arm_right beats arm_left). Always records n_clusters, even
    when the row floor or the bootstrap itself yields no interval."""
    n_clusters = len(set(r["date"] for r in scored))
    if len(scored) < MIN_FOLD_N:
        return {"lo": None, "hi": None, "n": len(scored), "n_clusters": n_clusters}
    diffs = [r["metrics"][arm_right]["crps"] - r["metrics"][arm_left]["crps"] for r in scored]
    clusters = [r["date"] for r in scored]
    lo, hi = cluster_boot_ci(diffs, clusters, n_boot=n_boot, seed=seed)
    return {"lo": lo, "hi": hi, "n": len(scored), "n_clusters": n_clusters}


def verdict_for_pair(ci_a: dict, ci_b: dict) -> str:
    """Both favour -> ACCEPT; one -> SINGLE-WINDOW; neither -> NULL; either
    under the row floor OR missing an interval endpoint -> INSUFFICIENT."""
    if ci_a["n"] < MIN_FOLD_N or ci_b["n"] < MIN_FOLD_N:
        return "INSUFFICIENT"
    if ci_a["lo"] is None or ci_a["hi"] is None or ci_b["lo"] is None or ci_b["hi"] is None:
        return "INSUFFICIENT"
    fav_a, fav_b = ci_a["hi"] < 0.0, ci_b["hi"] < 0.0
    if fav_a and fav_b:
        return "ACCEPT"
    if fav_a or fav_b:
        return "SINGLE-WINDOW"
    return "NULL"


def build_paired_losses(scored_by_fold: Dict[str, List[dict]], best_r: float, best_beta: float) -> List[dict]:
    """Q9: fold/date/game/pitcher, each arm's CRPS, both paired deltas, the
    as-of params and THAT ROW's OWN cpcv split id (AMENDMENT 6(a): each
    scored row already carries its own "split_id", set at scoring time --
    never one shared value) for EVERY scored row."""
    out: List[dict] = []
    for label, scored in scored_by_fold.items():
        for row in scored:
            crps = {arm: row["metrics"][arm]["crps"] for arm in ARMS}
            out.append({
                "fold": label, "date": str(row["date"]), "game_pk": row["game_pk"],
                "pitcher": row["player_id"],
                "crps_a": crps["A"], "crps_b": crps["B"], "crps_c": crps["C"],
                "delta_b_minus_a": crps["B"] - crps["A"], "delta_c_minus_a": crps["C"] - crps["A"],
                "r": best_r, "beta": best_beta, "history_cutoff": str(row["date"]),
                "split_id": row.get("split_id"),
            })
    return out


