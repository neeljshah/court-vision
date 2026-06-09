"""
Replay script — reconstructs report from already-captured results.
Run this to avoid re-running 20 min of training.
"""
import os, sys, json
import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models")

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]

# Results from the run that crashed before print_report
# Approach 1 - Full-train, CV-restricted holdout (n_holdout=10177, cv_eligible=5998)
A1 = {
    "pts":  {"baseline_mae_full": 4.8059, "cv_mae_full": 4.8413, "baseline_mae_filtered": 4.9642, "cv_mae_filtered": 5.0000, "delta_filtered": +0.0359, "delta_pct_filtered": +0.72,  "n_holdout_total": 10177, "n_holdout_cv": 5998},
    "reb":  {"baseline_mae_full": 1.9321, "cv_mae_full": 1.9306, "baseline_mae_filtered": 1.9312, "cv_mae_filtered": 1.9311, "delta_filtered": -0.0001, "delta_pct_filtered": -0.01, "n_holdout_total": 10177, "n_holdout_cv": 5998},
    "ast":  {"baseline_mae_full": 1.3842, "cv_mae_full": 1.3930, "baseline_mae_filtered": 1.4742, "cv_mae_filtered": 1.4838, "delta_filtered": +0.0096, "delta_pct_filtered": +0.65,  "n_holdout_total": 10177, "n_holdout_cv": 5998},
    "fg3m": {"baseline_mae_full": 0.9340, "cv_mae_full": 0.9276, "baseline_mae_filtered": 0.9910, "cv_mae_filtered": 0.9854, "delta_filtered": -0.0056, "delta_pct_filtered": -0.56, "n_holdout_total": 10177, "n_holdout_cv": 5998},
    "stl":  {"baseline_mae_full": 0.7492, "cv_mae_full": 0.7485, "baseline_mae_filtered": 0.7602, "cv_mae_filtered": 0.7603, "delta_filtered": +0.0001, "delta_pct_filtered": +0.01,  "n_holdout_total": 10177, "n_holdout_cv": 5998},
    "blk":  {"baseline_mae_full": 0.5290, "cv_mae_full": 0.5288, "baseline_mae_filtered": 0.5249, "cv_mae_filtered": 0.5253, "delta_filtered": +0.0004, "delta_pct_filtered": +0.08,  "n_holdout_total": 10177, "n_holdout_cv": 5998},
    "tov":  {"baseline_mae_full": 0.9182, "cv_mae_full": 0.9185, "baseline_mae_filtered": 0.9495, "cv_mae_filtered": 0.9509, "delta_filtered": +0.0015, "delta_pct_filtered": +0.15,  "n_holdout_total": 10177, "n_holdout_cv": 5998},
}

# Approach 2 - 2025-26 only (23458 rows, 14074 train, 4692 val, 4692 test, 48.8% CV coverage)
A2 = {
    "pts":  {"baseline_mae": 4.7191, "cv_mae": 4.7231, "delta": +0.0040, "delta_pct": +0.09},
    "reb":  {"baseline_mae": 1.8982, "cv_mae": 1.8893, "delta": -0.0089, "delta_pct": -0.47},
    "ast":  {"baseline_mae": 1.3553, "cv_mae": 1.3543, "delta": -0.0010, "delta_pct": -0.07},
    "fg3m": {"baseline_mae": 0.9029, "cv_mae": 0.9038, "delta": +0.0010, "delta_pct": +0.11},
    "stl":  {"baseline_mae": 0.7355, "cv_mae": 0.7360, "delta": +0.0005, "delta_pct": +0.07},
    "blk":  {"baseline_mae": 0.5264, "cv_mae": 0.5300, "delta": +0.0036, "delta_pct": +0.68},
    "tov":  {"baseline_mae": 0.9018, "cv_mae": 0.9018, "delta": +0.0001, "delta_pct": +0.01},
    "__meta__": {"n_season": 23458, "n_train": 14074, "n_val": 4692, "n_test": 4692, "cv_cover": 11458, "cv_cover_pct": 48.8},
}

# Approach 3 -- NOTE: per_row_data was lost in the crash (not reconstructible without re-run)
# We can skip this since the CV-by-bucket data requires actual per-row predictions
A3 = {}  # empty -- approach 3 data not available from crash output

PREV_WF = {
    "pts":  ("-0.0031", "1/4"),
    "reb":  ("-0.0037", "4/4 SHIP"),
    "ast":  ("+0.0000", "0/4"),
    "fg3m": ("N/A",     "--"),
    "stl":  ("N/A",     "--"),
    "blk":  ("N/A",     "--"),
    "tov":  ("N/A",     "--"),
}

# Dataset metadata
N_TOTAL = 101765
N_WITH_CV = 12043
PCT_CV = 11.83
N_2526 = 23458
N_HOLDOUT_CV = 5998

def main():
    lines = []
    lines.append("")
    lines.append("=" * 80)
    lines.append("F1 CV-RESTRICTED MAGNITUDE TEST -- FINAL REPORT")
    lines.append("=" * 80)
    lines.append("")
    lines.append("### Dataset breakdown")
    lines.append(f"- Total rows: {N_TOTAL:,}")
    lines.append(f"- Rows with cv_n_games > 0: {N_WITH_CV:,} ({PCT_CV:.2f}%)")
    lines.append(f"- 2025-26 rows (Approach 2): {N_2526:,}")
    lines.append("")

    # Approach 1
    lines.append("### Approach 1: Full-train, CV-only holdout")
    lines.append("")
    lines.append(f"Holdout slice: last 10% of timeline (~{N_HOLDOUT_CV:,} rows have cv_n_games > 0 out of ~10,177 total)")
    lines.append("")
    lines.append("| stat | baseline MAE (restricted) | with_cv MAE (restricted) | delta | delta % | full-WF reported (comparison) |")
    lines.append("|------|--------------------------|-------------------------|-------|---------|-------------------------------|")
    for stat in STATS:
        r = A1[stat]
        prev_d, prev_wf = PREV_WF[stat]
        delta = r["delta_filtered"]
        dpct = r["delta_pct_filtered"]
        dstr = f"**{delta:+.4f}**" if delta < 0 else f"{delta:+.4f}"
        lines.append(f"| {stat} | {r['baseline_mae_filtered']:.4f} | {r['cv_mae_filtered']:.4f} | {dstr} | {dpct:+.2f}% | {prev_d} ({prev_wf}) |")
    lines.append("")

    # Approach 2
    lines.append("### Approach 2: 2025-26-only train/test")
    lines.append("")
    meta = A2["__meta__"]
    lines.append(f"- N 2025-26 rows: {meta['n_season']:,}")
    lines.append(f"- N train: {meta['n_train']:,}  |  N val: {meta['n_val']:,}  |  N test: {meta['n_test']:,}")
    lines.append(f"- CV-eligible rows in slice: {meta['cv_cover']:,} ({meta['cv_cover_pct']}%)")
    lines.append("")
    lines.append("| stat | baseline MAE | with_cv MAE | delta | delta % |")
    lines.append("|------|-------------|------------|-------|---------|")
    for stat in STATS:
        r = A2[stat]
        delta = r["delta"]
        dstr = f"**{delta:+.4f}**" if delta < 0 else f"{delta:+.4f}"
        lines.append(f"| {stat} | {r['baseline_mae']:.4f} | {r['cv_mae']:.4f} | {dstr} | {r['delta_pct']:+.2f}% |")
    lines.append("")

    # Approach 3
    lines.append("### Approach 3: MAE by CV coverage bucket")
    lines.append("")
    lines.append("*Per-row prediction arrays lost in crash -- re-run full script to populate.*")
    lines.append("*Approach 1 and 2 data above is complete and accurate.*")
    lines.append("")

    # Honest read
    lines.append("### Honest read")
    lines.append("")
    lines.append("**Per-stat CV signal magnitude -- Approach 1 (restricted holdout):**")
    lines.append("")

    improved_a1 = [s for s in STATS if A1[s]["delta_filtered"] < 0]
    improved_a2 = [s for s in STATS if isinstance(A2[s], dict) and A2[s]["delta"] < 0]
    consistent = [s for s in STATS if s in improved_a1 and s in improved_a2]

    for stat in STATS:
        r1 = A1[stat]
        r2 = A2.get(stat, {})
        d1 = r1["delta_filtered"]
        pct1 = r1["delta_pct_filtered"]
        d2 = r2.get("delta", float("nan"))
        a1_better = "IMPROVED" if d1 < 0 else "REGRESSED"
        a2_better = "IMPROVED" if d2 < 0 else "REGRESSED"
        both = "CONSISTENT" if d1 < 0 and d2 < 0 else ("BOTH REGRESS" if d1 >= 0 and d2 >= 0 else "INCONSISTENT")
        lines.append(f"- **{stat.upper()}**: A1_delta={d1:+.4f} ({pct1:+.2f}%) | A2_delta={d2:+.4f} | {a1_better}/{a2_better} | {both}")

    lines.append("")
    lines.append("**Summary:**")
    lines.append(f"- Stats improved on CV-restricted holdout (Approach 1): {improved_a1 if improved_a1 else 'NONE'}")
    lines.append(f"- Stats improved on 2025-26 slice (Approach 2): {improved_a2 if improved_a2 else 'NONE'}")
    lines.append(f"- Consistent improvements (both approaches): {consistent if consistent else 'NONE'}")
    lines.append("")

    lines.append("**Key findings:**")
    lines.append("")
    lines.append("1. The structural hypothesis is CONFIRMED but with MIXED direction:")
    lines.append("   - REB is the only stat showing improvement in BOTH approaches")
    lines.append("     (A1: -0.0001 / -0.01%, A2: -0.0089 / -0.47%)")
    lines.append("   - FG3M improves on the CV-restricted holdout (-0.0056/-0.56%) but not on 2025-26 slice")
    lines.append("   - PTS REGRESSES on both slices (+0.0359/+0.72% and +0.0040/+0.09%)")
    lines.append("   - AST, STL, BLK, TOV show near-zero or negative effects")
    lines.append("")
    lines.append("2. CV does NOT provide a broad, consistent MAE improvement even on the slice where it has data.")
    lines.append("   The REB improvement on Approach 2 (-0.47%) is meaningful but small;")
    lines.append("   the full-WF REB result (-0.0037, 4/4) appears to persist but is not amplified")
    lines.append("   when measured only on the timeline where CV training data exists.")
    lines.append("")
    lines.append("3. PTS REGRESSION on CV-restricted rows (+0.72%) is the most concerning signal --")
    lines.append("   CV features appear to HURT PTS prediction on recent data despite the model")
    lines.append("   having them during training. This suggests feature noise > signal for PTS.")
    lines.append("")
    lines.append("4. The full-WF gate (4/4 folds) correctly identified REB as the only ship candidate.")
    lines.append("   No stat shows a hidden, larger CV effect that was masked by fold averaging.")
    lines.append("   The structural concern about folds 1-3 having no CV data was valid but")
    lines.append("   the implication (WF understates CV signal) is NOT confirmed for most stats.")
    lines.append("")
    lines.append("5. VERDICT: CV feature value is marginal and stat-specific. Only REB shows")
    lines.append("   consistent improvement. The 4/4 WF gate was correct to REJECT all but REB.")
    lines.append("   Do not expand CV feature usage beyond the current REB pilot.")

    lines.append("")
    output = "\n".join(lines)
    print(output)

    # Save
    report_path = os.path.join(MODELS_DIR, "test_cv_recent_only_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"\nReport saved to: {report_path}")

    # Save JSON
    json_path = os.path.join(MODELS_DIR, "test_cv_recent_only_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"approach1": A1, "approach2": A2, "approach3": A3,
                   "cv_coverage": {"total_rows": N_TOTAL, "rows_with_cv": N_WITH_CV, "pct_covered": PCT_CV},
                   "note": "approach3 lost in crash -- re-run test_cv_recent_only.py for per-bucket data"},
                  f, indent=2)
    print(f"JSON saved to: {json_path}")

if __name__ == "__main__":
    main()
