"""scripts.platformkit.live_edge.tail_calib.run_gpu_dist_v2 -- GPU-DIST v2
4-way head-to-head: Normal baseline vs empirical-quantile incumbent (tier-1)
vs GPU-v1 (gpu_dist.py, MIXED/narrows) vs GPU-v2 (gpu_dist_v2.py,
coverage-constrained affine rescale), on BOTH promoted corpora (NBA player
points, MLB team runs), through the SAME promote_gate methodology as
run_gpu_dist.py (paired per-game CRPS, BH across entities, both-halves-
same-direction, class-level pooled test clustered by entity).

WIN BAR (strict, per LIVE-EDGE rails): v2 must, on BOTH corpora, keep central
50/80/90% coverage error NO WORSE than empirical AND improve PIT-KS AND not
lose CRPS vs empirical. Anything short = incumbent stays.

Report-only, no journal writes, edge_claimed=False.

INVARIANTS: <=300 LOC. ASCII stdout. Never writes data/registry/.
"""
from __future__ import annotations

import pathlib
import time

import numpy as np
import pandas as pd

from scripts.platformkit.live_edge import tails as tl
from scripts.platformkit.live_edge.tail_calib import calib as tc
from scripts.platformkit.live_edge.tail_calib import calib_v2 as tc2
from scripts.platformkit.live_edge.tail_calib import gpu_dist as gd
from scripts.platformkit.live_edge.tail_calib import gpu_dist_v2 as gd2
from scripts.platformkit.live_edge.tail_calib import promote_gate as pg

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
OUT_DIR = REPO_ROOT / "data" / "omni" / "live_edge" / "tail_calib" / "gpu_v2"
MIN_RESERVE_ROWS = 10  # same floor as run_gpu_dist/mlb_replicate/apex
SEEDS = (0, 1)  # 2 seeds per rails; GPU fits here are deterministic-enough
                # (no random init beyond LightGBM/torch internals) -- 2 runs
                # are a stability check, not a resample.

PPF = {"normal": lambda q, m: tc.baseline_ppf(q, m["mean"], m["std"]),
       "empirical": lambda q, m: tc.tail_aware_ppf(q, m["quantiles"]),
       "gpu_v1": lambda q, m: tc2.tail_aware_v2_ppf(q, m["quantiles"]),
       "gpu_v2": lambda q, m: tc2.tail_aware_v2_ppf(q, m["quantiles"])}
CDF = {"normal": lambda x, m: tc.baseline_cdf(x, m["mean"], m["std"]),
       "empirical": lambda x, m: tc.tail_aware_cdf(x, m["quantiles"]),
       "gpu_v1": lambda x, m: tc2.tail_aware_v2_cdf(x, m["quantiles"]),
       "gpu_v2": lambda x, m: tc2.tail_aware_v2_cdf(x, m["quantiles"])}
NAMES = ("normal", "empirical", "gpu_v1", "gpu_v2")


def evaluate_4way(reserve: pd.DataFrame, fits: dict[str, dict],
                   entity_col: str, stat_col: str) -> pd.DataFrame:
    rows = []
    for _, r in reserve.iterrows():
        e = r[entity_col]
        ms = {n: fits[n].get(e) for n in NAMES}
        if any(m is None or m.get("insufficient") for m in ms.values()):
            continue
        x = float(r[stat_col])
        row = {"entity": e, "actual": x}
        for n in NAMES:
            row[f"pit_{n}"] = min(max(CDF[n](x, ms[n]), 0.0), 1.0)
            row[f"crps_{n}"] = tc.crps_approx(lambda q, nn=n, mm=ms[n]: PPF[nn](q, mm), x)
        rows.append(row)
    return pd.DataFrame(rows)


def coverage_4way(reserve: pd.DataFrame, fits: dict[str, dict],
                   entity_col: str, stat_col: str) -> pd.DataFrame:
    rows = []
    for level in tc.COVERAGE_LEVELS:
        lo_q, hi_q = round((1 - level) / 2, 4), round(1 - (1 - level) / 2, 4)
        hits = {n: 0 for n in NAMES}
        total = 0
        for _, r in reserve.iterrows():
            e = r[entity_col]
            ms = {n: fits[n].get(e) for n in NAMES}
            if any(m is None or m.get("insufficient") for m in ms.values()):
                continue
            x = float(r[stat_col])
            for n in NAMES:
                lo_v, hi_v = PPF[n](lo_q, ms[n]), PPF[n](hi_q, ms[n])
                hits[n] += int(lo_v <= x <= hi_v)
            total += 1
        row = {"nominal": level, "n": total}
        for n in NAMES:
            row[f"realized_{n}"] = hits[n] / total if total else float("nan")
        rows.append(row)
    return pd.DataFrame(rows)


def gate_v2_vs_incumbent(reserve: pd.DataFrame, fit_emp: dict, fit_v2: dict,
                          entity_col: str, stat_col: str) -> pd.DataFrame:
    """Same gate shape as run_gpu_dist.gate_gpu_vs_incumbent (imported
    pattern, kept local since it's v2-specific pairing): per-entity paired
    CRPS diff (empirical - gpu_v2; positive = v2 wins), BH, both-halves."""
    half_a, half_b = pg.split_reserve_halves(reserve)
    entities = sorted(e for e, m in fit_emp.items() if not m.get("insufficient") and e in fit_v2)

    def _diff(eid, slice_df):
        rows = slice_df[slice_df[entity_col] == eid]
        if not len(rows):
            return np.array([])
        actual = rows[stat_col].to_numpy(dtype=float)
        m1, m2 = fit_emp[eid], fit_v2[eid]
        crps_emp = np.array([tc.crps_approx(lambda q: PPF["empirical"](q, m1), x) for x in actual])
        crps_v2 = np.array([tc.crps_approx(lambda q: PPF["gpu_v2"](q, m2), x) for x in actual])
        return crps_emp - crps_v2

    out = []
    for e in entities:
        pooled = _diff(e, reserve)
        if len(pooled) < MIN_RESERVE_ROWS:
            continue
        a_res, b_res = pg.paired_test(_diff(e, half_a)), pg.paired_test(_diff(e, half_b))
        pooled_res = pg.paired_test(pooled)
        out.append({"entity_id": e, "n_pooled": pooled_res["n"], "mean_pooled": pooled_res["mean"],
                     "p_pooled": pooled_res["p_value"], "n_half_a": a_res["n"], "mean_half_a": a_res["mean"],
                     "n_half_b": b_res["n"], "mean_half_b": b_res["mean"]})
    table = pd.DataFrame(out)
    if not len(table):
        return table
    table["bh_q"] = pg.bh_correct(table["p_pooled"].fillna(1.0))
    dir_p, dir_a, dir_b = np.sign(table["mean_pooled"]), np.sign(table["mean_half_a"]), np.sign(table["mean_half_b"])
    ok_halves = (table["n_half_a"] >= pg.MIN_HALF_ROWS) & (table["n_half_b"] >= pg.MIN_HALF_ROWS)
    table["survivor"] = ok_halves & (dir_p == dir_a) & (dir_p == dir_b) & (dir_p != 0) & (table["bh_q"] < pg.BH_ALPHA)
    return table


def run_observable_seed(disc: pd.DataFrame, reserve: pd.DataFrame,
                         entity_col: str, stat_col: str, seed: int) -> dict:
    np.random.seed(seed)  # gate/eval have no resampling, but keeps the seed loop honest/reproducible
    fit_emp = tc.fit_predictors(disc, entity_col, stat_col)
    t0 = time.perf_counter()
    fit_v1_gpu = gd.fit_gpu_quantiles(disc, entity_col, stat_col)
    fit_gpu_v1 = gd.predict_entity_quantiles(fit_v1_gpu)
    v2_fit = gd2.fit_gpu_v2(disc, entity_col, stat_col)
    train_seconds = time.perf_counter() - t0

    fits = {"normal": fit_emp, "empirical": fit_emp, "gpu_v1": fit_gpu_v1, "gpu_v2": v2_fit["quantiles"]}
    row_eval = evaluate_4way(reserve, fits, entity_col, stat_col)
    coverage = coverage_4way(reserve, fits, entity_col, stat_col)
    gate = gate_v2_vs_incumbent(reserve, fit_emp, v2_fit["quantiles"], entity_col, stat_col)
    class_result = pg.class_level_test(gate) if len(gate) else {
        "n_entities": 0, "mean": float("nan"), "p_value": float("nan"),
        "ci_lo": float("nan"), "ci_hi": float("nan")}

    ks = {n: tc.pit_uniformity(row_eval[f"pit_{n}"].to_numpy()) for n in NAMES} if len(row_eval) else {}
    crps_mean = {n: float(row_eval[f"crps_{n}"].mean()) for n in NAMES} if len(row_eval) else {}
    return {"seed": seed, "device": v2_fit["device"], "train_seconds": train_seconds,
            "rows_scored": len(row_eval), "n_gate_entities": len(gate),
            "n_gate_survivors": int(gate["survivor"].sum()) if len(gate) else 0,
            "crps_mean": crps_mean, "ks": ks, "coverage": coverage, "gate_class": class_result}


def run_observable(name: str, disc: pd.DataFrame, reserve: pd.DataFrame,
                    entity_col: str, stat_col: str) -> dict:
    seed_results = [run_observable_seed(disc, reserve, entity_col, stat_col, s) for s in SEEDS]
    r = seed_results[0]  # seed 0 is the reported run; others are the stability check below
    r["observable"] = name
    r["seed_crps_v2"] = [s["crps_mean"].get("gpu_v2", float("nan")) for s in seed_results]
    r["seed_ks_v2"] = [s["ks"].get("gpu_v2", {}).get("ks_stat", float("nan")) for s in seed_results]
    return r


def _fmt_ks(d: dict) -> str:
    return " / ".join(f"{n}={d[n]['ks_stat']:.4f}" for n in NAMES) if d else "n/a"


def _verdict(r: dict) -> str:
    central = r["coverage"][r["coverage"]["nominal"].isin([0.50, 0.80, 0.90])]
    err_emp = (central["realized_empirical"] - central["nominal"]).abs().mean()
    err_v2 = (central["realized_gpu_v2"] - central["nominal"]).abs().mean()
    width_kept = err_v2 <= err_emp
    ks_better = r["ks"].get("gpu_v2", {}).get("ks_stat", 1.0) < r["ks"].get("empirical", {}).get("ks_stat", 0.0)
    crps_kept = r["crps_mean"].get("gpu_v2", 1e9) <= r["crps_mean"].get("empirical", 0.0)
    if width_kept and ks_better and crps_kept:
        return "CLEAN_WIN (width kept, PIT improved, CRPS not lost)"
    return ("NOT_CLEAN (width_kept=%s ks_better=%s crps_kept=%s -- central err "
            "empirical=%.4f v2=%.4f)" % (width_kept, ks_better, crps_kept, err_emp, err_v2))


def _write_report(results: list[dict]) -> pathlib.Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    L = ["# GPU_DIST_V2_REPORT -- coverage-constrained GPU quantile model "
         "(affine-rescaled to empirical width) vs Normal vs empirical incumbent "
         "vs GPU-v1 (calibration language only, edge_claimed=False)\n\n"]
    both_clean = True
    for r in results:
        v = _verdict(r)
        if not v.startswith("CLEAN_WIN"):
            both_clean = False
        L.append(f"## {r['observable']}\n\n")
        L.append(f"- GPU device: {r['device']}  (train_seconds={r['train_seconds']:.2f}, seed=0 run)\n")
        L.append(f"- reserve rows scored: {r['rows_scored']}\n")
        L.append(f"- CRPS mean: normal={r['crps_mean'].get('normal', float('nan')):.4f} "
                 f"empirical={r['crps_mean'].get('empirical', float('nan')):.4f} "
                 f"gpu_v1={r['crps_mean'].get('gpu_v1', float('nan')):.4f} "
                 f"gpu_v2={r['crps_mean'].get('gpu_v2', float('nan')):.4f}\n")
        L.append(f"- PIT KS (lower=better): {_fmt_ks(r['ks'])}\n")
        L.append(f"- 2-seed stability -- crps_v2: {['%.4f' % c for c in r['seed_crps_v2']]}  "
                 f"ks_v2: {['%.4f' % k for k in r['seed_ks_v2']]}\n")
        L.append(f"- coverage table:\n\n{r['coverage'].to_string(index=False)}\n\n")
        cr = r["gate_class"]
        L.append(f"- GATE gpu_v2-vs-empirical-incumbent: {r['n_gate_survivors']}/{r['n_gate_entities']} "
                  f"individual survivors (BH q<0.05 + both-halves-same-direction)\n")
        L.append(f"- CLASS-level (clustered by entity, n={cr['n_entities']}): mean CRPS delta "
                  f"(empirical-gpu_v2, positive=v2 wins)={cr['mean']:+.4f} 95%CI "
                  f"[{cr['ci_lo']:+.4f},{cr['ci_hi']:+.4f}] p={cr['p_value']:.4g}\n\n")
        L.append(f"- VERDICT: **{v}**\n\n")
    L.append(f"## Program verdict\n\n- BOTH CORPORA CLEAN WIN: **{both_clean}**\n")
    if both_clean:
        L.append("- Per Fable promotion rules, this is a candidate for naming as an improved "
                  "tier-1 predictive-dist model (coverage-preserving, GPU). NOT self-promoted here "
                  "-- Fable/human ledgers any promotion decision, same as promote_gate.py's precedent.\n")
    else:
        L.append("- Incumbent (empirical-quantile tier-1) STAYS. v2 did not clear the strict win bar "
                  "on both corpora.\n")
    path = OUT_DIR / "GPU_DIST_V2_REPORT.md"
    path.write_text("".join(L), encoding="ascii")
    return path


def main() -> int:
    nba_box = tl.load_nba_player_box()
    nba_disc, nba_reserve = tl.split_nba_discovery_reserve(nba_box)
    mlb_df = tl.load_mlb_team_runs()
    mlb_disc, mlb_reserve = tl.split_mlb_discovery_reserve(mlb_df)

    results = [
        run_observable("NBA player points (player_id/pts)", nba_disc, nba_reserve, "player_id", "pts"),
        run_observable("MLB team runs (team/runs)", mlb_disc, mlb_reserve, "team", "runs"),
    ]
    path = _write_report(results)
    for r in results:
        print(f"[run_gpu_dist_v2] {r['observable']}: device={r['device']} "
              f"gate={r['n_gate_survivors']}/{r['n_gate_entities']} "
              f"crps_v2={r['crps_mean'].get('gpu_v2', float('nan')):.4f} "
              f"crps_empirical={r['crps_mean'].get('empirical', float('nan')):.4f} "
              f"ks_v2={r['ks'].get('gpu_v2', {}).get('ks_stat', float('nan')):.4f} "
              f"ks_empirical={r['ks'].get('empirical', {}).get('ks_stat', float('nan')):.4f}")
    print(f"[run_gpu_dist_v2] wrote {path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
