"""probe_inplay_blend.py — cycle 95e (loop 5). Multi-snapshot weighted blend.

WHY: cycle 94d's endQ3 MAE for the cycle-88 single-snapshot projector is
2.44 PTS / 0.20 BLK. endQ3 is the highest-information snapshot but also the
most noise-prone (one foul-out, one blowout pull, one garbage-time spike can
dominate the projection). endQ2 is more stable. This probe asks whether
BLENDING multiple snapshots (endQ1 + endQ2 + endQ3) with weighted averaging
squeezes further MAE out — analogous to how ensemble averaging tames variance
in a stack of weak learners.

Approach (mirrors retro_inplay_mae_v2 cycle 94d):
  1. For each retro game in data/player_quarter_stats.parquet, reconstruct
     snapshots at endQ1/endQ2/endQ3 and project each through
     predict_in_game.project_snapshot. Reuses v1's snapshot + projection
     helpers — identical projector, no re-training.
  2. Sweep a fixed grid of blend weights (see _WEIGHT_SCHEMES below).
  3. Per-stat MAE per weighting scheme on the SAME (game, pid, stat) triples
     (intersection across all three snapshot points).
  4. NNLS solver: fit non-negative weights on first 30 games, validate on
     last 20. Sum-to-one constraint via post-normalization.
  5. Report per-stat: Q3_only_mae | best_blend_mae | best_weights | delta.

Strictly read-only. No mutation of predict_in_game / live_factors / parquets.

Run:
    python scripts/probe_inplay_blend.py
    python scripts/probe_inplay_blend.py --max-games 20
    python scripts/probe_inplay_blend.py --output scripts/_results/inplay_blend_v1.md
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import retro_inplay_mae as v1  # noqa: E402  (reuse snapshot/actuals helpers)

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
SNAPSHOT_POINTS = ("endQ1", "endQ2", "endQ3")


# ── blend weight schemes (ordered: q1, q2, q3) ────────────────────────────────

def _exp_decay_weights(lam: float) -> Tuple[float, float, float]:
    """Exponential-decay weights heavier on Q3 (most recent snapshot).

    Weights proportional to lam**(2-i) for i in {0=Q1, 1=Q2, 2=Q3}:
      lam=0.5 -> Q1:0.25 Q2:0.5  Q3:1.0  -> normalized (0.143, 0.286, 0.571)
      lam=0.7 -> Q1:0.49 Q2:0.7  Q3:1.0  -> normalized (0.224, 0.320, 0.456)
      lam=0.9 -> Q1:0.81 Q2:0.9  Q3:1.0  -> normalized (0.299, 0.332, 0.369)

    Lower lam = sharper recency bias toward Q3; higher lam approaches uniform.
    """
    raw = np.array([lam ** 2, lam ** 1, lam ** 0], dtype=float)
    raw = raw / raw.sum()
    return (float(raw[0]), float(raw[1]), float(raw[2]))


# A scheme is a 3-tuple (w_q1, w_q2, w_q3). All schemes normalized to sum=1
# at apply time so the report is apples-to-apples.
_WEIGHT_SCHEMES: Dict[str, Tuple[float, float, float]] = {
    "q3_only":           (0.0, 0.0, 1.0),         # baseline (cycle 94d)
    "q3_90_q2_10":       (0.0, 0.10, 0.90),
    "q3_80_q2_20":       (0.0, 0.20, 0.80),
    "q3_70_q2_20_q1_10": (0.10, 0.20, 0.70),
    "q2_q3_equal":       (0.0, 0.50, 0.50),
    "exp_lambda_0_5":    _exp_decay_weights(0.5),
    "exp_lambda_0_7":    _exp_decay_weights(0.7),
    "exp_lambda_0_9":    _exp_decay_weights(0.9),
}


def normalize_weights(w: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Renormalize so the components sum to 1.0. Returns (0,0,0) if all-zero."""
    s = float(w[0] + w[1] + w[2])
    if s <= 1e-12:
        return (0.0, 0.0, 0.0)
    return (w[0] / s, w[1] / s, w[2] / s)


def blend_projection(
    q1: Optional[float],
    q2: Optional[float],
    q3: Optional[float],
    weights: Tuple[float, float, float],
) -> Optional[float]:
    """Weighted-average blend of up-to-three snapshot projections.

    Missing snapshots are dropped and the remaining weights re-normalized.
    Returns None if NO snapshot is available.
    """
    vals: List[Tuple[float, float]] = []
    for w, v in zip(weights, (q1, q2, q3)):
        if v is None or w <= 0.0:
            continue
        vals.append((float(w), float(v)))
    if not vals:
        return None
    total_w = sum(w for w, _ in vals)
    if total_w <= 1e-12:
        return None
    return sum(w * v for w, v in vals) / total_w


# ── per-game blended projections + MAE ────────────────────────────────────────

def collect_projections(
    games: List[str],
    qstats_df,
) -> Tuple[
    Dict[str, Dict[str, Dict[Tuple[int, str], float]]],
    Dict[str, Dict[Tuple[int, str], float]],
]:
    """Build snapshots + actuals for every game.

    Returns:
        snaps_per_game[game_id][point] = {(pid, stat): projected_final}
        actuals[game_id] = {(pid, stat): full_game_total}
    """
    snaps_per_game: Dict[str, Dict[str, Dict[Tuple[int, str], float]]] = {}
    actuals: Dict[str, Dict[Tuple[int, str], float]] = {}
    for gid in games:
        snaps_per_game[gid] = {}
        for point in SNAPSHOT_POINTS:
            snap = v1.build_snapshot(gid, point, qstats_df)
            if snap is None:
                continue
            snaps_per_game[gid][point] = v1.project_snapshot_to_finals(snap)
        actuals[gid] = v1.actuals_for_game(gid, qstats_df)
    return snaps_per_game, actuals


def compute_blend_mae(
    snaps_per_game: Dict[str, Dict[str, Dict[Tuple[int, str], float]]],
    actuals: Dict[str, Dict[Tuple[int, str], float]],
    weights: Tuple[float, float, float],
    game_subset: Optional[List[str]] = None,
) -> Dict[str, Tuple[int, float]]:
    """MAE per stat for a given blend on a (possibly restricted) game set.

    Only triples present in ALL three snapshots AND with an actual are scored,
    so every weighting scheme sees the SAME denominator (apples-to-apples).
    """
    buckets: Dict[str, List[float]] = defaultdict(list)
    gids = game_subset if game_subset is not None else list(snaps_per_game.keys())
    for gid in gids:
        by_point = snaps_per_game.get(gid, {})
        q1_map = by_point.get("endQ1") or {}
        q2_map = by_point.get("endQ2") or {}
        q3_map = by_point.get("endQ3") or {}
        # Triples present in ALL THREE snapshots.
        keys = set(q1_map) & set(q2_map) & set(q3_map)
        gact = actuals.get(gid, {})
        for k in keys:
            actual = gact.get(k)
            if actual is None:
                continue
            stat = k[1]
            pred = blend_projection(q1_map[k], q2_map[k], q3_map[k], weights)
            if pred is None:
                continue
            buckets[stat].append(abs(pred - actual))
    return {s: (len(v), sum(v) / len(v)) for s, v in buckets.items() if v}


# ── NNLS fit per stat (train on first 30, validate on last 20) ────────────────

def fit_nnls_weights_per_stat(
    snaps_per_game: Dict[str, Dict[str, Dict[Tuple[int, str], float]]],
    actuals: Dict[str, Dict[Tuple[int, str], float]],
    fit_games: List[str],
) -> Dict[str, Tuple[float, float, float]]:
    """Fit per-stat non-negative weights (Q1, Q2, Q3) minimizing
       || actual - (w1*q1 + w2*q2 + w3*q3) ||_2  s.t. w_i >= 0.

    Post-normalized to sum to 1.0 so the result is interpretable as a convex
    combination. Returns empty (0,0,0) on under-determined stats.
    """
    from scipy.optimize import nnls  # noqa: PLC0415

    per_stat_rows: Dict[str, List[Tuple[float, float, float, float]]] = defaultdict(list)
    for gid in fit_games:
        by_point = snaps_per_game.get(gid, {})
        q1_map = by_point.get("endQ1") or {}
        q2_map = by_point.get("endQ2") or {}
        q3_map = by_point.get("endQ3") or {}
        keys = set(q1_map) & set(q2_map) & set(q3_map)
        gact = actuals.get(gid, {})
        for k in keys:
            a = gact.get(k)
            if a is None:
                continue
            stat = k[1]
            per_stat_rows[stat].append((q1_map[k], q2_map[k], q3_map[k], float(a)))

    out: Dict[str, Tuple[float, float, float]] = {}
    for stat in STATS:
        rows = per_stat_rows.get(stat, [])
        if len(rows) < 10:
            out[stat] = (0.0, 0.0, 0.0)
            continue
        A = np.array([[r[0], r[1], r[2]] for r in rows], dtype=float)
        y = np.array([r[3] for r in rows], dtype=float)
        try:
            coeffs, _ = nnls(A, y)
        except Exception:
            out[stat] = (0.0, 0.0, 0.0)
            continue
        s = float(coeffs.sum())
        if s <= 1e-9:
            out[stat] = (0.0, 0.0, 0.0)
        else:
            out[stat] = (float(coeffs[0] / s),
                         float(coeffs[1] / s),
                         float(coeffs[2] / s))
    return out


# ── report ────────────────────────────────────────────────────────────────────

def build_report(
    n_games: int,
    n_fit: int,
    n_val: int,
    val_mae_by_scheme: Dict[str, Dict[str, Tuple[int, float]]],
    nnls_weights: Dict[str, Tuple[float, float, float]],
    nnls_val_mae: Dict[str, Tuple[int, float]],
) -> Tuple[str, Dict[str, Tuple[float, str, Tuple[float, float, float]]]]:
    """Build markdown + return per-stat winner table.

    Per-stat winner table: {stat: (best_blend_mae, best_scheme_name, weights)}.
    """
    lines: List[str] = []
    lines.append("# In-play multi-snapshot blend probe — cycle 95e (loop 5)")
    lines.append("")
    lines.append(f"**Games analyzed:** {n_games}  ·  fit={n_fit}  val={n_val}")
    lines.append("")
    lines.append(
        "Asks whether a WEIGHTED blend of endQ1 + endQ2 + endQ3 snapshot "
        "projections (cycle-88 projector) beats the single-snapshot endQ3 "
        "baseline (cycle 94d). Each blend is MAE'd on the validation set "
        "(last 20 games) using ONLY (game, player, stat) triples that have "
        "ALL THREE snapshots — apples-to-apples denominator. The `nnls_fit` "
        "scheme is per-stat: weights fit on the first 30 games minimizing "
        "L2 residual to actuals, then evaluated on the holdout."
    )
    lines.append("")

    # Sweep table.
    lines.append("## Validation MAE per scheme")
    lines.append("")
    header = "| stat | " + " | ".join(_WEIGHT_SCHEMES.keys()) + " |"
    sep = "|" + "------|" * (len(_WEIGHT_SCHEMES) + 1)
    lines.append(header)
    lines.append(sep)
    for stat in STATS:
        row = [stat]
        for name in _WEIGHT_SCHEMES.keys():
            cell = val_mae_by_scheme.get(name, {}).get(stat)
            row.append(f"{cell[1]:.4f}" if cell else "—")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # Per-stat winner (across all fixed schemes + NNLS).
    lines.append("## Per-stat best blend (vs Q3-only baseline)")
    lines.append("")
    lines.append("| stat | n | Q3_only_mae | best_blend_mae | best_scheme | weights (Q1,Q2,Q3) | delta |")
    lines.append("|------|---|-------------|----------------|-------------|-------------------|-------|")

    winners: Dict[str, Tuple[float, str, Tuple[float, float, float]]] = {}
    wins_vs_q3 = 0
    big_wins_vs_q3 = 0  # delta <= -0.05
    for stat in STATS:
        q3 = val_mae_by_scheme.get("q3_only", {}).get(stat)
        if q3 is None:
            continue
        n_q3, mae_q3 = q3

        # Candidates: every fixed scheme that has a value for this stat,
        # plus the NNLS-fit scheme (which has its own per-stat weights).
        candidates: List[Tuple[str, float, Tuple[float, float, float]]] = []
        for name, w in _WEIGHT_SCHEMES.items():
            entry = val_mae_by_scheme.get(name, {}).get(stat)
            if entry is None:
                continue
            candidates.append((name, entry[1], normalize_weights(w)))

        nnls_w = nnls_weights.get(stat, (0.0, 0.0, 0.0))
        nnls_entry = nnls_val_mae.get(stat)
        if nnls_entry is not None and sum(nnls_w) > 0:
            candidates.append(("nnls_fit", nnls_entry[1], nnls_w))

        if not candidates:
            continue
        best_name, best_mae, best_w = min(candidates, key=lambda x: x[1])
        delta = best_mae - mae_q3
        winners[stat] = (best_mae, best_name, best_w)
        if delta < 0:
            wins_vs_q3 += 1
            if delta <= -0.05:
                big_wins_vs_q3 += 1
        w_str = f"({best_w[0]:.2f},{best_w[1]:.2f},{best_w[2]:.2f})"
        lines.append(
            f"| {stat} | {n_q3} | {mae_q3:.4f} | {best_mae:.4f} | "
            f"{best_name} | {w_str} | {delta:+.4f} |"
        )

    lines.append("")
    lines.append("## NNLS-fit per-stat weights")
    lines.append("")
    lines.append("| stat | w_Q1 | w_Q2 | w_Q3 | sum | val_mae | n |")
    lines.append("|------|------|------|------|-----|---------|---|")
    for stat in STATS:
        w = nnls_weights.get(stat, (0.0, 0.0, 0.0))
        entry = nnls_val_mae.get(stat)
        n = entry[0] if entry else 0
        mae = f"{entry[1]:.4f}" if entry else "—"
        lines.append(
            f"| {stat} | {w[0]:.3f} | {w[1]:.3f} | {w[2]:.3f} | "
            f"{sum(w):.3f} | {mae} | {n} |"
        )
    lines.append("")

    # Verdict.
    lines.append("## Verdict")
    lines.append("")
    lines.append(
        f"**Best blend beats Q3-only on {wins_vs_q3}/{len(STATS)} stats** "
        f"(threshold delta>=0.05 MAE: {big_wins_vs_q3}/{len(STATS)})."
    )
    lines.append("")
    if big_wins_vs_q3 >= 4:
        lines.append(
            "**SHIP THE BLEND** — blend beats Q3-only by >=0.05 MAE on "
            "majority of stats. Follow-up cycle should add an optional "
            "`snapshots=[...] + weights=[...]` arg to "
            "`live_engine.project_from_snapshot` (once cycle 95c ships) so "
            "the live pipeline can ensemble snapshots from a single tick."
        )
    elif wins_vs_q3 >= 4:
        lines.append(
            "**MARGINAL — measurable but small improvement on majority of "
            "stats.** Doesn't clear the 0.05-MAE ship threshold. Document "
            "the per-stat best weights for future reference; do NOT wire "
            "the blend into live_engine yet."
        )
    else:
        lines.append(
            "**Q3-ONLY REMAINS BEST.** The cycle-88 endQ3 single-snapshot "
            "projection already captures the most-informative state. Blending "
            "in earlier snapshots adds bias (stale state) faster than it "
            "reduces variance (regularizing toward Q2 mean). The hypothesis "
            "that Q3 noise dominates Q2 stability is rejected."
        )
    lines.append("")

    return "\n".join(lines) + "\n", winners


# ── main runner ───────────────────────────────────────────────────────────────

def run(max_games: Optional[int] = None,
        output: Optional[str] = None,
        fit_n: int = 30,
        val_n: int = 20) -> int:
    qstats_df = v1.load_quarter_stats()
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]
    print(f"  probe_inplay_blend: {len(games)} games")

    snaps_per_game, actuals = collect_projections(games, qstats_df)

    fit_games = games[:fit_n]
    val_games = games[fit_n:fit_n + val_n] if val_n > 0 else games[fit_n:]
    print(f"  fit games: {len(fit_games)}  val games: {len(val_games)}")

    # Evaluate every fixed scheme on the VALIDATION subset.
    val_mae_by_scheme: Dict[str, Dict[str, Tuple[int, float]]] = {}
    for name, w in _WEIGHT_SCHEMES.items():
        val_mae_by_scheme[name] = compute_blend_mae(
            snaps_per_game, actuals, normalize_weights(w),
            game_subset=val_games or None,
        )

    # NNLS fit on first 30, evaluate on last 20 (per-stat weights).
    nnls_weights = fit_nnls_weights_per_stat(snaps_per_game, actuals, fit_games)
    nnls_val_buckets: Dict[str, List[float]] = defaultdict(list)
    for gid in val_games:
        by_point = snaps_per_game.get(gid, {})
        q1_map = by_point.get("endQ1") or {}
        q2_map = by_point.get("endQ2") or {}
        q3_map = by_point.get("endQ3") or {}
        keys = set(q1_map) & set(q2_map) & set(q3_map)
        gact = actuals.get(gid, {})
        for k in keys:
            a = gact.get(k)
            if a is None:
                continue
            stat = k[1]
            w = nnls_weights.get(stat, (0.0, 0.0, 0.0))
            if sum(w) <= 0:
                continue
            pred = blend_projection(q1_map[k], q2_map[k], q3_map[k], w)
            if pred is None:
                continue
            nnls_val_buckets[stat].append(abs(pred - a))
    nnls_val_mae = {
        s: (len(v), sum(v) / len(v)) for s, v in nnls_val_buckets.items() if v
    }

    # Report.
    report, winners = build_report(
        n_games=len(games), n_fit=len(fit_games), n_val=len(val_games),
        val_mae_by_scheme=val_mae_by_scheme,
        nnls_weights=nnls_weights, nnls_val_mae=nnls_val_mae,
    )
    out_path = output or os.path.join(
        PROJECT_DIR, "scripts", "_results", "inplay_blend_v1.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"  wrote {out_path}")

    # Console summary.
    print("\n  per-stat winners (vs Q3-only baseline):")
    for stat in STATS:
        q3 = val_mae_by_scheme.get("q3_only", {}).get(stat)
        if q3 is None:
            continue
        best = winners.get(stat)
        if best is None:
            continue
        best_mae, best_name, _ = best
        delta = best_mae - q3[1]
        sign = "WIN " if delta < 0 else "tied" if abs(delta) < 1e-6 else "loss"
        print(f"    {stat:4s}: q3={q3[1]:.4f}  best={best_mae:.4f}  "
              f"({best_name})  delta={delta:+.4f}  {sign}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None,
                    help="Limit to first N games (debug).")
    ap.add_argument("--output", default=None,
                    help="Markdown output path (default: "
                         "scripts/_results/inplay_blend_v1.md)")
    ap.add_argument("--fit-n", type=int, default=30,
                    help="Number of early games used for NNLS fit (default 30).")
    ap.add_argument("--val-n", type=int, default=20,
                    help="Number of later games used for validation (default 20).")
    args = ap.parse_args()
    return run(max_games=args.max_games, output=args.output,
               fit_n=args.fit_n, val_n=args.val_n)


if __name__ == "__main__":
    sys.exit(main())
