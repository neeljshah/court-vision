"""probe_per_quarter_pace_decay.py — cycle 89d (loop 5).

Hypothesis: NBA team scoring/usage decays through the game — Q1 is faster
than Q4. A Q1-led linear projection therefore systematically OVERSHOOTS
the final. A per-quarter decay coefficient multiplied into remaining-share
should compress overshoots and lower MAE on in-game (Q1-end) projections.

This probe is meant to validate or reject that coefficient empirically.

Strategy A (PREFERRED) would compute Q1/Q2/Q3/Q4 per-player stat shares
from real per-quarter boxscore data, fit a decay curve, then re-run the
validator harness. But the per-game training dataset only contains
FULL-GAME totals — no per-quarter splits exist in:
    - data/cache/playerlogs/*.json   (GAME_DATE / MIN / GAME_ID only)
    - data/player_*.parquet          (season aggregates)
    - src/prediction/prop_pergame.build_pergame_dataset
A per-quarter pull (e.g. boxscorefourfactorsv3 per period, or PBP-derived
per-quarter aggregation) would unlock Strategy A but is outside the
30-min scope of this cycle.

Strategy B (FALLBACK — synthetic simulation, this script):
    - For each holdout (player, game), synthesise a "snapshot at end of Q1"
      by allocating 25% of the player's actual final stat to Q1 (uniform
      across regulation minutes assumption).
    - Apply scripts.predict_in_game.project_final at (period=2, clock=12:00)
      i.e. exactly at the Q1 -> Q2 boundary, with quarter_decay in
      {0.00, 0.05, 0.10, 0.15}.
    - Compare projected_final vs actual_final; report MAE per stat per coef.
    - Because the synthetic baseline ASSUMES uniform distribution (decay
      coefficient effectively = 0 at the data-generating step), any
      non-zero decay can only INCREASE MAE under this synthetic. The
      probe therefore mechanically REJECTS shipping without real Q1
      observations -- it cannot find the true coefficient, only confirm
      that uniform-assumption + linear projection is internally consistent.
    - The honest take from Strategy B is: "no signal under synthetic;
      real per-quarter fetch is the data-unlock path".

Run:
    python scripts/probe_per_quarter_pace_decay.py

Writes a markdown report to scripts/_results/per_quarter_pace_decay_v1.md.
"""
from __future__ import annotations

import os
import sys
import warnings
from typing import Dict, List, Tuple

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset,
)
from scripts.predict_in_game import project_final  # noqa: E402

OUT_PATH = os.path.join(PROJECT_DIR, "scripts", "_results",
                        "per_quarter_pace_decay_v1.md")

# Decay coefficients to probe. Interpretation: remaining-share is multiplied
# by (1 - quarter_decay) before being applied — higher coefficient = more
# compression of remaining (i.e. stronger end-of-game slowdown assumption).
COEFFS = [0.00, 0.05, 0.10, 0.15]

# Snapshot timing for the synthetic: simulate "end of Q1" exactly.
# At period=2 with clock_remaining=12.0 we have elapsed = 12 + 0 = 12 min,
# share_played = 12/48 = 0.25, share_remaining = 0.75.
SNAP_PERIOD = 2
SNAP_CLOCK_MIN = 12.0


def _project_with_decay(current_stat: float, decay: float) -> float:
    """Apply project_final with a quarter_decay coefficient by passing
    pace_factor = (1.0 - decay). The base projector multiplies remaining
    by pace_factor, so this is exactly the multiplicative decay knob the
    spec proposes (without needing to change project_remaining itself
    for the probe).
    """
    pace = 1.0 - decay
    return project_final(
        current_stat=current_stat,
        period=SNAP_PERIOD,
        clock_remaining_min=SNAP_CLOCK_MIN,
        pace_factor=pace,
    )


def run() -> Tuple[Dict[str, Dict[float, float]], int]:
    """Build holdout, simulate end-of-Q1 snapshot under uniform-elapsed
    assumption, compute MAE vs actual final per coefficient per stat.

    Returns:
        per_stat_mae: { stat: { coef: mae } }
        n_used: holdout row count
    """
    print("Loading pergame dataset...", flush=True)
    rows, _ = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    holdout = rows[int(n * 0.80):]
    print(f"  n={n} holdout={len(holdout)}\n", flush=True)

    per_stat_mae: Dict[str, Dict[float, float]] = {}
    for stat in STATS:
        targets = np.array([
            np.nan if r.get(f"target_{stat}") is None
            else float(r[f"target_{stat}"])
            for r in holdout
        ], dtype=float)
        mask = ~np.isnan(targets)
        y_true = targets[mask]
        # Synthetic "current at end of Q1" under uniform-distribution assumption.
        q1_synth = y_true * 0.25
        coef_mae: Dict[float, float] = {}
        for c in COEFFS:
            preds = np.array([_project_with_decay(float(v), c) for v in q1_synth])
            coef_mae[c] = float(np.mean(np.abs(preds - y_true)))
        per_stat_mae[stat] = coef_mae
    return per_stat_mae, sum(
        1 for r in holdout if any(r.get(f"target_{s}") is not None for s in STATS)
    )


def _verdict(per_stat_mae: Dict[str, Dict[float, float]]) -> Tuple[str, str]:
    """Pick the best non-zero coefficient by sum-of-MAE-deltas vs c=0.
    Return (verdict, reason). Strategy B can only ship if some c > 0
    beats c = 0 on >= 4/7 stats AND total delta < 0 -- which is
    impossible by construction under uniform synthesis (decay > 0
    shrinks remaining and undershoots the final). So we expect REJECT.
    """
    best_coef = 0.0
    best_total = 0.0
    best_improved = 0
    for c in COEFFS:
        if c == 0.0:
            continue
        improved = 0
        total = 0.0
        for stat in STATS:
            d = per_stat_mae[stat][c] - per_stat_mae[stat][0.0]
            total += d
            if d < -1e-4:
                improved += 1
        if improved > best_improved or (
            improved == best_improved and total < best_total
        ):
            best_improved = improved
            best_total = total
            best_coef = c
    if best_improved >= 4 and best_total < 0:
        return (
            f"SHIP coef={best_coef:.2f}",
            f"{best_improved}/7 stats improved, total MAE delta {best_total:+.4f}",
        )
    return (
        "REJECT",
        "Strategy B synthetic assumes uniform Q-distribution, so any "
        "decay > 0 mechanically undershoots vs the (uniform-derived) "
        "actual. The synthetic CANNOT detect the true decay -- only real "
        "per-quarter player data can. See Follow-up.",
    )


def write_md(per_stat_mae: Dict[str, Dict[float, float]], n_used: int) -> None:
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    verdict, reason = _verdict(per_stat_mae)
    lines: List[str] = []
    lines.append("# Cycle 89d (loop 5) — Per-quarter pace decay probe")
    lines.append("")
    lines.append("## Strategy used")
    lines.append("")
    lines.append("**Strategy B (synthetic).** Strategy A was rejected because the")
    lines.append("training dataset has no per-quarter player splits. Sources checked:")
    lines.append("")
    lines.append("- `data/cache/playerlogs/*.json` — only GAME_DATE / MIN / GAME_ID")
    lines.append("- `data/player_*.parquet` — season-level aggregates only")
    lines.append("- `src/prediction/prop_pergame.build_pergame_dataset` — full-game totals")
    lines.append("")
    lines.append("Synthetic protocol: for each holdout (player, game), allocate")
    lines.append("25% of the actual final stat to Q1 under a uniform-elapsed")
    lines.append("assumption, then call `predict_in_game.project_final` at")
    lines.append(f"(period={SNAP_PERIOD}, clock={SNAP_CLOCK_MIN:.0f}m) with")
    lines.append("`pace_factor = (1 - quarter_decay)` and compare to the actual.")
    lines.append("")
    lines.append("## Tested coefficients + MAE per stat")
    lines.append("")
    header = "| stat | " + " | ".join(f"c={c:.2f}" for c in COEFFS) + " |"
    sep = "|" + "----|" * (1 + len(COEFFS))
    lines.append(header)
    lines.append(sep)
    for stat in STATS:
        cells = " | ".join(f"{per_stat_mae[stat][c]:.4f}" for c in COEFFS)
        lines.append(f"| {stat} | {cells} |")
    lines.append("")
    lines.append("### Delta vs c=0.00 (negative = improvement)")
    lines.append("")
    nonzero = [c for c in COEFFS if c != 0.0]
    header = "| stat | " + " | ".join(f"d(c={c:.2f})" for c in nonzero) + " |"
    sep = "|" + "----|" * (1 + len(nonzero))
    lines.append(header)
    lines.append(sep)
    for stat in STATS:
        base = per_stat_mae[stat][0.0]
        cells = " | ".join(
            f"{per_stat_mae[stat][c] - base:+.4f}" for c in nonzero
        )
        lines.append(f"| {stat} | {cells} |")
    lines.append("")
    lines.append(f"Holdout n = {n_used}")
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append(f"**{verdict}** — {reason}")
    lines.append("")
    lines.append("## Follow-up")
    lines.append("")
    if verdict.startswith("SHIP"):
        coef = verdict.split("=")[-1]
        lines.append(f"1. Wire `quarter_decay={coef}` into")
        lines.append("   `predict_in_game.project_remaining` as an additive arg")
        lines.append("   with default `1.0` (multiplicative pace-style knob).")
        lines.append("2. Register the adjustment in `scripts/validate_adjustment.py`")
        lines.append("   and re-run the harness to confirm n~19964 holdout MAE delta.")
        lines.append("3. Commit + push only after the validator confirms.")
    else:
        lines.append("Strategy B cannot discover the true coefficient — it only")
        lines.append("confirms that the projector is internally consistent with")
        lines.append("its own uniform-distribution assumption. To unblock Strategy A:")
        lines.append("")
        lines.append("1. Add `scripts/fetch_per_quarter_boxscores.py` that calls")
        lines.append("   `boxscoretraditionalv3` PER period (1..4) and writes")
        lines.append("   `data/player_quarter_stats.parquet` with columns")
        lines.append("   `(game_id, player_id, period, pts, reb, ast, fg3m, stl, blk, tov, min)`.")
        lines.append("2. Aggregate to per-(player, season) Q1-vs-Q4 rate ratios.")
        lines.append("   If the median q4_rate / q1_rate ratio is < 0.95 across ≥30")
        lines.append("   player-game-pairs per stat, fit a single-coefficient decay.")
        lines.append("3. Re-run this probe with Strategy A: simulate Q1-end snapshot")
        lines.append("   using REAL Q1 pts (not synthetic), project final via")
        lines.append("   `project_final` with the fitted decay, compare to real final.")
        lines.append("4. Ship gate: ≥ 4/7 stats improve AND validator harness")
        lines.append("   confirms direction on the n~19964 holdout.")
        lines.append("")
        lines.append("Cycle 89d does NOT ship a coefficient. Production")
        lines.append("`predict_in_game.project_remaining` is unchanged.")
    lines.append("")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote {OUT_PATH}", flush=True)


def main() -> int:
    per_stat_mae, n_used = run()
    write_md(per_stat_mae, n_used)
    # Console summary
    print("\n== Per-stat MAE by quarter_decay coefficient ==")
    header = f"{'stat':<5} " + " ".join(f"{f'c={c:.2f}':>9}" for c in COEFFS)
    print(header)
    print("-" * len(header))
    for stat in STATS:
        row = f"{stat:<5} " + " ".join(
            f"{per_stat_mae[stat][c]:>9.4f}" for c in COEFFS
        )
        print(row)
    verdict, reason = _verdict(per_stat_mae)
    print(f"\nVerdict: {verdict}")
    print(f"Reason:  {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
