"""scripts.platformkit.proof_nba.gate_b_diagnostics -- Q06 Gate B adversarial-review helpers.

Split out of gate_b_tracking_ablation.py to keep that module under the 300 LOC cap.
(1) constant_in_train_families: a family whose columns are ALL constant after the model's
    own train-median imputation carries zero information -- any verdict attributed to it
    alone must be NOT_TESTED, never CEILING_ZERO (a degenerate {0,0,0} CI is not a null
    result, it is an untestable one).
(2) seed_stability: LightGBM at colsample_bytree=1.0 is deterministic, so re-running the
    same RNG_SEED is not stability evidence. Refits at colsample_bytree<1 across several
    seeds and reports whether the sign and CI class agree.
(3) mde_80pct: minimum detectable effect at 80 pct power backed out of the already-computed
    95 pct CI half-width (no new bootstrap needed).
(4) adv_stats_covers_2025_26 / within_2025_26_dm_only: 2025-26 preflight + the one corpus
    with full per-game defender_matchup coverage, gated on that preflight.

CALIBRATION ONLY. ASCII only. n_jobs=2. <=300 LOC.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Sequence
import numpy as np
import pandas as pd
import lightgbm as lgb

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
from scripts.platformkit.dist_metrics import crps_ensemble_rows  # noqa: E402
from scripts.platformkit.proof_nba.prop_game_model import (  # noqa: E402
    RNG_SEED, TAUS, _delta_ci, _rd, split_corpus)


def match_rates_for_corpus(df2: pd.DataFrame, corpus: str, trk_cols: list, hus_cols: list,
                            dm_cols: list, matched_cols: dict) -> dict:
    sub = df2[df2["season"] == corpus]
    def _rate(cols, mcol):
        nonnull = float(sub[cols[0]].notna().mean()) if cols else float("nan")
        join = float(sub[mcol].mean()) if mcol in sub.columns else float("nan")
        return {"join_rate": round(join, 4), "nonnull_rate": round(nonnull, 4)}
    return {"player_tracking_prior_season": _rate(trk_cols, matched_cols["trk"]),
            "hustle_prior_season": _rate(hus_cols, matched_cols["hus"]),
            "defender_matchup_asof": _rate(dm_cols, matched_cols["dm"]), "n_rows": int(len(sub))}


def tracking_feature_importance(xtr: pd.DataFrame, ytr: pd.Series, tracking_cols: list) -> list:
    """Gain-based feature importance (median-quantile fit) restricted to tracking columns."""
    m = lgb.LGBMRegressor(objective="quantile", alpha=0.5, n_estimators=200, num_leaves=15,
                           min_child_samples=30, n_jobs=2, random_state=RNG_SEED,
                           deterministic=True, force_row_wise=True, verbosity=-1,
                           importance_type="gain")
    m.fit(xtr, ytr)
    imp = dict(zip(xtr.columns, m.feature_importances_.tolist()))
    ranked = sorted(((c, imp.get(c, 0.0)) for c in tracking_cols), key=lambda kv: -kv[1])
    return [{"feature": c, "gain": round(float(g), 2)} for c, g in ranked[:15]]


def markdown_table(results: list) -> str:
    lines = ["champion = landed per-game prop model (Q15); baseline comparison is champion vs "
             "champion+tracking; 2023-24 is a within-season fallback split; calibration only; "
             "no monetary claim. CEILING_ZERO = no improvement bigger than mde_80pct detected, "
             "not proof of exactly zero. NOT_TESTED = that family's columns were constant in "
             "train (dead weight), not a measured null.", "",
             "| stat | corpus | n_test | verdict_full | delta_crps_full | mde_80pct | "
             "champ_crps | verdict_dm_only |", "|---|---|---|---|---|---|---|---|"]
    for r in results:
        if r["status"] != "OK":
            lines.append(f"| {r['stat']} | {r['corpus']} | {r.get('n_test', 0)} | "
                          f"{r['status']} | - | - | - | - |")
            continue
        d = r["delta_crps_full"]
        lines.append(f"| {r['stat']} | {r['corpus']} | {r['n_test']} | {r['verdict_crps_full']} | "
                      f"{d['point']:.4f} [{d['ci_lo']:.4f}, {d['ci_hi']:.4f}] | "
                      f"{r['mde_80pct_crps_full']:.4f} | {r['champion_crps_level']:.4f} | "
                      f"{r['verdict_crps_defender_matchup_only']} |")
    return "\n".join(lines)


def overall_verdicts(results: list, stats: list) -> dict:
    out = {}
    for stat in stats:
        verdicts = [r["verdict_crps_full"] for r in results if r["stat"] == stat and r["status"] == "OK"]
        if not verdicts or all(v == "NOT_TESTED" for v in verdicts):
            out[stat] = "NOT_TESTED"
        else:
            out[stat] = "CEILING_POSITIVE" if all(v == "CEILING_POSITIVE" for v in verdicts) else "CEILING_ZERO"
    return out


def constant_in_train_families(train_df: pd.DataFrame, families: dict) -> dict:
    """families: {name: [cols]}. Checks post-imputation values (train median, then 0.0) --
    the same values the model actually sees. all_constant=True means that family is dead
    weight in THIS split."""
    out = {}
    for name, cols in families.items():
        if not cols:
            out[name] = {"constant_cols": [], "all_constant": False}
            continue
        med = train_df[cols].median()
        imputed = train_df[cols].fillna(med).fillna(0.0)
        const_cols = [c for c in cols if imputed[c].nunique(dropna=False) <= 1]
        out[name] = {"constant_cols": const_cols, "all_constant": len(const_cols) == len(cols)}
    return out


def mde_80pct(ci: dict) -> float:
    """MDE at 80 pct power, 5 pct two-sided alpha: 2.802 * SE, SE backed out of the CI
    (95 pct CI = point +/- 1.96*SE, so SE = (ci_hi - ci_lo) / 3.92)."""
    se = (ci["ci_hi"] - ci["ci_lo"]) / 3.92
    return round(2.802 * se, 5)


def _lgb_quantiles_seeded(xtr, ytr, xte, seed: int, colsample: float) -> np.ndarray:
    preds = np.zeros((len(xte), len(TAUS)))
    for i, tau in enumerate(TAUS):
        m = lgb.LGBMRegressor(objective="quantile", alpha=tau, n_estimators=200, num_leaves=15,
                               min_child_samples=30, n_jobs=2, random_state=seed,
                               colsample_bytree=colsample, deterministic=True,
                               force_row_wise=True, verbosity=-1)
        preds[:, i] = m.fit(xtr, ytr).predict(xte)
    preds.sort(axis=1)
    return preds


def seed_stability(train_df: pd.DataFrame, test_df: pd.DataFrame, fcols_champ: list,
                    fcols_chall: list, stat: str, seeds: Sequence[int],
                    colsample: float = 0.8) -> dict:
    """Refit champion & challenger (full arm) at each seed with colsample_bytree<1.
    Reuses the champion's own game-clustered _delta_ci; only the fit is re-seeded."""
    from scripts.platformkit.proof_nba.gate_b_tracking_ablation import ceiling_verdict
    ytr = train_df[stat].astype(float)
    yte = test_df[stat].astype(float).to_numpy()
    gids = test_df["game_id"].to_numpy()
    med_c, med_h = train_df[fcols_champ].median(), train_df[fcols_chall].median()
    xtr_c = train_df[fcols_champ].fillna(med_c).fillna(0.0)
    xte_c = test_df[fcols_champ].fillna(med_c).fillna(0.0)
    xtr_h = train_df[fcols_chall].fillna(med_h).fillna(0.0)
    xte_h = test_df[fcols_chall].fillna(med_h).fillna(0.0)
    per_seed = []
    for seed in seeds:
        q_c = _lgb_quantiles_seeded(xtr_c, ytr, xte_c, seed, colsample)
        q_h = _lgb_quantiles_seeded(xtr_h, ytr, xte_h, seed, colsample)
        ci = _delta_ci(yte, q_c, q_h, gids, crps_ensemble_rows)
        per_seed.append({"seed": int(seed), **_rd(ci), "verdict": ceiling_verdict(ci)})
    signs = {(1 if r["point"] > 0 else (-1 if r["point"] < 0 else 0)) for r in per_seed}
    verdicts = {r["verdict"] for r in per_seed}
    return {"colsample_bytree": colsample, "per_seed": per_seed,
            "seed_stable": len(signs) == 1 and len(verdicts) == 1}


def adv_stats_covers_2025_26() -> bool:
    """Preflight: does data/player_adv_stats.parquet (the champion's advanced-stats join)
    carry any 2025-26-season games (Oct 2025 on)? If not, both the 2025-26 cross-season
    corpus and the within-2025-26 variant are blocked (the CHAMPION itself would be
    degraded, not only the challenger)."""
    adv = pd.read_parquet(_REPO / "data" / "player_adv_stats.parquet")
    return bool((pd.to_datetime(adv["game_date"]) >= "2025-10-01").any())


def within_2025_26_dm_only(df2: pd.DataFrame, champ_cols: list, dm_cols: list, stat: str) -> Optional[dict]:
    """The per-game family in isolation, split WITHIN 2025-26 only (70/30, embargoed) --
    the only corpus where defender_matchup has full-season coverage. Filtering df2 to one
    season before calling split_corpus makes it fall into within_season_fallback for free
    (no prior season exists inside the filtered frame)."""
    from scripts.platformkit.proof_nba.gate_b_tracking_ablation import ceiling_verdict
    sdf = df2[df2["season"] == "2025-26"].reset_index(drop=True)
    if len(sdf) < 400:
        return None
    train_df, test_df, split_meta = split_corpus(sdf, "2025-26")
    if len(train_df) < 200 or len(test_df) < 50:
        return None
    fcols_dm = champ_cols + [f"opp_allowed_{stat}_10"] + dm_cols
    fam = constant_in_train_families(train_df, {"defender_matchup": dm_cols})
    ytr = train_df[stat].astype(float)
    yte = test_df[stat].astype(float).to_numpy()
    med_c = train_df[champ_cols + [f"opp_allowed_{stat}_10"]].median()
    med_d = train_df[fcols_dm].median()
    xtr_c = train_df[champ_cols + [f"opp_allowed_{stat}_10"]].fillna(med_c).fillna(0.0)
    xte_c = test_df[champ_cols + [f"opp_allowed_{stat}_10"]].fillna(med_c).fillna(0.0)
    xtr_d = train_df[fcols_dm].fillna(med_d).fillna(0.0)
    xte_d = test_df[fcols_dm].fillna(med_d).fillna(0.0)
    from scripts.platformkit.proof_nba.prop_game_model import lgb_quantiles
    q_c = lgb_quantiles(xtr_c, ytr, xte_c)
    q_d = lgb_quantiles(xtr_d, ytr, xte_d)
    ci = _delta_ci(yte, q_c, q_d, test_df["game_id"].to_numpy(), crps_ensemble_rows)
    verdict = "NOT_TESTED" if fam["defender_matchup"]["all_constant"] else ceiling_verdict(ci)
    return {"stat": stat, "corpus": "2025-26_within", **split_meta, "n_train": int(len(train_df)),
            "n_test": int(len(test_df)), "family_constant_in_train": fam,
            "delta_crps_defender_matchup_only": {"positive_means_challenger_better": True, **_rd(ci)},
            "verdict": verdict, "edge_claimed": False}
