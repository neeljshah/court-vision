"""scripts.platformkit.live_edge.width_expand.run_expand -- driver + report
writer. Runs expand.run_observable over every qualifying NBA player count
observable + MLB team observable, writes
data/omni/live_edge/width_expand/WIDTH_EXPAND_REPORT.md. Report-only: no
claims-journal writes (WIDTH-EXPAND lane owns no journal).

CPU only (pandas/numpy/scipy) -- never imports torch-cuda or sets a
lightgbm gpu device (sibling GPU lane owns the GPU this cycle).

INVARIANTS: <=300 LOC. ASCII stdout. edge_claimed=False, calibration
language only, no $/ROI.
"""
from __future__ import annotations

import pathlib

from scripts.platformkit.live_edge.width_expand import expand as ex

_REPORT_PATH = pathlib.Path("data/omni/live_edge/width_expand/WIDTH_EXPAND_REPORT.md")
BH_ALPHA = 0.05


def run(base_dir=None) -> list[dict]:
    results = [ex.run_observable(spec) for spec in ex.observable_specs()]
    _write_report(results, base_dir)
    return results


def _significant(r: dict) -> bool:
    """Class-level width-correction claim: BH-alpha-significant pooled test
    AND mean sign says tail-aware wins (mean_pooled = baseline-tail_aware
    CRPS, positive = tail-aware lower CRPS = better)."""
    p, m = r["class_p"], r["class_mean"]
    return (p == p) and p < BH_ALPHA and (m == m) and m > 0


def _write_report(results: list[dict], base_dir) -> pathlib.Path:
    path = _REPORT_PATH if base_dir is None else pathlib.Path(base_dir) / _REPORT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    sig = [r for r in results if _significant(r)]
    null = [r for r in results if not _significant(r)]
    sig_sorted = sorted(sig, key=lambda r: r["class_p"])

    L = ["# WIDTH-EXPAND report -- incumbent tail-calib method + EXACT "
         "promote_gate methodology run over the full count-observable set "
         "(calibration language only, edge_claimed=False)\n\n",
         "Method: per-observable empirical-quantile predictive dist fit on "
         "DISCOVERY, evaluated on RESERVE (same split rule as the incumbent "
         "per sport); gate = per-entity paired CRPS test + BH across "
         "entities + both-trailing-halves same-direction + class-level "
         "pooled test clustered by entity. Gate never loosened vs the "
         "NBA-points incumbent.\n\n",
         "## Summary ranking -- CLASS-LEVEL SIGNIFICANT (candidate width-"
         "correction additions; Fable rules on promotion/tier)\n\n",
         "observable | positive_control | class_delta | 95%CI | p | survivors/total\n"
         "---|---|---|---|---|---\n"]
    for r in sig_sorted:
        L.append(f"{r['name']} | {r['positive_control']} | {r['class_mean']:+.4f} | "
                  f"[{r['class_ci_lo']:+.4f},{r['class_ci_hi']:+.4f}] | {r['class_p']:.4g} | "
                  f"{r['n_survivors']}/{r['n_entities_tested']}\n")
    if not sig_sorted:
        L.append("(none)\n")

    L.append("\n## Honest nulls (not class-level significant, or wrong-direction)\n\n")
    L.append("observable | class_delta | 95%CI | p | survivors/total\n---|---|---|---|---\n")
    for r in null:
        L.append(f"{r['name']} | {r['class_mean']:+.4f} | "
                  f"[{r['class_ci_lo']:+.4f},{r['class_ci_hi']:+.4f}] | {r['class_p']:.4g} | "
                  f"{r['n_survivors']}/{r['n_entities_tested']}\n")

    L.append("\n## Per-observable full calibration suite (PIT KS / coverage / CRPS)\n\n")
    for r in results:
        c = r["calib"]
        L.append(f"\n### {r['name']}\n\n")
        L.append(f"- reserve rows scored: {c['reserve_rows_scored']}\n")
        L.append(f"- CRPS baseline={c['crps_baseline']:.4f} tail_aware={c['crps_tail_aware']:.4f} "
                  f"delta={c['crps_delta']:+.4f}\n")
        L.append(f"- PIT-KS baseline ks={c['pit_baseline']['ks_stat']:.4f} "
                  f"p={c['pit_baseline']['ks_pvalue']:.4g} | tail_aware ks={c['pit_tail_aware']['ks_stat']:.4f} "
                  f"p={c['pit_tail_aware']['ks_pvalue']:.4g}\n")
        L.append("- coverage nominal|realized_baseline|realized_tail_aware: ")
        L.append("; ".join(f"{row['nominal']:.2f}|{row['realized_baseline']:.3f}|{row['realized_tail_aware']:.3f}"
                            for _, row in c["coverage"].iterrows()))
        L.append("\n")

    L.append("\n## Not verified\n\n"
              "- Same clip-beyond-anchors artifact as the incumbent (tail_aware_ppf/_cdf flat/clip "
              "past the 0.5%/99.5% fitted anchors) affects every observable here identically.\n"
              "- Entity universe for the gate = all entities with sufficient discovery fit (tails.MIN_N), "
              "not a pre-existing claims-journal set (these observables have no journal claims yet) -- "
              "same statistical bar as promote_gate, different (larger) universe than the 412 NBA-points "
              "entities promote_gate re-derived from claims.\n"
              "- No claims-journal writes; these are candidate additions to the width-correction class, "
              "not promoted claims -- Fable/judge-level promotion decision pending.\n"
              "- MLB player-grain and NBA `min` (minutes) not run: MLB player box is DATA_ABSENT on disk "
              "(tails.py), and `min` is a court-time measure, not a count-stat outcome the tier-1 class "
              "targets.\n")
    path.write_text("".join(L), encoding="ascii")
    print(f"[width_expand] wrote {path}")
    return path


def main() -> int:
    results = run()
    for r in results:
        flag = "SIGNIFICANT" if _significant(r) else "null"
        print(f"[width_expand] {r['name']}: class_mean={r['class_mean']:+.4f} "
              f"p={r['class_p']:.4g} survivors={r['n_survivors']}/{r['n_entities_tested']} [{flag}]")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
