"""scripts/probe_R6_B_validate_full_compose.py -- R6-B full-compose validation.

Validates that all 8 shipped ships compose correctly in production by running
the live_engine baseline (which includes ALL wired overrides) on the full
1508-game corpus at endQ3 + endQ2 + endQ1 and reports per-stat MAE.

Shipped ships currently wired:
  - cycle 110 learned Q4 minutes
  - cycle 112 quantile recalibration
  - R1_D_v2 per-player quantile bands (endQ2 + endQ3)
  - R2_F residual heads at endQ3
  - R3_A residual heads at endQ2
  - R4_A residual heads at endQ1
  - R5_F endQ1 symmetric bands

Uses scaffold's _live_engine_baseline (= production projection function).
Treatment is identical to baseline -- this is a NO-OP probe whose purpose is
to surface the absolute MAE per stat per point as the current production floor.

Compares against a hardcoded PRE-LOOP reference MAE.

Run:
    python scripts/probe_R6_B_validate_full_compose.py
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import retro_inplay_mae as v1  # noqa: E402
from scripts.improve_loop.scaffold import BASELINE  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
POINTS = ("endQ1", "endQ2", "endQ3")

# Pre-loop MAE reference (per user spec; endQ2 + endQ1 are approximate).
PRE_LOOP = {
    "endQ3": {"pts": 2.45, "reb": 1.00, "ast": 0.68, "fg3m": 0.42,
              "stl": 0.31, "blk": 0.19, "tov": 0.44},
    "endQ2": {"pts": 3.50, "reb": 1.30, "ast": 0.85, "fg3m": 0.55,
              "stl": 0.40, "blk": 0.25, "tov": 0.55},
    "endQ1": {"pts": 4.20, "reb": 1.60, "ast": 1.05, "fg3m": 0.70,
              "stl": 0.50, "blk": 0.30, "tov": 0.65},
}


def _mae(xs: List[float]) -> float:
    return (sum(xs) / len(xs)) if xs else float("nan")


def evaluate_point(point: str, qstats_df, games: List[str]) -> Dict[str, Tuple[float, int]]:
    """Return {stat: (mae, n)} for BASELINE at this snapshot point."""
    errs: Dict[str, List[float]] = {s: [] for s in STATS}
    skipped = 0
    for gid in games:
        snap = v1.build_snapshot(gid, point, qstats_df)
        if snap is None:
            skipped += 1
            continue
        try:
            actuals = v1.actuals_for_game(gid, qstats_df)
            proj = BASELINE(snap)
        except Exception:
            skipped += 1
            continue
        for (pid, stat), pval in proj.items():
            actual = actuals.get((pid, stat))
            if actual is None:
                continue
            errs[stat].append(abs(pval - actual))
    return {s: (_mae(errs[s]), len(errs[s])) for s in STATS}, skipped


def main() -> int:
    print("[R6_B] loading quarter stats ...")
    qstats_df = v1.load_quarter_stats()
    games = sorted(qstats_df["game_id"].unique().tolist())
    n_games = len(games)
    print(f"[R6_B] {n_games} games in corpus")

    results: Dict[str, Dict[str, Tuple[float, int]]] = {}
    skip_counts: Dict[str, int] = {}
    for point in POINTS:
        print(f"[R6_B] evaluating {point} ...")
        results[point], skip_counts[point] = evaluate_point(point, qstats_df, games)
        print(f"  done. skipped={skip_counts[point]}")

    # Build markdown report.
    lines = ["# R6_B -- Production Validation (full compose)", "",
             f"**Corpus:** {n_games} games  ",
             "**Projection:** `live_engine.project_from_snapshot` (= BASELINE)  ",
             "**Wired ships:** cycle 110 Q4-minutes, cycle 112 quant-recal, "
             "R1_D_v2 per-player bands (endQ2+endQ3), R2_F heads@endQ3, "
             "R3_A heads@endQ2, R4_A heads@endQ1, R5_F endQ1 bands",
             ""]
    for point in POINTS:
        ref = PRE_LOOP[point]
        cur = results[point]
        lines.append(f"## {point}  (skipped={skip_counts[point]})")
        lines.append("")
        lines.append("| stat | n | pre-loop MAE | current MAE | delta | rel % |")
        lines.append("|------|---|--------------|-------------|-------|-------|")
        for s in STATS:
            mae, n = cur[s]
            pre = ref[s]
            delta = mae - pre
            relpct = (delta / pre) * 100.0 if pre else 0.0
            mark = "Y" if delta < 0 else ("." if abs(delta) < 1e-4 else "REG")
            lines.append(f"| {s} | {n} | {pre:.4f} | {mae:.4f} | "
                         f"{delta:+.4f} | {relpct:+.2f}% | {mark}")
        lines.append("")

    # Summary deltas per point.
    lines.append("## Cumulative summary")
    lines.append("")
    lines.append("| point | sum(pre) | sum(cur) | sum delta | mean rel % |")
    lines.append("|-------|----------|----------|-----------|------------|")
    for point in POINTS:
        ref = PRE_LOOP[point]
        cur = results[point]
        sum_pre = sum(ref[s] for s in STATS)
        sum_cur = sum(cur[s][0] for s in STATS if not (cur[s][0] != cur[s][0]))
        mean_rel = sum(((cur[s][0] - ref[s]) / ref[s]) * 100.0
                       for s in STATS) / len(STATS)
        lines.append(f"| {point} | {sum_pre:.4f} | {sum_cur:.4f} | "
                     f"{sum_cur - sum_pre:+.4f} | {mean_rel:+.2f}% |")
    lines.append("")
    lines.append("Run-time projection identical to live_engine; no treatment delta.")
    lines.append("")

    out_dir = os.path.join(PROJECT_DIR, "scripts", "_results")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "improve_R6_B_production_validation.md")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"[R6_B] wrote {out_path}")

    # Console summary.
    for point in POINTS:
        cur = results[point]
        ref = PRE_LOOP[point]
        print(f"  {point}: " + "  ".join(
            f"{s}={cur[s][0]:.3f}(d{cur[s][0]-ref[s]:+.3f})" for s in STATS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
