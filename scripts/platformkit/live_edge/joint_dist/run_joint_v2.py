"""scripts.platformkit.live_edge.joint_dist.run_joint_v2 -- JOINT-EXTEND
orchestrator. Two questions per stat group, same promote_gate methodology
(per-entity paired test, BH, both-halves, class-level) JOINT-DIST v1 used:
  (1) independence vs gaussian -- sanity-check reproduction of v1's incumbent.
  (2) gaussian vs t-copula -- does the fatter-tailed Student-t copula beat
      the Gaussian copula OOS? Re-reports the SGP joint-tail calibration
      table with a third (t-copula) column, for both (pts,reb,ast) and the
      NEW (pts,reb,ast,fg3m) 4-vector.

Report-only: writes data/omni/live_edge/joint_dist/v2/JOINT_V2_REPORT.md.
No claims journal write (this lane owns no journal). Imports joint.py,
run_joint.py, promote_gate.py read-only (never edited).
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd

from scripts.platformkit.live_edge import tails as tl
from scripts.platformkit.live_edge.joint_dist import joint as jt
from scripts.platformkit.live_edge.joint_dist import joint_v2 as jv2
from scripts.platformkit.live_edge.joint_dist import run_joint as rj
from scripts.platformkit.live_edge.tail_calib import promote_gate as pg

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
OUT_DIR = REPO_ROOT / "data" / "omni" / "live_edge" / "joint_dist" / "v2"
STAT_GROUPS = {"pts_reb_ast": ["pts", "reb", "ast"],
               "pts_reb_ast_fg3m": ["pts", "reb", "ast", "fg3m"]}
N_SAMPLES = rj.N_SAMPLES
SEEDS = rj.SEEDS
Q_LEGS = rj.Q_LEGS


def three_way_diffs(entity_id, dep, marginals, nu, reserve: pd.DataFrame, entity_col: str,
                     stat_cols: list[str], device: str) -> tuple[np.ndarray, np.ndarray]:
    """Per-game energy-score differentials averaged over SEEDS: (independence
    - gaussian) and (gaussian - t_copula); positive = the 2nd model wins."""
    rows = reserve[reserve[entity_col] == entity_id]
    actual = rows[stat_cols].to_numpy(dtype=float)
    if len(actual) == 0:
        return np.array([]), np.array([])
    ig_acc, gt_acc = np.zeros(len(actual)), np.zeros(len(actual))
    for seed in SEEDS:
        cloud_i = jt.sample_cloud(entity_id, dep, marginals, stat_cols, N_SAMPLES, device, seed, independence=True)
        cloud_g = jt.sample_cloud(entity_id, dep, marginals, stat_cols, N_SAMPLES, device, seed, independence=False)
        cloud_t = jv2.sample_cloud_t(entity_id, dep, marginals, stat_cols, N_SAMPLES, device, seed, nu, independence=False)
        es_i, es_g, es_t = (jt.energy_scores(c, actual, device) for c in (cloud_i, cloud_g, cloud_t))
        ig_acc += (es_i - es_g)
        gt_acc += (es_g - es_t)
    return ig_acc / len(SEEDS), gt_acc / len(SEEDS)


def gate_table_from_diffs(entities: list, per_entity: dict, label: str) -> pd.DataFrame:
    """promote_gate-style table from precomputed per-entity (full, half_a,
    half_b) diff arrays -- avoids resampling clouds a 2nd time per comparison."""
    rows = []
    for e in entities:
        full, half_a, half_b = per_entity[e]
        pooled, a_res, b_res = pg.paired_test(full), pg.paired_test(half_a), pg.paired_test(half_b)
        rows.append({"entity_id": e, "n_pooled": pooled["n"], "mean_pooled": pooled["mean"],
                      "p_pooled": pooled["p_value"], "n_half_a": a_res["n"], "mean_half_a": a_res["mean"],
                      "n_half_b": b_res["n"], "mean_half_b": b_res["mean"]})
    table = pd.DataFrame(rows)
    table["bh_q"] = pg.bh_correct(table["p_pooled"].fillna(1.0))
    dir_p, dir_a, dir_b = np.sign(table["mean_pooled"]), np.sign(table["mean_half_a"]), np.sign(table["mean_half_b"])
    halves_ok = (table["n_half_a"] >= pg.MIN_HALF_ROWS) & (table["n_half_b"] >= pg.MIN_HALF_ROWS)
    same_dir = (dir_p == dir_a) & (dir_p == dir_b) & (dir_p != 0)
    table["survivor"] = halves_ok & same_dir & (table["bh_q"] < pg.BH_ALPHA)
    table["comparison"] = label
    return table


def sgp_table_3way(entities: list, dep, marginals, nu, reserve: pd.DataFrame, entity_col: str,
                    stat_cols: list[str], device: str) -> pd.DataFrame:
    rows = []
    for q in Q_LEGS:
        predicted_indep = jt.independence_event_prob(q, len(stat_cols))
        tot_hits = tot_n = 0
        w_gauss = w_t = w_n = 0.0
        for e in entities:
            thr = jt.leg_thresholds(e, marginals, stat_cols, q)
            actual = reserve[reserve[entity_col] == e][stat_cols].to_numpy(dtype=float)
            n = len(actual)
            if n == 0:
                continue
            hits = int(np.all(actual >= thr[None, :], axis=1).sum())
            tot_hits += hits
            tot_n += n
            cloud_g = jt.sample_cloud(e, dep, marginals, stat_cols, N_SAMPLES, device, seed=0, independence=False)
            cloud_t = jv2.sample_cloud_t(e, dep, marginals, stat_cols, N_SAMPLES, device, seed=0, nu=nu, independence=False)
            w_gauss += jt.copula_event_prob(cloud_g, thr) * n
            w_t += jt.copula_event_prob(cloud_t, thr) * n
            w_n += n
        rows.append({"q_leg": q, "predicted_independence": predicted_indep,
                     "predicted_gaussian": w_gauss / w_n if w_n else float("nan"),
                     "predicted_t_copula": w_t / w_n if w_n else float("nan"),
                     "realized": tot_hits / tot_n if tot_n else float("nan"), "n_games": tot_n})
    return pd.DataFrame(rows)


def run_one_group(stat_cols: list[str], box: pd.DataFrame, entity_col: str, device: str) -> dict:
    disc, reserve = tl.split_nba_discovery_reserve(box)
    entities = rj.qualifying_entities(disc, reserve, entity_col)
    marginals = jt.fit_marginals(disc, entity_col, stat_cols)
    dep, pooled_corr = jt.fit_dependence(disc, entity_col, stat_cols, marginals, device)
    nu = jv2.fit_dof(disc, entity_col, stat_cols, marginals, pooled_corr, device)

    half_a, half_b = pg.split_reserve_halves(reserve)
    per_ig, per_gt = {}, {}
    for e in entities:
        full_ig, full_gt = three_way_diffs(e, dep, marginals, nu, reserve, entity_col, stat_cols, device)
        a_ig, a_gt = three_way_diffs(e, dep, marginals, nu, half_a, entity_col, stat_cols, device)
        b_ig, b_gt = three_way_diffs(e, dep, marginals, nu, half_b, entity_col, stat_cols, device)
        per_ig[e], per_gt[e] = (full_ig, a_ig, b_ig), (full_gt, a_gt, b_gt)

    table_ig = gate_table_from_diffs(entities, per_ig, "independence_vs_gaussian")
    table_gt = gate_table_from_diffs(entities, per_gt, "gaussian_vs_tcopula")
    class_ig, class_gt = pg.class_level_test(table_ig), pg.class_level_test(table_gt)
    sgp = sgp_table_3way(entities, dep, marginals, nu, reserve, entity_col, stat_cols, device)
    return {"stat_cols": stat_cols, "n_entities": len(entities), "nu": nu,
            "table_ig": table_ig, "table_gt": table_gt,
            "class_ig": class_ig, "class_gt": class_gt, "sgp": sgp}


def _write_report(results: dict, device: str) -> pathlib.Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    L = ["# JOINT-V2 report -- Student-t copula vs Gaussian-copula incumbent, "
         "NBA player joint stats, OOS 2025-26 reserve "
         "(calibration language only, edge_claimed=False)\n\n",
         f"GPU device: {device}\n\n"]
    for name, r in results.items():
        r["table_ig"].to_parquet(OUT_DIR / f"gate_table_ig_{name}.parquet", index=False)
        r["table_gt"].to_parquet(OUT_DIR / f"gate_table_gt_{name}.parquet", index=False)
        surv_gt = r["table_gt"][r["table_gt"]["survivor"]]
        L += [f"## Stat group: {name} ({r['stat_cols']})\n\n",
              f"entities tested: {r['n_entities']}; fitted t-copula dof "
              f"(global, GPU likelihood grid-search): {r['nu']:.1f}\n\n",
              "### independence vs gaussian (sanity-check reproduction of v1)\n\n",
              f"class mean(indep-gauss): {r['class_ig']['mean']:+.4f} p={r['class_ig']['p_value']:.4g} "
              f"ci=[{r['class_ig']['ci_lo']:+.4f},{r['class_ig']['ci_hi']:+.4f}]\n\n",
              "### gaussian vs t-copula (the new question)\n\n",
              f"survivors (BH q<0.05 pooled AND same-direction both halves): "
              f"{len(surv_gt)} / {len(r['table_gt'])}\n",
              f"class mean(gauss-t; positive=t-copula wins): {r['class_gt']['mean']:+.4f} "
              f"p={r['class_gt']['p_value']:.4g} "
              f"ci=[{r['class_gt']['ci_lo']:+.4f},{r['class_gt']['ci_hi']:+.4f}]\n\n",
              "### SGP joint-tail calibration (independence / gaussian / t-copula / realized)\n\n",
              r["sgp"].round(5).to_string(index=False) + "\n\n"]
    L.append("## Not verified\n\n"
             "- dof (nu) is a single GLOBAL value fit on pooled discovery correlation, not "
             "per-entity -- documented simplification (per-entity nu not attempted).\n"
             "- Per-entity correlation matrix is reused verbatim from the Gaussian fit "
             "(joint.fit_dependence); only the mixing/tail shape changes -- the dependence "
             "STRENGTH parameter is not jointly re-estimated with nu.\n"
             "- Energy score remains an MC approximation (2 seeds for the gate; the SGP table's "
             "gaussian/t-copula columns use seed=0 only, same convention as v1).\n"
             "- 4-vector (pts,reb,ast,fg3m) reuses the SAME qualifying-entity/reserve machinery as "
             "the 3-way; fg3m's marginal fit is tier-1 validated (WIDTH-EXPAND) but its JOINT "
             "dependence with the other three was never tested before this lane.\n")
    path = OUT_DIR / "JOINT_V2_REPORT.md"
    path.write_text("".join(L), encoding="ascii")
    return path


def main() -> int:
    device = jt.device_string()
    print(f"[joint_v2] device={device}")
    box = tl.load_nba_player_box()
    entity_col = "player_id"
    results = {}
    for name, stat_cols in STAT_GROUPS.items():
        print(f"[joint_v2] running group {name} {stat_cols}")
        r = run_one_group(stat_cols, box, entity_col, jt.DEVICE)
        results[name] = r
        print(f"[joint_v2] {name}: n={r['n_entities']} nu={r['nu']:.1f} "
              f"class(gauss-t) mean={r['class_gt']['mean']:+.4f} p={r['class_gt']['p_value']:.4g}")
    path = _write_report(results, device)
    print(f"[joint_v2] wrote {path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
