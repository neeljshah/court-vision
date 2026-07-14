"""scripts.platformkit.live_edge.tail_calib.run_gpu_dist -- GPU-DIST 3-way
head-to-head: Normal baseline vs empirical-quantile incumbent (tail_v1, tier-1
class) vs the GPU-trained conditional quantile model (gpu_dist.py), on BOTH
promoted corpora (NBA player points, MLB team runs), through the SAME
promote_gate methodology (paired per-game CRPS, BH across entities,
both-halves-same-direction, class-level pooled test clustered by entity).

Answers: does the GPU model fix the incumbent's PIT body-shape miscalibration
while keeping the width gain -- i.e. does it BEAT tail_v1 on PIT/coverage/CRPS
OOS, on both corpora? Report-only, no journal writes, edge_claimed=False.

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
from scripts.platformkit.live_edge.tail_calib import promote_gate as pg

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
OUT_DIR = REPO_ROOT / "data" / "omni" / "live_edge" / "tail_calib" / "gpu"
MIN_RESERVE_ROWS = 10  # same floor as mlb_replicate/apex

PPF = {"normal": lambda q, m: tc.baseline_ppf(q, m["mean"], m["std"]),
       "empirical": lambda q, m: tc.tail_aware_ppf(q, m["quantiles"]),
       "gpu": lambda q, m: tc2.tail_aware_v2_ppf(q, m["quantiles"])}
CDF = {"normal": lambda x, m: tc.baseline_cdf(x, m["mean"], m["std"]),
       "empirical": lambda x, m: tc.tail_aware_cdf(x, m["quantiles"]),
       "gpu": lambda x, m: tc2.tail_aware_v2_cdf(x, m["quantiles"])}


def evaluate_3way(reserve: pd.DataFrame, fit_v1: dict, fit_gpu: dict,
                   entity_col: str, stat_col: str) -> pd.DataFrame:
    rows = []
    for _, r in reserve.iterrows():
        e = r[entity_col]
        m1, m2 = fit_v1.get(e), fit_gpu.get(e)
        if m1 is None or m1.get("insufficient") or m2 is None:
            continue
        x = float(r[stat_col])
        row = {"entity": e, "actual": x}
        for name, m in (("normal", m1), ("empirical", m1), ("gpu", m2)):
            row[f"pit_{name}"] = min(max(CDF[name](x, m), 0.0), 1.0)
            row[f"crps_{name}"] = tc.crps_approx(lambda q, n=name, mm=m: PPF[n](q, mm), x)
        rows.append(row)
    return pd.DataFrame(rows)


def coverage_3way(reserve: pd.DataFrame, fit_v1: dict, fit_gpu: dict,
                   entity_col: str, stat_col: str) -> pd.DataFrame:
    rows = []
    for level in tc.COVERAGE_LEVELS:
        lo_q, hi_q = round((1 - level) / 2, 4), round(1 - (1 - level) / 2, 4)
        hits = {n: 0 for n in PPF}
        total = 0
        for _, r in reserve.iterrows():
            e = r[entity_col]
            m1, m2 = fit_v1.get(e), fit_gpu.get(e)
            if m1 is None or m1.get("insufficient") or m2 is None:
                continue
            x = float(r[stat_col])
            for name, m in (("normal", m1), ("empirical", m1), ("gpu", m2)):
                lo_v, hi_v = PPF[name](lo_q, m), PPF[name](hi_q, m)
                hits[name] += int(lo_v <= x <= hi_v)
            total += 1
        row = {"nominal": level, "n": total}
        for name in PPF:
            row[f"realized_{name}"] = hits[name] / total if total else float("nan")
        rows.append(row)
    return pd.DataFrame(rows)


def gate_gpu_vs_incumbent(reserve: pd.DataFrame, fit_v1: dict, fit_gpu: dict,
                           entity_col: str, stat_col: str) -> pd.DataFrame:
    """Same gate as promote_gate.run_gate: per-entity paired CRPS diff
    (empirical - gpu; positive = gpu wins), BH across tested entities,
    both-trailing-date-halves same-direction survivor flag."""
    half_a, half_b = pg.split_reserve_halves(reserve)
    entities = sorted(e for e, m in fit_v1.items()
                       if not m.get("insufficient") and e in fit_gpu)

    def _diff(eid, slice_df):
        rows = slice_df[slice_df[entity_col] == eid]
        if not len(rows):
            return np.array([])
        actual = rows[stat_col].to_numpy(dtype=float)
        m1, m2 = fit_v1[eid], fit_gpu[eid]
        crps_emp = np.array([tc.crps_approx(lambda q: PPF["empirical"](q, m1), x) for x in actual])
        crps_gpu = np.array([tc.crps_approx(lambda q: PPF["gpu"](q, m2), x) for x in actual])
        return crps_emp - crps_gpu

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


def run_observable(name: str, disc: pd.DataFrame, reserve: pd.DataFrame,
                    entity_col: str, stat_col: str) -> dict:
    fit_v1 = tc.fit_predictors(disc, entity_col, stat_col)
    t0 = time.perf_counter()
    gpu_fit = gd.fit_gpu_quantiles(disc, entity_col, stat_col)
    fit_gpu = gd.predict_entity_quantiles(gpu_fit)
    train_seconds = time.perf_counter() - t0

    row_eval = evaluate_3way(reserve, fit_v1, fit_gpu, entity_col, stat_col)
    coverage = coverage_3way(reserve, fit_v1, fit_gpu, entity_col, stat_col)
    gate = gate_gpu_vs_incumbent(reserve, fit_v1, fit_gpu, entity_col, stat_col)
    class_result = pg.class_level_test(gate) if len(gate) else {
        "n_entities": 0, "mean": float("nan"), "p_value": float("nan"),
        "ci_lo": float("nan"), "ci_hi": float("nan")}

    ks = {n: tc.pit_uniformity(row_eval[f"pit_{n}"].to_numpy()) for n in PPF} if len(row_eval) else {}
    crps_mean = {n: float(row_eval[f"crps_{n}"].mean()) for n in PPF} if len(row_eval) else {}

    return {
        "observable": name, "device": gpu_fit["device"], "train_seconds": train_seconds,
        "rows_scored": len(row_eval), "n_gate_entities": len(gate), "n_gate_survivors":
            int(gate["survivor"].sum()) if len(gate) else 0,
        "crps_mean": crps_mean, "ks": ks, "coverage": coverage, "gate_class": class_result,
    }


def _fmt_ks(d: dict) -> str:
    return " / ".join(f"{n}={d[n]['ks_stat']:.4f}" for n in ("normal", "empirical", "gpu")) if d else "n/a"


def _write_report(results: list[dict]) -> pathlib.Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    L = ["# GPU_DIST_REPORT -- GPU-trained conditional quantile model vs "
         "Normal baseline vs empirical-quantile incumbent (calibration language "
         "only, edge_claimed=False)\n\n"]
    for r in results:
        L.append(f"## {r['observable']}\n\n")
        L.append(f"- GPU device: {r['device']}  (train_seconds={r['train_seconds']:.2f})\n")
        L.append(f"- reserve rows scored: {r['rows_scored']}\n")
        L.append(f"- CRPS mean: normal={r['crps_mean'].get('normal', float('nan')):.4f} "
                 f"empirical={r['crps_mean'].get('empirical', float('nan')):.4f} "
                 f"gpu={r['crps_mean'].get('gpu', float('nan')):.4f}\n")
        L.append(f"- PIT KS (lower=better): {_fmt_ks(r['ks'])}\n")
        L.append(f"- coverage table:\n\n{r['coverage'].to_string(index=False)}\n\n")
        cr = r["gate_class"]
        L.append(f"- GATE gpu-vs-empirical-incumbent: {r['n_gate_survivors']}/{r['n_gate_entities']} "
                  f"individual survivors (BH q<0.05 + both-halves-same-direction)\n")
        L.append(f"- CLASS-level (clustered by entity, n={cr['n_entities']}): mean CRPS delta "
                  f"(empirical-gpu, positive=gpu wins)={cr['mean']:+.4f} 95%CI "
                  f"[{cr['ci_lo']:+.4f},{cr['ci_hi']:+.4f}] p={cr['p_value']:.4g}\n\n")
        crps_better = r['crps_mean'].get('gpu', 1e9) < r['crps_mean'].get('empirical', 0)
        ks_better = r['ks'].get('gpu', {}).get('ks_stat', 1.0) < r['ks'].get('empirical', {}).get('ks_stat', 0.0)
        gate_wins = cr['n_entities'] > 0 and cr['p_value'] < 0.05 and cr['mean'] > 0
        # width check: the incumbent was promoted SPECIFICALLY for closing
        # central-coverage gaps at 50/80/90% nominal -- a "beats incumbent"
        # verdict requires the GPU model NOT regress that (checking only
        # CRPS/KS/gate would hide a body-shape trade rather than a fix).
        central = r["coverage"][r["coverage"]["nominal"].isin([0.50, 0.80, 0.90])]
        err_emp = (central["realized_empirical"] - central["nominal"]).abs().mean()
        err_gpu = (central["realized_gpu"] - central["nominal"]).abs().mean()
        width_kept = err_gpu <= err_emp
        if crps_better and ks_better and gate_wins and width_kept:
            verdict = "GPU_BEATS_INCUMBENT"
        elif crps_better or ks_better or gate_wins:
            verdict = "MIXED (central 50/80/90pct coverage error empirical=%.4f gpu=%.4f, %s)" % (
                err_emp, err_gpu, "width KEPT" if width_kept else "width REGRESSES")
        else:
            verdict = "NULL_INCUMBENT_STAYS"
        L.append(f"- VERDICT: **{verdict}**\n\n")
    path = OUT_DIR / "GPU_DIST_REPORT.md"
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
        print(f"[run_gpu_dist] {r['observable']}: device={r['device']} "
              f"gate={r['n_gate_survivors']}/{r['n_gate_entities']} "
              f"crps_gpu={r['crps_mean'].get('gpu', float('nan')):.4f} "
              f"crps_empirical={r['crps_mean'].get('empirical', float('nan')):.4f}")
    print(f"[run_gpu_dist] wrote {path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
