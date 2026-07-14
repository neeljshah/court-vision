"""scripts.platformkit.live_edge.joint_dist.run_joint -- JOINT-DIST orchestrator.
Fits joint.py's copula on NBA discovery (pts,reb,ast) and gates it against the
independence baseline on the RESERVE (2025-26), OOS. Reuses promote_gate's
generic paired_test/bh_correct/class_level_test/split_reserve_halves
(imported read-only -- same gate pattern as the promoted tail-calib class,
adapted to the joint/energy-score statistic).

Report-only: writes data/omni/live_edge/joint_dist/JOINT_REPORT.md. No claims
journal write (this lane owns no journal).
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd

from scripts.platformkit.live_edge import tails as tl
from scripts.platformkit.live_edge.joint_dist import joint as jt
from scripts.platformkit.live_edge.tail_calib import promote_gate as pg

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
OUT_DIR = REPO_ROOT / "data" / "omni" / "live_edge" / "joint_dist"
STAT_COLS = ["pts", "reb", "ast"]
MIN_RESERVE_N = 10
N_SAMPLES = 3000
SEEDS = [0, 1]
Q_LEGS = [0.75, 0.90]


def qualifying_entities(disc: pd.DataFrame, reserve: pd.DataFrame, entity_col: str) -> list:
    dn = disc.groupby(entity_col).size()
    rn = reserve.groupby(entity_col).size()
    both = sorted(set(dn[dn >= tl.MIN_N].index) & set(rn[rn >= MIN_RESERVE_N].index))
    return both


def entity_es_diffs(entity_id, dep, marginals, reserve: pd.DataFrame, entity_col: str,
                     stat_cols: list[str], device: str) -> np.ndarray:
    """Per-game energy-score differential (independence ES - joint ES;
    positive = joint wins), averaged over SEEDS to damp MC sampling noise."""
    rows = reserve[reserve[entity_col] == entity_id]
    actual = rows[stat_cols].to_numpy(dtype=float)
    if len(actual) == 0:
        return np.array([])
    acc = np.zeros(len(actual))
    for seed in SEEDS:
        cloud_dep = jt.sample_cloud(entity_id, dep, marginals, stat_cols, N_SAMPLES, device, seed, independence=False)
        cloud_ind = jt.sample_cloud(entity_id, dep, marginals, stat_cols, N_SAMPLES, device, seed, independence=True)
        es_joint = jt.energy_scores(cloud_dep, actual, device)
        es_indep = jt.energy_scores(cloud_ind, actual, device)
        acc += (es_indep - es_joint)
    return acc / len(SEEDS)


def run_gate_table(entities: list, dep, marginals, reserve: pd.DataFrame, entity_col: str,
                    stat_cols: list[str], device: str) -> pd.DataFrame:
    half_a, half_b = pg.split_reserve_halves(reserve)
    rows = []
    for e in entities:
        diffs = entity_es_diffs(e, dep, marginals, reserve, entity_col, stat_cols, device)
        diffs_a = entity_es_diffs(e, dep, marginals, half_a, entity_col, stat_cols, device)
        diffs_b = entity_es_diffs(e, dep, marginals, half_b, entity_col, stat_cols, device)
        pooled = pg.paired_test(diffs)
        a_res = pg.paired_test(diffs_a)
        b_res = pg.paired_test(diffs_b)
        rows.append({"entity_id": e, "n_pooled": pooled["n"], "mean_pooled": pooled["mean"],
                      "p_pooled": pooled["p_value"], "n_half_a": a_res["n"], "mean_half_a": a_res["mean"],
                      "n_half_b": b_res["n"], "mean_half_b": b_res["mean"]})
    table = pd.DataFrame(rows)
    table["bh_q"] = pg.bh_correct(table["p_pooled"].fillna(1.0))
    dir_pooled, dir_a, dir_b = np.sign(table["mean_pooled"]), np.sign(table["mean_half_a"]), np.sign(table["mean_half_b"])
    halves_ok = (table["n_half_a"] >= pg.MIN_HALF_ROWS) & (table["n_half_b"] >= pg.MIN_HALF_ROWS)
    same_dir = (dir_pooled == dir_a) & (dir_pooled == dir_b) & (dir_pooled != 0)
    table["survivor"] = halves_ok & same_dir & (table["bh_q"] < pg.BH_ALPHA)
    return table


def sgp_calibration_table(entities: list, dep, marginals, reserve: pd.DataFrame, entity_col: str,
                           stat_cols: list[str], device: str) -> pd.DataFrame:
    rows = []
    for q in Q_LEGS:
        predicted_indep = jt.independence_event_prob(q, len(stat_cols))
        tot_hits = tot_n = 0
        weighted_copula = weighted_n = 0.0
        for e in entities:
            thr = jt.leg_thresholds(e, marginals, stat_cols, q)
            actual = reserve[reserve[entity_col] == e][stat_cols].to_numpy(dtype=float)
            n = len(actual)
            if n == 0:
                continue
            hits = int(np.all(actual >= thr[None, :], axis=1).sum())
            tot_hits += hits
            tot_n += n
            cloud = jt.sample_cloud(e, dep, marginals, stat_cols, N_SAMPLES, device, seed=0, independence=False)
            weighted_copula += jt.copula_event_prob(cloud, thr) * n
            weighted_n += n
        rows.append({"q_leg": q, "predicted_independence": predicted_indep,
                     "predicted_copula": weighted_copula / weighted_n if weighted_n else float("nan"),
                     "realized": tot_hits / tot_n if tot_n else float("nan"), "n_games": tot_n})
    return pd.DataFrame(rows)


def _write_report(corr_pooled: np.ndarray, stat_cols: list[str], gate_table: pd.DataFrame,
                   class_result: dict, sgp_table: pd.DataFrame, device: str) -> pathlib.Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gate_table.to_parquet(OUT_DIR / "gate_table.parquet", index=False)
    survivors = gate_table[gate_table["survivor"]]
    L = ["# JOINT-DIST report -- GPU joint predictive distribution vs INDEPENDENCE "
         "baseline on NBA player (pts,reb,ast), OOS 2025-26 reserve "
         "(calibration language only, edge_claimed=False)\n\n",
         f"GPU device: {device}\n\n",
         "## Correlation matrix (league-pooled, copula z-score space, discovery)\n\n",
         f"stats order: {stat_cols}\n\n{pd.DataFrame(corr_pooled, index=stat_cols, columns=stat_cols).round(3).to_string()}\n\n",
         "## Energy-score head-to-head (per-entity paired test, independence - joint; positive = joint wins)\n\n",
         f"entities tested: {len(gate_table)}\n",
         f"survivors (BH q<0.05 pooled AND same-direction both trailing-date halves): {len(survivors)} / {len(gate_table)}\n\n",
         f"## CLASS-level pooled test (clustered by entity, n={class_result['n_entities']})\n\n",
         f"- mean per-game energy-score delta (independence-joint): {class_result['mean']:+.4f} "
         f"95%CI [{class_result['ci_lo']:+.4f}, {class_result['ci_hi']:+.4f}]\n",
         f"- p-value: {class_result['p_value']:.4g}\n\n",
         "## SGP-shaped joint-threshold event calibration (pooled across entities)\n\n",
         sgp_table.round(5).to_string(index=False) + "\n\n",
         "## Not verified\n\n"
         "- Correlation fit is IN-SAMPLE on discovery (same convention as calib.py's marginals); "
         "no held-out check of the correlation matrix ITSELF (only the resulting joint-score is OOS).\n"
         "- Copula assumes elliptical (Gaussian) dependence; tail-dependence beyond what a Gaussian "
         "copula captures is not modeled (marginals already carry their own tier-1 fat-tail correction).\n"
         "- Energy score is an MC approximation (finite sample cloud); 2 seeds reduce but do not eliminate "
         "sampling noise.\n"
         "- (pts,fg3m) extension and per-half correlation refit not run this lane (time-boxed to the "
         "highest-corr triple).\n"]
    path = OUT_DIR / "JOINT_REPORT.md"
    path.write_text("".join(L), encoding="ascii")
    return path


def main() -> int:
    device = jt.device_string()
    print(f"[joint] device={device}")
    box = tl.load_nba_player_box()
    disc, reserve = tl.split_nba_discovery_reserve(box)
    entity_col = "player_id"

    entities = qualifying_entities(disc, reserve, entity_col)
    print(f"[joint] qualifying entities (disc>={tl.MIN_N} & reserve>={MIN_RESERVE_N}): {len(entities)}")

    marginals = jt.fit_marginals(disc, entity_col, STAT_COLS)
    dep, pooled_corr = jt.fit_dependence(disc, entity_col, STAT_COLS, marginals, jt.DEVICE)

    gate_table = run_gate_table(entities, dep, marginals, reserve, entity_col, STAT_COLS, jt.DEVICE)
    class_result = pg.class_level_test(gate_table)
    sgp_table = sgp_calibration_table(entities, dep, marginals, reserve, entity_col, STAT_COLS, jt.DEVICE)

    path = _write_report(pooled_corr, STAT_COLS, gate_table, class_result, sgp_table, device)
    print(f"[joint] n_survivors={int(gate_table['survivor'].sum())}/{len(gate_table)}")
    print(f"[joint] class mean={class_result['mean']:+.4f} p={class_result['p_value']:.4g} "
          f"ci=[{class_result['ci_lo']:+.4f},{class_result['ci_hi']:+.4f}]")
    print(f"[joint] wrote {path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
