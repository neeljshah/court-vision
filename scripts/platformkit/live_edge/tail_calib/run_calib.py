"""scripts.platformkit.live_edge.tail_calib.run_calib -- OOS driver + report
writer for the tail-calibration head-to-head (baseline Normal vs B2
tail-aware empirical quantiles), NBA player points, reserve = 2025-26.

No claims-ledger writes (tail_calib lane is not a journal writer this
cycle -- see live_edge_STATE.md CYCLE 5). Report only.

INVARIANTS: pandas/numpy/scipy + stdlib only. <=300 LOC. ASCII stdout.
Never writes data/registry/. No $/edge claims -- calibration language only.
"""
from __future__ import annotations

import pathlib

import numpy as np

from scripts.platformkit.live_edge import tails as tl
from scripts.platformkit.live_edge.tail_calib import calib as tc

_REPORT_PATH = pathlib.Path("data/omni/live_edge/tail_calib/TAIL_CALIB_REPORT.md")
MIN_ROWS_FOR_VERDICT = 30  # ponytail: below this a verdict is noise, report NULL/INSUFF as-is


def run(base_dir=None, nba_box_source=None) -> dict:
    nba_box = tl.load_nba_player_box(nba_box_source)
    discovery, reserve = tl.split_nba_discovery_reserve(nba_box)

    fit_metrics = tc.fit_predictors(discovery, "player_id", "pts")

    row_eval = tc.evaluate_reserve(reserve, fit_metrics, "player_id", "pts")
    coverage = tc.coverage_table(reserve, fit_metrics, "player_id", "pts")
    bins_baseline = tc.tail_bin_check(reserve, fit_metrics, "baseline", "player_id", "pts")
    bins_tail = tc.tail_bin_check(reserve, fit_metrics, "tail_aware", "player_id", "pts")

    pit_base = tc.pit_uniformity(row_eval["pit_baseline"].to_numpy())
    pit_tail = tc.pit_uniformity(row_eval["pit_tail"].to_numpy())

    crps_base_mean = float(row_eval["crps_baseline"].mean()) if len(row_eval) else float("nan")
    crps_tail_mean = float(row_eval["crps_tail"].mean()) if len(row_eval) else float("nan")

    result = {
        "reserve_season": tl.NBA_RESERVE_SEASON,
        "reserve_rows_total": int(len(reserve)),
        "reserve_rows_scored": int(len(row_eval)),
        "entities_fit_sufficient": sum(1 for m in fit_metrics.values() if not m.get("insufficient")),
        "crps_baseline_mean": crps_base_mean,
        "crps_tail_aware_mean": crps_tail_mean,
        "crps_delta_tail_minus_baseline": crps_tail_mean - crps_base_mean,
        "pit_ks_baseline": pit_base, "pit_ks_tail_aware": pit_tail,
    }
    verdict = _verdict(result, coverage)
    result["verdict"] = verdict
    _write_report(result, coverage, bins_baseline, bins_tail, base_dir)
    return result


def _verdict(result: dict, coverage) -> str:
    if result["reserve_rows_scored"] < MIN_ROWS_FOR_VERDICT:
        return "INSUFFICIENT_DATA"
    crps_better = result["crps_delta_tail_minus_baseline"] < 0  # lower CRPS = better
    pit_better = (result["pit_ks_tail_aware"]["ks_stat"] < result["pit_ks_baseline"]["ks_stat"])
    # extreme-tail coverage (99%) is B2's specific claim -- check it explicitly
    row99 = coverage[coverage["nominal"] == 0.99].iloc[0]
    tail_closer_99 = abs(row99["realized_tail_aware"] - 0.99) < abs(row99["realized_baseline"] - 0.99)
    wins = sum([crps_better, pit_better, tail_closer_99])
    if wins >= 2:
        return "TAIL_AWARE_IMPROVES_CALIBRATION"
    if wins == 1:
        return "MIXED"
    return "NULL"


def _write_report(result: dict, coverage, bins_baseline, bins_tail, base_dir) -> None:
    path = _REPORT_PATH if base_dir is None else pathlib.Path(base_dir) / _REPORT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    L = ["# TAIL-CALIB report -- B2 tail claims tested w/ the right instrument "
         "(OOS distribution calibration, NOT conditional-mean CRPS)\n\n",
         f"Reserve: {result['reserve_season']} ({result['reserve_rows_total']} rows, "
         f"{result['reserve_rows_scored']} scored, "
         f"{result['entities_fit_sufficient']} entities w/ sufficient discovery fit).\n\n",
         f"## VERDICT: {result['verdict']}\n\n",
         "## CRPS (quantile-approx, full predictive distribution, lower=better)\n\n",
         f"- baseline (Normal, discovery mean/std): {result['crps_baseline_mean']:.4f}\n",
         f"- tail-aware (B2 empirical quantiles): {result['crps_tail_aware_mean']:.4f}\n",
         f"- delta (tail - baseline): {result['crps_delta_tail_minus_baseline']:+.4f}\n\n",
         "## PIT uniformity (KS test vs Uniform(0,1); lower ks_stat = more uniform = better calibrated)\n\n",
         f"- baseline: n={result['pit_ks_baseline']['n']} ks_stat={result['pit_ks_baseline']['ks_stat']:.4f} "
         f"p={result['pit_ks_baseline']['ks_pvalue']:.4g}\n",
         f"- tail-aware: n={result['pit_ks_tail_aware']['n']} ks_stat={result['pit_ks_tail_aware']['ks_stat']:.4f} "
         f"p={result['pit_ks_tail_aware']['ks_pvalue']:.4g}\n\n",
         "## Quantile coverage (nominal vs realized, OOS reserve)\n\n",
         "nominal | n | realized_baseline | realized_tail_aware\n---|---|---|---\n"]
    for _, r in coverage.iterrows():
        L.append(f"{r['nominal']:.2f} | {int(r['n'])} | {r['realized_baseline']:.4f} | "
                  f"{r['realized_tail_aware']:.4f}\n")

    L.append("\n## Tail-bin realized-vs-predicted -- BASELINE (Normal), OOS reserve\n\n")
    L.append("bin | predicted | realized | n | ratio\n---|---|---|---|---\n")
    for _, r in bins_baseline.iterrows():
        L.append(f"{r['bin']} | {r['predicted']:.4f} | {r['realized']:.4f} | {int(r['n'])} | {r['ratio']:.2f}\n")

    L.append("\n## Tail-bin realized-vs-predicted -- TAIL-AWARE (B2 empirical quantiles), OOS reserve\n\n")
    L.append("bin | predicted | realized | n | ratio\n---|---|---|---|---\n")
    for _, r in bins_tail.iterrows():
        L.append(f"{r['bin']} | {r['predicted']:.4f} | {r['realized']:.4f} | {int(r['n'])} | {r['ratio']:.2f}\n")

    L.append("\n## Not verified\n\n"
              "- Only NBA player points scored (strongest B2 signal per rails). NBA team pts / MLB "
              "team runs tail claims NOT run through this OOS instrument.\n"
              "- CRPS is a quantile-grid approximation (13-pt shared grid, Gneiting-Raftery "
              "decomposition), not the closed-form integral -- fair for the head-to-head delta, "
              "not an absolute CRPS.\n"
              "- tail_aware_ppf/_cdf CLIP (not smoothly extend) beyond the 0.5%/99.5% anchors: any "
              "true value past that boundary is pinned to PIT=0.005 or 0.995 instead of spreading "
              "toward 0/1. This creates an artificial pileup at those two points that the KS test "
              "penalizes -- the tail-aware PIT-uniformity result (worse than baseline) may be this "
              "clipping artifact, not a real calibration deficit. Not disentangled here.\n"
              "- Extreme-tail (99% nominal) coverage is similarly poor for BOTH predictors OOS "
              "(~96% realized vs 99% nominal) -- consistent with roster non-stationarity (rookies, "
              "role changes season-to-season) diluting a fixed discovery-fit vector, not just "
              "distribution-shape mismatch.\n")
    path.write_text("".join(L), encoding="ascii")
    print(f"[tail_calib] wrote {path}")


def main() -> int:
    result = run()
    for k in ("reserve_rows_scored", "entities_fit_sufficient", "crps_baseline_mean",
              "crps_tail_aware_mean", "crps_delta_tail_minus_baseline", "verdict"):
        print(f"[tail_calib] {k}: {result[k]}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
