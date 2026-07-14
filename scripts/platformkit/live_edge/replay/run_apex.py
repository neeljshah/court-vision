"""scripts.platformkit.live_edge.replay.run_apex -- B4-APEX orchestrator.

Runs all three additions (placebo FP-rate, MDE/power, tails testability
expansion) against the real ledger + real corpora, writes
data/omni/live_edge/replay/apex/APEX_REPORT.md. The full 20,109-claim
mean-CRPS ledger is NOT rescored here (run_full_ledger already did that,
committed at bb790fc2, results on disk at full_ledger_results.parquet) --
apex reuses those results for the MDE step and only builds fresh corpora
for the placebo negative control (which needs its own SHUFFLED world, not
the real one).

INVARIANTS: pandas/numpy/scipy stdlib only. <=300 LOC. ASCII stdout.
edge_claimed=False, calibration language only, no $/ROI.
"""
from __future__ import annotations

import pathlib
import sys

import pandas as pd

from scripts.platformkit.live_edge.replay import apex as ax
from scripts.platformkit.live_edge.replay import run_full_ledger as rfl
from scripts.platformkit.live_edge import tails as tl

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
CLAIMS_PATH = REPO_ROOT / "data" / "omni" / "claims" / "claims.parquet"
LEDGER_RESULTS_PATH = REPO_ROOT / "data" / "omni" / "live_edge" / "replay" / "full_ledger_results.parquet"
OUT_DIR = ax.OUT_DIR


def run_all(placebo_n_cap: int = ax.PLACEBO_N_CAP, seed: int = 0) -> dict:
    claims_df = pd.read_parquet(CLAIMS_PATH)
    print(f"[run_apex] loaded {len(claims_df)} ledger claims", flush=True)
    classified = ax.classify_all(claims_df)
    n_total_testable = int(classified["grain"].notna().sum())

    print("[run_apex] building corpora (shared by placebo + MDE sigma)...", flush=True)
    corpora = rfl.build_corpora()

    print(f"[run_apex] 1/3 placebo run (cap={placebo_n_cap})...", flush=True)
    placebo_results = ax.placebo_run(claims_df, classified, corpora, n_total_testable, placebo_n_cap, seed)
    p_summary = ax.placebo_summary(placebo_results)
    p_defensible = ax.placebo_defensible_check(placebo_results, claims_df, n_total_testable)
    print(f"[run_apex] placebo done: {p_summary} | defensible={p_defensible}", flush=True)

    print("[run_apex] 2/3 MDE/power report...", flush=True)
    ledger_results = pd.read_parquet(LEDGER_RESULTS_PATH)
    sigma = ax.corpus_sigma(corpora)
    power_df = ax.power_report(ledger_results, sigma)
    power_summ = ax.mde_summary(power_df)
    print(f"[run_apex] MDE done: {power_summ}", flush=True)

    print("[run_apex] 3/3 tails testability expansion...", flush=True)
    nba_box = tl.load_nba_player_box()
    nba_disc, nba_res = tl.split_nba_discovery_reserve(nba_box)
    expansion_df = ax.expand_tails_testability(claims_df, nba_disc, nba_res)
    expansion_summ = ax.expansion_summary(expansion_df)
    print(f"[run_apex] expansion done: {expansion_summ}", flush=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    placebo_results.to_parquet(OUT_DIR / "placebo_results.parquet", index=False)
    power_df.to_parquet(OUT_DIR / "mde_report.parquet", index=False)
    expansion_df.to_parquet(OUT_DIR / "tails_expansion.parquet", index=False)

    report_path = write_report(p_summary, p_defensible, power_summ, expansion_summ, n_total_testable)
    print(f"[run_apex] wrote {report_path}", flush=True)
    return {"placebo": p_summary, "mde": power_summ, "expansion": expansion_summ}


def write_report(placebo_summary: dict, p_defensible: dict, power_summ: dict, expansion_summ: dict,
                  n_total_testable: int, out_path: pathlib.Path = None) -> pathlib.Path:
    out_path = out_path or (OUT_DIR / "APEX_REPORT.md")
    bonf_survivors = placebo_summary["bonferroni_survivors_on_placebo"]
    n_defensible = p_defensible["n_defensible"]
    lines = [
        "# B4-APEX -- placebo FP-rate + power/MDE + testability expansion\n",
        "edge_claimed=False. Calibration language only -- gate integrity, "
        "coverage, and honest power reporting; none of it manufactures a "
        "survivor.\n",
        "## 1. Placebo / negative-control FP-rate\n",
        f"Sampled {placebo_summary['n_sampled']} real claim cells/deltas (of "
        f"{placebo_summary['n_total_testable_for_bonferroni']} tick-testable), scored "
        "against SHUFFLED (placebo) corpora through the exact hardened gate "
        "(same DM-clustered test, same 2-corpora combine).\n",
        f"- pre-correction single-corpus IMPROVES rate: corpus A "
        f"{placebo_summary['empirical_improves_rate_a']:.4f}, corpus B "
        f"{placebo_summary['empirical_improves_rate_b']:.4f} (n={placebo_summary['n_scored_a']}/"
        f"{placebo_summary['n_scored_b']}); WORSE rate: corpus A "
        f"{placebo_summary['empirical_worse_rate_a']:.4f}, corpus B "
        f"{placebo_summary['empirical_worse_rate_b']:.4f}. NOTE: this is elevated vs the naive "
        f"nominal {placebo_summary['nominal_reject_rate']:.4f} two-sided rate BY DESIGN, not a gate "
        "defect -- placebo keeps each claim's REAL discovered_delta (fit to a genuine discovery-"
        "slice relationship) and scores it against a SHUFFLED reserve where that relationship no "
        "longer holds, so a nonzero delta scoring WORSE-than-baseline is a CORRECT rejection of a "
        "now-miscalibrated predictor, not a false positive. IMPROVES is the side that matters for "
        "gate integrity (spuriously 'still works' on pure noise).\n",
        f"- raw IMPROVES_BOTH_CORPORA on placebo data: "
        f"{placebo_summary['raw_both_corpora_pass']}/{placebo_summary['n_sampled']}.\n",
        f"- after Bonferroni ALONE (alpha={placebo_summary['alpha_bonferroni']:.2e}, using the "
        f"real ledger's N={placebo_summary['n_total_testable_for_bonferroni']} tests): "
        f"{bonf_survivors} survivor(s) on PURE NOISE.\n",
        f"- after ALSO applying the SAME majority-class filter run_full_ledger.layer_gate uses "
        f"(reused, not re-derived): {n_defensible} DEFENSIBLE survivor(s) on pure noise "
        f"(the {bonf_survivors - n_defensible} Bonferroni-only survivor(s) were majority-class "
        f"degenerate cells -- claim_id(s) {p_defensible['majority_class_ids']}).\n",
        ("VERDICT: the FULL defensible gate (Bonferroni AND majority-class filter) has FP rate 0 "
         "on this placebo sample -- matches the real ledger's own defensible=0. Bonferroni ALONE is "
         "NOT perfectly immune to majority-class-cell degeneracy even under a true null (this run "
         f"found {bonf_survivors} such case(s)) -- this is evidence the majority-class filter is a "
         "REQUIRED second layer, not optional belt-and-suspenders." if n_defensible == 0 else
         "VERDICT: *** GATE BUG *** a placebo (pure noise) claim survived BOTH Bonferroni AND the "
         "majority-class filter -- the full defensible gate is passing noise; do not trust real "
         "survivors until this is fixed."),
        "\n## 2. Power / MDE for the INSUFFICIENT_DATA bucket\n",
        f"n_insufficient={power_summ['n_insufficient']} (of the real full-ledger run); "
        f"n_with_finite_mde={power_summ['n_finite_mde']}.\n",
        f"- team grain (n={power_summ.get('team_n', 0)}): median MDE (PPP units) = "
        f"{power_summ.get('team_median_mde', float('nan')):.4f} "
        f"[p25={power_summ.get('team_p25_mde', float('nan')):.4f}, "
        f"p75={power_summ.get('team_p75_mde', float('nan')):.4f}].\n",
        f"- player grain (n={power_summ.get('player_n', 0)}): median MDE (scored-rate "
        f"units) = {power_summ.get('player_median_mde', float('nan')):.4f} "
        f"[p25={power_summ.get('player_p25_mde', float('nan')):.4f}, "
        f"p75={power_summ.get('player_p75_mde', float('nan')):.4f}].\n",
        "NOTE: this MDE uses raw n_active (i.i.d. simplification), not the "
        "game-clustered effective sample size the real DM test uses -- it is an "
        "OPTIMISTIC LOWER BOUND on the true MDE. It distinguishes 'genuinely no "
        "power to test' from 'tested and null'; it does not certify power.\n",
        "\n## 3. Testability expansion (tails.* via calibration instrument)\n",
        f"n_tails_claims={expansion_summ['n_tails_claims']} | "
        f"verdict_counts={expansion_summ['verdict_counts']}\n",
        f"newly_testable={expansion_summ['newly_testable']} (adjudicated by the "
        "per-entity calibration-coverage instrument -- paired CRPS, tail-aware "
        "empirical quantile vector vs baseline Normal -- instead of the mean-"
        "CRPS design run_full_ledger structurally cannot apply to a quantile "
        "claim).\n",
        f"NEW TICK-TESTABLE TOTAL (mean-CRPS {n_total_testable} + calibration-"
        f"instrument {expansion_summ['newly_testable']}) = "
        f"{n_total_testable + expansion_summ['newly_testable']}.\n",
        "\n## Not verified / caveats\n",
        "- Placebo shuffles the outcome column once per corpus (fixed seed) and "
        "reuses that single shuffled world across all sampled claims -- an "
        "efficient, not a fully independent-replicate, Monte Carlo; the reject-"
        "rate CI at this n is a few points wide, not exact.\n",
        "- MDE sigma is a GLOBAL (pooled) outcome std per grain, not per-cell -- "
        "a documented simplification; per-cell MDE would vary (e.g. low-pace "
        "cells have lower point variance).\n",
        "- Tails expansion covers NBA player points only (the one observable "
        "already instrument-validated by TAIL-CALIB); MLB/team tails topics, if "
        "any exist later, stay NOT_TESTABLE_HERE honestly.\n",
        "- The MDE/power section reuses on-disk full_ledger_results.parquet "
        "rather than rescoring the full ledger here (avoids repeating "
        "run_full_ledger's expensive scoring pass) -- CONFIRMED (2026-07-14, "
        "this lane) that file is a LIVE, externally-maintained artifact: its "
        "row count and even its verdict-label set changed between two "
        "consecutive runs of this script minutes apart, meaning another "
        "process is actively rescoring the growing ledger concurrently. "
        "The MDE numbers above are therefore a snapshot AS OF READ TIME, not "
        "a frozen reference -- rerun this script for a fresh snapshot rather "
        "than trusting these exact figures as static. The placebo step "
        "(section 1) always uses the freshly-loaded current ledger for its "
        "testable-claim sample and Bonferroni N, so it is not stale.\n",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="ascii", errors="replace")
    return out_path


def main() -> int:
    run_all()
    return 0


__all__ = ["run_all", "write_report"]

if __name__ == "__main__":
    sys.exit(main())
